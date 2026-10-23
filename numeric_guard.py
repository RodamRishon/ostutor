"""Numeric guard: the deterministic simulator is the single source of truth for every scheduling number.

An LLM explanation of a scheduling problem is free text, so it can slip: a wrong waiting time, an average computed
from the wrong column, a Gantt chart with one segment out of place. This module reads the explanation, extracts every
numerical CLAIM it makes about the problem, compares each one with the simulator result, and

  * rewrites a wrong value in place with the simulator's value (the sentence and the reasoning around it are kept),
  * reports each correction precisely: which claim was wrong, what the explanation said, what the simulator gives,
    and what it was corrected to,
  * reports claims that cannot be fixed by swapping a number (a scheduling decision that contradicts the simulator,
    a process that is not in the problem) as `unresolved`, so the caller can withhold the narrative instead of
    showing something false.

Claims checked
    per process      arrival, burst, priority, first start, completion, turnaround, waiting, response
                     (in prose "P2 waiting time = 11 - 7 = 4", in lists "P2: WT = 4", "Waiting time: P1 = 6, P2 = 0",
                     and in tables, including an Average row)
    averages         average waiting / turnaround / response time, including "(6 + 0 + 3 + 9) / 4 = 4.50"
    Gantt chart      the text bar "| P1 | P2 |" with its time line, and segment lists "P1 (0-2), P2 2-6"
    events           "P2 completes at t=6", "P3 arrives at 3", "P2 preempts P1 at t=2", "at t=8, P1 runs"

The module only reads the simulator result; it never runs a scheduler of its own.
"""
from __future__ import annotations

import ast
import operator
import re
from dataclasses import dataclass, field

from scheduler import gantt_text

# --------------------------------------------------------------------------- vocabulary
METRICS = {                      # key in a simulator row -> (label shown to the student, regex of its names)
    "arrival": ("arrival time", r"arrival(?:\s+time)?|(?-i:\bAT\b)"),
    "burst": ("burst time", r"burst(?:\s+time)?|(?-i:\bBT\b)"),
    "priority": ("priority", r"priority"),
    "start": ("first start time", r"(?:first\s+)?start(?:ing)?(?:\s+time)?"),
    "completion": ("completion time", r"completion(?:\s+time)?|finish(?:ing)?(?:\s+time)?|(?-i:\bCT\b)"),
    "turnaround": ("turnaround time", r"turn\s*-?\s*around(?:\s+time)?|(?-i:\bTAT\b)"),
    "waiting": ("waiting time", r"waiting(?:\s+time)?|(?-i:\bWT\b)"),
    "response": ("response time", r"response(?:\s+time)?|(?-i:\bRT\b)"),
}
AVERAGES = {"waiting": ("avg_waiting", r"waiting(?:\s+time)?|(?-i:\bWT\b)"),
            "turnaround": ("avg_turnaround", r"turn\s*-?\s*around(?:\s+time)?|(?-i:\bTAT\b)"),
            "response": ("avg_response", r"response(?:\s+time)?|(?-i:\bRT\b)")}
_NAMES = {k: re.compile(v[1], re.I) for k, v in METRICS.items()}
_PER_PROCESS = ("arrival", "burst", "completion", "turnaround", "waiting", "response")   # prose patterns (not 'start')

_NUM = r"\d+(?:\.\d+)?"
# an arithmetic expression that ends in a number: "4", "11 - 7 = 4", "(6 + 0 + 3 + 9) / 4 = 4.50"
_EXPR = r"(?P<expr>[\d(][\d \t.+\-−–—×*/÷()=]*[\d)]|\d)"
# a symbolic left-hand side before the numbers: "WT = TAT - BT = 14 - 8 = 6", "TAT(P1) = CT - AT = 14 - 0 = 14"
_WORDS = r"[A-Za-z]{1,20}(?:[ \t]+[A-Za-z]{1,20}){0,3}"
_SYMB = r"(?:" + _WORDS + r"(?:[ \t]*[-\u2212\u2013+][ \t]*" + _WORDS + r")*[ \t]*=[ \t]*)*"
_HEDGE = r"(?:(?:about|approximately|approx\.?|roughly|around|exactly|only)\s+|[≈~]\s*)?"
_VERB = r"(?:=|:|\bis\b|\bwas\b|\bequals\b|\bcomes\s+to\b|\bwill\s+be\b|\bgives?\b|→|->)"
_PID = r"P\d+"
_PRE_AVG = re.compile(r"(?:average|avg\.?|mean|total|sum\s+of)\s*(?:\w+\s+){0,1}$", re.I)


# --------------------------------------------------------------------------- data classes
class _Shift:
    """A regex match found inside a slice of the text, with positions reported in whole-text coordinates."""
    def __init__(self, m, base):
        self.m, self.base = m, base

    def start(self, g):
        return self.base + self.m.start(g)

    def end(self, g):
        return self.base + self.m.end(g)

    def group(self, g):
        return self.m.group(g)


@dataclass
class Issue:
    kind: str             # 'metric' | 'average' | 'gantt' | 'event' | 'arithmetic'
    subject: str          # "P2 waiting time", "average turnaround time", "Gantt chart"
    claimed: str          # what the explanation said
    expected: str         # what the simulator gives
    message: str          # one sentence for the student: claim, expected value, corrected value
    corrected: bool = True


@dataclass
class Report:
    text: str                                   # the explanation after correction (unchanged if nothing was wrong)
    claims: int = 0                             # how many numerical claims were checked
    issues: list = field(default_factory=list)  # corrected in place
    unresolved: list = field(default_factory=list)   # contradictions that a number swap cannot repair

    @property
    def ok(self):
        return not self.issues and not self.unresolved

    @property
    def messages(self):
        return [i.message for i in self.issues] + [i.message for i in self.unresolved]


# --------------------------------------------------------------------------- arithmetic
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def safe_eval(expr):
    """Value of an arithmetic expression (+ - x /, parentheses), or None if it is not one."""
    s = (expr.replace("−", "-").replace("–", "-").replace("—", "-")
         .replace("×", "*").replace("÷", "/").strip())

    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
            return float(n.value)
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](walk(n.left), walk(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
            v = walk(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        raise ValueError
    try:
        return walk(ast.parse(s, mode="eval"))
    except (SyntaxError, ValueError, ZeroDivisionError, RecursionError):
        return None


def expression_value(expr):
    """The value an expression asserts: the last side of a chain "a - b = c = d" -> d (the others must agree with it)."""
    sides = [x.strip() for x in expr.split("=") if x.strip()]
    return safe_eval(sides[-1]) if sides else None


def _decimals(text):
    m = re.search(r"\.(\d+)\s*$", text.strip())
    return len(m.group(1)) if m else 0


def agrees(claimed, expected, decimals=0):
    """Does the claimed number equal the simulator's value, allowing the rounding the claim itself states?"""
    if claimed is None:
        return False
    if abs(claimed - expected) <= 0.005 + 1e-9:
        return True
    if decimals == 1:
        return abs(claimed - expected) <= 0.05 + 1e-9
    return decimals >= 2 and abs(claimed - expected) <= 0.011


def _fmt(v):
    return str(int(v)) if float(v) == int(v) else f"{v:.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------------------- the simulator as a lookup
class _Truth:
    def __init__(self, result):
        self.result = result
        self.rows = {r["pid"]: r for r in result["rows"]}
        self.timeline = {}
        for pid, s, e in result["gantt"]:
            for t in range(s, e):
                self.timeline[t] = pid
        self.end = max(self.timeline, default=-1) + 1
        self.start = min(self.timeline, default=0)
        self.segments = [tuple(g) for g in result["gantt"]]

    def derivation(self, key, pid):
        r = self.rows[pid]
        if key == "turnaround":
            return f"completion {r['completion']} − arrival {r['arrival']} = {r['turnaround']}"
        if key == "waiting":
            return f"turnaround {r['turnaround']} − burst {r['burst']} = {r['waiting']}"
        if key == "response":
            return f"first start {r['start']} − arrival {r['arrival']} = {r['response']}"
        if key in ("arrival", "burst", "priority"):
            return "as given in the problem"
        return "from the simulator's Gantt chart"

    def chain(self, key, pid):
        r = self.rows[pid]
        if key == "turnaround":
            return f"{r['completion']} − {r['arrival']} = {r['turnaround']}"
        if key == "waiting":
            return f"{r['turnaround']} − {r['burst']} = {r['waiting']}"
        if key == "response":
            return f"{r['start']} − {r['arrival']} = {r['response']}"
        return str(r[key])

    def average_chain(self, col):
        vals = [r[col] for r in self.result["rows"]]
        return f"({' + '.join(str(v) for v in vals)}) / {len(vals)} = {self.result['avg_' + col]:.2f}"

    def preemptions(self):
        """(running, preemptor, t): one process leaves the CPU, unfinished, because another takes it."""
        out = []
        for (a, s1, e1), (b, s2, e2) in zip(self.segments, self.segments[1:]):
            if a != "idle" and b != "idle" and e1 == s2 and a != b and a in self.rows and self.rows[a]["completion"] > e1:
                out.append((a, b, e1))
        return out


# --------------------------------------------------------------------------- the checker
class _Checker:
    def __init__(self, text, result):
        self.raw = text
        # bold markers are blanked (same length) so "= **4.50**" reads as a number; edits still land in `raw`
        self.text = text.replace("**", "  ")
        self.truth = _Truth(result)
        self._seen = []
        self.claims = 0
        self.edits = []                    # (start, end, replacement)
        self.issues, self.unresolved = [], []

    # -- bookkeeping ---------------------------------------------------------------------------------------
    def _claim(self, a, b):
        """Register the span of a claim; False if an earlier pattern already owns (part of) it."""
        if any(a < e and s < b for s, e in self._seen):
            return False
        self._seen.append((a, b))
        self.claims += 1
        return True

    def _edit(self, a, b, new):
        self.edits.append((a, b, new))

    def _bad(self, issue):
        (self.issues if issue.corrected else self.unresolved).append(issue)

    @staticmethod
    def _operand(text, pos):
        """True if the name at `pos` is an operand of a formula ("TAT = CT - AT = 9 - 3"): the character before it
        is an arithmetic operator, so it is being used in a calculation, not claimed to equal something."""
        before = text[:pos].rstrip(" \t")
        return bool(before) and before[-1] in "-\u2212\u2013\u2014+\u00d7*/"

    # -- expression claims (metric values and averages) ------------------------------------------------------
    def _check_value(self, m, key, pid=None, average_col=None, label_prefix=None):
        """Check the expression captured as group 'expr' of match m against the simulator and queue a fix."""
        t = self.truth
        a, b = m.start("expr"), m.end("expr")
        if not self._claim(a, b):
            return
        expr = m.group("expr")
        sides = [x.strip() for x in expr.split("=") if x.strip()]
        values = [safe_eval(x) for x in sides]
        if average_col:
            expected = t.result["avg_" + average_col]
            subject = f"average {METRICS[average_col][0]}"
            chain = t.average_chain(average_col)
        else:
            if pid not in t.rows:
                self._bad(Issue("metric", f"{pid} {METRICS[key][0]}", expr.strip(), "no such process",
                                f"The explanation gives a {METRICS[key][0]} for {pid}, which is not one of this "
                                f"problem's processes ({', '.join(t.rows)}).", corrected=False))
                return
            expected = t.rows[pid][key]
            subject = f"{pid} {METRICS[key][0]}"
            chain = t.chain(key, pid)
        d = _decimals(sides[-1]) if sides else 0
        lone = lambda x: not re.search(r"[+\-−*/×()]", x)
        # every side of the chain must agree with the simulator (a chain whose sides disagree is itself wrong);
        # a computed side such as (6 + 0 + 3 + 9) / 4 is unrounded, so it gets the 2-decimal tolerance
        wrong = [v is None or not agrees(v, expected, _decimals(x) if lone(x) else 2) for x, v in zip(sides, values)]
        if not any(wrong):
            return
        last = values[-1]
        claimed = sides[-1] if (last is None or lone(sides[-1])) else _fmt(last)     # echo the claim as the explanation wrote it
        shown = _fmt_avg(expected) if average_col else _fmt(expected)
        simple = len(sides) == 1 and lone(sides[0])
        if average_col:
            replacement = _fmt_avg(expected) if simple else chain
        else:
            replacement = str(expected) if simple else chain
        if "**" in self.raw[a:b] and "=" in replacement:      # keep the bold final value: "= **4.50**"
            replacement = re.sub(r"=\s*([^=]*)$", lambda mm: "= **" + mm.group(1), replacement)
        if last is not None and not agrees(last, expected, d if lone(sides[-1]) else 2):
            msg = (f"{subject}: the explanation said {claimed}, the simulator gives {shown} "
                   f"({t.derivation(key, pid) if not average_col else chain}); corrected to {shown}.")
        else:
            msg = (f"{subject}: the explanation's working “{expr.strip()}” does not add up; the simulator gives "
                   f"{shown} ({t.derivation(key, pid) if not average_col else chain}); corrected to {shown}.")
        self._edit(a, b, replacement)
        self._bad(Issue("average" if average_col else "metric", subject, claimed, shown, msg))

    def per_process_prose(self):
        text = self.text
        for key in _PER_PROCESS:
            name = METRICS[key][1]
            # "waiting time of P2 is 4" / "WT(P2) = 4" / "waiting time for P2: 11 - 7 = 4"
            a = re.compile(r"(?P<name>\b(?:" + name + r"))\s*(?:\(\s*(?P<p1>" + _PID + r")\s*\)|(?:of|for)\s+(?P<p2>" + _PID +
                           r"))\s*" + _VERB + r"\s*" + _HEDGE + _SYMB + _EXPR, re.I)
            # "P2 waiting time = 4" / "P2's waiting time is 4" / "P2 has a waiting time of 4" / "P2: waiting 4"
            b = re.compile(r"(?P<p1>\b" + _PID + r")(?:'s|’s)?\s*[:,]?\s*(?:has\s+(?:an?\s+)?|had\s+(?:an?\s+)?)?(?:" + name +
                           r")\s*(?:of\s+|" + _VERB + r"\s*)" + _HEDGE + _SYMB + _EXPR, re.I)
            for rx in (a, b):
                for m in rx.finditer(text):
                    if _PRE_AVG.search(text[max(0, m.start() - 14):m.start()]) or self._operand(text, m.start()):
                        continue
                    pid = (m.group("p1") or m.groupdict().get("p2") or "").upper()
                    self._check_value(m, key, pid)

    def lists(self):
        """"P1: WT = 6, TAT = 14" (a process first) and "Waiting time: P1 = 6, P2 = 0" (a metric first)."""
        text = self.text
        lead = re.compile(r"(?m)^[ \t]*(?:[-*•]\s*|\d+[.)]\s*)?\**(?P<pid>" + _PID + r")\**[ \t]*[:\-–—(][ \t]*(?P<rest>.*)$")
        for lm in lead.finditer(text):
            rest, base = lm.group("rest"), lm.start("rest")
            for key in _PER_PROCESS:
                for m in re.finditer(r"\b(?:" + METRICS[key][1] + r")\s*(?:=|:|\bis\b|\bof\b)\s*" + _HEDGE + _SYMB + _EXPR, rest, re.I):
                    if not self._operand(rest, m.start()):
                        self._shifted(m, base, key, lm.group("pid").upper())
        head = re.compile(r"(?P<name>\b(?:" + "|".join(METRICS[k][1] for k in _PER_PROCESS) + r"))s?\s*(?:times?)?\s*[:\-]\s*(?P<rest>[^\n]*)", re.I)
        for hm in head.finditer(text):
            if _PRE_AVG.search(text[max(0, hm.start() - 14):hm.start()]) or self._operand(text, hm.start()):
                continue
            key = next((k for k in _PER_PROCESS if _NAMES[k].fullmatch(hm.group("name").strip())), None)
            if not key:
                continue
            rest, base = hm.group("rest"), hm.start("rest")
            for m in re.finditer(r"(?P<pid>\b" + _PID + r")\s*(?:=|:|\bis\b)\s*" + _HEDGE + _SYMB + _EXPR, rest, re.I):
                self._shifted(m, base, key, m.group("pid").upper())

    def _shifted(self, m, base, key, pid):
        """Run _check_value on a match found inside a slice of the text that starts at `base`."""
        self._check_value(_Shift(m, base), key, pid)

    def averages(self):
        for col, (_, name) in AVERAGES.items():
            gap = r"(?:[^\d\n=:]|\bP\d+\b|\b\d+(?=\s+(?:processes|jobs|tasks)))"
            rx = re.compile(r"(?:\b(?:average|avg\.?|mean)\s+(?:" + name + r")|\bA(?:WT|TAT|RT)\b)" + r"\s*" + gap + r"{0,60}?\s*" +
                            _VERB + r"\s*" + _HEDGE + _SYMB + _EXPR, re.I)
            for m in rx.finditer(self.text):
                whole = m.group(0).lower()
                tag = re.search(r"\bA(WT|TAT|RT)\b", m.group(0))
                if tag:                                   # AWT / ATAT / ART name their own column
                    c = {"WT": "waiting", "TAT": "turnaround", "RT": "response"}[tag.group(1)]
                    if c != col:
                        continue
                self._check_value(m, col, average_col=col)

    # -- tables ----------------------------------------------------------------------------------------------
    def tables(self):
        lines = [(m.start(), m.group(0)) for m in re.finditer(r"^.*$", self.text, re.M)]
        i = 0
        while i < len(lines):
            pos, line = lines[i]
            if line.strip().startswith("|") and i + 1 < len(lines) and re.fullmatch(r"\s*\|[\s:|\-]+\|?\s*", lines[i + 1][1]):
                cols = self._header(line)
                j = i + 2
                while j < len(lines) and lines[j][1].strip().startswith("|"):
                    self._row(lines[j][0], lines[j][1], cols)
                    j += 1
                i = j
            else:
                i += 1

    @staticmethod
    def _header(line):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        cols = {}
        for idx, c in enumerate(cells):
            for key in ("turnaround", "waiting", "response", "completion", "arrival", "burst", "priority", "start"):
                if _NAMES[key].search(c) and not (key == "arrival" and re.search(r"turn", c, re.I)):
                    cols[idx] = key
                    break
        return cols

    def _row(self, pos, line, cols):
        if not cols:
            return
        cells, offsets = [], []
        lead = len(line) - len(line.lstrip())
        raw = line.strip().strip("|")
        base = pos + lead + (1 if line.strip().startswith("|") else 0)
        at = 0
        for cell in raw.split("|"):
            cells.append(cell)
            offsets.append(base + at)
            at += len(cell) + 1
        first = re.sub(r"[*`_ ]", "", cells[0]) if cells else ""
        is_avg = bool(re.match(r"(?:average|avg|mean)", first, re.I))
        if not (re.fullmatch(_PID, first, re.I) or is_avg):
            return
        for idx, key in cols.items():
            if idx >= len(cells):
                continue
            if is_avg and key not in AVERAGES:
                continue
            m = re.search(_EXPR, cells[idx])
            if not m:
                continue
            where = _Shift(m, offsets[idx])
            if is_avg:
                self._check_value(where, key, average_col=key)
            else:
                self._check_value(where, key, first.upper())

    # -- Gantt chart ---------------------------------------------------------------------------------------------
    def gantt_bars(self):
        """| P1 | P2 | P3 |  with the line of times beneath it."""
        t = self.truth
        lines = [(m.start(), m.group(0)) for m in re.finditer(r"^.*$", self.text, re.M)]
        for (p1, bar), (p2, axis) in zip(lines, lines[1:]):
            if not re.fullmatch(r"\s*\|(?:\s*(?:P\d+|idle)\s*\|)+\s*", bar, re.I):
                continue
            nums = re.findall(r"\d+", axis)
            if not nums or re.sub(r"[\d\s]", "", axis):
                continue
            who = re.findall(r"P\d+|idle", bar, re.I)
            end = p2 + len(axis)
            if not self._claim(p1, end):
                continue
            if len(nums) != len(who) + 1:
                self._gantt_fix(p1, end, bar, "(a time line that does not match its bars)", bar.strip() + " / " + axis.strip())
                continue
            claimed = [(w if w.lower() == "idle" else w.upper(), int(nums[k]), int(nums[k + 1])) for k, w in enumerate(who)]
            if not self._same_chart(claimed):
                self._gantt_fix(p1, end, bar, claimed, None)

    def _same_chart(self, claimed):
        t = self.truth
        merged = []
        for pid, s, e in claimed:
            if merged and merged[-1][0] == pid and merged[-1][2] == s:
                merged[-1] = (pid, merged[-1][1], e)
            else:
                merged.append((pid, s, e))
        return merged == [(p, s, e) for p, s, e in t.segments]

    @staticmethod
    def _chart_str(segs):
        return ", ".join(f"{p} {s}–{e}" for p, s, e in segs)

    def _gantt_fix(self, a, b, bar, claimed, raw):
        t = self.truth
        indent = re.match(r"\s*", bar).group(0)
        new = "\n".join(indent + ln for ln in gantt_text(t.segments).split("\n"))
        shown = raw if raw else self._chart_str(claimed)
        self._edit(a, b, new)
        self._bad(Issue("gantt", "Gantt chart", shown, self._chart_str(t.segments),
                        f"Gantt chart: the explanation showed {shown}, the simulator's chart is {self._chart_str(t.segments)}; "
                        "replaced with the simulator's chart."))

    _SEG = re.compile(
        r"\b(?P<pid>P\d+|idle)\b(?P<verb>\s+(?:runs?|executes?|is\s+running|is\s+scheduled|is\s+executed|uses\s+the\s+CPU|gets\s+the\s+CPU|occupies\s+the\s+CPU))?"
        r"\s*(?P<open>[:(\[])?\s*(?:(?:from|during|between)\s+)?(?:t\s*=\s*)?(?P<a>\d+)\s*(?P<sep>-|–|—|to|→|->|until|and)\s*(?:t\s*=\s*)?(?P<b>\d+)"
        r"(?!\s*[=+*/×]|\s*[-−]\s*\d|\d|\.\d)", re.I)

    def segments(self):
        t = self.truth
        found = []
        for m in self._SEG.finditer(self.text):
            a, b = int(m.group("a")), int(m.group("b"))
            if b > a and not any(m.start() < e and s < m.end() for s, e in self._seen):
                found.append(m)
        runs, cur = [], []
        for m in found:
            if cur and re.fullmatch(r"[\s,;→>|\-–—)\]]*(?:then|and)?[\s,;→>|\-–—)\]]*", self.text[cur[-1].end():m.start()], re.I):
                cur.append(m)
            else:
                if cur:
                    runs.append(cur)
                cur = [m]
        if cur:
            runs.append(cur)
        for run in runs:
            if len(run) >= 3 and not any(m.group("verb") for m in run):
                self._segment_run(run)
            else:
                for m in run:
                    self._segment(m)

    def _segment_run(self, run):
        """Three or more consecutive segments are a whole chart: compare it as a chart, not segment by segment."""
        t = self.truth
        claimed = [(m.group("pid").upper() if m.group("pid").lower() != "idle" else "idle", int(m.group("a")), int(m.group("b")))
                   for m in run]
        for m in run:
            self._claim(m.start(), m.end())
        if all(all(t.timeline.get(x) == p for x in range(s, e)) for p, s, e in claimed):
            return
        shown, want = self._chart_str(claimed), self._chart_str(t.segments)
        same_order = [p for p, _, _ in self._merged(claimed)] == [p for p, _, _ in t.segments] and len(run) == len(t.segments)
        if same_order:                                     # right processes in the right order: only times are off
            for m, (p, s, e) in zip(run, t.segments):
                if (int(m.group("a")), int(m.group("b"))) != (s, e):
                    self._edit(m.start("a"), m.end("a"), str(s))
                    self._edit(m.start("b"), m.end("b"), str(e))
            self._bad(Issue("gantt", "Gantt chart", shown, want,
                            f"Gantt chart: the explanation listed {shown}, the simulator's chart is {want}; the times were corrected."))
            return
        first = run[0]
        style = {"(": "paren", "[": "bracket", ":": "colon"}.get(first.group("open") or "", "plain")
        fmt = {"paren": "{p} ({s}-{e})", "bracket": "{p} [{s}-{e}]", "colon": "{p}: {s}-{e}", "plain": "{p} {s}-{e}"}[style]
        a, b = run[0].start(), run[-1].end()
        if style in ("paren", "bracket") and self.text[b:b + 1] in (")", "]"):
            b += 1                                          # the last segment's closing bracket belongs to the run
        arrows = "→" in self.text[a:b] or "->" in self.text[a:b]
        new = (" → " if arrows else ", ").join(fmt.format(p=p, s=s, e=e) for p, s, e in t.segments)
        self._edit(a, b, new)
        self._bad(Issue("gantt", "Gantt chart", shown, want,
                        f"Gantt chart: the explanation listed {shown}, the simulator's chart is {want}; replaced with the simulator's chart."))

    @staticmethod
    def _merged(segs):
        out = []
        for p, s, e in segs:
            if out and out[-1][0] == p and out[-1][2] == s:
                out[-1] = (p, out[-1][1], e)
            else:
                out.append((p, s, e))
        return out

    def _segment(self, m):
        t = self.truth
        pid = m.group("pid").upper() if m.group("pid").lower() != "idle" else "idle"
        a, b = int(m.group("a")), int(m.group("b"))
        if not self._claim(m.start(), m.end()):
            return
        if pid != "idle" and pid not in t.rows:
            self._bad(Issue("gantt", f"{pid} on the CPU", f"{pid} {a}–{b}", "no such process",
                            f"The explanation puts {pid} on the CPU from {a} to {b}, but {pid} is not one of this "
                            f"problem's processes ({', '.join(t.rows)}).", corrected=False))
            return
        if all(t.timeline.get(x) == pid for x in range(a, b)):
            return
        own = [g for g in t.segments if g[0] == pid]
        if not own:
            self._bad(Issue("gantt", f"{pid} on the CPU", f"{pid} {a}–{b}", f"{pid} never runs",
                            f"The explanation puts {pid} on the CPU from {a} to {b}; in the simulator's chart {pid} never runs.",
                            corrected=False))
            return
        best = max(own, key=lambda g: (min(b, g[2]) - max(a, g[1]), -abs(g[1] - a)))
        _, s, e = best
        self._edit(m.start("a"), m.end("a"), str(s))
        self._edit(m.start("b"), m.end("b"), str(e))
        self._bad(Issue("gantt", f"{pid} on the CPU", f"{pid} {a}–{b}", f"{pid} {s}–{e}",
                        f"{pid} on the CPU: the explanation said {a}–{b}, the simulator's chart has {pid} at "
                        f"{s}–{e}; corrected to {s}–{e}."))

    # -- events ------------------------------------------------------------------------------------------------
    def events(self):
        t = self.truth
        at = r"(?:at|by|in)\s+(?:time\s+|t\s*=\s*|t\s+)?"
        lead = r"(?:at\s+)?(?:time\s+|t\s*=\s*)"
        sep = r"\s*[:,–—\-]?\s*(?:then\s+|now\s+)?"
        specs = [
            ("completion", r"(?P<pid>" + _PID + r")\s+(?:completes?|completed|finishes|finished|terminates|terminated|ends|ended)\s+(?:its\s+execution\s+|execution\s+)?" + at + r"(?P<n>\d+)"),
            ("completion", lead + r"(?P<n>\d+)" + sep + r"(?P<pid>" + _PID + r")\s+(?:completes?|completed|finishes|finished|terminates|terminated|ends|ended)\b"),
            ("arrival", r"(?P<pid>" + _PID + r")\s+(?:arrives?|arrived)\s+" + at + r"(?P<n>\d+)"),
            ("arrival", lead + r"(?P<n>\d+)" + sep + r"(?P<pid>" + _PID + r")\s+(?:arrives?|arrived)\b"),
            ("start", r"(?P<pid>" + _PID + r")\s+(?:first\s+runs?|first\s+starts?|is\s+first\s+scheduled|gets\s+the\s+CPU\s+for\s+the\s+first\s+time|starts\s+executing\s+for\s+the\s+first\s+time)\s+" + at + r"(?P<n>\d+)"),
        ]
        for key, pat in specs:
            for m in re.finditer(pat, self.text, re.I):
                pid = m.group("pid").upper()
                if not self._claim(m.start("n"), m.end("n")):
                    continue
                if pid not in t.rows:
                    self._bad(Issue("event", f"{pid} {key}", m.group("n"), "no such process",
                                    f"The explanation mentions {pid}, which is not one of this problem's processes.", corrected=False))
                    continue
                want, got = t.rows[pid][key], int(m.group("n"))
                if want != got:
                    name = {"completion": "completes", "arrival": "arrives", "start": "first runs"}[key]
                    self._edit(m.start("n"), m.end("n"), str(want))
                    self._bad(Issue("event", f"{pid} {name}", str(got), str(want),
                                    f"{pid} {name}: the explanation said t={got}, the simulator gives t={want}; corrected to t={want}."))
        # preemption: "P2 preempts P1 at t=2" / "at t=2, P2 preempts P1"
        pre = t.preemptions()
        for pat, order in ((r"(?P<hi>" + _PID + r")\s*(?:\([^)\n]*\)\s*)?preempts?\s+(?P<lo>" + _PID + r")(?:\s*\([^)\n]*\))?\s*(?:" + at + r"|\bwhen\b[^.\n]{0,40}?at\s+(?:time\s+|t\s*=\s*))(?P<n>\d+)", None),
                           (lead + r"(?P<n>\d+)" + sep + r"(?P<hi>" + _PID + r")\s*(?:\([^)\n]*\)\s*)?preempts?\s+(?P<lo>" + _PID + r")", None)):
            for m in re.finditer(pat, self.text, re.I):
                hi, lo, n = m.group("hi").upper(), m.group("lo").upper(), int(m.group("n"))
                if not self._claim(m.start("n"), m.end("n")):
                    continue
                if (lo, hi, n) in pre:
                    continue
                cand = [x for x in pre if x[0] == lo and x[1] == hi]
                if len(cand) == 1:
                    want = cand[0][2]
                    self._edit(m.start("n"), m.end("n"), str(want))
                    self._bad(Issue("event", f"{hi} preempts {lo}", str(n), str(want),
                                    f"{hi} preempting {lo}: the explanation said t={n}, the simulator has it at t={want}; corrected to t={want}."))
                else:
                    self._bad(Issue("event", f"{hi} preempts {lo}", f"t={n}", "no such preemption",
                                    f"The explanation says {hi} preempts {lo} at t={n}; the simulator's chart has no such preemption"
                                    + (f" (preemptions: {', '.join(f'{b} preempts {a} at t={c}' for a, b, c in pre)})" if pre else " (nothing is preempted)") + ".",
                                    corrected=False))
        # decisions: "t=8: ready [P1, P4] -> run P1", "At t=3, P2 runs"
        for pat in (lead + r"(?P<n>\d+)\s*[:,]\s*(?:ready\s*\[[^\]\n]*\]\s*(?:->|→)\s*)?run(?:s|ning)?\s+(?P<pid>" + _PID + r")",
                    lead + r"(?P<n>\d+)" + sep + r"(?P<pid>" + _PID + r")\s*(?:\([^)\n]*\)\s*)?(?:runs|is\s+running|executes|is\s+selected|is\s+chosen|is\s+picked|resumes|gets\s+the\s+CPU)\b"):
            for m in re.finditer(pat, self.text, re.I):
                pid, n = m.group("pid").upper(), int(m.group("n"))
                if not self._claim(m.start("n"), m.end("pid")):
                    continue
                if n >= t.end:
                    continue
                if t.timeline.get(n) != pid:
                    runs = t.timeline.get(n, "the CPU is idle")
                    self._bad(Issue("event", f"{pid} runs at t={n}", pid, str(runs),
                                    f"The explanation says {pid} runs at t={n}; the simulator runs "
                                    f"{runs if runs != 'the CPU is idle' else 'nobody (the CPU is idle)'} at that time.",
                                    corrected=False))

    # -- driver ------------------------------------------------------------------------------------------------
    def run(self):
        self._seen = []
        self.tables()
        self.gantt_bars()
        self.events()
        self.segments()
        self.averages()
        self.lists()
        self.per_process_prose()
        return self


def _fmt_avg(v):
    return f"{v:.2f}"


def _apply(text, edits):
    out = text
    for a, b, new in sorted(set(edits), key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:a] + new + out[b:]
    return out


def validate(text, result):
    """Check every numerical claim in `text` against the simulator `result`; return a Report with the corrected text."""
    if not text or not result:
        return Report(text=text or "")
    c = _Checker(text, result).run()
    fixed = _apply(text, c.edits) if c.edits else text
    rep = Report(text=fixed, claims=c.claims, issues=c.issues, unresolved=c.unresolved)
    if c.edits:                       # the corrected text must itself pass: otherwise do not pretend it was repaired
        again = _Checker(fixed, result).run()
        for i in again.issues + again.unresolved:
            if i.message not in [x.message for x in rep.unresolved]:
                rep.unresolved.append(Issue(i.kind, i.subject, i.claimed, i.expected,
                                            i.message + " (this could not be corrected cleanly)", corrected=False))
    return rep

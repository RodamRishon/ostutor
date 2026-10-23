"""Work out *what the student is actually asking for* so the answer does exactly that.

Two parts:
  * concept questions  -> detect_intent() picks an answer format (define / compare / why /
                          true-false / advantages / analogy / steps ...) that goes into the LLM prompt;
                          style_examples() adds the two most similar solved Q&As from the instruction
                          dataset as in-context examples (the same tutor style the QLoRA run teaches).
  * numerical questions -> direct_answer() answers the specific thing asked ("waiting time of P2",
                          "Gantt chart only", "how many context switches") straight from the simulator,
                          before the full solution.
"""
from __future__ import annotations

import json
import pathlib
import re

from build_index import tokenize

ROOT = pathlib.Path(__file__).parent

# (name, pattern, instruction for the answer).  First match wins, so order matters.
INTENTS = [
    # Exam formats come first: their option lists and stems contain words ("which", "compare", "why") that would
    # otherwise route them to a different answer shape.
    ("assertion_reason", r"\bassertion\b.*\breason\b",
     "Say whether the Assertion is true, whether the Reason is true, and whether the Reason correctly explains the "
     "Assertion; then name the matching option if options are given. Base each verdict on the context."),
    ("incorrect_statement", r"\b(incorrect|false|wrong|not true)\s+(statement|option|sentence)|"
                            r"which\s+(?:one\s+)?(?:of\s+(?:these|the following)\s+)?(?:statements?\s+)?(?:is|are)\s+(?:incorrect|false|wrong|not (?:true|correct))|"
                            r"\bexcept\b",
     "Name the INCORRECT option first (letter and text), then say in one sentence why it is wrong, and briefly why "
     "each of the others is correct."),
    ("fill_blank", r"fill in the blanks?|_{3,}|\.{5,}",
     "Give the missing word or phrase first, in bold, then one sentence explaining why it fits."),
    ("true_false", r"\btrue\s*(?:or|/)\s*false\b|\bt\s*/\s*f\b|\bstate (?:whether )?true or false",
     "Begin with 'True' or 'False', then give the reason in one or two sentences, and correct the statement if it is false."),
    ("mcq", r"\bwhich of the following\b|\bchoose the (?:correct|right|best)\s+(?:option|answer|choice|statement|alternative|one)\b|\bselect the (?:correct|right)\b|"
            r"(?:^|\n|\s)\(?a[.)]\s.*\(?b[.)]\s",
     "Start with the correct option (its letter and text), then give a one- or two-sentence reason from the context. "
     "Do not discuss the other options unless it helps."),
    ("which_list", r"\bwhich\b(?:\s+[\w-]+){0,4}?\s+(?:algorithms|algos|schedulers|policies|techniques)\b",
     "List every algorithm the context says has this property, one line each with the reason; do not list algorithms "
     "the context says do NOT have it. Mention an important exception or assumption if the context gives one."),
    ("compare", r"\b(compare|comparison|difference|differences|differ|differs|differentiate|versus|vs\.?|distinguish|"
                r"better than|which is better|contrast)\b|"
                r"\b(?:better|faster|worse|more efficient|more fair)\b[^?.]*\bor\b|"
                r"\bor\b[^?.]*\b(?:better|faster|worse|more efficient)\b",
     "Structure the answer as: (1) a one-sentence definition of the first item; (2) a one-sentence definition of the "
     "second; (3) a small comparison table (rows = only the aspects that distinguish them, e.g. cause, effect, "
     "typical algorithm; never an aspect the context does not cover); (4) one simple example for each; "
     "(5) a one-line exam-ready conclusion that follows from the table. Leave out any section that does not help "
     "answer the question, and do not mention algorithms the question does not concern."),
    ("true_false", r"\b(is (this|that|it|he|she) (correct|true|right|accurate)|true or false|"
                   r"a student (says|claims|thinks)|is (it|this) true|am i right|is that right|correct\?)",
     "Begin with 'Yes' or 'No' (or 'Correct' / 'Incorrect'), then give the reason in two or three sentences, "
     "and correct the misconception if there is one."),
    ("why", r"\bwhy\b|\bhow come\b|\breason\b",
     "Give the reason directly: state the cause, then the effect it produces. Do not just define the term."),
    # "Which algorithm is the best / most efficient / fastest ...?" asks for a JUDGEMENT against a criterion, not for the
    # algorithm that follows a rule, so it must not be matched against rule sentences ("identify") and refused when
    # none is found.  Placed before "identify", whose pattern also matches "which ... algorithm".
    ("recommend", r"\b(?:best|most efficient|more efficient|efficient|fastest|optimal|ideal|worst|simplest|easiest|"
                  r"most suitable|recommend\w*|preferred|used in (?:real|practice|windows|linux|modern|industry)|"
                  r"(?:windows|linux|macos|android) (?:use|uses|used))\b",
     "Name the algorithm(s) that best satisfy the criterion in the question, say under which condition that holds, "
     "give the main reason and the main trade-off. Do not claim that one algorithm is best in every situation."),
    # "Which algorithm selects the earliest arrival?" asks for a NAME. It must not fall through to "define" and be
    # answered with a definition of whichever concept the question happens to mention (the ready queue ...).
    ("identify", r"\bwhich\b(?:\s+[\w-]+){0,4}?\s+(?:algorithm|algo|scheduler|policy|technique)\b|"
                 r"\bwhat\b(?:\s+[\w-]+){0,3}?\s+(?:algorithm|algo|scheduler|policy|technique)\s+"
                 r"(?:is|are|does|do|can|will|would|selects?|uses?|gives?|allocates?|picks?|runs?)\b|"
                 r"\bname the (?:algorithm|scheduler|policy)\b",
     "Start with the name of the algorithm in bold, then give the rule from the context that identifies it "
     "(how it picks the next process). Do not define other concepts mentioned in the question."),
    ("analogy", r"\banalog|real[- ]life|real[- ]world|everyday|metaphor|\bimagine\b|layman|simple words|"
                r"in simple terms|like i'?m (5|five)|like i am (5|five)|easy way|intuition",
     "Give one everyday analogy, then map each part of the analogy onto the scheduling concept."),
    ("pros_cons", r"\badvantage|\bdisadvantage|\bpros\b|\bcons\b|drawback|benefit|limitation|weakness|"
                  r"strength|merit|demerit",
     "Give two short bullet lists: advantages and disadvantages. One line each, no extra theory."),
    ("formula", r"\bformula|\bequation|how (is|are|do you|to) (compute|calculate|find|work out)|"
                r"how (do|can) i (compute|calculate|find)",
     "State the formula first, define every symbol in it, then give one tiny numeric illustration."),
    ("steps", r"step[- ]by[- ]step|\bhow does\b.*\b(work|decide|choose|select|pick)|how do(es)? .* (work|decide)|"
              r"\bprocedure\b|\balgorithm for\b|\bsteps?\b|how (is|are) .* (scheduled|selected|chosen)",
     "Explain as numbered steps, in the order the scheduler performs them."),
    ("list", r"\blist\b|\bname\b|\bwhat are the (types|kinds|criteria|metrics|goals|states)\b|\benumerate\b",
     "Answer as a short list with one line per item."),
    ("example", r"\bexample\b|\billustrate\b|\bdemonstrate\b|\bscenario\b",
     "Give one short, concrete scenario that shows the idea. Do not do a full numerical solution."),
    ("define", r"\bwhat is\b|\bwhat are\b|\bwhat's\b|\bwhats\b|\bdefine\b|\bmeaning\b|\bdefinition\b|"
               r"\bexplain\b|\bdescribe\b|\btell me about\b|\bwhat do you mean\b|\bwho\b|\bwhich\b|\bwhen\b|\bwhere\b",
     "Define it in one sentence, then explain how it works and why it matters, in a short paragraph."),
]
# formats whose question text lists options or a stem: they must not be forced to contain a topic's "essential points"
EXAM_INTENTS = {"mcq", "true_false", "fill_blank", "incorrect_statement", "assertion_reason", "which_list"}
DEFAULT_INSTRUCTION = "Answer the question directly in a short paragraph."

LENGTH_HINT = {"mcq": 70, "true_false": 70, "fill_blank": 50, "incorrect_statement": 90, "assertion_reason": 90, "which_list": 120,
               "identify": 80, "recommend": 150, "compare": 280, "pros_cons": 100, "steps": 140, "define": 130, "analogy": 150}


def detect_intent(question: str):
    low = question.lower()
    for name, pat, instruction in INTENTS:
        if re.search(pat, low):
            return name, instruction
    return "answer", DEFAULT_INSTRUCTION


def format_directive(question: str) -> str:
    """The instruction block added to the LLM prompt for a concept question."""
    name, instruction = detect_intent(question)
    words = LENGTH_HINT.get(name, 120)
    return (f"The student wants: {name.replace('_', '/')}. {instruction}\n"
            f"Answer ONLY what was asked, and answer it in the first sentence. Do not describe other algorithms or "
            f"topics unless the question names them. Stay under about {words} words. Use only facts from the "
            f"context; if the context does not contain the answer, say exactly that. State the assumption behind "
            f"any claim that holds only under conditions (for example 'if shorter jobs keep arriving'); do not use "
            f"'always' or 'never' unless the context does. Do not contradict yourself.")


# --------------------------------------------------------------------------- #
# In-context examples from the instruction dataset                             #
# --------------------------------------------------------------------------- #
SOURCE_TAG = re.compile(r"\s*\(Source:[^)]*\)")
_QA = None


def _load_qa():
    global _QA
    if _QA is None:
        _QA = []
        seen = set()
        for f in ("theory.jsonl", "concepts.jsonl", "qa_bank.jsonl"):
            path = ROOT / "data" / "raw" / f
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        r = json.loads(line)
                        if r["output"] in seen:          # a rephrased copy of an answer already loaded
                            continue
                        seen.add(r["output"])
                        _QA.append((set(tokenize(r["instruction"])), r))
    return _QA


_FRAME = {t for w in ("explain describe define what is the of a an how does do why which tell me about part "
                      "algo algorithm algorithms scheduling schedule cpu process processes student says "
                      "correct true right compare difference between").split() for t in tokenize(w)}
_ALGO = {t for w in "round robin sjf srtf fcfs priority rr".split() for t in tokenize(w)}


def style_examples(question: str, idf: dict | None = None, k: int = 2, min_score: float = 2.0):
    """The k solved Q&As whose question is most similar to this one.

    Question-framing words ("explain", "what is") are ignored and the algorithm's name counts for
    little, so "explain the time-quantum part of RR" finds the quantum answer, not the generic RR one."""
    idf = idf or {}
    weight = lambda t: (0.25 if t in _ALGO else 1.0) * idf.get(t, 1.0)
    q = {t for t in tokenize(question) if "_" not in t and t not in _FRAME}
    scored = []
    for toks, rec in _load_qa():
        shared = q & {t for t in toks if "_" not in t and t not in _FRAME}
        if not shared:
            continue
        score = sum(weight(t) for t in shared) / (1 + 0.05 * len(toks))
        scored.append((score, rec))
    scored.sort(key=lambda x: -x[0])
    return [r for sc, r in scored[:k] if sc >= min_score * 0.25]


def examples_block(question, idf=None, k=2):
    ex = style_examples(question, idf, k)
    if not ex:
        return ""
    body = "\n\n".join(f"Q: {r['instruction']}\nA: {SOURCE_TAG.sub('', r['output'])}" for r in ex)
    return ("Examples of verified tutor answers to related questions (match their tone and depth; "
            "do not copy details that do not apply to the new question):\n\n" + body)


# --------------------------------------------------------------------------- #
# Numerical questions: answer the specific thing asked                         #
# --------------------------------------------------------------------------- #
METRICS = [
    ("waiting", r"wait\w*"), ("turnaround", r"turn\s*-?around|\btat\b"), ("response", r"response"),
    ("completion", r"completion|finish(?:es|ed)? (?:time|at)|complete(?:s|d)? (?:at|time)"),
]


METRIC_PAT = dict(METRICS)
PID_LIST = r"(?P<pids>p\d+(?:\s*(?:,|and|&)\s*p\d+)*)"


def _target_pids(low, metric_pat, rows):
    """Processes the question attaches to this metric: 'waiting time of P2 and P3', "P2's waiting time".
    Process data written elsewhere in the question (P1=24, P2=3 ...) is deliberately not counted."""
    found = []
    for pat in (r"(?:" + metric_pat + r")(?:\s*times?)?\s*(?:of|for|in)\s*(?:process(?:es)?\s*)?" + PID_LIST,
                PID_LIST + r"(?:'s|s')\s*(?:" + metric_pat + ")"):
        for m in re.finditer(pat, low):
            found += re.findall(r"p\d+", m.group("pids"))
    return [p.upper() for p in dict.fromkeys(found) if p.upper() in rows]


def direct_answer(question: str, result: dict) -> str | None:
    """A one-to-three line answer to exactly what was asked, computed from the simulator result."""
    low = question.lower()
    rows = {r["pid"]: r for r in result["rows"]}
    lines = []

    asked = [m for m, pat in METRICS if re.search(pat, low)]
    wants_avg = bool(re.search(r"\b(average|avg|mean)\b", low))
    for m in asked:
        key = m
        pids = _target_pids(low, METRIC_PAT[m], rows)
        if pids and not wants_avg:
            vals = ", ".join(f"{p} = {rows[p][key]}" for p in pids)
            lines.append(f"**{m.capitalize()} time**: {vals}")
        elif wants_avg and key != "completion":
            lines.append(f"**Average {m} time = {result['avg_' + m]:.2f}**")
        else:
            vals = ", ".join(f"{p} = {r[key]}" for p, r in rows.items())
            extra = f"; average = {result['avg_' + m]:.2f}" if key != "completion" else ""
            lines.append(f"**{m.capitalize()} time**: {vals}{extra}")

    if re.search(r"gantt|chart|timeline|order of execution|execution order|sequence", low):
        chart = " → ".join(f"{pid} ({s}–{e})" for pid, s, e in result["gantt"])
        lines.append(f"**Gantt chart**: {chart}")
    if re.search(r"(which|what) process(es)? (finish|complete)s? (first|last)|finish(es)? (first|last)|"
                 r"completes? (first|last)|order of completion", low):
        order = sorted(result["rows"], key=lambda r: r["completion"])
        lines.append("**Completion order**: " + " → ".join(f"{r['pid']} (t={r['completion']})" for r in order))
    if re.search(r"context[- ]switch", low):
        segs = [g for g in result["gantt"] if g[0] != "idle"]
        switches = sum(1 for a, b in zip(segs, segs[1:]) if a[0] != b[0])
        lines.append(f"**Context switches** between processes: {switches} "
                     "(counting each change of running process, not the start or the end).")
    if re.search(r"cpu utili[sz]ation|utili[sz]ation", low):
        busy = sum(e - s for p, s, e in result["gantt"] if p != "idle")
        total = result["gantt"][-1][2] - result["gantt"][0][1]
        lines.append(f"**CPU utilisation** = {busy} / {total} = {100 * busy / total:.1f}%")
    if re.search(r"throughput", low):
        total = result["gantt"][-1][2]
        lines.append(f"**Throughput** = {len(rows)} processes / {total} time units = {len(rows) / total:.3f}")
    if re.search(r"longest (waiting|wait)|waits? (the )?longest|maximum waiting|most waiting|\bstarv", low):
        worst = max(result["rows"], key=lambda r: r["waiting"])
        lines.append(f"**Longest wait**: {worst['pid']} waits {worst['waiting']} time units.")
    return "\n\n".join(lines) if lines else None

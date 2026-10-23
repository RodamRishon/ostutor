"""Routing layer (report Section 6.2).

Looks at a student's message and decides where it goes:

    numerical  -> the message contains process data: the simulator computes the
                  answer, retrieval adds the explanation of the algorithm
    practice   -> "give me a practice problem ..."
    check      -> "check my answer ..." with the student's waiting times / chart
    concept    -> everything else: retrieval-grounded explanation

It also parses process data out of the free text the way students actually type it:
    "P1 0 24, P2 1 3"                         (pid arrival burst [priority])
    "P1=24, P2=3, P3=3"                       (bursts only, all arrive at 0)
    "burst times 8,4,9,5 arrival 0,1,2,3"     (parallel lists)
    "P1: arrival 0, burst 10, priority 3"     (labelled)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from scheduler import Process

ALGO_PATTERNS = [
    ("srtf", r"\bsrtf\b|shortest remaining|\bstcf\b"),
    ("rr", r"\brr\b|round[\s-]*robin|time\s*quantum|\bquantum\b|time\s*slice"),
    ("priority", r"\bpriorit(y|ies)\b"),
    ("sjf", r"\bsjf\b|shortest job|\bsjn\b"),
    ("fcfs", r"\bfcfs\b|first[\s-]*come|\bfifo\b"),
]
ALGO_LABEL = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SJF", "priority": "Priority",
              "priority_p": "Priority", "rr": "Round Robin"}

PRACTICE = r"\b(practice|generate|give me|make me|create|new)\b.*\b(problem|question|numerical|exercise)s?\b"
CHECK = r"\b(check|verify|mark|grade|is (this|my) (answer|solution)|did i get)\b"
# "Explain SJF with a numerical" / "show me an example of RR": the student wants
# the tutor to solve and walk through an example itself, not be handed an
# unsolved practice problem (that's PRACTICE) and not just the theory (concept).
WORKED_EXAMPLE = (r"\b(with|using)\s+(a\s+|an\s+)?(numerical|example|worked[\s-]example)\b"
                  r"|\bshow\s+(me\s+)?(an?\s+)?(numerical\s+)?example\b"
                  r"|\bwalk\s+me\s+through\b|\bworked[\s-]example\b")


# "Solve this Round Robin problem and calculate the average waiting time." with no process table attached
NEEDS_DATA = (r"^\W*(?:please\s+)?(?:solve|work out)\b|"
              r"\b(?:solve|calculate|compute|find)\s+(?:this|the|my|a)\s+(?:[\w-]+\s+){0,3}(?:problem|numerical|question)\b")


@dataclass
class Route:
    kind: str                       # numerical | practice | check | concept
    algorithm: str | None = None    # scheduler key, e.g. "rr"
    quantum: int | None = None
    processes: list = field(default_factory=list)
    preemptive: bool | None = None
    notes: list = field(default_factory=list)   # parser remarks shown to the student

    multi: bool = False             # question names more than one algorithm
    algorithms: list = field(default_factory=list)   # compare_numerical: every algorithm to run on the same data

    @property
    def topic(self):
        if self.multi:
            return "Comparison"
        return ALGO_LABEL.get(self.algorithm)


def detect_algorithms(text):
    """Every algorithm the text names, in order: "compare FCFS, SJF and Round Robin" -> ['sjf', 'rr', 'fcfs']."""
    low = text.lower()
    found = [k for k, pat in ALGO_PATTERNS if re.search(pat, low)]
    pre = re.search(r"\bpre-?empt", re.sub(r"non[\s-]*pre-?empt", "", low))
    nonpre = re.search(r"non[\s-]*pre-?empt", low)
    if "priority" in found and pre and not nonpre:
        found[found.index("priority")] = "priority_p"
    if "sjf" in found and pre and not nonpre and "srtf" not in found:
        found[found.index("sjf")] = "srtf"
    return list(dict.fromkeys(found))


def detect_algorithm(text):
    low = text.lower()
    nonpre = re.search(r"non[\s-]*pre-?empt", low)
    pre = re.search(r"\bpre-?empt", re.sub(r"non[\s-]*pre-?empt", "", low))
    for key, pat in ALGO_PATTERNS:
        if re.search(pat, low):
            if key == "srtf" and nonpre and not pre:
                return "sjf"
            if key == "priority" and pre:
                return "priority_p"
            if key == "sjf" and pre:
                return "srtf"
            return key
    return None


def detect_quantum(text):
    """The time quantum as written, including 0 or a negative number (the caller reports those as invalid)."""
    m = re.search(r"(?:quantum|time\s*slice|\bq\b)\s*(?:=|:|of|is)?\s*(-?\d+)", text, re.I)
    if not m:
        m = re.search(r"(-?\d+)\s*(?:ms|units?)?\s*(?:time\s*)?quantum", text, re.I)
    return int(m.group(1)) if m else None


def _ints(s):
    return [int(x) for x in re.findall(r"\d+", s)]


def _list_after(label_regex, text):
    """Numbers following a label, e.g. 'burst times: 8, 4, 9, 5' -> [8, 4, 9, 5]."""
    m = re.search(r"(?:" + label_regex + r")(?:\s*(?:times?|values?|are|is|of|=|:|\(ms\)|ms|respectively)\s*)*"
                  r"((?:\d+\s*(?:,|and|\s)\s*)+\d+)(?!\s*[A-Za-z]*\d)", text, re.I)
    return _ints(m.group(1)) if m else None


def _complete(procs, text):
    """Order the parsed processes by first mention, and refuse (rather than silently drop one) if any process
    named in the text has no readable arrival/burst."""
    mentioned = list(dict.fromkeys(m.upper() for m in re.findall(r"\bP\d+\b", text, re.I)))
    have = {p.pid for p in procs}
    missing = [m for m in mentioned if m not in have]
    if missing:
        raise ValueError(f"I could not read the arrival and burst times for {', '.join(missing)}")
    return sorted(procs, key=lambda p: mentioned.index(p.pid))


def parse_processes(text):
    """Return a list of Process objects, or [] if the text holds no process data."""
    notes = []
    # 1. labelled lines: "P1: arrival 0, burst 10, priority 3" (any order)
    labelled = []
    for m in re.finditer(r"\b(P\d+)\b(.*?)(?=\bP\d+\b|\n|$)", text, re.I | re.S):
        chunk = m.group(2)
        a = re.search(r"arriv\w*\s*(?:time)?\s*(?:=|:|at|of)?\s*(\d+)|\bat\s*[=:]\s*(\d+)", chunk, re.I)
        b = re.search(r"(?:burst|cpu|service|execution)\w*\s*(?:time)?\s*(?:=|:|of)?\s*(\d+)|\bbt\s*[=:]\s*(\d+)",
                      chunk, re.I)
        pr = re.search(r"priority\s*(?:=|:|of)?\s*(\d+)", chunk, re.I)
        if b:
            labelled.append(Process(m.group(1).upper(), int(a.group(1) or a.group(2)) if a else 0,
                                    int(b.group(1) or b.group(2)),
                                    int(pr.group(1)) if pr else 0))
    if len(labelled) >= 2:
        try:
            return _complete(labelled, text), notes
        except ValueError:      # some processes are in another format: the row parser below merges them in
            pass

    # 2. parallel lists: "burst times 8,4,9,5 arrival 0,1,2,3 priorities 3,1,4"
    bursts = _list_after(r"burst(?:\s*times?)?|cpu\s*bursts?|service\s*times?", text)
    if bursts and len(bursts) >= 2:
        arrivals = _list_after(r"arriv\w*(?:\s*times?)?", text) or [0] * len(bursts)
        prios = _list_after(r"priorit(?:y|ies)", text) or [0] * len(bursts)
        if len(arrivals) != len(bursts):
            notes.append("arrival list length differs from burst list; missing arrivals taken as 0")
            arrivals = (arrivals + [0] * len(bursts))[:len(bursts)]
        prios = (prios + [0] * len(bursts))[:len(bursts)]
        return [Process(f"P{i+1}", arrivals[i], bursts[i], prios[i]) for i in range(len(bursts))], notes

    # 3. table rows: "P1 0 24 3" -> pid arrival burst [priority]
    rows = re.findall(r"\b(P\d+)\b[\s|,:]+(\d+)[\s|,]+(\d+)(?:[\s|,]+(\d+))?(?!\s*[=\d])", text, re.I)
    if len(rows) + len(labelled) >= 2 and rows:
        # Column order: arrival before burst unless a header line says otherwise.
        header = text[:re.search(r"\bP\d+\b", text, re.I).start()].lower()
        swap = "burst" in header and "arriv" in header and header.index("burst") < header.index("arriv")
        if swap:
            notes.append("header lists burst before arrival; columns read in that order")
        procs = [Process(pid.upper(), int(b) if swap else int(a), int(a) if swap else int(b),
                         int(p) if p else 0) for pid, a, b, p in rows]
        # a question may mix "P1 arrives 0 burst 24" with "P2 0 3": keep the labelled ones too
        have = {p.pid for p in procs}
        procs += [p for p in labelled if p.pid not in have]
        return _complete(procs, text), notes

    # 4. bursts only: "P1=24, P2=3, P3=3" or "P1 = 24 ms"
    pairs = re.findall(r"\b(P\d+)\s*(?:=|:|->|with burst)\s*(\d+)", text, re.I)
    if len(pairs) >= 2:
        notes.append("no arrival times given, so all processes are taken to arrive at t=0")
        return [Process(pid.upper(), 0, int(b)) for pid, b in pairs], notes
    return [], notes


def route(text):
    low = text.lower()
    algo = detect_algorithm(text)
    if re.search(PRACTICE, low):
        return Route("practice", algorithm=algo, quantum=detect_quantum(text))
    try:
        procs, notes = parse_processes(text)
    except ValueError as e:                 # e.g. a burst time of 0
        return Route("invalid", algorithm=algo, notes=[f"could not use the process data: {e}"])
    q = detect_quantum(text)
    if algo == "rr" and q is not None and q <= 0 and (procs or re.search(NEEDS_DATA, low)):
        return Route("invalid", algorithm=algo, quantum=q, notes=[f"the time quantum must be a positive whole number (got {q})"])
    if re.search(CHECK, low) and procs:
        r = Route("check", algorithm=algo, quantum=detect_quantum(text), processes=procs, notes=notes)
        return r
    if len(procs) >= 2 and len(detect_algorithms(text)) >= 2:
        algos = detect_algorithms(text)
        r = Route("compare_numerical", algorithm=algos[0], quantum=detect_quantum(text), processes=procs, notes=notes,
                  algorithms=algos)
        if "rr" in algos and not r.quantum:
            r.quantum = 2
            r.notes.append("no time quantum given, so q = 2 is assumed for Round Robin")
        if any(a.startswith("priority") for a in algos) and all(p.priority == 0 for p in procs):
            r.notes.append("no priorities were found in the question; every process has priority 0")
        return r
    if len(procs) >= 2:
        r = Route("numerical", algorithm=algo, quantum=detect_quantum(text), processes=procs, notes=notes)
        if r.algorithm is None:
            r.algorithm = "fcfs"
            r.notes.append("no algorithm named, so FCFS is used; name one (SJF, SRTF, RR q=4, priority) to change it")
        if r.algorithm == "rr" and not r.quantum:
            r.quantum = 2
            r.notes.append("no time quantum given, so q = 2 is assumed")
        if r.algorithm in ("priority", "priority_p") and all(p.priority == 0 for p in procs):
            r.notes.append("no priorities were found in the question; every process has priority 0")
        return r
    if algo and re.search(WORKED_EXAMPLE, low):
        return Route("worked_example", algorithm=algo, quantum=detect_quantum(text))
    if algo and re.search(NEEDS_DATA, low):
        return Route("needs_data", algorithm=algo, quantum=detect_quantum(text))
    named = {ALGO_LABEL[k] for k, pat in ALGO_PATTERNS if re.search(pat, low)}
    return Route("concept", algorithm=algo, multi=len(named) >= 2)

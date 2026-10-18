"""Check a student's worked answer against the simulator (report Section 6.2,
verification layer): pinpoint the first step where the calculation diverges.

The student can give any of:
    a Gantt chart     "P1 0-24, P2 24-27, P3 27-30"   or  "P1(0-4) P2(4-7) ..."
    waiting times     "waiting P1=0, P2=24, P3=27"
    an average        "average waiting time = 17"
"""
from __future__ import annotations

import re


def parse_student_answer(text):
    ans = {"gantt": [], "waiting": {}, "turnaround": {}, "avg_waiting": None, "avg_turnaround": None}
    for pid, s, e in re.findall(r"\b(P\d+|idle)\s*[\(\[:]?\s*(\d+)\s*(?:-|–|to)\s*(\d+)", text, re.I):
        ans["gantt"].append((pid.upper() if pid.lower() != "idle" else "idle", int(s), int(e)))
    # per-process values: look inside the clause that mentions waiting / turnaround
    for key, label in (("waiting", r"wait\w*|\bwt\b"), ("turnaround", r"turn\s*-?around|\btat\b")):
        for clause in re.findall(r"(?:" + label + r")[^.;\n]*", text, re.I):
            if re.search(r"av(?:g|erage)", clause, re.I):
                continue
            for pid, v in re.findall(r"\b(P\d+)\s*(?:=|:|is)\s*(\d+(?:\.\d+)?)", clause, re.I):
                ans[key][pid.upper()] = float(v)
    m = re.search(r"av(?:g|erage)\.?\s*(?:waiting|wt)[^\d\n]{0,20}(\d+(?:\.\d+)?)", text, re.I)
    if m:
        ans["avg_waiting"] = float(m.group(1))
    m = re.search(r"av(?:g|erage)\.?\s*(?:turn\s*-?around|tat)[^\d\n]{0,20}(\d+(?:\.\d+)?)", text, re.I)
    if m:
        ans["avg_turnaround"] = float(m.group(1))
    return ans


def _timeline(gantt):
    """Expand segments into one entry per time unit: [(t, pid), ...]."""
    out = {}
    for pid, s, e in gantt:
        for t in range(s, e):
            out[t] = pid
    return out


def _context(log, t):
    """Simulator log lines at or just before time t: the decision the student missed."""
    best = []
    for line in log:
        m = re.match(r"t=(\d+):", line)
        if m and int(m.group(1)) <= t:
            best.append(line)
    return best[-3:]


def check_answer(result, student_text):
    """Return {'correct': bool, 'findings': [...], 'first_error': str|None}."""
    ans = parse_student_answer(student_text)
    findings, first_error = [], None
    if not (ans["gantt"] or ans["waiting"] or ans["turnaround"] or
            ans["avg_waiting"] is not None or ans["avg_turnaround"] is not None):
        return {"correct": False, "first_error": None, "parsed": ans,
                "findings": ["I could not find a Gantt chart, waiting times or an average in your answer. "
                             "Write it like: 'P1 0-24, P2 24-27, P3 27-30; waiting P1=0, P2=24, P3=27; "
                             "average waiting = 17'."]}

    # 1. Gantt chart: the earliest divergence explains everything after it
    if ans["gantt"]:
        mine, truth = _timeline(ans["gantt"]), _timeline(result["gantt"])
        end = max(max(mine, default=0), max(truth, default=0)) + 1
        for t in range(end):
            if mine.get(t) != truth.get(t):
                expected, got = truth.get(t, "nothing (all done)"), mine.get(t, "nothing")
                first_error = (f"Your Gantt chart first diverges at t={t}: you have {got} on the CPU, "
                               f"but {expected} should run.")
                findings.append(first_error)
                ctx = _context(result["log"], t)
                if ctx:
                    findings.append("What the scheduler sees at that point:\n" +
                                    "".join(f"\n    - {c}" for c in ctx))
                break
        else:
            findings.append("Gantt chart: correct.")

    # 2. per-process times
    truth_rows = {r["pid"]: r for r in result["rows"]}
    for key in ("waiting", "turnaround"):
        for pid, v in ans[key].items():
            if pid not in truth_rows:
                findings.append(f"{pid} is not one of the processes in this problem.")
                continue
            want = truth_rows[pid][key]
            if abs(v - want) > 0.01:
                r = truth_rows[pid]
                how = (f"turnaround = completion − arrival = {r['completion']} − {r['arrival']} = {r['turnaround']}"
                       if key == "turnaround" else
                       f"waiting = turnaround − burst = {r['turnaround']} − {r['burst']} = {r['waiting']}")
                msg = f"{pid} {key} time: you wrote {v:g}, correct is {want} ({how})."
                findings.append(msg)
                first_error = first_error or msg

    # 3. averages
    for key in ("avg_waiting", "avg_turnaround"):
        if ans[key] is not None:
            want = result[key]
            if abs(ans[key] - want) > 0.011:
                label = key.replace("avg_", "average ").replace("_", " ")
                col = key.replace("avg_", "")
                parts = " + ".join(str(r[col]) for r in result["rows"])
                msg = (f"Your {label} time is {ans[key]:g}, correct is {want:.2f} "
                       f"= ({parts}) / {len(result['rows'])}.")
                findings.append(msg)
                first_error = first_error or msg
            else:
                findings.append(f"{key.replace('avg_', 'Average ').replace('_', ' ')} time: correct ({want:.2f}).")

    correct = first_error is None
    return {"correct": correct, "first_error": first_error, "findings": findings, "parsed": ans}

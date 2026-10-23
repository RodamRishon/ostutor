"""A chronological, structured explanation of a simulator result.

Everything here is derived from the simulator's own output (the Gantt chart and the per-process rows): no language
model is involved and no number is computed from anything else.  The module replays the scheduling RULE of the
algorithm over the simulator's timeline to say WHY each decision was taken (who was ready, with which key, which tie
was broken how, who was preempted with how much burst left, what the Round Robin queue looked like) and checks as it
goes that the rule really produces the simulator's choice.  If the replay ever disagrees with the simulator it sets
`consistent = False` and falls back to a plain segment-by-segment account that makes no claim about reasons, so an
explanation can be less detailed but never different from the Gantt chart.

    steps(result)        -> Steps(lines, consistent)      every decision, arrival, preemption, completion, idle period
    derivations(result)  -> [markdown line per process]   how CT, TAT, WT and RT of each process follow
    averages(result)     -> [markdown line per average]   the actual column values, the sum, the division, the rounding
    checks(result)       -> [markdown line]               consistency facts that hold for this schedule
    render(result, ...)  -> markdown                      the whole worked solution
    unmatched_requests(question) -> [str]                 numbered requests in a question that nothing here can answer
"""
from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass
from decimal import Decimal

from scheduler import ALGO_RULE, check_invariants, gantt_text, table_text

MINUS = "−"
PREEMPTIVE = ("srtf", "priority_p")

CONVENTIONS = {          # only what ALGO_RULE (scheduler.py) does not already say
    "fcfs": "Processes that arrive together are ordered by their position in the input.",
    "sjf": "Equal bursts are broken by earlier arrival, then by position in the input.",
    "srtf": "Ties are broken by earlier arrival, then by position in the input.",
    "priority": "Equal priorities are broken by earlier arrival, then by position in the input.",
    "priority_p": "Ties are broken by earlier arrival, then by position in the input.",
    "rr": "A process that arrives at the instant a quantum expires joins the queue before the preempted process; arrivals "
          "at the same time are queued in input order.",
}
_CRITERION = {"fcfs": "the earliest arrival", "sjf": "the shortest burst", "srtf": "the least remaining time",
              "priority": "the best priority (lowest number)", "priority_p": "the best priority (lowest number)"}
_NOUN = {"fcfs": "arrival time", "sjf": "burst", "srtf": "remaining time", "priority": "priority", "priority_p": "priority"}


def _num(x):
    return str(int(x)) if float(x) == int(x) else f"{x:.2f}"


def _joined(names):
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@dataclass
class Steps:
    lines: list
    consistent: bool


class _Facts:
    """What the timeline says, looked up by process and by time."""

    def __init__(self, result):
        self.result = result
        self.algo = result["algorithm"]
        self.rows = {r["pid"]: r for r in result["rows"]}
        self.order = {pid: i for i, pid in enumerate(self.rows)}
        self.segments = [tuple(g) for g in result["gantt"]]
        self.run_at = {}
        for pid, s, e in self.segments:
            for t in range(s, e):
                self.run_at[t] = pid
        self.end = max((e for _, _, e in self.segments), default=0)
        rem = {pid: r["burst"] for pid, r in self.rows.items()}
        self.rem_before = []                       # remaining burst of every process just before time t runs
        for t in range(self.end + 1):
            self.rem_before.append(dict(rem))
            who = self.run_at.get(t)
            if who and who != "idle":
                rem[who] -= 1

    def ready(self, t):
        return [p for p, r in self.rows.items() if r["arrival"] <= t and self.rem_before[t][p] > 0]

    def key(self, pid, t):
        r, rem = self.rows[pid], self.rem_before[t][pid]
        a, o = r["arrival"], self.order[pid]
        return {"fcfs": (a, o), "sjf": (r["burst"], a, o), "srtf": (rem, a, o),
                "priority": (r["priority"], a, o), "priority_p": (r["priority"], a, o)}[self.algo]

    def attr(self, pid, t):
        r, rem = self.rows[pid], self.rem_before[t][pid]
        return {"fcfs": f"arrived t={r['arrival']}", "sjf": f"burst {r['burst']}", "srtf": f"remaining {rem}",
                "priority": f"priority {r['priority']}",
                "priority_p": f"priority {r['priority']}, remaining {rem}"}[self.algo]

    def arrival_text(self, pids):
        def one(p):
            r = self.rows[p]
            extra = f", priority {r['priority']}" if self.algo.startswith("priority") else ""
            return f"{p} (burst {r['burst']}{extra})"
        if len(pids) == 1:
            return f"{one(pids[0])} arrives."
        return f"{_joined(one(p) for p in pids)} arrive together; arrivals at the same time are ordered by their position in the input."


def _tie_note(f, cur, tied, t):
    """Why `cur` beat the processes that tied with it on the first key."""
    group = [cur] + tied
    names = _joined(group)
    arrivals = {p: f.rows[p]["arrival"] for p in group}
    value = f.key(cur, t)[0]
    if f.algo == "fcfs":
        return f"{names} arrived at the same time (t={value}), so their order in the input decides: {cur} is listed first"
    if len(set(arrivals.values())) == len(group):
        times = ", ".join(f"{p} at t={arrivals[p]}" for p in group)
        return f"{names} tie on {_NOUN[f.algo]} ({value}); the earlier arrival wins ({times})"
    if len(set(arrivals.values())) == 1:
        return f"{names} tie on {_NOUN[f.algo]} ({value}) and arrived together, so their order in the input decides: {cur} is listed first"
    return (f"{names} tie on {_NOUN[f.algo]} ({value}); the earlier arrival wins, and among equal arrivals the order in the input "
            f"({', '.join(f'{p} at t={arrivals[p]}' for p in group)})")


# --------------------------------------------------------------------------- FCFS / SJF / SRTF / Priority
def _steps_by_key(f):
    ev, ok = [], True
    add = lambda t, prio, text: ev.append((t, prio, len(ev), text))
    moments = sorted({r["arrival"] for r in f.rows.values()} | {s for _, s, _ in f.segments} | {e for _, _, e in f.segments})
    preemptive = f.algo in PREEMPTIVE
    crit, noun = _CRITERION[f.algo], _NOUN[f.algo]
    for t in moments:
        prev = f.run_at.get(t - 1) if t > 0 else None
        cur = f.run_at.get(t)
        done_now = [p for p, r in f.rows.items() if r["completion"] == t]
        arr_now = sorted((p for p, r in f.rows.items() if r["arrival"] == t), key=f.order.get)
        for p in done_now:
            add(t, 0, f"{p} completes (CT = {t}).")
        explained = set()                     # arrivals that a decision line below already describes
        if t < f.end and cur is not None and cur != "idle":
            ready = f.ready(t)
            if cur not in ready:
                ok = False
            elif cur != prev:
                others = sorted((p for p in ready if p != cur), key=lambda p: f.key(p, t))
                best = min(ready, key=lambda p: f.key(p, t))
                if best != cur:
                    ok = False
                preempted = prev not in (None, "idle") and prev not in done_now
                if preempted:
                    if not preemptive or not f.key(cur, t)[0] < f.key(prev, t)[0]:
                        ok = False
                    came = "arrives and " if cur in arr_now else ""
                    if cur in arr_now:
                        explained.add(cur)
                    text = (f"{cur} ({f.attr(cur, t)}) {came}preempts {prev} ({f.attr(prev, t)}): its {noun} is strictly better. "
                            f"{prev} goes back to the ready queue with {f.rem_before[t][prev]} unit(s) of its burst left.")
                elif not others:
                    text = f"only {cur} is ready ({f.attr(cur, t)}), so {cur} runs."
                else:
                    cands = ", ".join(f"{p} ({f.attr(p, t)})" for p in [cur] + others)
                    text = f"the CPU is free; ready: {cands}. {cur} runs: it has {crit}."
                tied = [p for p in others if f.key(p, t)[0] == f.key(cur, t)[0]]
                if tied:
                    text += " Tie-break: " + _tie_note(f, cur, tied, t) + "."
                text += (" Ready queue now: [" + ", ".join(f"{p} ({f.attr(p, t)})" for p in others) + "]."
                         if others else " Ready queue now: empty.")
                add(t, 2, text)
            else:
                late = [a for a in arr_now if a != cur]
                if preemptive:
                    for a in late:
                        ka, kc = f.key(a, t)[0], f.key(cur, t)[0]
                        if not ka >= kc:
                            ok = False
                        why = (f"its {noun} ({ka}) equals {cur}'s ({kc}) and equal values never preempt" if ka == kc
                               else f"its {noun} ({ka}) is not better than {cur}'s ({kc})")
                        add(t, 2, f"{a} ({f.attr(a, t)}) arrives but does not preempt {cur} ({f.attr(cur, t)}): {why}, "
                                  f"so {cur} keeps the CPU and {a} waits in the ready queue.")
                        explained.add(a)
                elif late:
                    def label(a):            # FCFS's usual label is the arrival time, which the sentence already says
                        return f"burst {f.rows[a]['burst']}" if f.algo == "fcfs" else f.attr(a, t)

                    add(t, 2, f"{_joined(f'{a} (' + (label(a)) + ')' for a in late)} arrive{'s' if len(late) == 1 else ''} and "
                              f"join{'s' if len(late) == 1 else ''} the ready queue; {cur} keeps running because a running process "
                              "is never interrupted.")
                    explained.update(late)
        rest = [a for a in arr_now if a not in explained]
        if rest:
            add(t, 1, f.arrival_text(rest))
        if cur == "idle" and prev != "idle" and t < f.end:
            stop = next(e for pid, s, e in f.segments if pid == "idle" and s == t)
            add(t, 2, f"no process is ready, so the CPU is idle until t={stop}.")
    return [f"t={t}: {text}" for t, _, _, text in sorted(ev)], ok


# --------------------------------------------------------------------------- Round Robin
def _steps_rr(f):
    q = f.result["quantum"]
    ev, ok = [], True
    add = lambda t, prio, text: ev.append((t, prio, len(ev), text))
    arrivals = sorted(f.rows, key=lambda p: (f.rows[p]["arrival"], f.order[p]))
    state = {"next": 0}
    queue = deque()
    rem = {p: r["burst"] for p, r in f.rows.items()}

    def enqueue(upto):
        """Queue every process that has arrived by `upto`; say so at the time it arrived. Returns the new ones."""
        new = []
        while state["next"] < len(arrivals) and f.rows[arrivals[state["next"]]]["arrival"] <= upto:
            p = arrivals[state["next"]]
            state["next"] += 1
            queue.append(p)
            new.append(p)
        by_time = {}
        for p in new:
            by_time.setdefault(f.rows[p]["arrival"], []).append(p)
        for at, group in sorted(by_time.items()):
            names = _joined(group)
            together = " (same arrival time: input order)" if len(group) > 1 else ""
            add(at, 1, f"{names} arrive{'s' if len(group) == 1 else ''} and join{'s' if len(group) == 1 else ''} the ready queue{together}.")
        return new

    prev_pid = None
    for pid, s, e in f.segments:
        if pid == "idle":
            if queue:
                ok = False
            add(s, 2, f"the ready queue is empty, so the CPU is idle until t={e}.")
            prev_pid = None
            continue
        enqueue(s)
        t = s
        while t < e:
            if not queue or queue[0] != pid:
                ok = False
                break
            before = list(queue)
            queue.popleft()
            span = min(q, rem[pid], e - t)
            if span != min(q, rem[pid]):
                ok = False
            left_before = rem[pid]
            rem[pid] -= span
            tn = t + span
            lone = prev_pid == pid and not before[1:] and t > s
            if not lone:
                names = ", ".join(before)
                add(t, 2, f"queue [{names}]: {pid} runs min(quantum {q}, remaining {left_before}) = {span} unit(s), "
                          f"from t={t} to t={tn}; its remaining time goes from {left_before} to {rem[pid]}.")
            else:
                add(t, 2, f"{pid} is the only process in the queue, so it keeps the CPU for another slice from t={t} to t={tn} "
                          f"(remaining {left_before} to {rem[pid]}).")
            new = enqueue(tn)
            if rem[pid] > 0:
                queue.append(pid)
                if list(queue) != [pid]:
                    at_same = [p for p in new if f.rows[p]["arrival"] == tn]
                    tie = (f" {_joined(at_same)} arrived at this very instant, so {'it is' if len(at_same) == 1 else 'they are'} queued before {pid}."
                           if at_same else "")
                    add(tn, 1.5, f"quantum expires: {pid} (remaining {rem[pid]}) goes to the back of the queue.{tie} "
                               f"Queue now: [{', '.join(queue)}].")
            else:
                add(tn, 0, f"{pid} completes (CT = {tn}).")
            prev_pid = pid
            t = tn
        else:
            continue
        break
    if any(v != 0 for v in rem.values()):
        ok = False
    return [f"t={t}: {text}" for t, _, _, text in sorted(ev)], ok


def _plain_steps(f):
    """Reason-free account used if the rule replay ever disagrees with the simulator: what ran when, and what finished."""
    ev = []
    add = lambda t, prio, text: ev.append((t, prio, len(ev), text))
    for p, r in f.rows.items():
        add(r["arrival"], 1, f"{p} arrives (burst {r['burst']}).")
        add(r["completion"], 0, f"{p} completes (CT = {r['completion']}).")
    for pid, s, e in f.segments:
        add(s, 2, "the CPU is idle." if pid == "idle" else f"{pid} runs from t={s} to t={e}.")
    return [f"t={t}: {text}" for t, _, _, text in sorted(ev)]


def steps(result):
    f = _Facts(result)
    lines, ok = _steps_rr(f) if f.algo == "rr" else _steps_by_key(f)
    if not ok:
        return Steps(_plain_steps(f), False)
    return Steps(lines, True)


# --------------------------------------------------------------------------- per-process derivations, averages, checks
def _intervals(f, pid):
    r = f.rows[pid]
    waits = [t for t in range(r["arrival"], r["completion"]) if f.run_at.get(t) != pid]
    spans, start = [], None
    for t in waits:
        if start is None:
            start = prev = t
        elif t == prev + 1:
            prev = t
        else:
            spans.append((start, prev + 1))
            start = prev = t
    if start is not None:
        spans.append((start, prev + 1))
    return spans


def derivations(result):
    f = _Facts(result)
    out = ["CT is the time a process's last unit on the CPU ends; AT = arrival time, BT = burst time.", ""]
    for p, r in f.rows.items():
        extra = f", priority {r['priority']}" if f.algo.startswith("priority") else ""
        spans = _intervals(f, p)
        waited = ""
        if spans and sum(e - s for s, e in spans) == r["waiting"]:
            waited = (" (it waited during " + ", ".join(f"t={s}–{e}" for s, e in spans)
                      + f" = {' + '.join(str(e - s) for s, e in spans)} = {r['waiting']} unit(s))" if len(spans) > 1 else
                      f" (it waited during t={spans[0][0]}–{spans[0][1]}, {r['waiting']} unit(s))")
        elif not spans and r["waiting"] == 0:
            waited = " (it never waited)"
        out.append(f"- **{p}** (arrival {r['arrival']}, burst {r['burst']}{extra}): "
                   f"CT = {r['completion']}; "
                   f"TAT = CT {MINUS} AT = {r['completion']} {MINUS} {r['arrival']} = {r['turnaround']}; "
                   f"WT = TAT {MINUS} BT = {r['turnaround']} {MINUS} {r['burst']} = {r['waiting']}{waited}; "
                   f"RT = first CPU start {MINUS} AT = {r['start']} {MINUS} {r['arrival']} = {r['response']}.")
    return out


def averages(result):
    rows = result["rows"]
    n = len(rows)
    out = []
    for col, name in (("waiting", "waiting"), ("turnaround", "turnaround"), ("response", "response")):
        vals = [r[col] for r in rows]
        total = sum(vals)
        shown = result["avg_" + col]
        line = f"- Average {name} time = ({' + '.join(str(v) for v in vals)}) / {n} = {total} / {n} = **{shown:.2f}**"
        exact = Decimal(total) / Decimal(n)
        if exact != Decimal(f"{shown:.2f}"):
            line += f" (the exact value {exact.quantize(Decimal('0.0001'))} is rounded to 2 decimal places)"
        out.append(line)
    return out


def checks(result):
    if check_invariants(result):
        return []
    f = _Facts(result)
    busy = sum(r["burst"] for r in f.rows.values())
    idle = sum(e - s for pid, s, e in f.segments if pid == "idle")
    done = max(r["completion"] for r in f.rows.values())
    parts = ["each process is on the CPU for exactly its burst time in the chart"]
    if busy + idle == f.end == done:
        parts.append(f"the bursts add up to {busy}, the CPU idles for {idle} unit(s), and the schedule ends at t={done} "
                     f"({busy} + {idle} = {busy + idle})")
    parts.append("TAT = WT + BT holds for every process")
    return ["- " + "; ".join(parts) + "."]


# --------------------------------------------------------------------------- the whole solution
def render(result, notes=(), chart=True):
    """The worked solution as markdown. chart=False leaves out the Gantt block and the table (the app draws those)."""
    q = f" with time quantum {result['quantum']}" if result["quantum"] else ""
    out = [f"**{result['algorithm_name']}{q}**: solved by the scheduling simulator (computed, not generated).\n"]
    if notes:
        out.append("Assumptions: " + "; ".join(notes) + ".\n")
    out.append(f"**Rule:** {ALGO_RULE[result['algorithm']]} {CONVENTIONS[result['algorithm']]} Context switches take no time.\n")
    out.append("**Step 1: scheduling decisions** (in time order)")
    out += [f"- {line}" for line in steps(result).lines]
    if chart:
        out.append("\n**Step 2: Gantt chart**\n```\n" + gantt_text(result["gantt"]) + "\n```")
        out.append(f"**Step 3: times** (turnaround = completion {MINUS} arrival, waiting = turnaround {MINUS} burst, "
                   f"response = first run {MINUS} arrival)\n\n" + table_text(result) + "\n")
        out += derivations(result)
        out.append("\n**Step 4: averages**")
    else:
        out.append(f"\n**Step 2: how each time is derived** (TAT = CT {MINUS} AT, WT = TAT {MINUS} BT, RT = first CPU start {MINUS} AT)")
        out += derivations(result)
        out.append("\n**Step 3: averages**")
    out += averages(result)
    ck = checks(result)
    if ck:
        out.append("\n**Checks**")
        out += ck
    return "\n".join(out)


# --------------------------------------------------------------------------- what was asked
_ANSWERABLE = re.compile(
    r"gantt|chart|timeline|completion|\bct\b|finish|turn\s*-?around|\btat\b|waiting|\bwt\b|response|\brt\b|average|avg|\bmean\b|"
    r"step|explain|explanation|decision|schedul|preempt|ready queue|queue|tie|remaining|idle|verify|check|formula|calculat|"
    r"deriv|context[- ]switch|utili[sz]ation|throughput|starv|execution order|order of execution|table|result",
    re.I)


def requested_items(question):
    """The numbered requests in a question ("1. The complete Gantt chart. 2. Completion time ..."), in order."""
    return [m.group(1).strip() for m in re.finditer(r"(?m)^\s*\d+[.)]\s+(\S.*)$", question)]


def unmatched_requests(question):
    """Numbered requests that name nothing a scheduling simulator can produce, so the answer can say it left them out
    instead of silently skipping them."""
    return [item.rstrip(" .") for item in requested_items(question) if not _ANSWERABLE.search(item)]


_ASPECTS = [r"gantt|chart|timeline", r"completion|\bct\b", r"turn\s*-?around|\btat\b", r"waiting|\bwt\b", r"response|\brt\b",
            r"average|avg|\bmean\b", r"step|explain|explanation|decision|preempt|ready queue|tie"]


def is_broad(question):
    """A request for the whole solution (chart, several times, averages, explanation) rather than one value: it is
    answered with the complete worked solution, in the order of the solution, instead of a short direct answer."""
    return sum(bool(re.search(p, question, re.I)) for p in _ASPECTS) >= 4

"""Deterministic CPU scheduling simulator: the verification layer.

Covers the four algorithms of the course unit:
    FCFS, SJF (non-preemptive and preemptive / SRTF),
    Priority (non-preemptive and preemptive), Round Robin.

Conventions (Silberschatz, Operating System Concepts):
    * a lower priority number means a higher priority
    * turnaround = completion - arrival
    * waiting    = turnaround - burst
    * response   = first time on the CPU - arrival
    * ties are broken by arrival time, then by the order the processes were given

Every algorithm also records a decision log ("t=3: P2 arrives ...") which the
tutor uses to explain the solution step by step and which the answer checker
uses to say *why* a student's chart is wrong.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int = 0
    # simulation state
    remaining: int = field(default=0, repr=False)
    start: int | None = field(default=None, repr=False)
    completion: int | None = field(default=None, repr=False)
    order: int = field(default=0, repr=False)  # position in the input, for ties

    def __post_init__(self):
        if self.burst <= 0:
            raise ValueError(f"{self.pid}: burst time must be positive")
        if self.arrival < 0:
            raise ValueError(f"{self.pid}: arrival time cannot be negative")
        self.remaining = self.burst


ALGORITHMS = {
    "fcfs": "First Come First Served",
    "sjf": "Shortest Job First (non-preemptive)",
    "srtf": "Shortest Remaining Time First (preemptive SJF)",
    "priority": "Priority (non-preemptive)",
    "priority_p": "Priority (preemptive)",
    "rr": "Round Robin",
}

# Plain-English selection rule shown above the step-by-step walkthrough, so a
# student can see which rule produced each decision in the log.
ALGO_RULE = {
    "fcfs": "At every decision point, run the ready process that arrived earliest. "
            "Once a process starts, it runs to completion.",
    "sjf": "At every decision point, run the ready process with the shortest burst time. "
           "Once a process starts, it runs to completion (non-preemptive).",
    "srtf": "At every time unit, run the ready process with the least remaining time. "
            "A newly arrived process preempts the one running if its remaining time is "
            "strictly shorter.",
    "priority": "At every decision point, run the ready process with the best (lowest-numbered) "
                "priority. Once a process starts, it runs to completion (non-preemptive).",
    "priority_p": "At every time unit, run the ready process with the best (lowest-numbered) "
                  "priority. A newly arrived process preempts the one running if its priority "
                  "is strictly better.",
    "rr": "Ready processes sit in a FIFO queue. The process at the front runs for one time "
          "quantum (or until it finishes, if that's sooner); if it still has work left it goes "
          "to the back of the queue, behind anyone who arrived during its slice.",
}


def _fresh(procs):
    """Copy the input so callers can reuse their Process list."""
    out = []
    for k, p in enumerate(procs):
        q = Process(p.pid, p.arrival, p.burst, p.priority)
        q.order = k
        out.append(q)
    return out


def _append(gantt, pid, start, end):
    """Add a Gantt segment, merging with the previous one if it is the same process."""
    if gantt and gantt[-1][0] == pid and gantt[-1][2] == start:
        gantt[-1] = (pid, gantt[-1][1], end)
    else:
        gantt.append((pid, start, end))


def _summarise(procs, gantt, log, algorithm, quantum=None):
    rows = []
    for p in sorted(procs, key=lambda p: p.order):
        tat = p.completion - p.arrival
        rows.append({
            "pid": p.pid, "arrival": p.arrival, "burst": p.burst,
            "priority": p.priority, "start": p.start, "completion": p.completion,
            "turnaround": tat, "waiting": tat - p.burst,
            "response": p.start - p.arrival,
        })
    n = len(rows)
    return {
        "algorithm": algorithm,
        "algorithm_name": ALGORITHMS[algorithm],
        "quantum": quantum,
        "gantt": gantt,
        "rows": rows,
        "log": log,
        "avg_waiting": round(sum(r["waiting"] for r in rows) / n, 2),
        "avg_turnaround": round(sum(r["turnaround"] for r in rows) / n, 2),
        "avg_response": round(sum(r["response"] for r in rows) / n, 2),
    }


def _names(ps):
    return "[" + ", ".join(p.pid for p in ps) + "]"


# --------------------------------------------------------------------------- #
# Non-preemptive algorithms: one event loop, they differ only in the pick key  #
# --------------------------------------------------------------------------- #
def _non_preemptive(procs, key, algorithm, why):
    procs = _fresh(procs)
    pending = sorted(procs, key=lambda p: (p.arrival, p.order))
    ready, gantt, log, time = [], [], [], 0
    while pending or ready:
        while pending and pending[0].arrival <= time:
            ready.append(pending.pop(0))
        if not ready:
            nxt = pending[0].arrival
            _append(gantt, "idle", time, nxt)
            log.append(f"t={time}: no process has arrived, CPU idle until t={nxt}")
            time = nxt
            continue
        ready.sort(key=key)
        cur = ready.pop(0)
        if len(ready) > 0:
            log.append(f"t={time}: ready {_names([cur] + ready)} -> run {cur.pid} ({why(cur)})")
        else:
            log.append(f"t={time}: only {cur.pid} is ready -> run {cur.pid}")
        cur.start = time
        _append(gantt, cur.pid, time, time + cur.burst)
        time += cur.burst
        cur.remaining = 0
        cur.completion = time
        log.append(f"t={time}: {cur.pid} completes")
    return procs, gantt, log


def fcfs(procs):
    out = _non_preemptive(procs, key=lambda p: (p.arrival, p.order), algorithm="fcfs",
                          why=lambda p: f"earliest arrival, t={p.arrival}")
    return _summarise(*out, "fcfs")


def sjf(procs, preemptive=False):
    if preemptive:
        return _preemptive(procs, key=lambda p: (p.remaining, p.arrival, p.order),
                           algorithm="srtf", label="remaining")
    out = _non_preemptive(procs, key=lambda p: (p.burst, p.arrival, p.order), algorithm="sjf",
                          why=lambda p: f"shortest burst = {p.burst}")
    return _summarise(*out, "sjf")


def priority_scheduling(procs, preemptive=False):
    if preemptive:
        return _preemptive(procs, key=lambda p: (p.priority, p.arrival, p.order),
                           algorithm="priority_p", label="priority")
    out = _non_preemptive(procs, key=lambda p: (p.priority, p.arrival, p.order),
                          algorithm="priority",
                          why=lambda p: f"highest priority = {p.priority}, lower number wins")
    return _summarise(*out, "priority")


# --------------------------------------------------------------------------- #
# Preemptive SJF (SRTF) and preemptive Priority: evaluated one time unit at a  #
# time, so a newly arrived process can take the CPU at any instant.            #
# --------------------------------------------------------------------------- #
def _preemptive(procs, key, algorithm, label):
    procs = _fresh(procs)
    n, done, time = len(procs), 0, 0
    gantt, log, running = [], [], None
    while done < n:
        ready = [p for p in procs if p.arrival <= time and p.remaining > 0]
        if not ready:
            nxt = min(p.arrival for p in procs if p.remaining > 0)
            _append(gantt, "idle", time, nxt)
            log.append(f"t={time}: no process has arrived, CPU idle until t={nxt}")
            time, running = nxt, None
            continue
        # The running process keeps the CPU on a tie: preempt only for a strictly better key.
        best = min(ready, key=key)
        if running is not None and running.remaining > 0 and running in ready:
            if key(best)[0] >= key(running)[0]:
                best = running
        if best is not running:
            value = best.remaining if label == "remaining" else best.priority
            if running is not None and running.remaining > 0:
                log.append(f"t={time}: {best.pid} ({label} {value}) preempts {running.pid} "
                           f"({label} {running.remaining if label == 'remaining' else running.priority})")
            else:
                log.append(f"t={time}: ready {_names(sorted(ready, key=key))} -> run {best.pid} "
                           f"(lowest {label} = {value})")
        if best.start is None:
            best.start = time
        _append(gantt, best.pid, time, time + 1)
        best.remaining -= 1
        time += 1
        running = best
        if best.remaining == 0:
            best.completion = time
            done += 1
            log.append(f"t={time}: {best.pid} completes")
            running = None
    return _summarise(procs, gantt, log, algorithm)


# --------------------------------------------------------------------------- #
# Round Robin                                                                  #
# --------------------------------------------------------------------------- #
def round_robin(procs, quantum):
    """FIFO ready queue; arrivals during a slice are enqueued before the
    preempted process rejoins the back of the queue."""
    if quantum <= 0:
        raise ValueError("time quantum must be positive")
    procs = _fresh(procs)
    order = sorted(procs, key=lambda p: (p.arrival, p.order))
    queue, gantt, log = deque(), [], []
    time, done, i, n = 0, 0, 0, len(order)
    while done < n:
        while i < n and order[i].arrival <= time:
            queue.append(order[i]); i += 1
        if not queue:
            _append(gantt, "idle", time, order[i].arrival)
            log.append(f"t={time}: ready queue empty, CPU idle until t={order[i].arrival}")
            time = order[i].arrival
            continue
        cur = queue.popleft()
        if cur.start is None:
            cur.start = time
        span = min(quantum, cur.remaining)
        if not queue and i == n and cur.remaining > quantum:
            # Nobody else will ever be ready: it gets quantum after quantum with no switch.
            log.append(f"t={time}: only {cur.pid} is left, so it gets every quantum and runs its "
                       f"remaining {cur.remaining} unit(s) to t={time + cur.remaining}")
            _append(gantt, cur.pid, time, time + cur.remaining)
            time += cur.remaining
            cur.remaining = 0
            cur.completion = time
            done += 1
            log.append(f"t={time}: {cur.pid} completes")
            continue
        log.append(f"t={time}: queue {_names([cur] + list(queue))} -> {cur.pid} runs "
                   f"{span} unit(s) (remaining {cur.remaining})")
        _append(gantt, cur.pid, time, time + span)
        time += span
        cur.remaining -= span
        arrived = []
        while i < n and order[i].arrival <= time:  # arrivals during the slice
            queue.append(order[i]); arrived.append(order[i]); i += 1
        if arrived:
            log.append(f"t={time}: {_names(arrived)} arrived during the slice and join the queue first")
        if cur.remaining > 0:
            queue.append(cur)
            log.append(f"t={time}: quantum expires, {cur.pid} goes to the back "
                       f"(remaining {cur.remaining})")
        else:
            cur.completion = time
            done += 1
            log.append(f"t={time}: {cur.pid} completes")
    return _summarise(procs, gantt, log, "rr", quantum)


# --------------------------------------------------------------------------- #
def solve(algorithm, procs, quantum=None):
    """Single entry point used by the router, the dataset tools and the UI."""
    algorithm = algorithm.lower()
    if algorithm == "fcfs":
        return fcfs(procs)
    if algorithm == "sjf":
        return sjf(procs, preemptive=False)
    if algorithm == "srtf":
        return sjf(procs, preemptive=True)
    if algorithm == "priority":
        return priority_scheduling(procs, preemptive=False)
    if algorithm == "priority_p":
        return priority_scheduling(procs, preemptive=True)
    if algorithm == "rr":
        if not quantum:
            raise ValueError("Round Robin needs a time quantum")
        return round_robin(procs, quantum)
    raise ValueError(f"unknown algorithm {algorithm!r}")


def gantt_text(gantt):
    """| P1 | P2 | ...  with the time line underneath."""
    top = "|" + "|".join(f" {pid} " for pid, _, _ in gantt) + "|"
    times = [str(gantt[0][1])]
    line = times[0]
    for (pid, s, e) in gantt:
        width = len(f" {pid} ") + 1
        line += str(e).rjust(width)
    return top + "\n" + line


def table_text(result):
    head = "| Process | Arrival | Burst |" + (" Priority |" if result["algorithm"].startswith("priority") else "")
    head += " Completion | Turnaround | Waiting | Response |"
    sep = "|" + "---|" * (head.count("|") - 1)
    lines = [head, sep]
    for r in result["rows"]:
        line = f"| {r['pid']} | {r['arrival']} | {r['burst']} |"
        if result["algorithm"].startswith("priority"):
            line += f" {r['priority']} |"
        line += f" {r['completion']} | {r['turnaround']} | {r['waiting']} | {r['response']} |"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    demo = [Process("P1", 0, 24), Process("P2", 0, 3), Process("P3", 0, 3)]
    res = round_robin(demo, 4)
    print(gantt_text(res["gantt"]))
    print(table_text(res))
    print("average waiting:", res["avg_waiting"])

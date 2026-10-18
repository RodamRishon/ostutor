"""Generate new practice problems with verified solutions (objective 7).

A problem is only handed out if
  1. the simulator solves it, and
  2. the router can parse the problem text back into exactly the same processes,
so the student is never given a question the tutor itself would misread.
"""
from __future__ import annotations

import random

from router import parse_processes
from scheduler import ALGORITHMS, Process, solve

ALGO_CHOICES = ["fcfs", "sjf", "srtf", "priority", "priority_p", "rr"]


def make_problem(algorithm=None, n=None, seed=None, all_at_zero=None):
    rng = random.Random(seed)
    algorithm = algorithm or rng.choice(ALGO_CHOICES)
    n = n or rng.randint(3, 5)
    if all_at_zero is None:
        all_at_zero = rng.random() < 0.3
    arrivals = [0] * n if all_at_zero else sorted([0] + [rng.randint(0, 8) for _ in range(n - 1)])
    bursts = [rng.randint(1, 10) for _ in range(n)]
    prios = rng.sample(range(1, n + 3), n) if algorithm.startswith("priority") else [0] * n
    procs = [Process(f"P{i+1}", arrivals[i], bursts[i], prios[i]) for i in range(n)]
    quantum = rng.choice([2, 3, 4]) if algorithm == "rr" else None
    return procs, algorithm, quantum


def problem_text(procs, algorithm, quantum=None):
    lines = [f"Schedule the following processes using {ALGORITHMS[algorithm]}"
             + (f" with time quantum {quantum}" if quantum else "") + "."]
    with_prio = algorithm.startswith("priority")
    lines.append("Process Arrival Burst" + (" Priority" if with_prio else ""))
    for p in procs:
        lines.append(f"{p.pid} {p.arrival} {p.burst}" + (f" {p.priority}" if with_prio else ""))
    if with_prio:
        lines.append("(A lower priority number means a higher priority.)")
    lines.append("Draw the Gantt chart and find the waiting and turnaround time of each process "
                 "and the averages.")
    return "\n".join(lines)


def verified_problem(algorithm=None, n=None, seed=None, all_at_zero=None, tries=20, quantum=None):
    """Return (problem_text, result, processes) for a problem that passed both checks."""
    for k in range(tries):
        procs, algo, q = make_problem(algorithm, n, None if seed is None else seed * 101 + k, all_at_zero)
        q = quantum or q
        text = problem_text(procs, algo, q)
        parsed, _ = parse_processes(text)
        same = [(p.pid, p.arrival, p.burst, p.priority) for p in parsed] == \
               [(p.pid, p.arrival, p.burst, p.priority) for p in procs]
        if not same:
            continue
        result = solve(algo, procs, q)
        return text, result, procs
    raise RuntimeError("could not generate a verifiable problem")

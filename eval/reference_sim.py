"""Independent reference scheduler for the evaluation suite.

Deliberately written differently from scheduler.py (that one is an event loop; this one advances the clock one
time unit at a time and keeps no shared code), so agreement between the two is evidence, not a tautology.

Conventions, identical to the ones documented in scheduler.py:
  * lower priority number = higher priority
  * ties: earlier arrival, then position in the input
  * preemptive algorithms preempt only for a STRICTLY better key; an equal key keeps the CPU
  * Round Robin: a process arriving at the instant a quantum expires is queued BEFORE the preempted process
  * context switches cost zero time
Processes are (pid, arrival, burst, priority) tuples.  Returns {pid: {"start", "completion"}} and the per-unit timeline.
"""


def simulate(algo, procs, quantum=None):
    n = len(procs)
    arr = {p[0]: p[1] for p in procs}
    left = {p[0]: p[2] for p in procs}
    pri = {p[0]: p[3] for p in procs}
    idx = {p[0]: i for i, p in enumerate(procs)}
    start, comp, timeline = {}, {}, []
    tie = lambda pid: (arr[pid], idx[pid])
    keyfun = {"fcfs": lambda q: (arr[q], idx[q]),
              "sjf": lambda q: (left[q],) + tie(q),            # left == burst until the process first runs
              "srtf": lambda q: (left[q],) + tie(q),
              "priority": lambda q: (pri[q],) + tie(q),
              "priority_p": lambda q: (pri[q],) + tie(q)}.get(algo)
    t, cur, queue, slice_used, enq = 0, None, [], 0, set()
    while len(comp) < n:
        arrived_now = sorted([q for q in left if left[q] > 0 and arr[q] <= t and q not in enq], key=tie)
        if algo == "rr":
            for q in arrived_now:
                queue.append(q); enq.add(q)
            if cur is not None and slice_used == quantum and left[cur] > 0:
                queue.append(cur); cur = None                  # quantum expired: back of the queue, after new arrivals
            if cur is None and queue:
                cur, slice_used = queue.pop(0), 0
        else:
            ready = [q for q in left if left[q] > 0 and arr[q] <= t]
            if cur is not None and left[cur] == 0:
                cur = None
            if ready:
                best = min(ready, key=keyfun)
                if cur is None:
                    cur = best
                elif algo in ("srtf", "priority_p") and keyfun(best)[0] < keyfun(cur)[0]:
                    cur = best                                  # strictly better only
        if cur is None:
            timeline.append("idle"); t += 1
            continue
        start.setdefault(cur, t)
        timeline.append(cur)
        left[cur] -= 1; slice_used += 1; t += 1
        if left[cur] == 0:
            comp[cur] = t
            cur = None
    out = {q: {"start": start[q], "completion": comp[q]} for q in left}
    return out, timeline


def metrics(algo, procs, quantum=None):
    """Per-process and average metrics + utilisation and throughput from the reference run."""
    res, timeline = simulate(algo, procs, quantum)
    rows = {}
    for pid, a, b, _ in procs:
        ct = res[pid]["completion"]
        rows[pid] = {"completion": ct, "turnaround": ct - a, "waiting": ct - a - b, "response": res[pid]["start"] - a,
                     "start": res[pid]["start"]}
    n = len(procs)
    avg = lambda k: sum(r[k] for r in rows.values()) / n
    span = len(timeline)
    return {"rows": rows, "avg_waiting": avg("waiting"), "avg_turnaround": avg("turnaround"), "avg_response": avg("response"),
            "utilisation": 100 * sum(1 for x in timeline if x != "idle") / span, "throughput": n / span,
            "timeline": timeline}


def runs(timeline):
    """Timeline -> merged Gantt segments [(pid, start, end)], idle included."""
    out = []
    for t, pid in enumerate(timeline):
        if out and out[-1][0] == pid and out[-1][2] == t:
            out[-1] = (pid, out[-1][1], t + 1)
        else:
            out.append((pid, t, t + 1))
    return out

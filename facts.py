"""Structured facts about each scheduling algorithm.

One table, three uses:
  * every pairwise comparison ("Compare SJF and Round Robin") is generated from it, so all
    15 pairs are covered and none contradicts another;
  * per-algorithm aspect answers (ties, new arrivals, implementation, best use ...) are generated from it;
  * both are written to corpus/notes/algorithm_facts_generated.md so retrieval can find them,
    and they become training data grounded in that same text.

Conventions: lower priority number = higher priority; ties broken by arrival time, then process number.
"""
from __future__ import annotations

import itertools
import pathlib

ROOT = pathlib.Path(__file__).parent

FACTS = {
    "fcfs": dict(
        name="First Come First Served (FCFS)", short="FCFS",
        rule="runs the ready process that arrived first, strictly in arrival order",
        preempt="non-preemptive: a running process keeps the CPU until it finishes or blocks for I/O",
        preemptive=False,
        starvation="does not normally starve a process, because every process eventually reaches the head of the FIFO queue as long as the processes ahead of it terminate (a long wait behind a long job is the convoy effect, not starvation)",
        wait="often long and very sensitive to the order of arrival",
        response="equal to the waiting time, which can be very long when a long job is ahead (the convoy effect)",
        overhead="the lowest, because there is no preemption",
        arrival="A newly arrived process joins the tail of the ready queue and never interrupts the running process.",
        ties="If two processes arrive at the same time, the one that comes first in the process list (the lower process number) runs first.",
        burst="FCFS does not need to know burst times at all.",
        impl="FCFS needs only a simple FIFO queue: enqueue at the tail, dequeue from the head, so each decision takes constant time.",
        use="simple batch systems where jobs are not interactive and low overhead matters",
        best_for="Batch workloads with no interactivity requirement.",
    ),
    "sjf": dict(
        name="Shortest Job First (SJF, non-preemptive)", short="SJF",
        rule="picks, among the processes that have arrived, the one with the smallest burst time and runs it to completion",
        preempt="non-preemptive: once a process starts, it finishes its burst even if a shorter job arrives",
        preemptive=False,
        starvation="can starve long jobs if shorter jobs keep arriving",
        wait="the minimum among non-preemptive algorithms",
        response="equal to the waiting time; short jobs start quickly but a long job may wait a long time",
        overhead="low, because there is no preemption",
        arrival="A newly arrived process, even a shorter one, must wait until the running process finishes its burst.",
        ties="If two processes have the same burst time, the one that arrived earlier runs first, and then the one with the lower process number.",
        burst="SJF needs the next CPU burst length in advance, which in practice must be predicted, for example with an exponential average of past bursts.",
        impl="SJF can be implemented with a min-heap (priority queue) keyed on burst time, so each decision takes O(log n).",
        use="batch systems where run times are known or can be estimated well",
        best_for="Batch workloads with known or predictable run times, when low average waiting time matters.",
    ),
    "srtf": dict(
        name="Shortest Remaining Time First (SRTF, preemptive SJF)", short="SRTF",
        rule="always runs the arrived process with the smallest remaining burst time",
        preempt="preemptive: a newly arrived process with a shorter remaining time takes the CPU at once",
        preemptive=True,
        starvation="can starve long jobs, even more easily than SJF, because a long job can also be preempted repeatedly",
        wait="the lowest of all the standard algorithms",
        response="very good for short jobs, which start almost immediately, but poor for long ones",
        overhead="higher than SJF, because every preemption is a context switch",
        arrival="A newly arrived process preempts the running one if its burst is strictly less than the running process's remaining time; with an equal value the running process keeps the CPU.",
        ties="If remaining times are equal, the running process keeps the CPU; otherwise the one that arrived earlier, then the lower process number, runs.",
        burst="SRTF needs the burst lengths in advance, so they must be known or predicted.",
        impl="SRTF can be implemented with a min-heap keyed on remaining time that is re-evaluated at every arrival, so each decision takes O(log n).",
        use="systems where burst lengths can be estimated accurately and a low average waiting time is the main goal",
        best_for="Workloads with accurate burst estimates where the lowest average waiting time is the goal.",
    ),
    "priority": dict(
        name="Priority scheduling (non-preemptive)", short="non-preemptive Priority",
        rule="picks, among the processes that have arrived, the one with the highest priority (the lowest priority number) and runs it to completion",
        preempt="non-preemptive: a higher-priority arrival waits until the running process finishes",
        preemptive=False,
        starvation="can starve low-priority processes if higher-priority ones keep arriving, which aging fixes",
        wait="not minimised; it depends on how the priorities are assigned",
        response="equal to the waiting time; high-priority work starts first, low-priority work may wait a long time",
        overhead="low, because there is no preemption",
        arrival="A newly arrived process, even with a higher priority, waits until the running process finishes its burst.",
        ties="Processes with equal priority are served in FCFS order: earlier arrival first, then the lower process number.",
        burst="Priority scheduling needs a priority value for every process, but not the burst length.",
        impl="Priority scheduling can be implemented with a priority queue (min-heap on the priority number), so each decision takes O(log n).",
        use="systems where processes differ in importance and switching must stay cheap",
        best_for="Systems where some processes are clearly more important than others.",
    ),
    "priority_p": dict(
        name="Priority scheduling (preemptive)", short="preemptive Priority",
        rule="always runs the arrived process with the highest priority (the lowest priority number)",
        preempt="preemptive: a newly arrived process with a strictly higher priority takes the CPU immediately",
        preemptive=True,
        starvation="can starve low-priority processes, which aging fixes",
        wait="not minimised; it depends on how the priorities are assigned",
        response="very good for high-priority processes and poor for low-priority ones",
        overhead="higher than non-preemptive Priority, because every preemption is a context switch",
        arrival="A newly arrived process preempts the running one only if its priority is strictly higher; an equal priority does not preempt.",
        ties="Processes with equal priority are served in FCFS order, and an arrival with an equal priority does not preempt the running process.",
        burst="Preemptive Priority scheduling needs a priority value for every process, but not the burst length.",
        impl="Preemptive Priority scheduling can be implemented with a priority queue (min-heap on the priority number) that is re-checked at every arrival, so each decision takes O(log n).",
        use="systems with urgent processes that must run immediately, such as interactive or real-time work",
        best_for="Systems with urgent processes that must not wait.",
    ),
    "rr": dict(
        name="Round Robin (RR)", short="Round Robin",
        rule="serves a circular FIFO ready queue and gives each process at most one time quantum before moving it to the tail",
        preempt="preemptive: a timer interrupt takes the CPU when the quantum expires",
        preemptive=True,
        starvation="does not starve a ready process under standard assumptions (a finite quantum and a finite ready queue), because every process gets the CPU within (n − 1) × q time units",
        wait="usually higher than SJF, but bounded for each turn",
        response="short and predictable, because every process gets its first turn within (n − 1) × q time units",
        overhead="the highest, because it switches at every quantum expiry",
        arrival="A newly arrived process joins the tail of the ready queue; if it arrives during a slice, it enters the queue before the preempted process is put back.",
        ties="Processes that arrive at the same time enter the queue in process-number order, and a process that arrives exactly when a quantum expires enters the queue before the preempted process.",
        burst="Round Robin does not need to know burst times; it needs a time quantum.",
        impl="Round Robin needs a circular FIFO queue and a timer interrupt, so each decision takes constant time.",
        use="time-sharing and interactive systems where every user needs regular turns",
        best_for="Interactive time-sharing systems.",
    ),
}
ORDER = ["fcfs", "sjf", "srtf", "priority", "priority_p", "rr"]


def _cap(s):
    return s[0].upper() + s[1:]


def aspect_qas():
    """(title, answer) for facts that the hand-written notes do not already cover per algorithm."""
    out = []
    for k in ORDER:
        f = FACTS[k]
        n, sh = f["name"], f["short"]
        out += [
            (f"How does {sh} handle a newly arrived process?", f["arrival"]),
            (f"What happens in {sh} when two processes have the same arrival time or priority?", f["ties"]),
            (f"Does {sh} need to know the burst time in advance?", f["burst"]),
            (f"How is {sh} implemented, and what data structure does it use?", f["impl"]),
            (f"What is the response time behaviour of {sh}?",
             f"In {sh}, the response time is {f['response']}."),
            (f"What kind of system is {sh} best suited for?",
             f"{sh} is best suited to {f['use']}. {f['best_for']}"),
            (f"Summarise {sh} in a few lines.",
             f"{n} {f['rule']}. It is {f['preempt']}. On starvation, it {f['starvation']}. "
             f"Its average waiting time is {f['wait']}, and its context-switch overhead is {f['overhead']}."),
            (f"What is the effect of {sh} on average waiting time?",
             f"The average waiting time under {sh} is {f['wait']}."),
            (f"What is the context-switch overhead of {sh}?",
             f"{sh} has {f['overhead']} context-switch overhead. It is {f['preempt']}."),
        ]
    return out


def compare_answer(a, b):
    fa, fb = FACTS[a], FACTS[b]
    pa, pb = fa["preemptive"], fb["preemptive"]
    if pa == pb:
        pre = (f"Both are {'preemptive' if pa else 'non-preemptive'}.")
    else:
        pre = (f"{fa['short']} is {'preemptive' if pa else 'non-preemptive'}, whereas "
               f"{fb['short']} is {'preemptive' if pb else 'non-preemptive'}.")
    return (
        f"{fa['short']} and {fb['short']} differ in how they choose the next process and in what they cost. "
        f"{fa['short']} {fa['rule']}. {fb['short']} {fb['rule']}. {pre} "
        f"On starvation, {fa['short']} {fa['starvation']}, while {fb['short']} {fb['starvation']}. "
        f"Average waiting time under {fa['short']} is {fa['wait']}, while under {fb['short']} it is {fb['wait']}. "
        f"For context-switch overhead, {fa['short']} has {fa['overhead']}, and {fb['short']} has {fb['overhead']}. "
        f"Choose {fa['short']} for {fa['use']}; choose {fb['short']} for {fb['use']}.")


def compare_qas():
    out = []
    for a, b in itertools.combinations(ORDER, 2):
        out.append((f"Compare {FACTS[a]['short']} and {FACTS[b]['short']} in detail", compare_answer(a, b)))
    return out


def all_qas():
    return aspect_qas() + compare_qas()


def write_markdown(path=ROOT / "corpus" / "notes" / "algorithm_facts_generated.md"):
    lines = ["# Algorithm facts: per-algorithm aspects and all pairwise comparisons", "",
             "## Per-algorithm aspects", ""]
    for title, ans in aspect_qas():
        lines += [f"### {title}", "", ans, ""]
    lines += ["## All pairwise comparisons", ""]
    for title, ans in compare_qas():
        lines += [f"### {title}", "", ans, ""]
    pathlib.Path(path).write_text("\n".join(lines), encoding="utf-8")
    return len(aspect_qas()), len(compare_qas())


if __name__ == "__main__":
    a, c = write_markdown()
    print(f"wrote {a} aspect answers and {c} comparisons")

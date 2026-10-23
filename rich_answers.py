"""Structured answers (side-by-side tables) for the comparison questions students and exams ask most.

A paragraph is a poor format for "difference between X and Y": the reader needs the two sides next to each
other. Each entry here is hand-written, with every row following the course conventions, and is shown as a
table. The same content is also written to the notes as plain sentences so retrieval, the model and the
training data can use it.
"""
from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).parent

RICH = [
    dict(
        title="What is the difference between preemptive and non-preemptive scheduling?",
        aliases=["difference between preemptive and non-preemptive scheduling",
                 "preemptive vs non-preemptive scheduling", "compare preemptive and non-preemptive scheduling",
                 "preemptive and non-preemptive scheduling difference", "preemptive versus non preemptive"],
        summary=("Non-preemptive scheduling lets a process keep the CPU until it finishes its burst or blocks; "
                 "preemptive scheduling lets the operating system take the CPU away mid-burst (on a timer "
                 "interrupt or a more urgent arrival), which improves response time at the cost of more context switches."),
        columns=["Non-preemptive", "Preemptive"],
        rows=[
            ("Who controls the CPU", "The running process keeps it until it finishes its burst or blocks for I/O",
             "The operating system can take it away before the burst is finished"),
            ("When the scheduler runs", "Only when the running process finishes or blocks",
             "Also on a timer interrupt and when a more urgent process arrives"),
            ("Examples", "FCFS, SJF, Priority (non-preemptive version)",
             "Round Robin, SRTF, Priority (preemptive version)"),
            ("Response time", "Can be poor: one long process makes everyone else wait",
             "Better: short or urgent processes get the CPU sooner"),
            ("Context-switch overhead", "Low: a switch only happens when a process ends or blocks",
             "Higher: every preemption is a context switch"),
            ("Starvation", "FCFS cannot starve a process; SJF and Priority can starve long or low-priority ones",
             "Round Robin cannot starve a process; SRTF and preemptive Priority can"),
            ("Shared data", "Simpler: a process is not interrupted in the middle of updating shared data",
             "Needs care: a process can be interrupted while updating shared data, so synchronisation is required"),
            ("Best suited to", "Batch systems where low overhead matters", "Interactive, time-sharing and real-time systems"),
        ],
        tip="Priority scheduling can be either: it is non-preemptive if a higher-priority arrival must wait, preemptive if it takes the CPU at once.",
    ),
    dict(
        title="Compare FCFS, SJF, SRTF, Priority and Round Robin in a table",
        aliases=["compare fcfs sjf priority and round robin", "compare all scheduling algorithms",
                 "compare all cpu scheduling algorithms", "compare the cpu scheduling algorithms",
                 "comparison of scheduling algorithms", "compare fcfs sjf srtf priority round robin",
                 "scheduling algorithms comparison table", "differences between fcfs sjf priority rr"],
        summary=("The algorithms differ in how they pick the next process, whether they preempt, whether they can "
                 "starve a process, and what they cost: SJF/SRTF minimise average waiting time, Round Robin gives the "
                 "best response time, FCFS is the simplest, and Priority serves important work first."),
        columns=["FCFS", "SJF", "SRTF", "Priority", "Round Robin"],
        rows=[
            ("Picks next", "Earliest arrival", "Smallest burst", "Smallest remaining time",
             "Highest priority (lowest number)", "Next in a circular queue, one quantum each"),
            ("Preemptive?", "No", "No", "Yes", "Either", "Yes"),
            ("Starvation", "No", "Long jobs can starve", "Long jobs can starve", "Low priority can starve (aging fixes it)", "No"),
            ("Average waiting time", "Often long; depends on arrival order", "Minimum among non-preemptive",
             "Lowest overall", "Depends on the priorities", "Usually higher than SJF"),
            ("Needs burst times?", "No", "Yes (or a prediction)", "Yes (or a prediction)", "No (needs priorities)", "No (needs a quantum)"),
            ("Overhead", "Lowest", "Low", "Higher", "Low (preemptive: higher)", "Highest"),
            ("Best for", "Simple batch", "Batch with known run times", "Known bursts, lowest waiting time",
             "Jobs of differing importance", "Interactive time-sharing"),
        ],
        tip="Tie-breaks: earlier arrival first, then the lower process number.",
    ),
    dict(
        title="What is the difference between waiting time, turnaround time and response time?",
        aliases=["difference between waiting time turnaround time and response time",
                 "waiting time vs turnaround time vs response time", "compare waiting turnaround and response time",
                 "waiting time turnaround time response time difference"],
        summary=("Turnaround time is the whole stay from arrival to completion, waiting time is the part of it spent in the "
                 "ready queue, and response time is only the wait until the first time on the CPU."),
        columns=["Waiting time", "Turnaround time", "Response time"],
        rows=[
            ("Measures", "Total time spent in the ready queue", "Total time from arrival to completion",
             "Time from arrival to the first time on the CPU"),
            ("Formula", "turnaround − burst", "completion − arrival", "first start − arrival"),
            ("Includes the running time?", "No", "Yes", "No"),
            ("Goal", "Minimise", "Minimise", "Minimise"),
            ("In non-preemptive algorithms", "Equals the response time", "Waiting time + burst time", "Equals the waiting time"),
            ("Relationship", "turnaround = waiting + burst", "Always at least the waiting time", "Never larger than the waiting time"),
        ],
        tip="Compute turnaround first, then waiting = turnaround − burst; read the first start off the Gantt chart for response.",
    ),
    dict(
        title="What is the difference between the long-term, medium-term and short-term scheduler?",
        aliases=["difference between long term medium term and short term scheduler", "types of schedulers",
                 "what are the types of schedulers", "long term vs short term scheduler",
                 "long-term medium-term short-term scheduler"],
        summary=("The long-term scheduler decides which jobs enter memory, the medium-term scheduler swaps processes out and "
                 "back in, and the short-term (CPU) scheduler picks the next ready process to run, very often."),
        columns=["Long-term (job)", "Medium-term", "Short-term (CPU)"],
        rows=[
            ("Role", "Admits jobs from the job pool into memory", "Swaps processes out of and back into memory",
             "Chooses which ready process gets the CPU next"),
            ("How often it runs", "Rarely (seconds to minutes)", "Occasionally", "Very often (every few milliseconds)"),
            ("What it controls", "The degree of multiprogramming", "The degree of multiprogramming, by swapping to relieve memory",
             "Which process runs on the CPU"),
            ("Speed needed", "Can be slow", "Moderate", "Must be very fast"),
            ("Algorithms", "Not the usual exam algorithms", "Swapping policy", "FCFS, SJF, SRTF, Priority, Round Robin"),
        ],
        tip="FCFS, SJF, Priority and Round Robin are all short-term (CPU) scheduling algorithms.",
    ),
    dict(
        title="What is the difference between CPU-bound and I/O-bound processes?",
        aliases=["difference between cpu bound and io bound process", "cpu bound vs i/o bound processes",
                 "cpu-bound and io-bound processes", "compare cpu bound and i/o bound"],
        summary=("A CPU-bound process computes for long stretches with few I/O waits, while an I/O-bound process "
                 "uses the CPU in short bursts between frequent I/O waits."),
        columns=["CPU-bound", "I/O-bound"],
        rows=[
            ("Where it spends its time", "Computing on the CPU", "Waiting for input or output"),
            ("CPU bursts", "Few and long", "Many and short"),
            ("I/O bursts", "Few and short", "Many and long"),
            ("Effect on the CPU", "Keeps the CPU busy", "Often leaves the CPU idle while it waits"),
            ("Scheduling advice", "Gets a lower priority or a lower queue", "Should be favoured: it needs the CPU only briefly and keeps devices busy"),
        ],
        tip="A good scheduler favours I/O-bound processes slightly, which improves overall utilisation.",
    ),
    dict(
        title="What are the CPU scheduling criteria?",
        aliases=["cpu scheduling criteria", "scheduling criteria", "criteria for comparing scheduling algorithms",
                 "list the cpu scheduling criteria", "scheduling metrics"],
        summary="Scheduling algorithms are compared on five criteria: two to maximise (utilisation, throughput) and three to minimise (turnaround, waiting, response time).",
        columns=["Goal", "Meaning"],
        rows=[
            ("CPU utilisation", "Maximise", "Percentage of time the CPU is busy running processes"),
            ("Throughput", "Maximise", "Number of processes completed per unit of time"),
            ("Turnaround time", "Minimise", "Completion time − arrival time"),
            ("Waiting time", "Minimise", "Turnaround time − burst time (time in the ready queue)"),
            ("Response time", "Minimise", "First time on the CPU − arrival time"),
        ],
        tip="In exam numericals the comparison is usually on average waiting time and average turnaround time.",
    ),
]


def _cell(s):
    return str(s).replace("|", "/")


def to_markdown(entry, source=None):
    cols = entry["columns"]
    head = "| | " + " | ".join(f"**{c}**" for c in cols) + " |"
    sep = "|---" * (len(cols) + 1) + "|"
    lines = [f"### {entry['title']}", "", f"> 💡 **In short:** {entry['summary']}", "", head, sep]
    for row in entry["rows"]:
        lines.append(f"| **{_cell(row[0])}** | " + " | ".join(_cell(c) for c in row[1:]) + " |")
    if entry.get("tip"):
        lines += ["", f"**Remember:** {entry['tip']}"]
    if source:
        lines += ["", f"*Source: {source}*"]
    return re.sub(r"</?[a-zA-Z][^>\n]*>", "", "\n".join(lines))


def flat_text(entry):
    """The same content as plain sentences, for the notes the retriever and the training data read."""
    parts = [entry["summary"]]
    for row in entry["rows"]:
        label, cells = row[0], row[1:]
        # the CPU-criteria table has a different shape: (name, goal, meaning)
        cols = entry["columns"]
        if len(cells) == len(cols):
            parts.append(f"{label}: " + "; ".join(f"{c} - {v}" for c, v in zip(cols, cells)) + ".")
        else:
            parts.append(f"{label}: " + "; ".join(map(str, cells)) + ".")
    if entry.get("tip"):
        parts.append(entry["tip"])
    return " ".join(parts)


def find(question, canon_tokens, threshold=0.75):
    """The entry whose alias means the same as the question, or None."""
    q = canon_tokens(question)
    if not q:
        return None
    best = None
    for e in RICH:
        for alias in [e["title"]] + e["aliases"]:
            t = canon_tokens(alias)
            if t:
                j = len(q & t) / len(q | t)
                if j >= threshold and (best is None or j > best[0]):
                    best = (j, e)
    return best[1] if best else None


def write_markdown(path=ROOT / "corpus" / "notes" / "rich_answers_generated.md"):
    lines = ["# Comparison answers (also shown as tables in the app)", "", "## Key comparisons", ""]
    for e in RICH:
        lines += [f"### {e['title']}", "", flat_text(e), ""]
    pathlib.Path(path).write_text("\n".join(lines), encoding="utf-8")
    return len(RICH)


if __name__ == "__main__":
    print("wrote", write_markdown(), "comparison answers")

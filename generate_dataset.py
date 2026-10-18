"""Build every dataset file the project needs (report Section 4).

    data/raw/concepts.jsonl     hand-written concept / comparison / misconception records
    data/raw/numerical.jsonl    worked numerical solutions, generated AND verified by the simulator
    data/raw/practice.jsonl     practice-problem-generation records (problem + verified solution)
    data/sample_raw.jsonl       deliberately flawed sample used to prove the validation pipeline
    data/eval_set.jsonl         held-out evaluation set (30 numerical + 20 conceptual, + 5 out-of-scope)
                                built AFTER the training data and checked for zero overlap

Then run:  python prepare_dataset.py data/raw data/processed
"""
from __future__ import annotations

import json
import pathlib
import random

import hashlib

import facts
from dataset_extra import _norm, check_records, qa_from_md, focus_records, refusal_records, theory_records
from practice import make_problem, problem_text
from scheduler import ALGORITHMS, Process, solve

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data"

META_ALGO = {"fcfs": ("fcfs", False), "sjf": ("sjf", False), "srtf": ("sjf", True),
             "priority": ("priority", False), "priority_p": ("priority", True), "rr": ("rr", False)}

# Textbook examples (report Table 6) always included in the training data.
TEXTBOOK = [
    ("fcfs", None, [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]),
    ("sjf", None, [("P1", 0, 6, 0), ("P2", 0, 8, 0), ("P3", 0, 7, 0), ("P4", 0, 3, 0)]),
    ("srtf", None, [("P1", 0, 8, 0), ("P2", 1, 4, 0), ("P3", 2, 9, 0), ("P4", 3, 5, 0)]),
    ("rr", 4, [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]),
    ("priority", None, [("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 4), ("P4", 0, 1, 5), ("P5", 0, 5, 2)]),
]

INSTRUCTIONS = [
    "Solve this {name} problem and draw the Gantt chart",
    "Find the average waiting time and average turnaround time using {name}",
    "Using {name}, compute the waiting and turnaround time of each process",
    "Schedule these processes with {name} and explain each step",
    "Draw the Gantt chart for {name} and calculate the average waiting time",
]


def signature(algo, quantum, procs):
    return (algo, quantum, tuple((p.arrival, p.burst, p.priority) for p in procs))


def format_input(procs, algo, quantum, style):
    """The same problem written the different ways it appears in papers and lab sheets."""
    prio = algo.startswith("priority")
    q = f"Time quantum = {quantum}.\n" if quantum else ""
    if style == 0 or prio:
        rows = ["Process Arrival Burst" + (" Priority" if prio else "")]
        rows += [f"{p.pid} {p.arrival} {p.burst}" + (f" {p.priority}" if prio else "") for p in procs]
        return q + "\n".join(rows)
    if style == 1:
        return (q + "Burst times: " + ", ".join(str(p.burst) for p in procs) +
                "\nArrival times: " + ", ".join(str(p.arrival) for p in procs))
    return q + "; ".join(f"{p.pid}: arrival {p.arrival}, burst {p.burst}" for p in procs)


def worked_solution(result):
    """Tutor-style target output.  Every number in it comes from the simulator."""
    q = f" with time quantum {result['quantum']}" if result["quantum"] else ""
    out = [f"Let's solve this step by step using {result['algorithm_name']}{q}.", "",
           "Step 1 - scheduling decisions:"]
    out += [f"- {line}" for line in result["log"]]
    chart = ", ".join(f"{pid} {s}-{e}" for pid, s, e in result["gantt"])
    out += ["", f"Step 2 - Gantt chart: {chart}.", "",
            "Step 3 - times (turnaround = completion - arrival, waiting = turnaround - burst):"]
    for r in result["rows"]:
        out.append(f"- {r['pid']}: completion {r['completion']}, turnaround {r['completion']} - {r['arrival']} = "
                   f"{r['turnaround']}, waiting {r['turnaround']} - {r['burst']} = {r['waiting']}")
    n = len(result["rows"])
    w = " + ".join(str(r["waiting"]) for r in result["rows"])
    t = " + ".join(str(r["turnaround"]) for r in result["rows"])
    out += ["", f"Step 4 - averages: average waiting time = ({w}) / {n} = {result['avg_waiting']:.2f}, "
                f"average turnaround time = ({t}) / {n} = {result['avg_turnaround']:.2f}."]
    return "\n".join(out)


def numerical_record(algo, quantum, procs, rng, category="numerical"):
    result = solve(algo, procs, quantum)
    meta_algo, pre = META_ALGO[algo]
    return {
        "instruction": rng.choice(INSTRUCTIONS).format(name=ALGORITHMS[algo]),
        "input": format_input(procs, algo, quantum, rng.randint(0, 2)),
        "output": worked_solution(result),
        "category": category,
        "meta": {"algorithm": meta_algo, "preemptive": pre, "quantum": quantum,
                 "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs],
                 "expected_avg_waiting": result["avg_waiting"]},
    }


def practice_record(algo, procs, quantum):
    result = solve(algo, procs, quantum)
    meta_algo, pre = META_ALGO[algo]
    prio = " with priorities" if algo.startswith("priority") else ""
    if all(p.arrival == 0 for p in procs):
        arrivals = "all arriving at time 0"
    elif any(r[0] == "idle" for r in result["gantt"]):
        arrivals = "with staggered arrivals that leave the CPU idle at some point"
    else:
        arrivals = f"with staggered arrivals up to t={max(p.arrival for p in procs)}"
    return {
        "instruction": f"Generate a {ALGORITHMS[algo]} practice problem with {len(procs)} processes{prio}, "
                       f"{arrivals}" + (f", quantum {quantum}" if quantum else ""),
        "input": "",
        "output": "Here is a practice problem.\n\n" + problem_text(procs, algo, quantum) +
                  "\n\nTry it first, then check against the solution.\n\nSolution:\n" + worked_solution(result),
        "category": "practice",
        "meta": {"algorithm": meta_algo, "preemptive": pre, "quantum": quantum,
                 "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs],
                 "expected_avg_waiting": result["avg_waiting"]},
    }


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def build_training(n_numerical=100, n_practice=24, seed=7):
    rng = random.Random(seed)
    seen, numerical, practice = set(), [], []
    for algo, q, rows in TEXTBOOK:
        procs = [Process(*r) for r in rows]
        seen.add(signature(algo, q, procs))
        numerical.append(numerical_record(algo, q, procs, rng))
    algos = list(ALGORITHMS)
    k = 0
    while len(numerical) < n_numerical:
        procs, algo, q = make_problem(algos[k % len(algos)], seed=seed * 1000 + k)
        k += 1
        sig = signature(algo, q, procs)
        if sig in seen:
            continue
        seen.add(sig)
        numerical.append(numerical_record(algo, q, procs, rng))
    prompts = set()
    while len(practice) < n_practice:
        procs, algo, q = make_problem(algos[k % len(algos)], seed=seed * 1000 + k)
        k += 1
        sig = signature(algo, q, procs)
        rec = practice_record(algo, procs, q)
        if sig in seen or rec["instruction"] in prompts:   # one target per prompt
            continue
        seen.add(sig)
        prompts.add(rec["instruction"])
        practice.append(rec)
    return numerical, practice, seen


EVAL_CONCEPT = [
    ("What is the convoy effect?", "FCFS", ["convoy"]),
    ("Does Round Robin cause starvation?", "Round Robin", ["starvation"]),
    ("What is aging in priority scheduling?", "Priority", ["aging"]),
    ("How is the next CPU burst length predicted?", "SJF", ["exponential", "burst"]),
    ("What happens if the time quantum is very large in Round Robin?", "Round Robin", ["quantum", "fcfs"]),
    ("Why is SJF called optimal?", "SJF", ["optimal"]),
    ("What is the difference between SJF and SRTF?", "SJF", ["preempt"]),
    ("Define turnaround time.", "General", ["turnaround"]),
    ("What does the dispatcher do?", "General", ["dispatch"]),
    ("What is dispatch latency?", "General", ["latency"]),
    ("Why are context switches considered overhead?", "Context switch", ["context switch"]),
    ("What is starvation in priority scheduling?", "Priority", ["starvation"]),
    ("When does a non-preemptive scheduler make decisions?", "General", ["non-preemptive"]),
    ("What is a multilevel feedback queue?", "MLFQ", ["feedback"]),
    ("What is response time?", "General", ["response time"]),
    ("Which algorithm suits time-sharing systems?", "Round Robin", ["time-sharing"]),
    ("Is SJF a special case of priority scheduling?", "SJF", ["special case"]),
    ("How should the Round Robin time quantum be chosen?", "Round Robin", ["quantum", "context"]),
    ("What are the CPU scheduling criteria?", "General", ["throughput", "utili"]),
    ("Can FCFS cause starvation?", "FCFS", ["starvation"]),
]
EVAL_OUT_OF_SCOPE = [
    "What is the capital of France?",
    "How do I make pasta?",
    "Explain the TCP three-way handshake.",
    "What is the time complexity of quicksort?",
    "Who won the cricket world cup?",
]
EVAL_PHRASING = [
    "Using {name}{q}, find the average waiting time. {data}",
    "{data}\nApply {name}{q} and compute the average turnaround time.",
    "Calculate waiting time for each process with {name}{q}: {data}",
]
EVAL_NAMES = {"fcfs": ["FCFS", "first come first served"], "sjf": ["non-preemptive SJF", "shortest job first"],
              "srtf": ["SRTF", "preemptive SJF", "shortest remaining time first"],
              "priority": ["non-preemptive priority scheduling"], "priority_p": ["preemptive priority scheduling"],
              "rr": ["Round Robin", "RR"]}


def build_eval(train_signatures, seed=2024):
    rng = random.Random(seed)
    rows, k = [], 0
    algos = list(ALGORITHMS)
    while len(rows) < 30:
        algo = algos[len(rows) % len(algos)]
        procs, algo, q = make_problem(algo, seed=seed * 1000 + k)
        k += 1
        if signature(algo, q, procs) in train_signatures:
            continue                                   # never test on a training problem
        result = solve(algo, procs, q)
        data = format_input(procs, algo, None, rng.randint(0, 2)).replace("\n", "\n" if rng.random() < .5 else "; ")
        qtxt = f" with time quantum {q}" if q else ""
        question = rng.choice(EVAL_PHRASING).format(name=rng.choice(EVAL_NAMES[algo]), q=qtxt, data=data)
        rows.append({"id": f"num-{len(rows)+1:02d}", "type": "numerical", "question": question,
                     "expected_route": "numerical", "expected_algorithm": algo,
                     "expected_avg_waiting": result["avg_waiting"],
                     "expected_avg_turnaround": result["avg_turnaround"],
                     "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs], "quantum": q})
    for i, (question, topic, keywords) in enumerate(EVAL_CONCEPT, 1):
        rows.append({"id": f"con-{i:02d}", "type": "concept", "question": question,
                     "expected_route": "concept", "topic": topic, "keywords": keywords})
    for i, question in enumerate(EVAL_OUT_OF_SCOPE, 1):
        rows.append({"id": f"oos-{i:02d}", "type": "out_of_scope", "question": question,
                     "expected_route": "concept"})
    return rows


def build_sample():
    """Five records with exactly three planted problems (report Listing 5)."""
    rr = solve("rr", [Process("P1", 0, 24), Process("P2", 0, 3), Process("P3", 0, 3)], 4)
    return [
        {"instruction": "Explain why Round Robin has higher context-switch overhead", "input": "",
         "output": next(a for t, a, _ in qa_from_md(ROOT / "corpus" / "notes" / "analogies_and_doubts.md")
                       if t.startswith("Why does Round Robin have higher"))},
        {"instruction": "Explain why Round Robin has higher context switch overhead", "input": "",
         "output": "Duplicate of the record above apart from the hyphen, so it must be removed by deduplication."},
        {"instruction": "What is FCFS?", "input": "", "output": "First come first served."},
        {"instruction": "Solve this FCFS problem", "input": "P1=24, P2=3, P3=3 (all arrive at 0)",
         "output": "FCFS runs P1, P2, P3 in order. Waiting times are 0, 24 and 27 ... so the average waiting "
                   "time is 12.0 time units, which is the final answer for this problem.",
         "meta": {"algorithm": "fcfs", "processes": [["P1", 0, 24], ["P2", 0, 3], ["P3", 0, 3]],
                  "expected_avg_waiting": 12.0}},
        {"instruction": "Solve this Round Robin problem with quantum 4", "input": "P1=24, P2=3, P3=3",
         "output": worked_solution(rr),
         "meta": {"algorithm": "rr", "quantum": 4, "processes": [["P1", 0, 24], ["P2", 0, 3], ["P3", 0, 3]],
                  "expected_avg_waiting": rr["avg_waiting"]}},
    ]


def _group(rec):
    m = rec["meta"]
    return "prob-" + hashlib.md5(json.dumps([m["algorithm"], m.get("preemptive"), m.get("quantum"),
                                             m["processes"]]).encode()).hexdigest()[:10]


def held_out_prompts():
    """Every prompt used for evaluation: none of them may appear in the training data."""
    import evaluate_answers
    banned = {_norm(c[1]) for c in evaluate_answers.CASES}
    banned |= {_norm(q) for q, _, _ in EVAL_CONCEPT} | {_norm(q) for q in EVAL_OUT_OF_SCOPE}
    return banned


def main():
    raw = DATA / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for old in raw.glob("*.jsonl"):                  # no stale files, so nothing is counted twice
        old.unlink()
    n_asp, n_cmp = facts.write_markdown()
    theory = theory_records()
    banned = held_out_prompts()
    kept = [r for r in theory if _norm(r["instruction"]) not in banned]
    numerical, practice, seen = build_training(n_numerical=240, n_practice=40)
    for rec in numerical + practice:
        rec["group"] = _group(rec)
    focus = focus_records(260, 11, seen, format_input)
    checks = check_records(48, 13, seen)
    refusals = [r for r in refusal_records() if _norm(r["instruction"]) not in banned]
    write_jsonl(raw / "theory.jsonl", kept)
    write_jsonl(raw / "numerical.jsonl", numerical)
    write_jsonl(raw / "focus.jsonl", focus)
    write_jsonl(raw / "practice.jsonl", practice)
    write_jsonl(raw / "check.jsonl", checks)
    write_jsonl(raw / "refusal.jsonl", refusals)
    write_jsonl(DATA / "sample_raw.jsonl", build_sample())
    ev = build_eval(seen)
    write_jsonl(DATA / "eval_set.jsonl", ev)
    total = len(kept) + len(numerical) + len(focus) + len(practice) + len(checks) + len(refusals)
    print(f"generated facts                  : {n_asp} aspect answers, {n_cmp} pairwise comparisons")
    print(f"theory (concept/compare/doubt)   : {len(kept)}  ({len(theory) - len(kept)} dropped: held-out prompts)")
    print(f"numerical, full solutions        : {len(numerical)}")
    print(f"numerical, one-thing questions   : {len(focus)}")
    print(f"practice generation              : {len(practice)}")
    print(f"check-my-answer feedback         : {len(checks)}")
    print(f"off-topic refusals               : {len(refusals)}")
    print(f"total instruction records        : {total}")
    print(f"eval set                         : {sum(r['type'] == 'numerical' for r in ev)} numerical, "
          f"{sum(r['type'] == 'concept' for r in ev)} concept, "
          f"{sum(r['type'] == 'out_of_scope' for r in ev)} out-of-scope")


if __name__ == "__main__":
    main()

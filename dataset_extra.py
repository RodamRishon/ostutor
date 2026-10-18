"""Extra instruction-record generators (report Section 4.2), used by generate_dataset.py.

  theory_records()    every stored Q&A (hand-written notes, reference notes, generated facts), each in
                      its original wording plus one differently-phrased variant
  focus_records()     numerical questions that ask for ONE thing ("waiting time of P2", "Gantt chart only",
                      "how many context switches") answered exactly as asked, then shown working
  check_records()     "check my answer" feedback, built with the same checker the app uses
  refusal_records()   off-topic questions and the refusal the app gives

Everything numerical is produced by the simulator, and every record is re-verified by prepare_dataset.py.
"""
from __future__ import annotations

import hashlib
import random
import re

from checker import check_answer
from dataset_concepts import records as concept_records
from intent import SOURCE_TAG, direct_answer
from practice import make_problem, problem_text
from router import route
from scheduler import ALGORITHMS, Process, solve
import facts

import pathlib
ROOT = pathlib.Path(__file__).parent

META_ALGO = {"fcfs": ("fcfs", False), "sjf": ("sjf", False), "srtf": ("sjf", True),
             "priority": ("priority", False), "priority_p": ("priority", True), "rr": ("rr", False)}


def _norm(t):
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t.lower())).strip()


# --------------------------------------------------------------------------- theory
def qa_from_md(path):
    """[(title, answer, section)] for every '### question' in a notes file."""
    text = pathlib.Path(path).read_text(encoding="utf-8")
    out = []
    for block in re.split(r"^(?=##\s)", text, flags=re.MULTILINE):
        head = re.match(r"##\s+(.+)", block)
        if not head:
            continue
        for q, a in re.findall(r"^###\s+(.+?)\n\n(.+?)(?=\n\n###|\Z)", block, flags=re.MULTILINE | re.DOTALL):
            out.append((q.strip(), " ".join(SOURCE_TAG.sub("", a).split()), head.group(1)))
    return out


def _category(title, section):
    if title.startswith("A student says") or re.search(r"misconception|doubt", section, re.I):
        return "misconception"
    if title.startswith("Compare") or re.match(r"Compar", section) or "pairwise" in section.lower():
        return "comparison"
    return "concept"


def variants(title):
    """One alternative phrasing, chosen deterministically from the title."""
    t = title.strip()
    low = t[0].lower() + t[1:]
    opts = [lambda: f"{low.rstrip('?. ')} (answer in a few lines)",
            lambda: f"Answer for an exam: {t}",
            lambda: f"Please explain: {low}",
            lambda: f"Quick question: {low}"]
    if not t.startswith("A student says"):
        opts.append(lambda: f"In simple words, {low}")
    return opts[int(hashlib.md5(t.encode()).hexdigest(), 16) % len(opts)]()


def theory_records():
    sources = [(r["instruction"], r["output"], "concept-notes", r["category"]) for r in concept_records()]
    for fname in ("algorithm_reference.md", "algorithm_facts_generated.md"):
        for title, ans, section in qa_from_md(ROOT / "corpus" / "notes" / fname):
            sources.append((title, ans, section, _category(title, section)))
    out, seen = [], set()
    for title, ans, _, cat in sources:
        ans = " ".join(SOURCE_TAG.sub("", ans).split())
        if _norm(title) in seen:
            continue
        seen.add(_norm(title))
        for phrasing in (title, variants(title)):
            out.append({"instruction": phrasing, "input": "", "output": ans, "category": cat,
                        "group": _norm(title), "meta": {"source_title": title}})
    return out


# --------------------------------------------------------------------------- focused numerical
FOCUS = [
    ("pid", "What is the waiting time of {P}?"), ("pid", "Find the waiting time for {P}."),
    ("pid", "Give the turnaround time of {P}."), ("pid", "What is the turnaround time for {P}?"),
    ("pid", "What is the response time of {P}?"), ("pid", "Find the response time for {P}."),
    ("pid", "What is the completion time of {P}?"),
    ("pid2", "Find the waiting time of {P} and {Q}."), ("pid2", "Give the turnaround time of {P} and {Q}."),
    ("all", "Find the waiting time of each process."), ("all", "Find the turnaround time of each process."),
    ("all", "Give the response time of every process."),
    ("all", "What is the completion time of each process?"),
    ("none", "Calculate the average waiting time."), ("none", "What is the average waiting time?"),
    ("none", "What is the average turnaround time?"), ("none", "Find the average response time."),
    ("none", "Draw the Gantt chart only."), ("none", "Give only the Gantt chart."),
    ("none", "Which process finishes last?"), ("none", "Which process finishes first?"),
    ("none", "How many context switches occur?"), ("none", "What is the CPU utilization?"),
    ("none", "What is the throughput?"), ("none", "Which process has the longest waiting time?"),
]
INPUT_STYLES = (0, 1, 2)


def _quantum_text(q):
    return f" with time quantum {q}" if q else ""


def focus_working(question_text, result, pids):
    """Short working that supports the direct answer. Every number comes from the simulator."""
    rows = {r["pid"]: r for r in result["rows"]}
    low = question_text.lower()
    lines = ["Gantt chart: " + " | ".join(f"{p} {s}–{e}" for p, s, e in result["gantt"])]
    for pid in pids or []:
        r = rows[pid]
        if re.search(r"turn\s*-?around", low):
            lines.append(f"{pid}: turnaround = completion − arrival = {r['completion']} − {r['arrival']} = {r['turnaround']}")
        elif re.search(r"response", low):
            lines.append(f"{pid}: response = first start − arrival = {r['start']} − {r['arrival']} = {r['response']}")
        elif re.search(r"completion", low):
            lines.append(f"{pid}: completes at t = {r['completion']} (end of its last box on the chart)")
        else:
            lines.append(f"{pid}: waiting = turnaround − burst = ({r['completion']} − {r['arrival']}) − {r['burst']} = {r['waiting']}")
    if re.search(r"\b(average|avg|mean)\b", low):
        for key, label in (("waiting", "waiting"), ("turnaround", "turnaround"), ("response", "response")):
            if re.search(label if label != "turnaround" else r"turn\s*-?around", low):
                vals = " + ".join(str(r[key]) for r in result["rows"])
                lines.append(f"Average {label} time = ({vals}) / {len(rows)} = {result['avg_' + key]:.2f}")
    elif not pids and re.search(r"each process|every process", low):
        for r in result["rows"]:
            key = "turnaround" if re.search(r"turn\s*-?around", low) else "response" if "response" in low \
                else "completion" if "completion" in low else "waiting"
            lines.append(f"{r['pid']}: {key} = {r[key]}")
    if re.search(r"finish(es)? (first|last)|completes? (first|last)", low):
        order = sorted(result["rows"], key=lambda r: r["completion"])
        lines.append("Completion times: " + ", ".join(f"{r['pid']} = {r['completion']}" for r in order))
    if re.search(r"context[- ]switch", low):
        segs = [g for g in result["gantt"] if g[0] != "idle"]
        at = [b[1] for a, b in zip(segs, segs[1:]) if a[0] != b[0]]
        lines.append("The running process changes at t = " + (", ".join(map(str, at)) if at else "(never)"))
    if re.search(r"utili[sz]ation", low):
        busy = sum(e - s for p, s, e in result["gantt"] if p != "idle")
        lines.append(f"Busy time = {busy}, total elapsed time = {result['gantt'][-1][2] - result['gantt'][0][1]}")
    if re.search(r"throughput", low):
        lines.append(f"Completed processes = {len(rows)}, total elapsed time = {result['gantt'][-1][2]}")
    return "Working:\n" + "\n".join(f"- {l}" for l in lines)


def focus_records(n, seed, seen, format_input):
    rng = random.Random(seed)
    algos = list(ALGORITHMS)
    out, k, guard = [], 0, 0
    while len(out) < n and guard < n * 40:
        guard += 1
        algo = algos[k % len(algos)]
        procs, algo, q = make_problem(algo, n=rng.randint(3, 6), seed=seed * 7919 + guard)
        sig = (algo, q, tuple((p.arrival, p.burst, p.priority) for p in procs))
        if sig in seen:
            continue
        kind, tmpl = FOCUS[(len(out) + rng.randint(0, 3)) % len(FOCUS)]
        pids = [p.pid for p in rng.sample(procs, 2)] if kind == "pid2" else \
               [rng.choice(procs).pid] if kind == "pid" else []
        question = tmpl.format(P=pids[0] if pids else "", Q=pids[1] if len(pids) > 1 else "")
        instruction = f"{question} Use {ALGORITHMS[algo]}{_quantum_text(q)}."
        inp = format_input(procs, algo, None, rng.choice(INPUT_STYLES))
        text = instruction + "\n" + inp
        r = route(text)                                  # the app must read this exactly as intended
        if (r.kind != "numerical" or r.algorithm != algo or (r.quantum or None) != (q or None)
                or [(p.pid, p.arrival, p.burst, p.priority) for p in r.processes]
                != [(p.pid, p.arrival, p.burst, p.priority) for p in procs]):
            continue
        result = solve(algo, procs, q)
        direct = direct_answer(text, result)
        if not direct:
            continue
        seen.add(sig)
        k += 1
        meta_algo, pre = META_ALGO[algo]
        out.append({"instruction": instruction, "input": inp, "category": "numerical",
                    "output": direct + "\n\n" + focus_working(question, result, pids),
                    "group": "focus-" + hashlib.md5(repr(sig).encode()).hexdigest()[:10],
                    "meta": {"algorithm": meta_algo, "preemptive": pre, "quantum": q, "direct": True,
                             "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs],
                             "expected_avg_waiting": result["avg_waiting"]}})
    return out


# --------------------------------------------------------------------------- check my answer
def _gantt_text(g):
    return ", ".join(f"{p} {s}-{e}" for p, s, e in g)


def check_records(n, seed, seen):
    rng = random.Random(seed)
    algos = list(ALGORITHMS)
    out, guard = [], 0
    while len(out) < n and guard < n * 60:
        guard += 1
        procs, algo, q = make_problem(algos[guard % len(algos)], n=rng.randint(3, 5), seed=seed * 104729 + guard)
        sig = (algo, q, tuple((p.arrival, p.burst, p.priority) for p in procs))
        if sig in seen:
            continue
        result = solve(algo, procs, q)
        mode = ["correct", "wrong_avg", "wrong_wait", "wrong_gantt"][len(out) % 4]
        wait = {r["pid"]: r["waiting"] for r in result["rows"]}
        gantt, avg = result["gantt"], result["avg_waiting"]
        if mode == "wrong_avg":
            avg = round(avg + rng.choice([-1.5, -0.5, 0.5, 1, 2]), 2)
            if avg < 0:
                continue
        elif mode == "wrong_wait":
            victim = rng.choice(list(wait))
            wait[victim] += rng.choice([1, 2, -1]) if wait[victim] > 0 else 1
            avg = round(sum(wait.values()) / len(wait), 2)
        elif mode == "wrong_gantt":
            other = solve("fcfs" if algo != "fcfs" else "sjf", procs, q)
            if other["gantt"] == result["gantt"]:
                continue
            gantt = other["gantt"]
        student = (f"Gantt: {_gantt_text(gantt)}. waiting " + ", ".join(f"{p}={w}" for p, w in wait.items())
                   + f". average waiting = {avg:g}")
        verdict = check_answer(result, student)
        if verdict["correct"] != (mode == "correct"):
            continue
        seen.add(sig)
        reply = ("✅ Your answer matches the simulator." if verdict["correct"] else
                 "❌ Not quite. " + (verdict["first_error"] or "")) + "\n\n" + \
                "\n".join(f"- {f}" for f in verdict["findings"])
        meta_algo, pre = META_ALGO[algo]
        out.append({"instruction": "Check my answer.", "category": "check", "output": reply,
                    "input": problem_text(procs, algo, q) + "\nMy answer: " + student,
                    "group": "check-" + hashlib.md5(repr(sig).encode()).hexdigest()[:10],
                    "meta": {"algorithm": meta_algo, "preemptive": pre, "quantum": q, "check": True,
                             "student": student, "skip_avg": True,
                             "processes": [[p.pid, p.arrival, p.burst, p.priority] for p in procs],
                             "expected_avg_waiting": result["avg_waiting"]}})
    return out


# --------------------------------------------------------------------------- refusals
REFUSAL = ("I can only answer questions about CPU scheduling from the course material, and I couldn't find "
           "anything relevant to that in my knowledge base. Try asking about FCFS, SJF/SRTF, Priority, "
           "Round Robin, or paste a scheduling problem to solve.")
OFF_TOPIC = [
    "What is the capital of Germany?", "Write a Python function to sort a list.", "Explain how paging works.",
    "What is a deadlock and how can it be prevented?", "Who won the last football world cup?",
    "How do I bake a chocolate cake?", "Explain the TCP three-way handshake.", "What is the time complexity of binary search?",
    "Tell me a joke.", "What is machine learning?", "Describe how virtual memory works.", "How do I install Linux?",
    "What is the boiling point of water?", "Translate 'hello' into French.", "Explain the OSI model.",
    "What are the symptoms of the flu?", "How does a hash table work?", "Recommend a good movie.",
    "What is the difference between a stack and a queue?", "Explain SQL joins.", "How does a file system store data?",
    "What is a semaphore?", "Explain the page replacement algorithm LRU.", "Who is the president of the USA?",
    "Solve x squared plus 5x plus 6 equals 0.", "What is the speed of light?", "Explain the producer consumer problem.",
    "How do I center a div in CSS?", "What is cloud computing?", "Write a poem about the sea.",
]


def refusal_records():
    return [{"instruction": q, "input": "", "output": REFUSAL, "category": "refusal", "group": "refusal-" + _norm(q)}
            for q in OFF_TOPIC]

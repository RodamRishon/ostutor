"""Evaluate the tutor on the held-out set (report Section 4.3, objective 8).

Metrics
  router accuracy        route (numerical / concept) and algorithm detected correctly
  numerical accuracy     average waiting AND turnaround match the reference to 0.01
  retrieval hit@3        the top-3 chunks contain the question's key terms
  out-of-scope refusal   off-topic questions are declined instead of answered

Optional baseline: --baseline MODEL asks a plain Ollama model (no retrieval, no
simulator) the same numerical questions and scores its stated average waiting time.

    python evaluate.py
    python evaluate.py --baseline qwen3:4b
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re

from router import route
from scheduler import solve
from tutor import Tutor, ollama_chat

ROOT = pathlib.Path(__file__).parent


def load_eval(path=ROOT / "data" / "eval_set.jsonl"):
    return [json.loads(line) for line in pathlib.Path(path).read_text().splitlines() if line.strip()]


def baseline_avg_waiting(model, question):
    text = ollama_chat(model, question + "\nGive the final average waiting time as a number.", timeout=180)
    m = list(re.finditer(r"average\s+waiting[^\d\n]{0,60}?(\d+(?:\.\d+)?)", text, re.I))
    return float(m[-1].group(1)) if m else None


def run(baseline=None, verbose=False):
    rows = load_eval()
    tutor = Tutor(use_llm=False)          # deterministic: scores the pipeline, not LLM prose
    res = {"router": [0, 0], "algorithm": [0, 0], "numerical": [0, 0], "retrieval": [0, 0],
           "refusal": [0, 0], "concept_answered": [0, 0], "failures": []}
    for r in rows:
        rt = route(r["question"])
        ok_route = rt.kind == r["expected_route"]
        res["router"][0] += ok_route
        res["router"][1] += 1
        if r["type"] == "numerical":
            res["algorithm"][0] += rt.algorithm == r["expected_algorithm"]
            res["algorithm"][1] += 1
            ok = False
            if ok_route and rt.processes:
                out = solve(rt.algorithm, rt.processes, rt.quantum)
                ok = (abs(out["avg_waiting"] - r["expected_avg_waiting"]) <= 0.01 and
                      abs(out["avg_turnaround"] - r["expected_avg_turnaround"]) <= 0.01)
            res["numerical"][0] += ok
            res["numerical"][1] += 1
            if not ok:
                res["failures"].append(f"{r['id']}: parsed {rt.kind}/{rt.algorithm}/{rt.quantum} "
                                       f"{[(p.pid, p.arrival, p.burst, p.priority) for p in rt.processes]}")
        elif r["type"] == "concept":
            hits = tutor.retriever.search(r["question"], algorithm=rt.topic)
            blob = " ".join(h["text"].lower() for h in hits)
            hit = all(k.lower() in blob for k in r["keywords"])
            res["retrieval"][0] += hit
            res["retrieval"][1] += 1
            answered = tutor.answer(r["question"])["in_scope"]
            res["concept_answered"][0] += answered
            res["concept_answered"][1] += 1
            if not hit:
                res["failures"].append(f"{r['id']}: top-3 missing {r['keywords']} for {r['question']!r}")
            if not answered:
                res["failures"].append(f"{r['id']}: wrongly refused {r['question']!r}")
        else:
            refused = not tutor.answer(r["question"])["in_scope"]
            res["refusal"][0] += refused
            res["refusal"][1] += 1
            if not refused:
                res["failures"].append(f"{r['id']}: answered off-topic {r['question']!r}")

    if baseline:
        correct = 0
        nums = [r for r in rows if r["type"] == "numerical"]
        for i, r in enumerate(nums, 1):
            try:
                got = baseline_avg_waiting(baseline, r["question"])
            except Exception as e:
                got = None
                print(f"  baseline error on {r['id']}: {e}")
            correct += got is not None and abs(got - r["expected_avg_waiting"]) <= 0.01
            if verbose:
                print(f"  baseline {i}/{len(nums)}: got {got}, expected {r['expected_avg_waiting']}")
        res["baseline"] = {"model": baseline, "numerical": [correct, len(nums)]}

    def pct(k):
        a, b = res[k]
        return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"

    summary = {
        "Router accuracy (route)": pct("router"),
        "Algorithm detection (numerical)": pct("algorithm"),
        "Numerical accuracy (tutor + simulator)": pct("numerical"),
        "Retrieval hit@3 (concept)": pct("retrieval"),
        "Concept questions answered": pct("concept_answered"),
        "Out-of-scope refusal": pct("refusal"),
    }
    if baseline:
        a, b = res["baseline"]["numerical"]
        summary[f"Baseline {baseline}, no tools (numerical)"] = f"{a}/{b} ({100 * a / b:.0f}%)"
    res["summary"] = summary
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "eval_results.json").write_text(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", help="Ollama model to use as a no-tools baseline, e.g. qwen3:4b")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    res = run(args.baseline, args.verbose)
    width = max(len(k) for k in res["summary"])
    for k, v in res["summary"].items():
        print(f"{k:<{width}}  {v}")
    if res["failures"]:
        print("\nmisses:")
        for f in res["failures"]:
            print("  " + f)
    print("\nsaved -> results/eval_results.json")

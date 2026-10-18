"""Validate and format the instruction dataset (report Section 5.3).

Four stages:
  1. schema check     - malformed JSON or missing fields are rejected
  2. deduplication    - normalised key, so "context-switch" and "context switch" collide
  3. quality filter   - answers that are too short or visibly truncated are removed
  4. numerical check  - every worked solution is recomputed by the simulator and
                        compared with the stated answer, so no wrong solution
                        can enter training

Then records are rendered into the Qwen chat format and split train / validation.

    python prepare_dataset.py data/sample_raw.jsonl out/
    python prepare_dataset.py data/raw/ data/processed/      # every .jsonl in a folder
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import sys

from scheduler import Process, fcfs, priority_scheduling, round_robin, sjf

REQUIRED = ("instruction", "input", "output")
MIN_OUTPUT_WORDS = 10
VAL_FRACTION = 0.1
SEED = 42
SYSTEM_PROMPT = ("You are an Operating Systems tutor. Explain CPU scheduling step by step, "
                 "using only the context provided, and cite the source note.")


def load_jsonl(path):
    paths = sorted(pathlib.Path(path).glob("*.jsonl")) if pathlib.Path(path).is_dir() else [pathlib.Path(path)]
    records, bad = [], 0
    for p in paths:
        for line_no, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not all(isinstance(rec.get(k), str) for k in REQUIRED):
                bad += 1
                continue
            records.append(rec)
    return records, bad


def _normalise(text):
    """Lowercase, turn punctuation into spaces (so "context-switch" and
    "context switch" collide), and collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def deduplicate(records):
    seen, kept, dropped = set(), [], 0
    for rec in records:
        key = hashlib.md5(_normalise(rec["instruction"] + " " + rec["input"]).encode()).hexdigest()
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        kept.append(rec)
    return kept, dropped


def quality_filter(records):
    kept, dropped = [], 0
    for rec in records:
        if len(rec["output"].split()) < MIN_OUTPUT_WORDS:
            dropped += 1
            continue
        if rec["output"].rstrip()[-1:] not in ".!?}`|*)0123456789%":  # truncated answer
            dropped += 1
            continue
        kept.append(rec)
    return kept, dropped


def verify_numerical(rec):
    """Recompute a worked solution and compare it with the stated answer.

    A numerical record carries a `meta` block, e.g.
        "meta": {"algorithm": "rr", "quantum": 4,
                 "processes": [["P1",0,24],["P2",0,3],["P3",0,3]],
                 "expected_avg_waiting": 5.67}
    """
    meta = rec.get("meta")
    if not meta or "processes" not in meta:
        return True, "not a numerical record"
    procs = [Process(*p) for p in meta["processes"]]
    algo = meta["algorithm"].lower()
    if algo == "fcfs":
        result = fcfs(procs)
    elif algo == "sjf":
        result = sjf(procs, preemptive=meta.get("preemptive", False))
    elif algo == "srtf":
        result = sjf(procs, preemptive=True)
    elif algo == "priority":
        result = priority_scheduling(procs, preemptive=meta.get("preemptive", False))
    elif algo == "rr":
        result = round_robin(procs, meta["quantum"])
    else:
        return False, f"unknown algorithm {algo!r}"
    text = rec["instruction"] + ("\n" + rec["input"] if rec["input"].strip() else "")
    if meta.get("direct"):                       # a focused question: the first lines must be the exact answer
        from intent import direct_answer
        want = direct_answer(text, result)
        if not want or not rec["output"].startswith(want):
            return False, "direct answer does not match the simulator"
    if meta.get("check"):                        # check-my-answer feedback must match the checker's verdict
        from checker import check_answer
        v = check_answer(result, meta["student"])
        if v["correct"] != rec["output"].startswith("✅") or (v["first_error"] and v["first_error"] not in rec["output"]):
            return False, "check feedback does not match the checker"
    stated = meta.get("expected_avg_waiting")
    if stated is not None and abs(stated - result["avg_waiting"]) > 0.01:
        return False, f"avg waiting stated {stated}, computed {result['avg_waiting']}"
    if not (meta.get("skip_avg") or meta.get("direct")) and str(result["avg_waiting"]) not in rec["output"]:
        return False, f"computed avg waiting {result['avg_waiting']} absent from output"
    return True, "verified"


def to_chat(rec):
    """Render into the chat format expected by the Qwen base model."""
    user = rec["instruction"] + (f"\n\n{rec['input']}" if rec["input"].strip() else "")
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user},
        {"role": "assistant", "content": rec["output"]},
    ]}


def split(records, val_fraction=VAL_FRACTION, seed=SEED):
    """Stratified by category and grouped: every phrasing of the same question, or the same scheduling
    problem, lands on the same side, so validation is never a rewording of something seen in training."""
    rng = random.Random(seed)
    by_cat = {}
    for r in records:
        by_cat.setdefault(r.get("category", "uncategorised"), {}).setdefault(r.get("group") or id(r), []).append(r)
    train, val = [], []
    for cat in sorted(by_cat):
        groups = sorted(by_cat[cat].items(), key=lambda kv: str(kv[0]))
        rng.shuffle(groups)
        n_val = max(1, round(len(groups) * val_fraction)) if len(groups) > 1 else 0
        for i, (_, rows) in enumerate(groups):
            (val if i < n_val else train).extend(rows)
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def run(src, out_dir, quiet=False, formatter=None):
    say = (lambda *a: None) if quiet else print
    records, bad = load_jsonl(src)
    say(f"loaded            : {len(records)}" + (f"  (rejected {bad} malformed)" if bad else ""))
    records, d = deduplicate(records)
    say(f"after dedup       : {len(records)} (removed {d})")
    records, q = quality_filter(records)
    say(f"after quality     : {len(records)} (removed {q})")
    valid, failed = [], []
    for rec in records:
        ok, why = verify_numerical(rec)
        (valid if ok else failed).append((rec, why))
    say(f"numerically valid : {len(valid)} (failed {len(failed)})")
    for rec, why in failed:
        say(f"  FAIL {rec['instruction'][:40]!r}: {why}")
    train, val = split([r for r, _ in valid])
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fmt = formatter or to_chat
    dropped_long = 0
    for name, rows in (("train.jsonl", train), ("val.jsonl", val)):
        kept = 0
        with open(out / name, "w", encoding="utf-8") as f:
            for r in rows:
                chat = fmt(r)
                if chat is None:                 # the formatter drops records that would not fit the context
                    dropped_long += 1
                    continue
                f.write(json.dumps(chat, ensure_ascii=False) + "\n")
                kept += 1
        if name == "train.jsonl":
            n_train = kept
        else:
            n_val = kept
    train_n, val_n = n_train, n_val
    if dropped_long:
        say(f"dropped by formatter: {dropped_long}")
    say(f"written           : train {train_n}, val {val_n} -> {out}")
    return {"loaded": len(records) + d + q, "malformed": bad, "dedup_removed": d, "quality_removed": q,
            "failed": len(failed), "failures": [w for _, w in failed],
            "train": train_n, "val": val_n,
            "categories": sorted({r.get("category", "uncategorised") for r, _ in valid})}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python prepare_dataset.py <raw.jsonl | raw_dir> <out_dir>")
    run(sys.argv[1], sys.argv[2])

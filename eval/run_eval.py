"""Run the evaluation suite against the real pipeline and write a report.

    python -m eval.run_eval --no-llm --tag baseline-template     # retrieval + vetted/template path (fast)
    python -m eval.run_eval --tag final-llm                       # full pipeline with the Ollama model
    python -m eval.run_eval --only B,F -v                         # categories, print every failure's answer

A concept case PASSES only if (1) the question was accepted as in scope, (2) every required fact matches,
(3) no forbidden claim matches, (4) the verdict matches where the question has one, (5) concept_check's fact rules find
nothing wrong, and (6) it is not an empty "see the sources" fallback.  Retrieval is scored separately: did the retrieved
passages contain the evidence needed (field `ev`)?  A failed case is blamed on retrieval when the evidence was absent and
on generation when it was present.  A numerical case passes only if EVERY completion/turnaround/waiting/response time and the
Gantt chart equal the independent reference simulator AND the number the student asked for is shown.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import concept_check  # noqa: E402
from eval import reference_sim as ref  # noqa: E402
from eval.questions import CASES, MISSING, NUM  # noqa: E402

FLAGS = re.I | re.S


# ----------------------------------------------------------------------------- question text for numerical cases
def render(n):
    procs, ask, q, style = n["procs"], n["ask"], n["q"], n["style"]
    name = {"fcfs": "FCFS", "sjf": "non-preemptive SJF", "srtf": "SRTF", "priority": "non-preemptive priority scheduling",
            "priority_p": "preemptive priority scheduling", "rr": "Round Robin", "multi": ""}[n["algo"]]
    qtxt = f" with time quantum {q}" if q else ""
    has_pri = n["algo"].startswith("priority")
    if style == "table":
        head = "Process Arrival Burst" + (" Priority" if has_pri else "")
        rows = "\n".join(f"{p} {a} {b}" + (f" {pr}" if has_pri else "") for p, a, b, pr in procs)
        body = f"{head}\n{rows}"
    elif style == "list":
        body = "; ".join(f"{p} {a} {b}" + (f" {pr}" if has_pri else "") for p, a, b, pr in procs)
    elif style == "parallel":
        body = (f"burst times {', '.join(str(p[2]) for p in procs)}, arrival times {', '.join(str(p[1]) for p in procs)}")
    elif style == "label":
        body = "\n".join(f"{p}: arrival {a}, burst {b}" + (f", priority {pr}" if has_pri else "") for p, a, b, pr in procs)
    else:    # bursts only
        body = ", ".join(f"{p}={b}" for p, a, b, pr in procs)
    if n["algo"] == "multi" and q:
        ask = f"{ask} Use time quantum {q} for Round Robin."
    lead = f"Using {name}{qtxt}, " if name else ""
    return f"{lead}consider these processes:\n{body}\n{ask}" if lead else f"{body}\n{ask}"


def fmt2(x):
    return f"{x:.2f}"


def check_numeric(out, n):
    """(ok, reason). Everything is compared with the independent reference simulator."""
    algo, procs, q = n["algo"], n["procs"], n["q"]
    shown = " ".join(str(out.get(k) or "") for k in ("text", "summary"))
    if algo == "multi":
        miss = [a for a in n["algos"] if fmt2(ref.metrics(a, procs, q if a == "rr" else None)["avg_waiting"]) not in shown]
        return (not miss), f"average waiting time of {miss} not shown" if miss else ""
    res = out.get("result")
    if out.get("kind") != "numerical" or res is None:
        return False, f"routed as {out.get('kind')}, no simulator result"
    if res["algorithm"] != algo:
        return False, f"ran {res['algorithm']} instead of {algo}"
    exp = ref.metrics(algo, procs, q)
    for r in res["rows"]:
        e = exp["rows"][r["pid"]]
        got = (r["completion"], r["turnaround"], r["waiting"], r["response"])
        want = (e["completion"], e["turnaround"], e["waiting"], e["response"])
        if got != want:
            return False, f"{r['pid']}: CT/TAT/WT/RT {got} != reference {want}"
    if [tuple(g) for g in res["gantt"]] != ref.runs(exp["timeline"]):
        return False, "Gantt chart differs from the reference"
    want = n.get("want")
    need = []
    if want is None:
        ask = n["ask"].lower()
        if "average waiting" in ask or ask.startswith("what is the average waiting"):
            need.append(fmt2(exp["avg_waiting"]))
        if "turnaround" in ask and "average" in ask:
            need.append(fmt2(exp["avg_turnaround"]))
    elif want == "tat":
        need.append(fmt2(exp["avg_turnaround"]))
    elif want == "rt":
        need.append(fmt2(exp["avg_response"]))
    elif want.startswith("rt-"):
        need.append(str(exp["rows"][want[3:]]["response"]))
    elif want.startswith("wt-"):
        need.append(f"{want[3:]} = {exp['rows'][want[3:]]['waiting']}")
    elif want == "util":
        need.append(f"{exp['utilisation']:.1f}%")
    elif want == "thru":
        need.append(f"{exp['throughput']:.3f}")
    elif want == "gantt":
        need.append(" → ".join(f"{p} ({s}–{e})" for p, s, e in ref.runs(exp["timeline"])))
    absent = [x for x in need if x not in shown]
    if absent:
        return False, f"correct simulation but the asked-for value {absent} is not shown"
    if "wt" in str(want) or want in ("rt", "tat") or want is None:
        pass
    return True, ""


def check_concept(out, c):
    """(ok, reason, evidence_ok)"""
    hits = out.get("hits") or []
    ev_text = " ".join(((h.get("title") or "") + " " + h["text"]) for h in hits)
    ev_ok = all(re.search(p, ev_text, FLAGS) for p in c["ev"]) if c["ev"] else True
    if not out.get("in_scope", True):
        return False, "refused as out of scope", ev_ok
    body = out.get("body") or out.get("text") or ""          # a stored answer's `body` excludes its own question title
    low = re.sub(r"[*_`]", "", body)
    if "The material I found is listed below" in low or len(low.split()) < 4:
        return False, "no answer given (only a source list)", ev_ok
    miss = [p for p in c["facts"] if not re.search(p, low, FLAGS)]
    if miss:
        return False, f"missing fact: {miss[0][:70]}", ev_ok
    for p in c["bad"]:
        if re.search(p, low, re.I | re.M):
            return False, f"forbidden claim matched: {p[:60]}", ev_ok
    if c["lead"] and not re.search(c["lead"], low.strip()[:220], re.I):
        return False, f"wrong or missing verdict (starts: {low.strip()[:70]!r})", ev_ok
    prob = concept_check.rule_problems(low) + concept_check.contradictions(low)
    if prob:
        return False, "fact rule: " + prob[0][:90], ev_ok
    return True, "", ev_ok


def check_scope(out):
    refused = (not out.get("in_scope", True)) and not out.get("hits") and "outside my scope" in (out.get("text") or "")
    return refused, "" if refused else "answered an out-of-scope question"


def verdict_key(out):
    body = (out.get("body") or out.get("text") or "").lower()
    m = re.match(r"\W*(yes|no|true|false|correct|incorrect|not)\b", body)
    return {"yes": "Y", "true": "Y", "correct": "Y", "no": "N", "false": "N", "incorrect": "N", "not": "N"}.get(m.group(1)) if m else "-"


# ----------------------------------------------------------------------------- driver
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("--tag", default="run")
    ap.add_argument("--only", default="", help="comma list of categories (A,B,D,E,F,G,M,S,X,N)")
    ap.add_argument("-v", action="store_true")
    a = ap.parse_args()
    only = {x.strip().upper() for x in a.only.split(",") if x.strip()}

    from tutor import Tutor
    t = Tutor(use_llm=not a.no_llm)
    print("mode:", t.mode, flush=True)
    results = []

    def record(id, cat, group, q, ok, reason, kind, ev_ok=True, out=None, secs=0.0):
        blame = None
        if not ok:
            blame = {"crash": "crash", "scope": "scope", "numeric": "numerical"}.get(kind) or ("retrieval" if not ev_ok else "generation")
        results.append(dict(id=id, cat=cat, group=group, q=q, ok=ok, reason=reason, kind=kind, blame=blame, ev_ok=ev_ok,
                            verdict=verdict_key(out) if out else None, secs=round(secs, 1),
                            answer=(out.get("body") or out.get("summary") or out.get("text") or "")[:700] if out else "",
                            hits=[(h.get("title") or h["source"]) for h in (out or {}).get("hits", [])][:6]))
        if a.v and not ok:
            print(f"FAIL {id}: {reason}\n   Q: {q[:100]!r}\n   A: {results[-1]['answer'][:200]!r}", flush=True)

    for c in CASES:
        if only and c["cat"] not in only:
            continue
        t0 = time.time()
        try:
            out = t.answer(c["q"])
            if c["kind"] == "scope":
                ok, why = check_scope(out)
                record(c["id"], c["cat"], c["group"], c["q"], ok, why, "scope", True, out, time.time() - t0)
            else:
                ok, why, ev_ok = check_concept(out, c)
                record(c["id"], c["cat"], c["group"], c["q"], ok, why, "concept", ev_ok, out, time.time() - t0)
        except Exception as e:
            record(c["id"], c["cat"], c["group"], c["q"], False, f"{type(e).__name__}: {e}", "crash")
            traceback.print_exc()
    if not only or "N" in only:
        for n in NUM:
            text = render(n)
            t0 = time.time()
            try:
                out = t.answer(text)
                ok, why = check_numeric(out, n)
                record(n["id"], "N", None, text, ok, why, "numeric", True, out, time.time() - t0)
            except Exception as e:
                record(n["id"], "N", None, text, False, f"{type(e).__name__}: {e}", "crash")
                traceback.print_exc()
        for id, text, pat in MISSING:
            try:
                out = t.answer(text)
                shown = " ".join(str(out.get(k) or "") for k in ("text", "summary")) + " " + " ".join(out.get("notes", []))
                ok = bool(re.search(pat, shown, FLAGS)) and "Traceback" not in shown
                record(id, "N", None, text, ok, "" if ok else "did not ask for / state the missing information", "numeric", True, out)
            except Exception as e:
                record(id, "N", None, text, False, f"{type(e).__name__}: {e}", "crash")

    # consistency across paraphrases of the same question
    groups = collections.defaultdict(list)
    for r in results:
        if r["group"]:
            groups[r["group"]].append(r)
    inconsistent = [g for g, rs in groups.items() if len(rs) > 1 and (len({x["ok"] for x in rs}) > 1 or len({x["verdict"] for x in rs}) > 1)]

    total, passed = len(results), sum(r["ok"] for r in results)
    by_cat = collections.OrderedDict()
    for r in sorted(results, key=lambda r: r["cat"]):
        d = by_cat.setdefault(r["cat"], [0, 0]); d[0] += r["ok"]; d[1] += 1
    blame = collections.Counter(r["blame"] for r in results if not r["ok"])
    ev_rate = [r["ev_ok"] for r in results if r["kind"] == "concept"]
    summary = dict(tag=a.tag, mode=t.mode, total=total, passed=passed, failed=total - passed, pass_rate=round(100 * passed / total, 1),
                   by_category={k: v for k, v in by_cat.items()}, failures_by_stage=dict(blame),
                   retrieval_evidence_rate=round(100 * sum(ev_rate) / len(ev_rate), 1) if ev_rate else None,
                   paraphrase_groups=len(groups), inconsistent_groups=inconsistent, distinct_questions=len({r["group"] or r["id"] for r in results}))
    outdir = ROOT / "eval" / "results"
    outdir.mkdir(exist_ok=True)
    (outdir / f"{a.tag}.json").write_text(json.dumps({"summary": summary, "results": results}, indent=1, ensure_ascii=False))
    lines = [f"# Evaluation `{a.tag}` ({t.mode})", "",
             f"**{passed}/{total} passed ({summary['pass_rate']}%)** over {summary['distinct_questions']} distinct questions. "
             f"Retrieval evidence present for {summary['retrieval_evidence_rate']}% of concept questions. "
             f"Inconsistent paraphrase groups: {len(inconsistent)}/{len(groups)}.", "",
             "| Category | Passed | Total |", "|---|---|---|"] + [f"| {k} | {v[0]} | {v[1]} |" for k, v in by_cat.items()]
    lines += ["", "Failures by stage: " + (", ".join(f"{k} {v}" for k, v in blame.items()) or "none"), "", "## Failures", ""]
    for r in results:
        if not r["ok"]:
            lines.append(f"- `{r['id']}` [{r['blame']}] {r['reason']} — {r['q'][:90]!r}")
    (outdir / f"{a.tag}.md").write_text("\n".join(lines))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()

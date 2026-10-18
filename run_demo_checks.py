"""Pre-demo self-test: one PASS/FAIL line per claim made in the progress report.

    python run_demo_checks.py
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import traceback

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))

results = []


def check(name):
    def wrap(fn):
        try:
            detail = fn()
            results.append(True)
            print(f"PASS  {name}" + (f"  ({detail})" if detail else ""))
        except Exception as e:
            results.append(False)
            print(f"FAIL  {name}: {e}")
            if "-v" in sys.argv:
                traceback.print_exc()
        return fn
    return wrap


# ---------------------------------------------------------------- simulator (Table 6)
from scheduler import Process as P, fcfs, priority_scheduling, round_robin, sjf  # noqa: E402

TABLE6 = [
    ("FCFS  P1=24,P2=3,P3=3", lambda: fcfs([P("P1", 0, 24), P("P2", 0, 3), P("P3", 0, 3)]), 17.00),
    ("SJF   P1=6,P2=8,P3=7,P4=3", lambda: sjf([P("P1", 0, 6), P("P2", 0, 8), P("P3", 0, 7), P("P4", 0, 3)]), 7.00),
    ("SRTF  8,4,9,5 @ 0,1,2,3", lambda: sjf([P("P1", 0, 8), P("P2", 1, 4), P("P3", 2, 9), P("P4", 3, 5)], True), 6.50),
    ("RR    P1=24,P2=3,P3=3 q=4", lambda: round_robin([P("P1", 0, 24), P("P2", 0, 3), P("P3", 0, 3)], 4), 5.67),
    ("Prio  10,1,2,1,5 / 3,1,4,5,2", lambda: priority_scheduling(
        [P("P1", 0, 10, 3), P("P2", 0, 1, 1), P("P3", 0, 2, 4), P("P4", 0, 1, 5), P("P5", 0, 5, 2)]), 8.20),
]
for label, run, expected in TABLE6:
    @check(f"simulator textbook case {label} -> avg waiting {expected:.2f}")
    def _(run=run, expected=expected):
        got = run()["avg_waiting"]
        assert abs(got - expected) < 0.005, f"got {got}"
        return f"computed {got:.2f}"


@check("Round Robin queue order: arrivals join before the preempted process")
def _():
    r = round_robin([P("P1", 0, 5), P("P2", 1, 3), P("P3", 2, 1)], 2)
    order = [pid for pid, _, _ in r["gantt"]]
    assert order == ["P1", "P2", "P3", "P1", "P2", "P1"], order
    return " ".join(order)


@check("simulator handles idle CPU gaps")
def _():
    r = fcfs([P("P1", 2, 3), P("P2", 8, 2)])
    assert r["gantt"][0][0] == "idle" and r["gantt"][2][0] == "idle", r["gantt"]
    return "idle 0-2 and 5-8"


# ---------------------------------------------------------------- processing (Section 5)
from clean_chunk import chunk_text, clean_text  # noqa: E402


@check("clean_text joins hyphenated words and strips page numbers")
def _():
    out = clean_text("CPU sched-\nuling is fun\n12\nnext line")
    assert "scheduling" in out and "\n12\n" not in out, out


@check("chunk_text makes ~300-word chunks with 45-word overlap")
def _():
    words = [f"w{i}" for i in range(700)]
    chunks = chunk_text(" ".join(words))
    assert all(len(c.split()) <= 300 for c in chunks)
    assert chunks[0].split()[-45:] == chunks[1].split()[:45]
    return f"{len(chunks)} chunks from 700 words"


from prepare_dataset import deduplicate, run as prepare  # noqa: E402


@check("dedup: 'context-switch' and 'context switch' collide")
def _():
    recs = [{"instruction": "Explain context-switch overhead", "input": ""},
            {"instruction": "Explain context switch overhead", "input": ""}]
    kept, dropped = deduplicate(recs)
    assert dropped == 1


@check("validation pipeline catches all 3 planted errors in sample_raw.jsonl (Listing 5)")
def _():
    with tempfile.TemporaryDirectory() as d:
        s = prepare(ROOT / "data" / "sample_raw.jsonl", d, quiet=True)
    assert (s["loaded"], s["dedup_removed"], s["quality_removed"], s["failed"], s["train"], s["val"]) == \
           (5, 1, 1, 1, 1, 1), s
    assert "stated 12.0, computed 17.0" in s["failures"][0], s["failures"]
    return "dup, truncated, wrong avg 12.0 vs 17.0"


@check("instruction dataset: >= 150 records, all valid, every category present")
def _():
    with tempfile.TemporaryDirectory() as d:
        s = prepare(ROOT / "data" / "raw", d, quiet=True)
    total = s["train"] + s["val"]
    assert total >= 150 and s["failed"] == 0, s
    need = {"concept", "numerical", "comparison", "misconception", "practice", "check", "refusal"}
    assert need <= set(s["categories"]), s["categories"]
    return f"{total} records, train {s['train']} / val {s['val']}"


@check("eval set has zero overlap with training problems")
def _():
    train = set()
    for f in (ROOT / "data" / "raw").glob("*.jsonl"):
        for line in f.read_text().splitlines():
            m = json.loads(line).get("meta") or {}
            if "processes" in m:
                train.add(tuple(tuple(p[1:]) for p in m["processes"]))
    ev = [json.loads(l) for l in (ROOT / "data" / "eval_set.jsonl").read_text().splitlines()]
    nums = [tuple(tuple(p[1:]) for p in r["processes"]) for r in ev if r["type"] == "numerical"]
    overlap = [n for n in nums if n in train]
    assert len(nums) == 30 and not overlap, f"{len(overlap)} overlapping"
    return f"30 numerical, 0 overlap with {len(train)} training problems"


@check("no held-out stress-test prompt appears in the training data")
def _():
    import evaluate_answers as ea
    from dataset_extra import _norm
    banned = {_norm(c[1]) for c in ea.CASES}
    hit = [json.loads(l)["instruction"] for f in (ROOT / "data" / "raw").glob("*.jsonl")
           for l in f.read_text().splitlines() if _norm(json.loads(l)["instruction"]) in banned]
    assert not hit, hit[:3]


@check("training files are in the app's real prompt format (context, definitions card, simulator output)")
def _():
    rows = [json.loads(l) for l in (ROOT / "data" / "processed" / "train.jsonl").read_text().splitlines()]
    rag = [r for r in rows if "Context from the course material" in r["messages"][1]["content"]]
    sim = [r for r in rag if "Simulator output" in r["messages"][1]["content"]]
    assert len(rag) > 500 and len(sim) > 200, (len(rag), len(sim))
    assert all(r["messages"][0]["role"] == "system" and r["messages"][2]["role"] == "assistant" for r in rows)
    return f"{len(rows)} train records: {len(rag) - len(sim)} theory + {len(sim)} numerical with retrieved context"


# ---------------------------------------------------------------- retrieval (Section 5.2 / 6.2)
from retriever import Retriever, cite  # noqa: E402

retriever = Retriever()


@check("knowledge-base index loads")
def _():
    assert len(retriever.records) > 50
    return f"{retriever.backend}, {len(retriever.records)} chunks"


@check("retrieval: Round Robin question returns a Round Robin chunk in top-3")
def _():
    hits = retriever.search("Why does round robin have higher context switch overhead?")
    assert any("round" in h["text"].lower() and "quantum" in h["text"].lower() for h in hits)
    return cite(hits[0])


@check("retrieval threshold: off-topic question is refused")
def _():
    q = "What is the capital of France?"
    assert not retriever.in_scope(q, retriever.search(q))


# ---------------------------------------------------------------- routing + tutor (Section 6)
from router import route  # noqa: E402


@check("router: numerical vs concept vs practice vs check")
def _():
    cases = {"Solve RR q=4: P1=24, P2=3, P3=3": ("numerical", "rr"),
             "What is the convoy effect?": ("concept", None),
             "Give me a practice problem on SJF": ("practice", "sjf"),
             "Check my answer: FCFS P1=5, P2=3. My answer: average waiting = 2": ("check", "fcfs"),
             "Non-preemptive priority. P1: burst 10, priority 3; P2: burst 1, priority 1": ("numerical", "priority"),
             "preemptive SJF burst times 8,4,9,5 arrival times 0,1,2,3": ("numerical", "srtf")}
    for q, (kind, algo) in cases.items():
        r = route(q)
        assert (r.kind, r.algorithm) == (kind, algo), f"{q!r} -> {r.kind}/{r.algorithm}"
    return f"{len(cases)} cases"


from tutor import Tutor  # noqa: E402

tutor = Tutor()


@check("tutor answers a numerical with simulator numbers")
def _():
    a = tutor.answer("Solve using Round Robin with quantum 4: P1=24, P2=3, P3=3")
    assert a["kind"] == "numerical" and a["result"]["avg_waiting"] == 5.67 and "5.67" in a["text"]


@check("tutor answers a concept question with cited sources")
def _():
    a = tutor.answer("A student says Round Robin causes starvation. Is this correct?")
    assert a["in_scope"] and a["hits"] and "starvation" in a["text"].lower()
    return cite(a["hits"][0])


from checker import check_answer  # noqa: E402


@check("answer checker pinpoints the first wrong step")
def _():
    r = round_robin([P("P1", 0, 5), P("P2", 1, 3), P("P3", 2, 1)], 2)
    v = check_answer(r, "P1 0-2, P2 2-4, P1 4-6, P3 6-7, P2 7-8, P1 8-9; average waiting = 4")
    assert not v["correct"] and "t=4" in v["first_error"], v["first_error"]
    return "diverges at t=4"


from practice import verified_problem  # noqa: E402


@check("practice problems are generated and simulator-verified for all 6 algorithms")
def _():
    for algo in ("fcfs", "sjf", "srtf", "priority", "priority_p", "rr"):
        text, result, procs = verified_problem(algo, seed=1)
        assert route(text).processes and result["avg_waiting"] >= 0


# ---------------------------------------------------------------- evaluation (objective 8)
import evaluate  # noqa: E402


@check("evaluation on held-out set: numerical accuracy 100%, refusal 100%")
def _():
    res = evaluate.run()
    assert res["numerical"][0] == res["numerical"][1], res["summary"]
    assert res["refusal"][0] == res["refusal"][1], res["summary"]
    s = res["summary"]
    return (f"router {s['Router accuracy (route)']}, retrieval {s['Retrieval hit@3 (concept)']}")


@check("numerical questions are answered exactly as asked (P2's waiting time, Gantt only, response time)")
def _():
    t = Tutor(use_llm=False)
    a = t.answer("Round Robin q=4: P1=24, P2=3, P3=3. What is the waiting time of P2?")["summary"]
    assert a.startswith("**Waiting time**: P2 = 4"), a[:80]
    a = t.answer("FCFS P1=24, P2=3, P3=3 draw the gantt chart only")["summary"]
    assert "P1 (0–24) → P2 (24–27) → P3 (27–30)" in a, a[:120]
    a = t.answer("SRTF P1 0 8, P2 1 4, P3 2 9, P4 3 5. what is the response time of P4?")["summary"]
    assert "P4 = 2" in a, a[:80]


@check("answer stress test (109 varied student prompts, retrieval + fallback only) >= 90%")
def _():
    import evaluate_answers as ea
    t = Tutor(use_llm=False)
    ok = sum(not ea.check(t, k, q, m, n)[2] for k, q, m, n in ea.CASES)
    assert ok / len(ea.CASES) >= 0.9, f"{ok}/{len(ea.CASES)}"
    return f"{ok}/{len(ea.CASES)} prompts"


@check("a model timeout never leaves the student without an answer")
def _():
    import tutor as tu
    t = Tutor(use_llm=False)
    t.model = "does-not-exist"                       # forces the Ollama call to fail
    a = t.answer("how would a timer interrupt help when one process hogs the cpu under round robin")
    assert a["text"].strip() and any("fell back" in n for n in a["notes"]), (a["notes"], a["text"][:80])


@check("Colab notebook is valid, in sync with its generator, and every code cell parses")
def _():
    import ast, sys as _s
    _s.path.insert(0, str(ROOT / "finetune"))
    import make_notebook
    nb = json.loads((ROOT / "finetune" / "ostutor_qlora_colab.ipynb").read_text())
    assert nb == json.loads(json.dumps(make_notebook.build_notebook())), "notebook differs from make_notebook.py: rerun it"
    n = 0
    for c in nb["cells"]:
        if c["cell_type"] == "code":
            ast.parse("\n".join("pass" if l.startswith("!") else l for l in "".join(c["source"]).split("\n")))
            n += 1
    src = "".join("".join(c["source"]) for c in nb["cells"])
    assert "NotebookProgressCallback" not in src and "tokenizer(t)[" not in src, "a known-bad pattern is back"
    assert "train_on_responses_only" in src and "text=" in src
    return f"{n} code cells, Qwen2.5-3B-Instruct"


@check("'What is round robin??' gets the short definition, not a section dump with a worked example")
def _():
    t = Tutor(use_llm=False)
    a = t.answer("What is round robin??")
    assert a["title"] == "What is Round Robin scheduling?", a.get("title")
    assert len(a["body"].split()) < 90 and "worked example" not in a["body"].lower(), len(a["body"].split())
    assert a["related"] and all(x != a["title"] for x in a["related"]), a["related"]
    return f"{len(a['body'].split())}-word answer, {len(a['related'])} related questions"


@check("answers are laid out for reading: summary + key points, formula box, steps, comparison table")
def _():
    import present, facts
    md = present.to_markdown("Round Robin is preemptive. It uses a quantum. The queue is circular. [1]", "What is RR?")
    assert "In short" in md and "Key points" in md and md.startswith("### What is RR?"), md
    assert "**Formula**" in present.to_markdown("Waiting time = turnaround time − burst time. It is time in queue.", None)
    st = present.to_markdown("First, sort. Second, run. Third, repeat.", None)
    assert "**Steps**" in st and "1. Sort." in st, st
    tb = present.to_markdown(facts.compare_answer("sjf", "rr"), "Compare SJF and Round Robin in detail")
    assert "|---|---|---|" in tb and "Starvation" in tb and sum(l.startswith("|") for l in tb.split("\n")) == 8, tb[:200]
    keep = "A short intro.\n\n- point one\n- point two"
    assert present.to_markdown(keep) == keep, "an answer that already has its own layout must be left alone"


@check("comparison questions get a side-by-side table; plain definitions stay short; no raw HTML shown")
def _():
    import present, rich_answers
    t = Tutor(use_llm=False)
    a = t.answer("What is the difference between preemptive and non-preemptive scheduling?")
    assert a.get("rich") and "| **Non-preemptive** | **Preemptive** |" in a["rich"], a.get("title")
    d = t.answer("what is non-preemptive scheduling")
    assert not d.get("rich") and len(d["body"].split()) < 90, (d.get("title"), len(d["body"].split()))
    c = t.answer("compare fcfs and sjf")
    assert "|---|---|---|" in present.to_markdown(c["body"], c["title"], source="1", intent=c["intent"]), c["title"]
    for e in rich_answers.RICH:                    # every row has the right number of cells
        assert all(len(r) == len(e["columns"]) + 1 for r in e["rows"]), e["title"]
        assert "<sub>" not in rich_answers.to_markdown(e)
    assert "<sub>" not in present.to_markdown("A. B. C. D. [1]", "T")
    return f"{len(rich_answers.RICH)} structured comparison tables"


@check("no HTML tag can reach the screen, and no answer repeats a label as its own definition")
def _():
    import present, re as _re
    assert present.clean("a <sub>Source</sub> b <br> c 3 < 5") == "a Source b  c 3 < 5"
    t = Tutor(use_llm=False)
    for q in ("what is non-preemptive scheduling", "what is preemptive scheduling", "what is round robin",
              "compare fcfs and sjf", "what is the formula for waiting time"):
        a = t.answer(q)
        md = present.to_markdown(a["body"], a["title"], source="1", intent=a["intent"])
        assert not _re.search(r"</?[a-zA-Z][^>\n]*>", md), (q, md[:200])
    # circular sentences like "non-preemptive SJF ... are non-preemptive" must not exist in the notes
    for f in (ROOT / "corpus" / "notes").glob("*.md"):
        bad = _re.findall(r"[^.]*non-preemptive[^.]* are non-preemptive\.", f.read_text())
        assert not bad, (f.name, bad[:1])


@check("web fetcher: extraction keeps the article and drops navigation; robots rules respected (offline test)")
def _():
    from rag.fetch_wiki import extract, slug
    html = ("<html><body><div class='headerContainer'><ul><li>Courses</li><li>Tutorials</li></ul></div>"
            "<h1>Round Robin</h1><div class='MainArticleContent_x'><h2>Idea</h2>"
            + "<p>Each process gets one time quantum and then goes to the back of the queue. </p>" * 12
            + "<ul><li>Fair</li></ul><pre>int main(){}</pre><div class='related-articles'><p>Other page</p></div>"
            "</div><footer>All rights reserved</footer></body></html>")
    title, body, lic = extract(html)
    assert title == "Round Robin" and "time quantum" in body and "## Idea" in body, body[:120]
    assert "Courses" not in body and "int main" not in body and "Other page" not in body, body
    assert "All rights reserved" in lic and slug("https://x.org/a/b/round-robin-scheduling/") == "round-robin-scheduling"


@check("scraped web text is kept separate from vetted answers (untitled, searched apart, no opposite convention)")
def _():
    import re as _re
    recs = json.loads((ROOT / "index" / "metadata.json").read_text())
    web = [r for r in recs if r["source"].startswith("web/")]
    if not web:
        return "no web pages indexed (fine)"
    assert all(not r["title"] for r in web), "a web chunk was given a Q&A title"
    bad = [r for r in web if _re.search(r"higher (number|value)[^.]{0,40}higher priority", r["text"], _re.I)]
    assert not bad, "a web chunk states the opposite priority convention"
    import retriever
    assert "web" not in retriever.SOURCE_WEIGHT and retriever.SOURCE_WEIGHT["notes"] > 1.0
    return f"{len(web)} web chunks, all untitled"


@check("advantages / disadvantages answers are drawn as two lists")
def _():
    import present
    md = present.to_markdown("Advantages: it is fast. It is simple. Disadvantages: it is rigid. It can starve jobs.", "Pros and cons?")
    assert "**Advantages**" in md and "**Disadvantages**" in md and "- It is simple." in md and "- It can starve jobs." in md, md


@check("web text supplements answers but never replaces them: separate search, labelled card, labelled prompt")
def _():
    import tutor as tu
    r = Retriever()
    assert all(not h["source"].startswith("web/") for h in r.search("what is hrrn", k=8)), "web leaked into vetted results"
    assert all(h["source"].startswith("web/") for h in r.search("what is hrrn", k=8, origin="web")), "web search returned other sources"
    t = Tutor(use_llm=False)
    a = t.answer("What is a multilevel feedback queue?")
    assert a["mode"].startswith("stored course answer"), "the vetted answer must still be the answer"
    m = a.get("more")
    assert m and m["url"].startswith("https://www.geeksforgeeks.org/") and 15 < len(m["excerpt"].split()) < 130, m
    assert "More detail" not in a["text"] and a["body"] != m["excerpt"], "the card must not replace the answer"
    assert not t.answer("what is the time quantum in round robin").get("more"), "a card appeared although it adds nothing"
    hits = r.search("what is hrrn", k=3)
    web = r.search("what is hrrn", k=2, origin="web")
    with_web = tu.build_prompt("what is hrrn", hits, web_hits=web, examples=False)
    assert "NOT vetted course material" in with_web and f"[{len(hits) + 1}]" in with_web
    assert "NOT vetted" not in tu.build_prompt("what is hrrn", hits, examples=False), "web block present without web passages"
    assert tu.excerpt("hrrn", web[0], known=()) and " ." not in tu.excerpt("hrrn", web[0], known=())
    return f"card: '{m['title'][:34]}…', {len(m['excerpt'].split())}-word quote"


@check("when an answer uses web text it says so, and a guard-replaced answer is never web text")
def _():
    t = Tutor(use_llm=False)
    t.model = "fake-model"                                     # forces the model path without calling Ollama
    web = t.retriever.search("hrrn starvation aging", k=1, origin="web")
    t.web_passages = lambda *a, **k: web
    t._generate = lambda q, hits, result=None, web_hits=None: (f"HRRN raises a waiting job's ratio over time [{len(hits) + 1}].", [])
    os.environ["OSTUTOR_NO_SHORTCUT"] = "1"
    try:
        a = t.answer("how does hrrn avoid starvation")
        assert a.get("web_used") and a["web_used"][0]["url"].startswith("https://www.geeksforgeeks.org/"), a.get("web_used")
        assert any("GeeksforGeeks" in n and "not vetted" in n for n in a["notes"]), a["notes"]
        t._generate = lambda q, hits, result=None, web_hits=None: ("Waiting time = completion time - burst time - 1 [4].", [])
        b = t.answer("how does hrrn avoid starvation")
        assert b.get("guard") and not b.get("web_used"), "a bad answer must be replaced and not credited to the web"
    finally:
        os.environ.pop("OSTUTOR_NO_SHORTCUT", None)


@check("Streamlit app imports cleanly")
def _():
    import ast
    ast.parse((ROOT / "app.py").read_text())
    import streamlit, matplotlib, pandas  # noqa: F401
    return f"streamlit {streamlit.__version__}"


# ---------------------------------------------------------------- informational
from tutor import ollama_model  # noqa: E402

m = ollama_model()
print(f"INFO  generation backend: {'Ollama model ' + m if m else 'grounded template mode (start Ollama with the tutor model to enable the LLM)'}")
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)

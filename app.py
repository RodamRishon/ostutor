"""OS CPU Scheduling Tutor: Streamlit presentation layer (report Section 6.2).

    streamlit run app.py
"""
from __future__ import annotations

import json
import pathlib
import re

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from build_index import build
import present
from checker import check_answer
from practice import verified_problem
from retriever import cite
from router import route
from scheduler import ALGO_RULE, ALGORITHMS, Process, solve
from tutor import Tutor
from viz import comparison_figure, gantt_figure

ROOT = pathlib.Path(__file__).parent
st.set_page_config(page_title="OS CPU Scheduling Tutor", page_icon="🖥️", layout="wide")


@st.cache_resource
def get_tutor():
    import tutor as _tutor_module          # looked up at call time, so a code reload (below) is picked up
    return _tutor_module.Tutor()


def show_gantt(result, upto=None):
    fig = gantt_figure(result, upto=upto)
    st.pyplot(fig, width="stretch")
    plt.close(fig)


def show_result(result, key=""):
    show_gantt(result)
    df = pd.DataFrame(result["rows"]).rename(columns=str.title).rename(columns={"Pid": "Process"})
    if not result["algorithm"].startswith("priority"):
        df = df.drop(columns=["Priority"])
    st.dataframe(df, hide_index=True, width="stretch")
    c1, c2, c3 = st.columns(3)
    c1.metric("Avg waiting", f"{result['avg_waiting']:.2f}")
    c2.metric("Avg turnaround", f"{result['avg_turnaround']:.2f}")
    c3.metric("Avg response", f"{result['avg_response']:.2f}")

    with st.expander("📖 Walk me through it, step by step", expanded=False):
        st.markdown(f"**How {result['algorithm_name']} decides:** {ALGO_RULE[result['algorithm']]}")
        log = result["log"]
        times = [int(re.match(r"t=(\d+)", line).group(1)) for line in log]
        step = st.slider("Step", 1, len(log), 1, key=f"step_{key}",
                         help="Drag to replay the scheduler's decisions one at a time.")
        show_gantt(result, upto=times[step - 1])
        st.caption(f"Chart as it stands after this step (t={times[step - 1]}).")
        for i, line in enumerate(log[:step]):
            if i == step - 1:
                st.markdown(f"**→ {line}**")
            else:
                st.caption(line)

    with st.expander("Full decision log"):
        st.code("\n".join(result["log"]), language=None)


def show_sources(hits):
    if not hits:
        return
    with st.expander(f"Sources ({len(hits)})"):
        for i, h in enumerate(hits, 1):
            st.markdown(f"**[{i}] {cite(h)}**: similarity {h['score']}")
            st.caption(h["text"][:600] + ("…" if len(h["text"]) > 600 else ""))


def render_concept(ans):
    """A concept answer as a short summary + key points / steps / formula / comparison table."""
    if ans.get("rich"):                                   # a hand-written side-by-side comparison table
        st.markdown(present.clean(ans["rich"]))
    elif ans.get("body"):                                 # a stored, vetted Q&A: title and answer are separate
        st.markdown(present.to_markdown(ans["body"], ans.get("title"), source="1", intent=ans.get("intent")))
    else:                                                 # a model-written or extracted answer
        st.markdown(present.to_markdown(ans["text"], intent=ans.get("intent")))


def render_more(more):
    """Optional card under a vetted answer: what a GeeksforGeeks page adds, quoted briefly with a link."""
    with st.expander(f"📚 More detail from GeeksforGeeks: {more['title']}"):
        st.caption("Web text, not vetted course material. A short quote, so check it against your notes.")
        if more.get("section"):
            st.markdown(f"**From the section: {more['section']}**")
        st.markdown(present.clean(more["excerpt"]))
        if more.get("url"):
            st.markdown(f"[Read the full article]({more['url']})")


def render_answer(ans, key, latest=False):
    if ans["kind"] == "concept" and ans.get("in_scope", True) and ans.get("text"):
        render_concept(ans)
    else:
        st.markdown(present.clean(ans.get("summary") or ans["text"]))
    if ans.get("more"):
        render_more(ans["more"])
    for n in ans.get("notes", []):
        st.info(n)
    status = ans.get("status")
    if status:                                            # only what actually happened to THIS answer
        icon = {"verified": "✅", "checked": "🟡", "stored": "📘", "none": "ℹ️", "unverified": "⚠️", "error": "❌"}[status["level"]]
        st.caption(f"{icon} {status['label']}")
    for j, res in enumerate(ans.get("results") or []):
        with st.expander(f"{res['algorithm_name']}: Gantt chart and times"):
            show_result(res, key=f"{key}-cmp{j}")
    if ans.get("result") is not None and ans["kind"] in ("numerical", "check", "worked_example"):
        show_result(ans["result"], key)
    if ans.get("kind") == "practice" and ans.get("result") is not None:
        with st.expander("Show solution"):
            show_result(ans["result"], key)
    if latest and ans.get("related"):                     # follow-ups on the same topic, one click away
        st.markdown("**Related questions**")
        for j, q in enumerate(ans["related"]):
            if st.button(q, key=f"rel-{key}-{j}"):
                st.session_state["_ask"] = q
                st.rerun()
    show_sources(ans.get("hits", []))
    st.caption(f"route: {ans['kind']} · generation: {ans['mode']}")


tutor = get_tutor()

# --------------------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🖥️ CPU Scheduling Tutor")
    st.caption("RAG + instruction-tuned LLM + deterministic simulator")
    st.subheader("System status")
    import json as _json
    import datetime as _dt
    import concept_check as _cc
    idx_meta = ROOT / "index" / "metadata.json"
    built = _dt.datetime.fromtimestamp(idx_meta.stat().st_mtime).strftime("%Y-%m-%d %H:%M") if idx_meta.exists() else "missing"
    docs = len({r["source"] for r in tutor.retriever.records})
    st.markdown(f"**Retrieval:** `{tutor.retriever.backend}` index, {len(tutor.retriever.records)} chunks from {docs} documents "
                f"(built {built})")
    st.markdown(f"**Generation:** {tutor.mode}" + ("" if tutor.model else " ⚠️ concept answers are quoted, exam-format questions need the model"))
    n_fail = sum(1 for _ in _cc.LOG_PATH.open()) if _cc.LOG_PATH.exists() else 0
    st.markdown("**Verification:** numbers are computed by the simulator and re-checked against their definitions; "
                "generated concept answers go through the fact-rule check (`concept_check.py`). "
                f"Logged check failures so far: {n_fail}.")
    if st.button("Rebuild index from corpus/"):
        try:
            with st.spinner("cleaning, chunking, indexing…"):
                backend, n = build(quiet=True)
            import importlib, sys
            # Also pick up edited code, not just the rebuilt index, so a restart of Streamlit is not needed. Every
            # project module is reloaded, leaves first: tutor.py imports from intent / scheduler / checker, so
            # reloading only retriever + tutor fails with ImportError as soon as one of those gained a new name.
            for _name in ("build_index", "scheduler", "numeric_guard", "facts", "concept_check", "rich_answers", "present", "checker",
                          "practice", "intent", "router", "retriever", "tutor"):
                if _name in sys.modules:
                    importlib.reload(sys.modules[_name])
            st.cache_resource.clear()
            st.session_state["_rebuild_msg"] = ("success", f"rebuilt: {backend}, {n} chunks")
            st.rerun()
        except Exception as e:                 # a failed rebuild must be visible, and must not leave a half-updated page
            st.error(f"Index rebuild failed: {type(e).__name__}: {e}. The previous index is still in use.")
    if st.session_state.get("_rebuild_msg"):
        kind, msg = st.session_state.pop("_rebuild_msg")
        getattr(st, kind)(msg)
    st.divider()
    st.caption("A lower priority number means a higher priority. Ties are broken by arrival time, "
               "then by process number.")

tab_chat, tab_sim, tab_practice, tab_check, tab_eval = st.tabs(
    ["💬 Tutor", "🧮 Simulator", "📝 Practice", "✅ Check my answer", "📊 Pipeline & evaluation"])

# --------------------------------------------------------------------------- chat
with tab_chat:
    if "history" not in st.session_state:
        st.session_state.history = []
    examples = [
        "Why does Round Robin have higher context-switch overhead?",
        "Solve using Round Robin with quantum 4: P1=24, P2=3, P3=3",
        "Preemptive SJF: burst times 8, 4, 9, 5 arrival times 0, 1, 2, 3",
        "A student says Round Robin causes starvation. Is this correct?",
        "Give me a practice problem on priority scheduling",
        "What is the capital of France?",
    ]
    cols = st.columns(3)
    clicked = None
    for i, ex in enumerate(examples):
        if cols[i % 3].button(ex, key=f"ex{i}", width="stretch"):
            clicked = ex
    if st.session_state.history and st.button("Clear conversation"):
        st.session_state.history = []
        st.rerun()

    for i, (q, ans) in enumerate(st.session_state.history):
        with st.chat_message("user"):
            st.markdown(q)
        with st.chat_message("assistant"):
            render_answer(ans, key=f"h{i}", latest=(i == len(st.session_state.history) - 1))

    typed = st.chat_input("Ask about CPU scheduling or paste a problem, e.g. P1 0 5 / P2 1 3 / "
                          "P3 2 1   Round Robin q=2 (Shift+Enter for a new line)")
    question = typed or clicked or st.session_state.pop("_ask", None)
    if question:
        with st.spinner("routing → simulating → retrieving → answering…"):
            ans = tutor.answer(question)
        st.session_state.history.append((question, ans))
        st.rerun()

# --------------------------------------------------------------------------- simulator
with tab_sim:
    st.subheader("Scheduling simulator")
    st.caption("Edit the table, pick an algorithm and run. Every number is computed, not generated.")
    if "sim_df" not in st.session_state:
        st.session_state.sim_df = pd.DataFrame({"Process": ["P1", "P2", "P3", "P4"], "Arrival": [0, 1, 2, 3],
                                                "Burst": [8, 4, 9, 5], "Priority": [3, 1, 4, 2]})
    df = st.data_editor(st.session_state.sim_df, num_rows="dynamic", width="stretch", key="sim_editor")
    c1, c2 = st.columns([3, 1])
    algo = c1.selectbox("Algorithm", list(ALGORITHMS), format_func=ALGORITHMS.get, index=2)
    q = c2.number_input("Time quantum (RR)", min_value=1, value=4, step=1)
    try:
        procs = [Process(str(r.Process), int(r.Arrival), int(r.Burst), int(r.Priority))
                 for r in df.dropna().itertuples()]
        if len(procs) < 1:
            raise ValueError("add at least one process")
        result = solve(algo, procs, q if algo == "rr" else None)
        show_result(result, "sim")
        st.markdown("#### All algorithms on this process set")
        everything = [solve(a, procs, q if a == "rr" else None) for a in ALGORITHMS]
        fig = comparison_figure(everything)
        st.pyplot(fig, width="stretch")
        plt.close(fig)
    except (ValueError, TypeError) as e:
        st.error(f"Check the table: {e}")

# --------------------------------------------------------------------------- practice
with tab_practice:
    st.subheader("Practice problems")
    st.caption("Each problem is solved by the simulator and re-parsed by the router before it is shown.")
    c1, c2, c3 = st.columns([2, 1, 1])
    p_algo = c1.selectbox("Algorithm", ["any"] + list(ALGORITHMS),
                          format_func=lambda a: "Any" if a == "any" else ALGORITHMS[a], key="p_algo")
    p_n = c2.slider("Processes", 3, 6, 4)
    if c3.button("New problem", type="primary", width="stretch") or "practice" not in st.session_state:
        st.session_state.practice = verified_problem(None if p_algo == "any" else p_algo, p_n)
        st.session_state.pop("practice_check", None)
    text, result, _ = st.session_state.practice
    st.code(text, language=None)
    mine = st.text_area("Your answer (Gantt chart, waiting times, averages)",
                        placeholder="P1 0-3, P2 3-8, ...  waiting P1=0, P2=2, ...  average waiting = 4.5")
    if st.button("Check", key="p_check") and mine.strip():
        st.session_state.practice_check = check_answer(result, mine)
    if "practice_check" in st.session_state:
        v = st.session_state.practice_check
        (st.success if v["correct"] else st.error)("Correct!" if v["correct"] else "Not quite.")
        for f in v["findings"]:
            st.markdown(f"- {f}")
    with st.expander("Show solution"):
        show_result(result, "practice")

# --------------------------------------------------------------------------- check
with tab_check:
    st.subheader("Check my answer")
    st.caption("Paste the question and your working. The tutor finds the first step where you went wrong.")
    c1, c2 = st.columns(2)
    prob = c1.text_area("Question", height=170,
                        value="Round Robin, time quantum 2\nProcess Arrival Burst\nP1 0 5\nP2 1 3\nP3 2 1")
    ans_text = c2.text_area("Your answer", height=170,
                            value="Gantt: P1 0-2, P2 2-4, P1 4-6, P3 6-7, P2 7-8, P1 8-9\n"
                                  "waiting P1=4, P2=4, P3=4\naverage waiting = 4")
    if st.button("Check answer", type="primary"):
        r = route(prob)
        if not r.processes:
            st.error("I couldn't find process data in the question. Use rows like 'P1 0 5' "
                     "(process, arrival, burst[, priority]).")
        else:
            algo = r.algorithm or "fcfs"
            res = solve(algo, r.processes, r.quantum or (2 if algo == "rr" else None))
            v = check_answer(res, ans_text)
            for n in r.notes:
                st.info(n)
            (st.success if v["correct"] else st.error)(
                "Your answer matches the simulator." if v["correct"] else (v["first_error"] or "Not quite."))
            for f in v["findings"]:
                st.markdown(f"- {f}")
            st.markdown("#### Correct solution")
            show_result(res, "check")

# --------------------------------------------------------------------------- evaluation
with tab_eval:
    st.subheader("Pipeline")
    st.markdown("""
**Phase A (once):** corpus → clean → chunk (300 words / 45 overlap) → embed → index ·
instruction dataset → validate → QLoRA fine-tune on Colab → Ollama
**Phase B (every query):** question → **router** → **simulator** (if numerical) → **retrieval** (top-3, threshold)
→ **generation** → answer with citations and verified numbers
""")
    proc = ROOT / "data" / "processed"
    raw = ROOT / "data" / "raw"
    if raw.exists():
        cats = {}
        for f in raw.glob("*.jsonl"):
            for line in f.read_text().splitlines():
                c = json.loads(line).get("category", "?")
                cats[c] = cats.get(c, 0) + 1
        n_train = sum(1 for _ in open(proc / "train.jsonl")) if (proc / "train.jsonl").exists() else 0
        n_val = sum(1 for _ in open(proc / "val.jsonl")) if (proc / "val.jsonl").exists() else 0
        c1, c2 = st.columns(2)
        c1.markdown("**Instruction dataset**")
        c1.dataframe(pd.DataFrame({"category": list(cats), "records": list(cats.values())}),
                     hide_index=True, width="stretch")
        c1.caption(f"total {sum(cats.values())} · after validation: train {n_train}, val {n_val}")
        c2.markdown("**Knowledge base**")
        srcs = {}
        for r in tutor.retriever.records:
            top = r["source"].split("/")[0]
            srcs[top] = srcs.get(top, 0) + 1
        c2.dataframe(pd.DataFrame({"source": list(srcs), "chunks": list(srcs.values())}),
                     hide_index=True, width="stretch")

    st.subheader("Evaluation on the held-out set")
    st.caption("30 numerical + 20 conceptual questions never used in training, plus 5 off-topic questions.")
    if st.button("Run evaluation", type="primary"):
        import evaluate
        with st.spinner("evaluating…"):
            res = evaluate.run()
        st.session_state.eval = res
    res = st.session_state.get("eval")
    if res is None and (ROOT / "results" / "eval_results.json").exists():
        res = json.loads((ROOT / "results" / "eval_results.json").read_text())
    if res:
        st.dataframe(pd.DataFrame({"metric": list(res["summary"]), "result": list(res["summary"].values())}),
                     hide_index=True, width="stretch")
        if res["failures"]:
            with st.expander(f"Misses ({len(res['failures'])})"):
                for f in res["failures"]:
                    st.markdown(f"- {f}")

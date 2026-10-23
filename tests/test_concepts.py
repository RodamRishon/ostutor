"""Regression tests for conceptual accuracy: the convoy effect / starvation mix-up and its relatives.

    python -m pytest tests -q

Layers covered: the fact rules (concept_check), retrieval (both concepts reach the model), the prompt, the
verify -> regenerate -> fall back loop (Ollama replaced by a stub, so everything runs offline), and the seven
regression questions A-G from the bug report.
"""
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import concept_check as cc  # noqa: E402
import tutor as tutor_module  # noqa: E402
from tutor import MAX_REGENERATIONS, SYSTEM_PROMPT, Tutor  # noqa: E402

Q_CONVOY = "What is the difference between convoy effect and starvation?"

# The answer that was actually reported: three different mistakes in one answer.
BAD_ANSWER = """**Convoy effect vs starvation**
- The convoy effect happens when short processes wait behind a long one.
- FCFS can starve short processes when a long process arrives first.
- SJF and Round Robin both avoid starvation by letting short jobs run first.
- Starvation is the same as the convoy effect, a form of starvation in FCFS."""

GOOD_ANSWER = """**Convoy effect vs starvation**
The convoy effect is a performance problem; starvation is indefinite postponement. [1][2]

| | Convoy effect | Starvation |
|---|---|---|
| Meaning | Short processes wait behind one long CPU-bound process | A process is passed over indefinitely |
| Does the wait end? | Yes, when the long process finishes | Not necessarily |
| Classic algorithm | FCFS | SJF/SRTF (long jobs), Priority (low-priority jobs) |

Example (convoy): a 100-unit job arrives first in FCFS and two 2-unit jobs wait about 100 units, but they do run.
Example (starvation): under SJF a long job can be passed over if shorter jobs keep arriving; aging is the remedy.
Standard FCFS does not normally starve a process, assuming the processes ahead of it terminate.
In short: the convoy effect is a long but finite delay; starvation is a wait that may never end."""


@pytest.fixture(scope="module")
def template_tutor():
    return Tutor(use_llm=False)


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "LOG_PATH", tmp_path / "verification.jsonl")


class StubModel:
    """Replaces ollama_chat: returns the queued replies in order (the last one repeats)."""
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, model, prompt, **kw):
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts), len(self.replies)) - 1]


@pytest.fixture
def llm_tutor(monkeypatch):
    def make(*replies):
        stub = StubModel(*replies)
        monkeypatch.setattr(tutor_module, "ollama_chat", stub)
        monkeypatch.setenv("OSTUTOR_NO_SHORTCUT", "1")          # reach the model instead of the stored answer
        t = Tutor(use_llm=False)
        t.model = "stub"
        monkeypatch.setattr(t, "web_passages", lambda *a, **k: [])
        return t, stub
    return make


def body(out):
    return out["text"].lower()


# ------------------------------------------------------------------ fact rules
@pytest.mark.parametrize("claim, fragment", [
    ("FCFS can starve short processes.", "FCFS causes starvation"),
    ("SJF and Round Robin both avoid starvation by letting short jobs run first.", "prevents starvation"),
    ("SJF and Round Robin both avoid starvation by letting short jobs run first.", "Round Robin favours"),
    ("The convoy effect is a form of starvation in FCFS.", "convoy effect as starvation"),
    ("Priority scheduling never starves anyone.", "never starves"),
    ("SJF will always starve long jobs.", "certain"),
    ("Round Robin gives priority to short processes.", "gives short processes priority"),
])
def test_known_mixups_are_caught(claim, fragment):
    assert any(fragment in p for p in cc.rule_problems(claim)), cc.rule_problems(claim)


@pytest.mark.parametrize("claim", [
    "Standard FCFS does not cause starvation; long waits behind a long job are the convoy effect.",
    "SJF can starve long jobs if shorter jobs keep arriving.",
    "Round Robin does not prioritize short processes; it serves processes in cyclic order.",
    "Unlike SJF, Round Robin avoids starvation under standard assumptions.",
    "Aging prevents starvation in Priority scheduling.",
    "The convoy effect is not starvation: the wait is long but finite.",
])
def test_correct_statements_are_not_flagged(claim):
    assert cc.rule_problems(claim) == []


def test_the_reported_answer_fails_and_a_good_one_passes():
    bad = cc.verify(Q_CONVOY, BAD_ANSWER)
    assert not bad["ok"] and len(bad["problems"]) >= 3
    assert any("Priority" in m for m in bad["missing"]) or any("SJF" in m for m in bad["missing"])
    assert cc.verify(Q_CONVOY, GOOD_ANSWER) == {"ok": True, "problems": [], "missing": [], "spec": "convoy_vs_starvation"}


def test_self_contradiction_and_unconditional_claims_are_caught():
    assert cc.contradictions("SJF can cause starvation of long jobs. SJF does not cause starvation.")
    assert cc.absolute_claims("Round Robin never causes starvation.")
    assert not cc.absolute_claims("Under standard assumptions Round Robin never causes starvation.")


def test_unsupported_claim_is_flagged_against_the_retrieved_context():
    ctx = "The convoy effect happens under FCFS when short processes wait behind a long process."
    assert cc.unsupported("Priority scheduling starves low-priority processes through aging.", ctx)
    assert not cc.unsupported("The convoy effect happens under FCFS when short processes wait behind a long one.", ctx)


def test_unrelated_algorithms_are_flagged():
    assert cc.unrelated_algorithms(Q_CONVOY, "The convoy effect occurs in FCFS. HRRN also uses aging.")


def test_no_vetted_course_passage_violates_the_fact_rules():
    """Lints the knowledge base itself: the misleading line that fed the bad answer must not come back."""
    records = json.loads((pathlib.Path(__file__).resolve().parent.parent / "index" / "metadata.json").read_text())
    offenders = [(r["source"], r.get("title"), cc.rule_problems(r["text"]) + cc.contradictions(r["text"]))
                 for r in records if not r["source"].startswith(("web/", "wikipedia/"))]
    assert [o for o in offenders if o[2]] == []


# ------------------------------------------------------------------ retrieval and prompt
def test_comparison_question_retrieves_a_defining_passage_for_each_concept(template_tutor):
    out = template_tutor.answer(Q_CONVOY)
    titles = [h["title"] for h in out["hits"]]
    assert "What is the convoy effect?" in titles and "What is starvation in CPU scheduling?" in titles
    keys = [(h["source"], h["title"]) for h in out["hits"]]
    assert len(keys) == len(set(keys)) <= tutor_module.MAX_CONCEPT_PASSAGES        # no duplicate passages


def test_prompt_has_both_concepts_the_facts_and_the_comparison_structure(llm_tutor):
    t, stub = llm_tutor(GOOD_ANSWER)
    t.answer(Q_CONVOY)
    prompt = stub.prompts[0]
    assert "the convoy effect happens under fcfs" in prompt.lower() and "starvation, also called indefinite blocking" in prompt.lower()
    assert "Scheduling facts for explanations" in prompt
    for part in ("definition of the first item", "comparison table", "one simple example for each", "exam-ready conclusion"):
        assert part in prompt
    assert "answer it in the first sentence" in prompt and "do not use 'always' or 'never'" in prompt
    for rule in ("directly", "ONLY the numbered context", "never contradict", "assumption"):
        assert rule in SYSTEM_PROMPT


# ------------------------------------------------------------------ verify -> regenerate -> fall back
def test_good_answer_is_accepted_after_one_call(llm_tutor):
    t, stub = llm_tutor(GOOD_ANSWER)
    out = t.answer(Q_CONVOY)
    assert len(stub.prompts) == 1 and out["text"] == GOOD_ANSWER and "verification" not in out


def test_bad_answer_is_regenerated_once_with_the_problems_and_the_log_records_it(llm_tutor):
    t, stub = llm_tutor(BAD_ANSWER, GOOD_ANSWER)
    out = t.answer(Q_CONVOY)
    assert len(stub.prompts) == 2 and out["text"] == GOOD_ANSWER
    retry = stub.prompts[1]
    assert "Rejected answer" in retry and "FCFS can starve short processes" in retry
    assert "claims FCFS causes starvation" in retry and "Remove or fix" in retry
    log = [json.loads(line) for line in cc.LOG_PATH.read_text().splitlines()]
    assert log and log[0]["outcome"] == "regenerate" and log[0]["problems"]


def test_persistent_failure_stops_after_the_limit_and_shows_the_vetted_answer(llm_tutor):
    t, stub = llm_tutor(BAD_ANSWER)
    out = t.answer(Q_CONVOY)
    assert len(stub.prompts) == MAX_REGENERATIONS + 1                      # no endless regeneration
    assert "fact check" in " ".join(out["notes"])
    assert "FCFS can starve" not in out["text"] and "avoid starvation by letting short" not in out["text"]
    assert cc.verify(Q_CONVOY, out["text"])["ok"]                           # what the student sees is itself correct
    assert json.loads(cc.LOG_PATH.read_text().splitlines()[-1])["outcome"] == "fallback"


def test_model_judge_is_advisory_only(llm_tutor, monkeypatch):
    t, stub = llm_tutor(GOOD_ANSWER)
    monkeypatch.setenv("OSTUTOR_JUDGE_MODEL", "judge")
    calls = []
    real = StubModel('{"issues": ["the example is vague"]}')
    monkeypatch.setattr(tutor_module, "ollama_chat", lambda m, p, **kw: (calls.append(m), real(m, p) if m == "judge" else GOOD_ANSWER)[1])
    out = t.answer(Q_CONVOY)
    assert out["text"] == GOOD_ANSWER and any("advisory" in n for n in out["notes"]) and "judge" in calls


# ------------------------------------------------------------------ the seven regression questions (no LLM: vetted path)
def test_A_convoy_vs_starvation(template_tutor):
    out = template_tutor.answer(Q_CONVOY)
    t = body(out)
    assert out["in_scope"] and cc.verify(Q_CONVOY, out["text"])["ok"]
    assert "performance problem" in t and "indefinite" in t                              # degradation vs postponement
    assert "convoy" in t and "fcfs" in t                                                 # classic FCFS convoy effect
    assert "fcfs does not cause starvation" in t or "does not cause starvation" in t     # standard FCFS: no starvation
    assert "sjf" in t and "long job" in t and "priority" in t and "low-priority" in t    # SJF and Priority can starve
    assert "sjf always prevents" not in t and "round robin prioritises" not in t and "round robin prioritizes" not in t
    assert cc.rule_problems(out["text"]) == []


@pytest.mark.parametrize("q, must", [
    ("Can starvation occur in SJF?", ["yes", "shorter jobs keep arriving", "long job"]),
    ("Can starvation occur in FCFS?", ["not in standard fcfs", "convoy effect", "finite", "not indefinite postponement"]),
    ("Why can starvation occur in Priority Scheduling?", ["low-priority", "bypassed", "higher-priority", "aging"]),
    ("Does Round Robin prioritize short processes?", ["no.", "cyclic", "time quantum", "fewer turns", "not selected first"]),
])
def test_B_to_E_concept_questions(template_tutor, q, must):
    out = template_tutor.answer(q)
    t = body(out)
    assert out["in_scope"] and out["hits"]
    for m in must:
        assert m in t, (m, out["text"])
    assert cc.verify(q, out["text"])["ok"] and cc.rule_problems(out["text"]) == []


# F: hand-computed independently of the simulator.  P1=5, P2=3, P3=8, all at t=0, q=2:
#   P1 0-2, P2 2-4, P3 4-6, P1 6-8, P2 8-9, P3 9-11, P1 11-12, P3 12-16
#   completion 12/9/16 -> waiting 7/6/8 -> average waiting 7.00, average turnaround 37/3
def test_F_round_robin_numerical_comes_from_the_simulator(template_tutor):
    out = template_tutor.answer("Solve this Round Robin problem and calculate average waiting time. "
                                "P1=5, P2=3, P3=8, time quantum 2")
    res = out["result"]
    assert out["kind"] == "numerical" and res["quantum"] == 2
    assert [(p, s, e) for p, s, e in res["gantt"]] == [("P1", 0, 2), ("P2", 2, 4), ("P3", 4, 6), ("P1", 6, 8), ("P2", 8, 9),
                                                      ("P3", 9, 11), ("P1", 11, 12), ("P3", 12, 16)]
    rows = {r["pid"]: r for r in res["rows"]}
    assert (rows["P1"]["completion"], rows["P2"]["completion"], rows["P3"]["completion"]) == (12, 9, 16)
    assert (rows["P1"]["waiting"], rows["P2"]["waiting"], rows["P3"]["waiting"]) == (7, 6, 8)
    assert (rows["P1"]["response"], rows["P2"]["response"], rows["P3"]["response"]) == (0, 2, 4)
    assert res["avg_waiting"] == pytest.approx(7.0) and res["avg_turnaround"] == pytest.approx(37 / 3, abs=0.005)
    assert any("arrive at t=0" in n for n in out["notes"]) and "time quantum 2" in out["text"]
    assert "7.00" in out["summary"]


# With arrivals, q=2 (an arrival at the instant a quantum expires queues before the preempted process, as in the course notes):
#   P1 0-2, P2 2-4, P3 4-5, P1 5-7, P2 7-8, P1 8-9 -> completion 9/8/5, waiting 4/4/2
def test_F_round_robin_with_arrival_times(template_tutor):
    out = template_tutor.answer("Round Robin quantum 2: P1 0 5, P2 1 3, P3 2 1. Calculate the average waiting time.")
    res = out["result"]
    assert res["gantt"] == [("P1", 0, 2), ("P2", 2, 4), ("P3", 4, 5), ("P1", 5, 7), ("P2", 7, 8), ("P1", 8, 9)] \
        or [tuple(g) for g in res["gantt"]] == [("P1", 0, 2), ("P2", 2, 4), ("P3", 4, 5), ("P1", 5, 7), ("P2", 7, 8), ("P1", 8, 9)]
    assert [r["waiting"] for r in res["rows"]] == [4, 4, 2]
    assert res["avg_waiting"] == pytest.approx(10 / 3, abs=0.005)


def test_F_a_numerical_request_without_data_asks_for_it_instead_of_inventing_numbers(template_tutor):
    out = template_tutor.answer("Solve this Round Robin problem and calculate average waiting time.")
    assert out["kind"] == "needs_data" and out["result"] is None and out["hits"] == []
    assert "arrival and burst time" in out["text"] and "q = 2" in out["text"]


def test_G_out_of_scope_question_is_declined_without_fabricated_citations(template_tutor):
    out = template_tutor.answer("What is the capital of France?")
    assert out["in_scope"] is False and out["hits"] == []
    assert "outside my scope" in out["text"]
    assert not any(w in out["text"].lower() for w in ("quantum", "gantt chart is", "fcfs is"))

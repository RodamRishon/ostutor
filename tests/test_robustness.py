"""Regression tests for the failures found by the evaluation suite (eval/run_eval.py). Each test names the eval case
it came from. Offline: the language model is never called."""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tutor as tutor_module  # noqa: E402
from eval import reference_sim as ref  # noqa: E402
from intent import detect_intent  # noqa: E402
from router import detect_algorithms, route  # noqa: E402
from scheduler import Process, check_invariants, solve  # noqa: E402
from tutor import Tutor  # noqa: E402


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path, monkeypatch):
    import concept_check
    monkeypatch.setattr(concept_check, "LOG_PATH", tmp_path / "verification.jsonl")


@pytest.fixture(scope="module")
def t():
    return Tutor(use_llm=False)


# ---- n-bad-q0: an explicit invalid quantum was silently replaced by q=2
@pytest.mark.parametrize("q", ["Round Robin with quantum 0: P1 0 5, P2 1 3. Find the average waiting time.",
                               "Round Robin quantum -2: P1 0 5, P2 1 3. average waiting time?"])
def test_invalid_quantum_is_reported_not_replaced(t, q):
    out = t.answer(q)
    assert out["kind"] == "invalid" and out["result"] is None
    assert "positive whole number" in out["text"] and out["status"]["level"] == "none"


def test_zero_burst_is_a_controlled_message(t):
    out = t.answer("FCFS: P1 0 0, P2 1 3, P3 2 8. Find the average waiting time.")
    assert out["kind"] == "invalid" and "burst" in out["text"] and "Traceback" not in out["text"]


# ---- n-compare3 / n-compare2: several algorithms on the same data
def test_several_algorithms_run_on_the_same_validated_data(t):
    out = t.answer("Process Arrival Burst\nP1 0 24\nP2 0 3\nP3 0 3\nCompare FCFS, SJF and Round Robin on average waiting time. "
                   "Use time quantum 4 for Round Robin.")
    assert out["kind"] == "compare_numerical" and len(out["results"]) == 3
    procs = [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]
    for res in out["results"]:
        want = ref.metrics(res["algorithm"], procs, 4 if res["algorithm"] == "rr" else None)["avg_waiting"]
        assert res["avg_waiting"] == pytest.approx(want, abs=0.005)
        assert f"{want:.2f}" in out["text"]
    assert out["status"]["level"] == "verified"
    assert "universally" not in out["text"] and "this workload and this metric only" in out["text"]


def test_a_single_algorithm_question_is_still_one_run():
    assert route("Using SJF: P1 0 5, P2 1 3. average waiting time?").kind == "numerical"
    assert detect_algorithms("compare SJF and SRTF") == ["srtf", "sjf"]
    assert detect_algorithms("preemptive SJF with P1 0 5, P2 1 3") == ["srtf"]


# ---- d-starve-2 / d-convoy-2: a sentence that DENIES the property must not name the algorithm
def test_plural_which_question_is_a_list_question_not_a_single_name():
    assert detect_intent("which scheduling algorithms can lead to starvation of processes")[0] == "which_list"
    assert detect_intent("Which algorithm selects the process with the shortest burst?")[0] == "identify"


@pytest.mark.parametrize("q, wrong", [("which scheduling algorithm has the convoy effect", "Round Robin"),
                                      ("which scheduling algorithms can lead to starvation of processes", "Answer: FCFS")])
def test_identify_never_names_an_algorithm_from_a_denying_or_hypothetical_sentence(t, q, wrong):
    out = t.answer(q)
    assert wrong not in out["text"].split("\n\n")[0]


# ---- b-fcfs-pros: both halves of "advantages and disadvantages"
def test_advantages_and_disadvantages_returns_both(t):
    out = t.answer("What are the advantages and disadvantages of FCFS?")
    low = out["text"].lower()
    assert "advantages." in low and "disadvantages." in low
    assert "simple" in low and "convoy" in low


# ---- a-cpusched-2/3: question made only of framing words must still find the definition
@pytest.mark.parametrize("q", ["explain cpu scheduling", "Define CPU scheduling in operating systems.", "what is cpu scheduling"])
def test_generic_definition_questions_find_the_definition(t, q):
    out = t.answer(q)
    assert out["hits"][0]["title"] == "What is CPU scheduling?"


# ---- a-process / a-states / a-queues / e-sim-cx / e-space / e-theory-prac: knowledge that was missing from the corpus
@pytest.mark.parametrize("q, must", [
    ("What is a process?", ["program in execution"]),
    ("What are the states of a process?", ["ready", "running", "waiting", "terminated"]),
    ("What are ready queues and waiting queues?", ["ready queue", "waiting queue"]),
    ("What is the time complexity of simulating FCFS for n processes?", ["o(n log n)"]),
    ("What is the space complexity of the ready queue?", ["o(n)"]),
    ("Why is SJF not practical in real systems even though it is optimal?", ["predict", "advance"]),
])
def test_fundamentals_and_complexity_are_in_the_knowledge_base(t, q, must):
    low = t.answer(q)["text"].lower()
    assert all(m in low for m in must), low[:300]


# ---- simulator self-check and honest status
def test_invariant_checker_catches_a_corrupted_result():
    res = solve("fcfs", [Process("P1", 0, 3), Process("P2", 1, 2)])
    assert check_invariants(res) == []
    res["rows"][0]["waiting"] += 1
    assert any("waiting" in p for p in check_invariants(res))
    res = solve("rr", [Process("P1", 0, 5), Process("P2", 1, 3)], 2)
    res["gantt"][0] = ("P1", 0, 3)
    assert check_invariants(res)


def test_numbers_are_withheld_when_the_self_check_fails(monkeypatch):
    monkeypatch.setattr(tutor_module, "check_invariants", lambda r: ["P1: waiting != turnaround - burst"])
    out = Tutor(use_llm=False).answer("FCFS: P1 0 5, P2 1 3, P3 2 8. Find the average waiting time.")
    assert out["status"]["level"] == "error" and "not showing" in out["text"]


def test_status_reflects_what_was_actually_done(t):
    assert t.answer("FCFS: P1 0 5, P2 1 3, P3 2 8. Find the average waiting time.")["status"]["level"] == "verified"
    assert t.answer("What is the capital of France?")["status"]["level"] == "none"
    assert t.answer("Solve this Round Robin problem.")["status"]["level"] == "none"
    assert t.answer("What is the convoy effect?")["status"]["level"] == "stored"      # quoted, never labelled "verified"


def test_a_pipeline_exception_becomes_a_controlled_error(monkeypatch):
    tt = Tutor(use_llm=False)
    monkeypatch.setattr(tt.retriever, "search", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("index corrupt")))
    out = tt.answer("What is the convoy effect?")
    assert out["kind"] == "error" and "won't guess" in out["text"] and out["status"]["level"] == "error"


@pytest.mark.parametrize("q", [
    "Round robin P1 arrives 0 burst 24, P2 0 3, P3 0 3 quantum 4 average waiting time",
    "FCFS P1 arrives 0 burst 24, P2 arrives 0 burst 3, P3 0 3",
])
def test_mixed_process_formats_keep_every_process(q):
    """A question that mixes 'P1 arrives 0 burst 24' with 'P2 0 3' used to drop P1 and answer for fewer processes."""
    r = route(q)
    assert [(p.pid, p.arrival, p.burst) for p in r.processes] == [("P1", 0, 24), ("P2", 0, 3), ("P3", 0, 3)]

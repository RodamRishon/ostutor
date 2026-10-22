"""Regression tests: a 'which algorithm ...?' question must be answered with the algorithm, not with a
definition of a related concept the question happens to mention (the ready queue, the time quantum ...).

    python -m pytest tests -q

Covers each stage of the pipeline: intent -> retrieval evidence -> routing -> final answer, in both the
grounded-template path (no LLM) and the LLM path (Ollama replaced by a stub, so the test is offline).
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tutor as tutor_module  # noqa: E402
from intent import detect_intent, format_directive  # noqa: E402
from retriever import Retriever  # noqa: E402
from router import route  # noqa: E402
from tutor import IDENTIFY_POOL, Tutor, selection_evidence  # noqa: E402

# question -> (key of the algorithm that must be identified, words its evidence sentence must contain)
WHICH = {
    "Which CPU scheduling algorithm selects the process that arrived earliest in the ready queue?": ("fcfs", "first"),
    "Which algorithm selects the process with the shortest CPU burst?": ("sjf", "burst"),
    "Which algorithm selects the process with the shortest remaining execution time?": ("srtf", "remaining"),
    "Which algorithm allocates CPU time using a fixed time quantum?": ("rr", "quantum"),
    "Which scheduling algorithm can cause the convoy effect?": ("fcfs", "convoy"),
    "Which algorithm is mentioned in my notes as selecting the earliest-arriving process?": ("fcfs", "first"),
}
LABEL = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": "Round Robin"}
# titles of stored definitions that the old pipeline returned instead of the answer
DEFINITIONS = ("What is the ready queue?", "How should the time quantum be chosen?",
               "What happens in SRTF when two processes have the same arrival time or priority?",
               "What is the convoy effect?")


@pytest.fixture(scope="module")
def retriever():
    return Retriever()


@pytest.fixture(scope="module")
def template_tutor():
    return Tutor(use_llm=False)


def answer_head(out):
    """The first line of the answer text: what the student reads first."""
    return out["text"].strip().splitlines()[0]


# ----------------------------------------------------------------------------- intent
@pytest.mark.parametrize("question", WHICH)
def test_which_algorithm_is_an_identify_question_not_a_definition(question):
    assert detect_intent(question)[0] == "identify"
    assert "name of the algorithm" in format_directive(question)


@pytest.mark.parametrize("question, intent", [
    ("What is the ready queue?", "define"),
    ("Differentiate between FCFS and Round Robin.", "compare"),
    ("Which is better, FCFS or SJF?", "compare"),
    ("Why does FCFS cause the convoy effect?", "why"),
    ("What are the types of CPU scheduling algorithms?", "list"),
])
def test_other_intents_are_unchanged(question, intent):
    assert detect_intent(question)[0] == intent


# ----------------------------------------------------------------------------- retrieval
@pytest.mark.parametrize("question, expected", WHICH.items())
def test_retrieval_finds_the_sentence_that_states_the_rule(retriever, question, expected):
    key, word = expected
    ev = selection_evidence(question, retriever.search(question, k=IDENTIFY_POOL), retriever.idf_lookup())
    assert ev is not None, "no sentence states the rule the question describes"
    assert ev["key"] == key
    hit, sentence = ev["sentences"][0]
    assert word in sentence.lower()                       # evidence about the rule, not about a related concept
    assert not sentence.rstrip().endswith("?")


@pytest.mark.parametrize("question", [
    "Which algorithm uses lottery tickets to pick the next process?",      # a topic the notes do not state
    "Which algorithm does Google use to rank web pages?",                   # not CPU scheduling at all
])
def test_no_evidence_means_no_algorithm_is_named(template_tutor, question):
    out = template_tutor.answer(question)
    assert "Answer:" not in out["text"]
    assert "won't guess" in out["text"] or out["in_scope"] is False


# ----------------------------------------------------------------------------- routing
def test_mentioning_a_concept_does_not_route_to_its_definition(template_tutor):
    q = "Which CPU scheduling algorithm selects the process that arrived earliest in the ready queue?"
    assert route(q).kind == "concept"
    out = template_tutor.answer(q)
    assert out["intent"] == "identify"
    assert out.get("title") not in DEFINITIONS and "ready queue holds" not in out["text"]


def test_a_definition_question_still_gets_the_definition(template_tutor):
    out = template_tutor.answer("What is the ready queue?")
    assert out["intent"] == "define"
    assert out["title"] == "What is the ready queue?"
    assert "ready to run" in out["text"]


# ----------------------------------------------------------------------------- final answer: grounded template
@pytest.mark.parametrize("question, expected", WHICH.items())
def test_template_answer_names_the_algorithm_first(template_tutor, question, expected):
    key, word = expected
    out = template_tutor.answer(question)
    assert LABEL[key] in answer_head(out)                  # the name is the headline
    assert answer_head(out).startswith("**Answer:")
    assert out.get("title") not in DEFINITIONS
    assert "[1]" in out["text"] and out["hits"], "the answer must cite the passage it quotes"
    assert word in out["text"].lower()


def test_convoy_answer_says_fcfs_can_cause_it(template_tutor):
    out = template_tutor.answer("Which scheduling algorithm can cause the convoy effect?")
    assert "FCFS" in answer_head(out) and "convoy" in out["text"].lower()


def test_comparison_covers_both_algorithms(template_tutor):
    out = template_tutor.answer("Differentiate between FCFS and Round Robin.")
    assert out["intent"] == "compare"
    assert "FCFS" in out["text"] and "Round Robin" in out["text"]


# ----------------------------------------------------------------------------- final answer: LLM path
class StubModel:
    """Stands in for Ollama: records the prompt, replies with a canned answer."""
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def __call__(self, model, prompt, **kw):
        self.prompts.append(prompt)
        return self.reply


@pytest.fixture
def llm_tutor(monkeypatch):
    def make(reply):
        stub = StubModel(reply)
        monkeypatch.setattr(tutor_module, "ollama_chat", stub)
        t = Tutor(use_llm=False)
        t.model = "stub"
        monkeypatch.setattr(t, "web_passages", lambda *a, **k: [])
        return t, stub
    return make


QUESTION = "Which CPU scheduling algorithm selects the process that arrived earliest in the ready queue?"


def test_llm_prompt_asks_for_the_name_and_carries_the_evidence(llm_tutor):
    t, stub = llm_tutor("**FCFS** runs the process that arrived first. [1]")
    out = t.answer(QUESTION)
    prompt = stub.prompts[0]
    assert "The student wants: identify" in prompt and "name of the algorithm" in prompt
    first_passage = prompt.split("[1]", 1)[1].split("[2]", 1)[0]
    assert "arrive" in first_passage and "first" in first_passage    # evidence passage is [1], not the ready-queue definition
    assert out["text"].startswith("**FCFS**")                         # a correct model answer is shown as written


def test_llm_answer_that_names_the_wrong_algorithm_is_replaced_by_the_evidence(llm_tutor):
    t, _ = llm_tutor("The ready queue is a data structure holding processes that wait for the CPU. [1]")
    out = t.answer(QUESTION)
    assert answer_head(out).startswith("**Answer: FCFS")
    assert any("did not name" in n for n in out["notes"])


def test_llm_path_without_evidence_does_not_fall_back_to_a_definition(llm_tutor):
    t, _ = llm_tutor("The course material does not say.")
    out = t.answer("Which algorithm uses lottery tickets to pick the next process?")
    assert "Answer:" not in out["text"]


# ----------------------------------------------------------------------------- numerical solving is untouched
NUMERICAL = ("Calculate average waiting time using FCFS for P1 (AT=0, BT=5), P2 (AT=1, BT=3), "
             "and P3 (AT=2, BT=1).")


def test_at_bt_notation_is_parsed_as_process_data():
    r = route(NUMERICAL)
    assert r.kind == "numerical" and r.algorithm == "fcfs"
    assert [(p.pid, p.arrival, p.burst) for p in r.processes] == [("P1", 0, 5), ("P2", 1, 3), ("P3", 2, 1)]


def test_numerical_question_gets_the_simulators_gantt_chart_and_averages(template_tutor):
    out = template_tutor.answer(NUMERICAL)
    res = out["result"]
    assert out["kind"] == "numerical"
    assert res["gantt"] == [("P1", 0, 5), ("P2", 5, 8), ("P3", 8, 9)]
    assert {r["pid"]: (r["completion"], r["turnaround"], r["waiting"]) for r in res["rows"]} == {
        "P1": (5, 5, 0), "P2": (8, 7, 4), "P3": (9, 7, 6)}
    assert res["avg_waiting"] == pytest.approx(10 / 3, abs=0.01)     # the simulator rounds to 2 decimals
    assert "3.33" in out["summary"]


@pytest.mark.parametrize("question, gantt", [
    ("SJF for P1 0 7, P2 2 4, P3 4 1, P4 5 4", [("P1", 0, 7), ("P3", 7, 8), ("P2", 8, 12), ("P4", 12, 16)]),
    ("SRTF for P1 0 8, P2 1 4, P3 2 9, P4 3 5", [("P1", 0, 1), ("P2", 1, 5), ("P4", 5, 10), ("P1", 10, 17),
                                                ("P3", 17, 26)]),
])
def test_other_algorithms_still_solve_correctly(template_tutor, question, gantt):
    assert template_tutor.answer(question)["result"]["gantt"] == gantt

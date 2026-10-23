"""Regression tests: multi-part questions are answered in full, and the conceptual fact check judges claims instead of
matching keywords.  Offline: Ollama is replaced by a stub, or the tutor runs in grounded-template mode.

    python -m pytest tests -q
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import concept_check as cc  # noqa: E402
import tutor as tutor_module  # noqa: E402
from eval import reference_sim as ref  # noqa: E402
from router import route  # noqa: E402
from scheduler import Process, solve  # noqa: E402
from tutor import Tutor, covers, parse_question_list  # noqa: E402

SIX_PART = """A CPU uses preemptive priority scheduling, where a lower numerical value indicates a higher priority.

A long-running process P1 has priority 5 and requires 20 CPU time units.

While P1 is waiting, new processes with priorities 1, 2, and 3 continue arriving. Assume higher-priority processes keep the CPU busy, preventing P1 from executing.

Answer the following questions:

1. Can P1 experience starvation? Explain why.
2. Is starvation the same as the convoy effect? Explain the difference.
3. What is aging in operating systems?
4. Explain how aging could help P1 eventually execute.
5. Does aging guarantee that starvation will never occur under every possible scheduling policy? Explain the limitations.
6. Give a practical example illustrating starvation and aging.

Use technically accurate explanations. Distinguish established scheduling concepts from assumptions made in this scenario."""


@pytest.fixture(scope="module")
def template_tutor():
    return Tutor(use_llm=False)


@pytest.fixture(autouse=True)
def _log_to_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(cc, "LOG_PATH", tmp_path / "verification.jsonl")


class StubModel:
    def __init__(self, *replies):
        self.replies, self.prompts = replies, []

    def __call__(self, model, prompt, **kw):
        self.prompts.append(prompt)
        return self.replies[min(len(self.prompts), len(self.replies)) - 1]


@pytest.fixture
def llm_tutor(monkeypatch):
    def make(*replies):
        stub = StubModel(*replies)
        monkeypatch.setattr(tutor_module, "ollama_chat", stub)
        monkeypatch.setenv("OSTUTOR_NO_SHORTCUT", "1")
        t = Tutor(use_llm=False)
        t.model = "stub"
        monkeypatch.setattr(t, "web_passages", lambda *a, **k: [])
        return t, stub
    return make


def _parts(text):
    """{n: body} for the '**Part n: ...**' blocks of a multi-part answer, in the order they appear."""
    import re
    blocks = re.split(r"\n\n---\n\n", text)
    return [(int(re.match(r"\*\*Part (\d+):", b).group(1)), b) for b in blocks]


# ------------------------------------------------------------------ 1. the six-part question
def test_six_part_question_answers_every_part_in_order(template_tutor):
    out = template_tutor.answer(SIX_PART)
    assert out["kind"] == "multi" and out["in_scope"]
    parts = _parts(out["text"])
    assert [n for n, _ in parts] == [1, 2, 3, 4, 5, 6]
    low = {n: b.lower() for n, b in parts}
    assert "starv" in low[1]                                                    # 1 can P1 starve
    assert "convoy" in low[2] and "starv" in low[2]                             # 2 convoy vs starvation
    assert "aging" in low[3] and "priority" in low[3]                           # 3 what is aging
    assert "aging" in low[4] and "priority" in low[4]                           # 4 how aging helps P1
    assert "guarantee" in low[5] and "not" in low[5]                            # 5 no universal guarantee
    assert "example" in low[6] or "print server" in low[6]                      # 6 practical example
    assert "could not find" not in out["text"]                                  # nothing silently dropped or refused
    assert out["status"]["label"].startswith("Answered 6 of 6 parts")


def test_six_part_question_with_the_model_is_not_replaced_by_a_single_fallback(llm_tutor):
    good = {  # one reply per call is enough: every part gets a rule-clean answer
        "p1": "Yes. Under preemptive priority scheduling P1 can starve: if higher-priority processes keep arriving, P1 may "
              "never get the CPU. This depends on the workload, so it is a possibility, not a certainty. [1]"}
    t, stub = llm_tutor(good["p1"])
    out = t.answer(SIX_PART)
    assert out["kind"] == "multi" and [n for n, _ in _parts(out["text"])] == [1, 2, 3, 4, 5, 6]
    assert len(stub.prompts) >= 1
    # the scenario reached the model as a premise, and the question of that part is stated separately
    assert "Scenario and instructions given by the student" in stub.prompts[0]
    assert "P1 has priority 5" in stub.prompts[0] and "Distinguish established scheduling concepts" in stub.prompts[0]


@pytest.mark.parametrize("q, n", [
    ("1. What is aging?\n2. What is starvation?", 2),
    ("1) What is aging?\n2) What is starvation?\n3) What is the convoy effect?", 3),
    ("- What is aging?\n- What is starvation?\n- What is the convoy effect?", 3),
    ("a) What is aging?\nb) What is starvation?", 2),
    ("1. What is aging and\n   why is it needed?\n2. What is starvation?", 2),               # wrapped line is joined
])
def test_lists_in_every_common_format_are_parsed(q, n):
    plan = parse_question_list(q)
    assert plan and len(plan["items"]) == n
    assert plan["items"][0].startswith("What is aging")


def test_list_keeps_scenario_and_closing_instruction_apart_from_the_questions():
    plan = parse_question_list(SIX_PART)
    assert len(plan["items"]) == 6 and plan["items"][0] == "Can P1 experience starvation? Explain why."
    assert "P1 has priority 5" in plan["scenario"] and "Distinguish established" in plan["scenario"]
    assert "Answer the following" not in plan["scenario"]


@pytest.mark.parametrize("q", [
    "What is round robin?",
    "Compare FCFS and Round Robin",
    "1. FCFS\n2. SJF\n3. Priority",                              # a plain list of names is not a list of questions
    "Explain SJF.",
])
def test_ordinary_and_non_question_lists_are_not_treated_as_multipart(q):
    assert parse_question_list(q) is None


def test_prose_questions_beyond_three_are_all_answered(template_tutor):
    out = template_tutor.answer("Can starvation occur in SJF? What is aging? Is the convoy effect the same as starvation? "
                                "How does Round Robin avoid starvation?")
    assert out["kind"] == "multi" and [n for n, _ in _parts(out["text"])] == [1, 2, 3, 4]


def test_a_list_around_a_scheduling_problem_still_goes_to_the_simulator(template_tutor):
    out = template_tutor.answer("Round Robin quantum 2: P1 0 5, P2 1 3, P3 2 1.\n1. What is the average waiting time?\n"
                                "2. What is the Gantt chart?")
    assert out["kind"] == "numerical" and out["result"]["quantum"] == 2


# ------------------------------------------------------------------ 2-4. starvation, convoy effect, aging
def test_starvation_under_sjf_and_srtf_is_workload_dependent(template_tutor):
    for q in ("Can starvation occur in SJF?", "Can starvation occur in SRTF?"):
        out = template_tutor.answer(q)
        t = out["text"].lower()
        assert "yes" in t and "keep arriving" in t and ("long job" in t or "long jobs" in t)
        assert not cc.rule_problems(out["text"]) and "always starve" not in t and "will always" not in t
    for claim in ("SJF starves long jobs only if shorter jobs keep arriving.",
                  "Starvation is possible in SRTF, but it depends on the arrival pattern."):
        assert cc.rule_problems(claim) == []
    assert cc.rule_problems("SJF will always starve long jobs.")                 # certain starvation is wrong


def test_convoy_effect_is_distinguished_from_starvation(template_tutor):
    out = template_tutor.answer("Is starvation the same as the convoy effect? Explain the difference.")
    t = out["text"].lower()
    assert "convoy" in t and "fcfs" in t and "finite" in t and "indefinite" in t
    assert cc.verify("Is starvation the same as the convoy effect?", out["text"])["ok"]
    for wrong in ("The convoy effect is another name for starvation.",
                  "The convoy effect is also known as starvation.",
                  "Convoy effect is just a different word for starvation."):
        assert any("convoy" in p for p in cc.rule_problems(wrong)), wrong
    assert cc.rule_problems("The convoy effect is a performance problem associated with FCFS, not starvation.") == []


def test_aging_is_explained_without_universal_guarantees(template_tutor):
    out = template_tutor.answer("Does aging guarantee that starvation will never occur under every possible scheduling "
                                "policy")
    t = out["text"].lower()
    assert "no, not in every case" in t and "not a guarantee" in t and "mitigation" in t and "assumptions" in t
    assert cc.rule_problems(out["text"]) == []
    assert any("aging" in p for p in cc.rule_problems("Aging guarantees that starvation can never happen in any scheduler."))
    assert any("aging" in p for p in cc.rule_problems("Aging ensures every process eventually runs in any system."))
    for fine in ("Aging does not guarantee freedom from starvation under every policy.",
                 "Aging mitigates starvation; it is not a guarantee in every workload.",
                 "With a positive aging rate, aging lets every waiting process eventually run under priority scheduling."):
        assert cc.rule_problems(fine) == [], fine


# ------------------------------------------------------------------ 5-6. keyword matching vs. meaning
@pytest.mark.parametrize("claim", [
    "Under preemptive priority scheduling, P1 will never get its turn and will wait indefinitely, illustrating starvation.",
    "Priority scheduling can cause starvation of low-priority processes, which never get the CPU while others keep arriving.",
    "A low-priority job that never runs because higher-priority jobs keep arriving is starved.",
    "SRTF may starve long processes indefinitely, whereas FCFS never starves a process once it has arrived.",
    "Starvation is not inevitable: it only occurs when the workload keeps supplying better-ranked processes.",
])
def test_correct_claims_with_suspicious_keywords_are_not_rejected(claim):
    assert cc.rule_problems(claim) == [] and cc.absolute_claims(claim) == [] and cc.contradictions(claim) == []


@pytest.mark.parametrize("claim", [
    "SJF never causes starvation.",
    "Priority scheduling cannot starve a process.",
    "Starvation is impossible in priority scheduling.",
    "There is no starvation in SJF.",
    "FCFS can starve short processes.",
    "The convoy effect is a form of starvation.",
    "SJF will always starve long jobs.",
])
def test_incorrect_universal_claims_are_flagged(claim):
    assert cc.rule_problems(claim), claim


def test_claims_are_classified_as_correct_incorrect_conditional_or_uncertain():
    ctx = ("Starvation is indefinite blocking. Priority scheduling can starve a process if higher-priority processes keep "
           "arriving. Aging gradually raises priority.")
    got = {c["sentence"]: c["verdict"] for c in cc.classify_claims(
        "SJF never causes starvation. Priority scheduling can starve a process if higher-priority processes keep arriving. "
        "Starvation is indefinite blocking. Round Robin never starves a process.", ctx)}
    assert got["SJF never causes starvation."] == "incorrect"
    assert got["Priority scheduling can starve a process if higher-priority processes keep arriving."] == "conditional"
    assert got["Starvation is indefinite blocking."] == "correct"
    assert got["Round Robin never starves a process."] == "conditional"            # true only under standard assumptions


def test_a_long_multipart_answer_is_not_judged_by_one_topic_spec():
    assert cc.spec_for(SIX_PART)[0] is None and cc.is_compound(SIX_PART)
    assert cc.spec_for("What is the difference between convoy effect and starvation?")[0] == "convoy_vs_starvation"


# ------------------------------------------------------------------ 7. incomplete answers: detected and repaired
def test_coverage_is_semantic_not_a_paragraph_count():
    assert covers("What is aging in operating systems?", "Aging gradually raises the priority of a waiting process.")
    assert not covers("Explain how aging could help P1 eventually execute.", "Round Robin gives each process a time quantum.")
    assert not covers("Is starvation the same as the convoy effect?", "FCFS is non-preemptive.\n\nSJF is optimal.\n\nRR is fair.")


def test_a_part_that_misses_its_question_is_repaired_once(template_tutor, monkeypatch):
    real = Tutor._answer
    calls = []

    def flawed(self, question):
        if "aging could help" in question:
            calls.append(question)
            return {"kind": "concept", "algorithm": "rr", "result": None, "hits": [], "notes": [], "mode": "stub",
                    "in_scope": True, "text": "Round Robin gives each process a time quantum."}
        return real(self, question)

    monkeypatch.setattr(Tutor, "_answer", flawed)
    out = template_tutor.answer(SIX_PART)
    part4 = dict(_parts(out["text"]))[4].lower()
    assert len(calls) == 1                                                       # the repair is bounded: no extra loop
    assert "aging" in part4 and "time quantum" not in part4
    assert any("answered again from a keyword search" in n for n in out["notes"])


def test_a_part_that_cannot_be_repaired_is_listed_not_dropped(template_tutor, monkeypatch):
    real = Tutor._answer
    monkeypatch.setattr(Tutor, "_repair", lambda self, part, o: o)
    monkeypatch.setattr(Tutor, "_answer", lambda self, q: ({"kind": "concept", "algorithm": None, "result": None, "hits": [],
                        "notes": [], "mode": "stub", "in_scope": False, "text": "outside my scope"}
                        if "aging could help" in q else real(self, q)))
    out = template_tutor.answer(SIX_PART)
    parts = dict(_parts(out["text"]))
    assert sorted(parts) == [1, 2, 3, 4, 5, 6]
    assert "could not find this in the course material" in parts[4]
    assert any(n.startswith("Part 4 could not be answered") for n in out["notes"])
    assert out["status"]["label"].startswith("Answered 5 of 6 parts")


# ------------------------------------------------------------------ 8. missing or contradictory source evidence
def test_a_source_that_breaks_the_fact_rules_is_disclosed_not_trusted_silently():
    bad = {"text": "FCFS can starve short processes when a long process arrives first.", "title": "A bad note",
           "source": "notes/x.md"}
    good = {"text": "Standard FCFS does not cause starvation.", "title": "Good", "source": "notes/y.md"}
    notes = Tutor._source_warnings([bad, good])
    assert len(notes) == 1 and "A bad note" in notes[0] and "not relied on" in notes[0] and "FCFS" in notes[0]
    assert Tutor._source_warnings([good]) == []


def test_contradicting_passages_are_disclosed():
    a = {"text": "Round Robin can cause starvation of processes.", "title": "A", "source": "n/a.md"}
    b = {"text": "Round Robin does not cause starvation of processes.", "title": "B", "source": "n/b.md"}
    notes = Tutor._source_warnings([a, b])
    assert notes and "disagree" in notes[-1]


def test_no_evidence_means_no_invented_citation(template_tutor):
    out = template_tutor.answer("What is the capital of France? And how does a B-tree stay balanced?")
    assert out["in_scope"] is False and out["hits"] == []
    assert not any(c in out["text"] for c in ("[1]", "[2]"))


def test_unsupported_but_not_wrong_sentences_are_kept_with_a_qualification(llm_tutor):
    extra = ("Real systems often combine priority queues with periodic boosting of waiting threads, so starvation is rare "
             "in practice.")
    reply = "Yes. If shorter jobs keep arriving, a long job may be passed over again and again, which is starvation. " + extra
    t, stub = llm_tutor(reply)
    q = "Can starvation occur in SJF?"
    out = t.answer(q)
    assert len(stub.prompts) == tutor_module.MAX_REGENERATIONS + 1               # one targeted retry, then qualify
    assert extra in out["text"]                                                  # the complete answer is NOT thrown away
    assert any("beyond the retrieved course passages" in n for n in out["notes"]) and out.get("limitation")
    assert out["status"]["level"] == "unverified" and "not backed" in out["status"]["label"]


def test_a_real_error_still_falls_back_to_the_vetted_answer(llm_tutor):
    t, stub = llm_tutor("FCFS can starve short processes.")
    out = t.answer("Can starvation occur in SJF?")
    assert "FCFS can starve" not in out["text"] and any("fact check" in n for n in out["notes"])


# ------------------------------------------------------------------ 9. simple questions are unchanged
def test_simple_question_keeps_its_concise_answer(template_tutor):
    out = template_tutor.answer("What is round robin??")
    assert out["kind"] == "concept" and "Part 1" not in out["text"] and len(out["text"].split()) < 140


def test_two_and_three_part_prose_questions_still_use_the_original_format(template_tutor):
    out = template_tutor.answer("What is a time quantum? Why does a small quantum increase overhead?")
    assert out["kind"] == "multi" and out["text"].count("**Part ") == 2 and "Answered" in out["status"]["label"]


# ------------------------------------------------------------------ 10. numerical results are untouched
PROCS = [("P1", 0, 7, 3), ("P2", 2, 4, 1), ("P3", 4, 1, 4), ("P4", 5, 4, 2), ("P5", 12, 3, 1)]


@pytest.mark.parametrize("algo, q", [("fcfs", None), ("sjf", None), ("srtf", None), ("priority", None),
                                     ("priority_p", None), ("rr", 3)])
def test_all_algorithms_match_the_independent_reference(algo, q):
    got = solve(algo, [Process(*p) for p in PROCS], q)
    exp = ref.metrics(algo, PROCS, q)
    for row in got["rows"]:
        e = exp["rows"][row["pid"]]
        assert (row["completion"], row["turnaround"], row["waiting"], row["response"]) == \
               (e["completion"], e["turnaround"], e["waiting"], e["response"]), (algo, row)
    assert got["avg_waiting"] == pytest.approx(exp["avg_waiting"], abs=0.005)


def test_a_numerical_question_inside_the_new_code_path_is_answered_by_the_simulator(template_tutor):
    out = template_tutor.answer("SRTF: P1 0 8, P2 1 4, P3 2 9, P4 3 5. Average waiting time?")
    assert out["kind"] == "numerical" and out["result"]["avg_waiting"] == 6.5 and out["status"]["level"] == "verified"
    assert route("Round robin P1 arrives 0 burst 24, P2 0 3, P3 0 3 quantum 4").kind == "numerical"

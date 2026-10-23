"""A scenario followed by several questions (numbered or running text) gets every question answered; a model answer
that merely repeats the question is rejected.   python -m pytest tests -q"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import tutor as tutor_module  # noqa: E402
from tutor import Tutor, echoes_question, split_bundle  # noqa: E402

SCENARIO = """A CPU uses preemptive priority scheduling, where a lower numerical value indicates a higher priority.

A long-running process P1 has priority 5 and requires 20 CPU time units.

While P1 is waiting, new processes with priorities 1, 2, and 3 continue arriving. Assume higher-priority processes keep the CPU busy, preventing P1 from executing.

Answer the following questions:

Can P1 experience starvation? Explain why. Is starvation the same as the convoy effect? Explain the difference. What is aging in operating systems? Explain how aging could help P1 eventually execute. Does aging guarantee that starvation will never occur under every possible scheduling policy? Explain the limitations. Give a practical example illustrating starvation and aging. Use technically accurate explanations. Distinguish established scheduling concepts from assumptions made in this scenario."""


def test_split_bundle_finds_the_six_questions_and_two_directives():
    scenario, items, directives = split_bundle(SCENARIO)
    assert len(items) == 6
    assert items[0] == "Can P1 experience starvation? Explain why."           # "Explain why." belongs to its question
    assert items[1].endswith("Explain the difference.")
    assert items[3].startswith("Explain how aging")                            # a real request, not a follow-up
    assert items[5].startswith("Give a practical example")
    assert len(directives) == 2 and directives[0].startswith("Use technically")
    assert "P1 has priority 5" in scenario and "Answer the following" not in scenario


@pytest.mark.parametrize("q", ["What is aging?", "Why is SJF optimal, and why can't real systems use it?",
                               "Solve RR q=2: P1 0 5 P2 1 3 P3 2 1. What is the average waiting time? What is the Gantt chart?"])
def test_ordinary_questions_are_not_bundles(q):
    assert split_bundle(q) is None


def test_every_question_is_answered(monkeypatch):
    out = Tutor(use_llm=False).answer(SCENARIO)
    text = out["text"].lower()
    assert out["kind"] == "multi"
    assert all(f"part {i}:" in text for i in range(1, 7))
    for word in ("convoy", "aging", "starvation"):
        assert word in text
    assert "established concepts vs. assumptions" in text and "assumptions you supplied" in text
    assert "differences" not in text.split("part 1")[0]                        # the old garbage heading


def test_echo_of_the_question_is_detected_and_rejected(monkeypatch):
    questions = [l.strip() for l in SCENARIO.split("Answer the following questions:")[1].replace("? ", "?\n").splitlines() if l.strip()]
    echo = "**Differences**\n\n" + "\n".join("- " + x for x in questions[:4])
    assert echoes_question(SCENARIO, echo)
    assert not echoes_question("What is aging?", "Aging gradually raises the priority of a waiting process.\nIt prevents starvation.\nIt is used in priority scheduling.")

    t = Tutor(use_llm=False)
    t.model = "stub"
    monkeypatch.setattr(t, "web_passages", lambda *a, **k: [])
    monkeypatch.setattr(tutor_module, "ollama_chat", lambda *a, **k: "**Differences**\n\n- What is aging in operating systems?\n- Explain how aging could help a process.\n- Is starvation the same as the convoy effect?")
    out = t.answer("What is aging in operating systems? Explain how aging could help a process. Is starvation the same as the convoy effect?")
    assert "- What is aging in operating systems?" not in out["text"]


def test_doubled_question_marks_do_not_make_a_bundle():
    assert split_bundle("which CPU Scheduling algorithm is the most efficient one? And why so??") is None
    assert split_bundle("What is aging??? Why does it matter???") is None


def test_scenario_written_as_one_line_is_still_a_bundle_not_a_practice_request():
    import re
    out = Tutor(use_llm=False).answer(re.sub(r"\s*\n+\s*", " ", SCENARIO))
    assert out["kind"] == "multi" and "practice problem" not in out["text"].lower()
    assert all(f"part {i}:" in out["text"].lower() for i in range(1, 7))


def test_a_real_process_table_is_never_treated_as_a_bundle():
    out = Tutor(use_llm=False).answer("Round Robin q=2. P1 0 5 P2 1 3 P3 2 1. What is the average waiting time? What is the Gantt chart? What is the average turnaround time?")
    assert out["kind"] != "multi"

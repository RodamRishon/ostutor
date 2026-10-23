"""A question with two parts must have BOTH parts answered, each from its own passage.   python -m pytest tests -q"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from tutor import Tutor, split_parts  # noqa: E402


@pytest.fixture(scope="module")
def tutor():
    return Tutor(use_llm=False)


@pytest.mark.parametrize("q,n", [
    ("Why is SJF optimal for average waiting time, and why can't real systems use it?", 2),
    ("What is a time quantum? Why does a small quantum increase overhead?", 2),
    ("What is the difference between FCFS and SJF?", 1),                         # 'and' inside one question
    ("Compare FCFS and Round Robin", 1),
    ("Which algorithm can cause starvation and how can it be fixed?", 1),        # 'it' has nothing to refer to
    ("Solve RR q=2: P1 0 5, P2 1 3 and what is the average waiting time?", 1),   # a numerical problem is never split
])
def test_split(q, n):
    assert len(split_parts(q)) == n


def test_pronoun_is_resolved_to_the_algorithm():
    assert split_parts("Why is SJF optimal, and why can't real systems use it?")[1].endswith("SJF?")


def test_both_parts_are_answered(tutor):
    out = tutor.answer("Why is SJF optimal for average waiting time, and why can't real systems use it?")
    assert out["kind"] == "multi" and out["in_scope"]
    text = out["text"].lower()
    assert "part 1" in text and "part 2" in text
    assert "swap" in text                       # why SJF is optimal
    assert "estimat" in text or "in advance" in text   # why it is not used in practice
    assert out["status"]["level"] in ("stored", "checked", "verified")


def test_citations_point_at_their_own_passage(tutor):
    out = tutor.answer("What is a time quantum? Why does a small quantum increase overhead?")
    first = len(tutor._answer("What is a time quantum?")["hits"])      # part 2's [1] is shifted past part 1's passages
    assert "[1]" in out["text"] and f"[{first + 1}]" in out["text"] and len(out["hits"]) > first


def test_off_topic_second_part_is_not_smuggled_in(tutor):
    out = tutor.answer("What is SJF and how does B-tree indexing work?")
    assert "B-tree" not in out["text"] and any("B-tree" in n or "What is SJF" in n for n in out["notes"])


def test_all_off_topic_is_still_refused(tutor):
    assert tutor.answer("How does a B-tree work, and why is it balanced?")["in_scope"] is False

"""A problem statement that merely says "verify" must be solved, not graded; real check-my-answer inputs still are."""
import pathlib

import pytest

from router import detect_algorithms, route
from tutor import Tutor

PROMPT = (pathlib.Path(__file__).parent / "priority_preemptive_prompt.txt").read_text(encoding="utf-8").strip()


def test_solve_prompt_with_verify_instruction_is_numerical():
    r = route(PROMPT)
    assert r.kind == "numerical" and r.algorithm == "priority_p" and len(r.processes) == 4


def test_tie_break_rule_is_not_a_second_algorithm():
    assert detect_algorithms(PROMPT) == ["priority_p"]
    assert detect_algorithms("Solve with SJF. If two processes have the same burst time use FCFS.") == ["sjf"]
    assert detect_algorithms("RR q=2; ties are broken by FCFS") == ["rr"]
    assert detect_algorithms("Compare FCFS and SJF") == ["sjf", "fcfs"]       # a real comparison is untouched


def test_full_answer_has_no_not_quite_banner():
    out = Tutor().answer(PROMPT)
    assert out["kind"] == "numerical"
    assert "Not quite" not in out["text"] and "❌" not in out["text"]
    assert "4.50" in out["text"] and "8.75" in out["text"] and "3.00" in out["text"]
    assert "| P1 | P2 | P3 | P1 | P4 |" in out["text"]


@pytest.mark.parametrize("text", [
    "Check my answer: FCFS P1 0 5 P2 1 3. My answer: average waiting = 2",
    "Is my answer correct? RR q=2 P1 0 5 P2 1 3 gantt P1 0-2 P2 2-4",
    "verify this: P1 0 5 P2 1 3 FCFS, waiting P1=0 P2=4",
    "FCFS P1 0 5 P2 1 3 I got average waiting = 3, verify",
    "Please grade my solution for SJF P1 0 5 P2 1 3",
])
def test_real_check_requests_still_route_to_check(text):
    assert route(text).kind == "check"


@pytest.mark.parametrize("text", [
    "Verify every calculation. SJF P1 0 5 P2 1 3",
    "Solve using SRTF and verify the results with the formulas. P1 0 7 P2 2 4 P3 4 1",
])
def test_verify_instruction_alone_is_not_a_check(text):
    assert route(text).kind == "numerical"

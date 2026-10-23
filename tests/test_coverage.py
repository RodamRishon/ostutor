"""Coverage guard: every on-topic CPU-scheduling question must get a real answer (no refusal, no
"not in the notes"), and every off-topic question must be refused.  Offline (no LLM).

    python -m pytest tests/test_coverage.py -q

Add new questions to tests/coverage_questions.txt (answerable) or tests/offtopic_questions.txt (refused).
"""
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tutor import Tutor  # noqa: E402


def _lines(name):
    return [l.strip() for l in (ROOT / "tests" / name).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]


@pytest.fixture(scope="module")
def tutor():
    return Tutor(use_llm=False) if "use_llm" in Tutor.__init__.__code__.co_varnames else Tutor()


@pytest.mark.parametrize("q", _lines("coverage_questions.txt"))
def test_on_topic_question_is_answered(tutor, q):
    out = tutor.answer(q)
    assert out["in_scope"] is not False, q
    assert len(out["text"]) > 40, q


@pytest.mark.parametrize("q", _lines("offtopic_questions.txt"))
def test_off_topic_question_is_refused(tutor, q):
    assert tutor.answer(q)["in_scope"] is False, q

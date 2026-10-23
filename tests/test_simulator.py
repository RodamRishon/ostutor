"""The simulator against an independent reference (eval/reference_sim.py) and against hand-verified textbook cases,
plus the invariants that must hold for any schedule and the controlled failures for invalid input."""
import pathlib
import random
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import reference_sim as ref  # noqa: E402
from scheduler import Process, solve  # noqa: E402

ALGOS = ["fcfs", "sjf", "srtf", "priority", "priority_p", "rr"]


def rand_case(rng):
    n = rng.randint(1, 7)
    return [(f"P{i+1}", rng.randint(0, 12), rng.randint(1, 9), rng.randint(0, 4)) for i in range(n)], rng.randint(1, 5)


def run_sim(algo, procs, q):
    return solve(algo, [Process(*p) for p in procs], q if algo == "rr" else None)


@pytest.mark.parametrize("algo", ALGOS)
def test_matches_independent_reference_on_random_workloads(algo):
    rng = random.Random(2024)
    for _ in range(300):
        procs, q = rand_case(rng)
        res, exp = run_sim(algo, procs, q), ref.metrics(algo, procs, q)
        for r in res["rows"]:
            e = exp["rows"][r["pid"]]
            assert (r["completion"], r["turnaround"], r["waiting"], r["response"]) == \
                   (e["completion"], e["turnaround"], e["waiting"], e["response"]), (algo, procs, q, r)
        assert [tuple(g) for g in res["gantt"]] == ref.runs(exp["timeline"]), (algo, procs, q)
        assert res["avg_waiting"] == pytest.approx(exp["avg_waiting"], abs=0.005)


@pytest.mark.parametrize("algo", ALGOS)
def test_invariants_hold_for_every_schedule(algo):
    rng = random.Random(7)
    for _ in range(200):
        procs, q = rand_case(rng)
        res = run_sim(algo, procs, q)
        gantt = res["gantt"]
        assert all(a[2] <= b[1] for a, b in zip(gantt, gantt[1:]))                          # intervals never overlap
        for r in res["rows"]:
            assert r["turnaround"] == r["completion"] - r["arrival"]
            assert r["waiting"] == r["turnaround"] - r["burst"] >= 0
            assert r["response"] == r["start"] - r["arrival"] >= 0 and r["response"] <= r["waiting"]
            ran = sum(e - s for p, s, e in gantt if p == r["pid"])
            assert ran == r["burst"]                                                        # every process gets exactly its burst
            assert all(s >= r["arrival"] for p, s, e in gantt if p == r["pid"])            # never runs before it arrives
        busy = sum(e - s for p, s, e in gantt if p != "idle")
        assert busy == sum(p[2] for p in procs)


# Hand-verified textbook cases (Silberschatz-style): independent of both implementations.
HAND = [
    ("fcfs", [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)], None, [0, 24, 27], 17.0),
    ("rr", [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)], 4, [6, 4, 7], 17 / 3),
    ("sjf", [("P1", 0, 7, 0), ("P2", 2, 4, 0), ("P3", 4, 1, 0), ("P4", 5, 4, 0)], None, [0, 6, 3, 7], 4.0),
    ("srtf", [("P1", 0, 7, 0), ("P2", 2, 4, 0), ("P3", 4, 1, 0), ("P4", 5, 4, 0)], None, [9, 1, 0, 2], 3.0),
    ("priority", [("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 4), ("P4", 0, 1, 5), ("P5", 0, 5, 2)], None, [6, 0, 16, 18, 1], 8.2),
]


@pytest.mark.parametrize("algo, procs, q, waits, avg", HAND)
def test_textbook_cases(algo, procs, q, waits, avg):
    res = run_sim(algo, procs, q)
    assert [r["waiting"] for r in res["rows"]] == waits
    assert res["avg_waiting"] == pytest.approx(avg, abs=0.005)


def test_idle_period_is_a_gap_in_the_chart_and_not_counted_as_waiting():
    res = run_sim("fcfs", [("P1", 0, 2, 0), ("P2", 5, 3, 0)], None)
    assert res["gantt"] == [("P1", 0, 2), ("idle", 2, 5), ("P2", 5, 8)]
    assert [r["waiting"] for r in res["rows"]] == [0, 0]


def test_priority_ties_go_to_earlier_arrival_then_input_order_and_equal_priority_never_preempts():
    res = run_sim("priority", [("P1", 0, 3, 2), ("P2", 0, 3, 2)], None)
    assert [g[0] for g in res["gantt"]] == ["P1", "P2"]
    res = run_sim("priority_p", [("P1", 0, 5, 2), ("P2", 1, 2, 2)], None)
    assert [g[0] for g in res["gantt"]] == ["P1", "P2"]          # equal priority does not preempt
    res = run_sim("priority_p", [("P1", 0, 5, 2), ("P2", 1, 2, 1)], None)
    assert [g[0] for g in res["gantt"]] == ["P1", "P2", "P1"]


def test_round_robin_queue_order_at_a_quantum_boundary():
    res = run_sim("rr", [("P1", 0, 6, 0), ("P2", 3, 2, 0), ("P3", 3, 4, 0)], 3)
    assert [g[0] for g in res["gantt"]] == ["P1", "P2", "P3", "P1", "P3"]      # arrivals at t=3 queue before P1


def test_zero_context_switch_cost_is_the_documented_model():
    import scheduler
    assert "context" in scheduler.__doc__.lower() and "zero" in scheduler.__doc__.lower()


@pytest.mark.parametrize("procs, algo, q", [
    ([], "fcfs", None),                                           # empty input
    ([("P1", 0, 0, 0)], "fcfs", None),                            # zero burst
    ([("P1", 0, -3, 0)], "sjf", None),                            # negative burst
    ([("P1", -1, 3, 0)], "fcfs", None),                           # negative arrival
    ([("P1", 0, 3, 0)], "rr", 0),                                 # zero quantum
    ([("P1", 0, 3, 0)], "rr", -2),                                # negative quantum
    ([("P1", 0, 3, 0)], "rr", None),                              # missing quantum
    ([("P1", 0, 3, 0), ("P1", 1, 2, 0)], "fcfs", None),           # duplicate pid
    ([("P1", 0, 3, 0)], "lottery", None),                         # unknown algorithm
    ([("P1", 0, 2.5, 0)], "fcfs", None),                          # non-integer burst
])
def test_invalid_input_is_a_controlled_value_error(procs, algo, q):
    with pytest.raises(ValueError):
        solve(algo, [Process(*p) for p in procs], q)

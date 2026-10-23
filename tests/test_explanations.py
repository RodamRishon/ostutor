"""Numerical accuracy and explanation quality for the CPU Scheduling Tutor.

The simulator is the single source of truth. These tests check, for FCFS, non-preemptive SJF, SRTF, Round Robin and
both priority variants, that (1) its schedules agree with an independent reference simulator, (2) every per-process
metric obeys TAT = CT - AT, WT = TAT - BT, RT = first start - AT and every average is computed from those rows with
the right n and round-half-up, (3) the chronological explanation reproduces the Gantt chart exactly (arrivals,
preemptions, remaining times, ready queue, tie-breaks, idle time), (4) the derivations and averages quote the table,
and (5) the answer a student sees is built from that structure, with no stray spelling notes or repeated sentences.
"""
import random
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "eval"))

import explain
import numeric_guard as ng
import reference_sim
import tutor
from scheduler import Process, check_invariants, mean2, solve

CASES = [("fcfs", None), ("sjf", None), ("srtf", None), ("rr", 2), ("rr", 3), ("priority", None), ("priority_p", None)]
IDS = [f"{a}{'' if q is None else q}" for a, q in CASES]

SCENARIOS = {
    "preemption": [("P1", 0, 8, 3), ("P2", 2, 4, 1), ("P3", 3, 2, 2), ("P4", 5, 3, 4)],
    "simultaneous": [("P1", 0, 5, 2), ("P2", 0, 3, 1), ("P3", 0, 3, 1)],
    "idle": [("P1", 0, 2, 1), ("P2", 6, 3, 2), ("P3", 7, 1, 1)],
    "tie": [("P1", 0, 4, 2), ("P2", 1, 3, 2), ("P3", 1, 3, 2), ("P4", 2, 3, 2)],
    "rr_expiry": [("P1", 0, 5, 1), ("P2", 2, 3, 1), ("P3", 3, 2, 1)],
    "lone": [("P1", 0, 5, 1), ("P2", 10, 2, 1)],
}


def procs(name):
    return [Process(*row) for row in SCENARIOS[name]]


def tuples(name):
    return [tuple(r) for r in SCENARIOS[name]]


def run(algo, q, name):
    return solve(algo, procs(name), q)


ALL = [(a, q, n) for a, q in CASES for n in SCENARIOS]
ALL_IDS = [f"{i}-{n}" for i, (a, q) in zip(IDS, CASES) for n in SCENARIOS]


def step_time(line):
    m = re.match(r"t=(\d+):", line)
    assert m, f"step line without a time stamp: {line!r}"
    return int(m.group(1))


# ------------------------------------------------------------------ 1. the simulator against an independent reference
@pytest.mark.parametrize("algo,q,name", ALL, ids=ALL_IDS)
def test_simulator_matches_the_independent_reference(algo, q, name):
    res = run(algo, q, name)
    ref = reference_sim.metrics(algo, tuples(name), q)
    assert check_invariants(res) == []
    for row in res["rows"]:
        want = ref["rows"][row["pid"]]
        for k in ("completion", "turnaround", "waiting", "response", "start"):
            assert row[k] == want[k], (row["pid"], k)
    for col in ("waiting", "turnaround", "response"):
        assert abs(res["avg_" + col] - ref["avg_" + col]) <= 0.005 + 1e-9


def test_random_schedules_match_the_reference_and_the_definitions():
    rng = random.Random(20261023)
    for _ in range(120):
        algo, q = rng.choice(CASES)
        n = rng.randint(1, 6)
        spec = [(f"P{i + 1}", rng.randint(0, 9), rng.randint(1, 7), rng.randint(1, 4)) for i in range(n)]
        res = solve(algo, [Process(*s) for s in spec], q)
        assert check_invariants(res) == [], (algo, q, spec)
        _, timeline = reference_sim.simulate(algo, spec, q)
        assert [tuple(g) for g in res["gantt"]] == reference_sim.runs(timeline), (algo, q, spec)


# ------------------------------------------------------------------ 2. per-process metrics and averages
@pytest.mark.parametrize("algo,q,name", ALL, ids=ALL_IDS)
def test_metric_formulas_and_averages(algo, q, name):
    res = run(algo, q, name)
    rows, n = res["rows"], len(res["rows"])
    for r in rows:
        assert r["turnaround"] == r["completion"] - r["arrival"]
        assert r["waiting"] == r["turnaround"] - r["burst"]
        assert r["response"] == r["start"] - r["arrival"]
        assert r["waiting"] >= 0 and r["response"] >= 0 and r["response"] <= r["waiting"]
    for col in ("waiting", "turnaround", "response"):
        assert res["avg_" + col] == mean2([r[col] for r in rows])
        assert abs(res["avg_" + col] - sum(r[col] for r in rows) / n) <= 0.005 + 1e-9


def test_averages_round_half_up_not_half_even():
    # 33 / 8 = 4.125 exactly: Python's round() and f"{x:.2f}" give 4.12 (half-even); the table must say 4.13.
    assert mean2([4, 4, 4, 4, 4, 4, 4, 5]) == 4.13
    assert mean2([1, 0]) == 0.5 and mean2([1, 1, 2]) == 1.33 and mean2([2, 2, 3]) == 2.33 and mean2([5, 6, 6, 6]) == 5.75
    spec = [Process(f"P{i + 1}", 0, 1) for i in range(8)]                    # FCFS: waits 0..7, sum 28, 28/8 = 3.5
    assert solve("fcfs", spec)["avg_waiting"] == 3.5


# ------------------------------------------------------------------ 3. the chronological explanation matches the chart
@pytest.mark.parametrize("algo,q,name", ALL, ids=ALL_IDS)
def test_steps_replay_reproduces_the_gantt_chart(algo, q, name):
    res = run(algo, q, name)
    st = explain.steps(res)
    assert st.consistent, "the rule replay disagrees with the simulator for this schedule"
    times = [step_time(line) for line in st.lines]
    assert times == sorted(times)                                              # chronological
    assert len(set(st.lines)) == len(st.lines)                                 # nothing said twice
    text = "\n".join(st.lines)
    for r in res["rows"]:                                                      # every completion, at the simulator's time
        assert re.search(rf"t={r['completion']}: {r['pid']} completes \(CT = {r['completion']}\)", text), r["pid"]
    for pid, s, e in res["gantt"]:
        if pid == "idle":
            assert re.search(rf"t={s}: .*idle until t={e}", text)
    for r in res["rows"]:                                                      # every process is introduced when it arrives
        assert re.search(rf"t={r['arrival']}: .*\b{r['pid']}\b", text), r["pid"]


@pytest.mark.parametrize("algo,q", [c for c in CASES if c[0] != "rr"], ids=[i for i, c in zip(IDS, CASES) if c[0] != "rr"])
def test_idle_period_is_explained(algo, q):
    res = run(algo, q, "idle")
    assert ("idle", 2, 6) in [tuple(g) for g in res["gantt"]]
    assert "t=2: no process is ready, so the CPU is idle until t=6." in explain.steps(res).lines


def test_round_robin_idle_and_lone_process():
    res = run("rr", 2, "lone")
    lines = explain.steps(res).lines
    assert any(l.startswith("t=2: P1 is the only process in the queue") for l in lines)
    assert "t=5: the ready queue is empty, so the CPU is idle until t=10." in lines
    assert explain.steps(res).consistent


def test_round_robin_arrival_at_quantum_expiry_is_queued_before_the_preempted_process():
    res = run("rr", 2, "rr_expiry")
    lines = explain.steps(res).lines
    assert [g[0] for g in res["gantt"][:3]] == ["P1", "P2", "P1"]
    assert any("P2 arrived at this very instant, so it is queued before P1. Queue now: [P2, P1]." in l for l in lines)
    assert any("from t=0 to t=2; its remaining time goes from 5 to 3" in l for l in lines)


def test_srtf_preemption_names_the_remaining_times():
    res = solve("srtf", [Process("P1", 0, 8), Process("P2", 1, 4), Process("P3", 2, 9), Process("P4", 3, 5)])
    lines = explain.steps(res).lines
    assert [g[0] for g in res["gantt"]][:2] == ["P1", "P2"]
    pre = next(l for l in lines if l.startswith("t=1:") and "preempts" in l)
    assert "P2 (remaining 4) arrives and preempts P1 (remaining 7)" in pre and "7 unit(s) of its burst left" in pre


def test_priority_preemption_and_non_preemption_are_both_explained():
    res = run("priority_p", None, "preemption")
    lines = explain.steps(res).lines
    assert any(l.startswith("t=2:") and "P2" in l and "preempts P1" in l and "strictly better" in l for l in lines)
    assert any(l.startswith("t=3:") and "P3" in l and "does not preempt P2" in l for l in lines)
    assert [tuple(g) for g in res["gantt"]] == [("P1", 0, 2), ("P2", 2, 6), ("P3", 6, 8), ("P1", 8, 14), ("P4", 14, 17)]


def test_non_preemptive_algorithms_never_claim_a_preemption():
    for algo in ("fcfs", "sjf", "priority"):
        for name in SCENARIOS:
            assert not any("preempts" in l.replace("does not preempt", "") for l in explain.steps(run(algo, None, name)).lines)


@pytest.mark.parametrize("algo", ["sjf", "srtf", "priority", "priority_p", "fcfs"])
def test_tie_break_is_named_exactly_when_there_is_a_tie(algo):
    text = "\n".join(explain.steps(run(algo, None, "tie")).lines)
    if algo == "fcfs":
        assert "Tie-break: P2 and P3 arrived at the same time (t=1)" in text and "P2 is listed first" in text
    else:                                                                      # P2, P3, P4 are equal on the key; arrival then input order decide
        assert "Tie-break: P2, P3 and P4 tie on" in text and "the earlier arrival wins" in text
        assert "P3 and P4 tie on" in text                                      # and again for the two that are left
    free = "\n".join(explain.steps(run(algo, None, "idle")).lines)            # no two processes compete in the idle scenario
    assert "Tie-break" not in free


def test_simultaneous_arrivals_are_announced_together():
    lines = explain.steps(run("sjf", None, "simultaneous")).lines
    assert lines[0].startswith("t=0: P1 (burst 5), P2 (burst 3) and P3 (burst 3) arrive together")


# ------------------------------------------------------------------ 4. derivations, averages and checks quote the table
@pytest.mark.parametrize("algo,q,name", ALL, ids=ALL_IDS)
def test_derivations_and_averages_quote_the_rows(algo, q, name):
    res = run(algo, q, name)
    text = "\n".join(explain.derivations(res))
    M = explain.MINUS
    for r in res["rows"]:
        want = (f"**{r['pid']}** (arrival {r['arrival']}, burst {r['burst']}" )
        assert want in text
        assert f"CT = {r['completion']}; TAT = CT {M} AT = {r['completion']} {M} {r['arrival']} = {r['turnaround']}; " in text
        assert f"WT = TAT {M} BT = {r['turnaround']} {M} {r['burst']} = {r['waiting']}" in text
        assert f"RT = first CPU start {M} AT = {r['start']} {M} {r['arrival']} = {r['response']}" in text
    avg = "\n".join(explain.averages(res))
    n = len(res["rows"])
    for col, label in (("waiting", "waiting"), ("turnaround", "turnaround"), ("response", "response")):
        vals = " + ".join(str(r[col]) for r in res["rows"])
        total = sum(r[col] for r in res["rows"])
        assert f"Average {label} time = ({vals}) / {n} = {total} / {n} = **{res['avg_' + col]:.2f}**" in avg


@pytest.mark.parametrize("algo,q,name", ALL, ids=ALL_IDS)
def test_whole_explanation_passes_the_numeric_guard(algo, q, name):
    res = run(algo, q, name)
    out = explain.render(res, chart=True)
    verdict = ng.validate(out, res)
    assert verdict.ok, [str(c) for c in getattr(verdict, "claims", [])][:3]
    assert explain.steps(res).consistent


def test_random_schedules_replay_consistently_and_pass_the_guard():
    rng = random.Random(7)
    for _ in range(150):
        algo, q = rng.choice(CASES)
        n = rng.randint(1, 6)
        res = solve(algo, [Process(f"P{i + 1}", rng.randint(0, 8), rng.randint(1, 6), rng.randint(1, 3)) for i in range(n)], q)
        st = explain.steps(res)
        assert st.consistent and len(set(st.lines)) == len(st.lines)
        assert ng.validate(explain.render(res, chart=False), res).ok


# ------------------------------------------------------------------ 5. the answer the student sees
PROMPT = (ROOT / "tests" / "priority_preemptive_prompt.txt").read_text().strip()


def sentences(text):
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", body) if len(s.strip()) > 40]


def test_priority_prompt_answers_every_requested_item_in_order():
    out = tutor.Tutor(use_llm=False).answer(PROMPT)
    assert out["kind"] == "numerical" and out["result"]["algorithm"] == "priority_p"
    s = out["summary"]
    assert [tuple(g) for g in out["result"]["gantt"]] == [("P1", 0, 2), ("P2", 2, 6), ("P3", 6, 8), ("P1", 8, 14), ("P4", 14, 17)]
    for token in ("**Step 1: scheduling decisions**", "**Step 2: how each time is derived**", "**Step 3: averages**", "**Checks**"):
        assert token in s
    assert s.index("Step 1") < s.index("Step 2") < s.index("Step 3")
    for pid, ct, tat, wt, rt in (("P1", 14, 14, 6, 0), ("P2", 6, 4, 0, 0), ("P3", 8, 5, 3, 3), ("P4", 17, 12, 9, 9)):
        assert f"**{pid}**" in s and f"CT = {ct}; TAT" in s and f"= {tat}; WT" in s
    assert "Average waiting time = (6 + 0 + 3 + 9) / 4 = 18 / 4 = **4.50**" in s
    assert "Average turnaround time = (14 + 4 + 5 + 12) / 4 = 35 / 4 = **8.75**" in s
    assert "Average response time = (0 + 0 + 3 + 9) / 4 = 12 / 4 = **3.00**" in s
    assert "t=2: P2 (priority 1, remaining 4) arrives and preempts P1 (priority 3, remaining 6)" in s
    assert "6 unit(s) of its burst left" in s


def test_priority_prompt_has_no_noise_or_contradictions():
    out = tutor.Tutor(use_llm=False).answer(PROMPT)
    assert out["notes"] == []                                                  # no spelling or routing notes on a solved problem
    assert "Not quite" not in out["summary"] and "Not quite" not in out["text"]
    assert out["status"]["level"] == "verified"
    assert ng.validate(out["summary"], out["result"]).ok and ng.validate(out["text"], out["result"]).ok
    seen = sentences(out["summary"])
    assert len(seen) == len(set(seen)), "a sentence is repeated"
    assert explain.unmatched_requests(PROMPT) == []                            # all seven numbered requests are answerable


def test_requests_the_simulator_cannot_answer_are_reported_not_skipped():
    q = "Solve FCFS: P1 0 5 P2 1 3.\n1. The Gantt chart.\n2. Draw the ER diagram of the database.\n3. Average waiting time."
    assert explain.requested_items(q) == ["The Gantt chart.", "Draw the ER diagram of the database.", "Average waiting time."]
    assert explain.unmatched_requests(q) == ["Draw the ER diagram of the database"]
    out = tutor.Tutor(use_llm=False).answer(q)
    assert any("Not answered" in n and "ER diagram" in n for n in out["notes"])


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_every_algorithm_answer_is_built_from_the_simulator(algo, q):
    name = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": f"Round Robin quantum {q}", "priority": "non-preemptive priority",
            "priority_p": "preemptive priority"}[algo]
    spec = SCENARIOS["preemption"]
    rows = " ".join(f"{p} {a} {b}" + (f" {pr}" if algo.startswith("priority") else "") for p, a, b, pr in spec)
    out = tutor.Tutor(use_llm=False).answer(f"Solve using {name}: {rows}")
    assert out["kind"] == "numerical" and out["result"]["algorithm"] == algo and out["notes"] == []
    res = solve(algo, [Process(*r) for r in spec], q)
    assert out["result"]["gantt"] == res["gantt"]
    strip = lambda rows: [{k: v for k, v in r.items() if k != "priority"} for r in rows]       # priority is not an input of the others
    assert strip(out["result"]["rows"]) == strip(res["rows"])
    assert ng.validate(out["summary"], res).ok and ng.validate(out["text"], res).ok
    for col in ("waiting", "turnaround", "response"):
        assert f"**{res['avg_' + col]:.2f}**" in out["summary"]


class _Stub(tutor.Tutor):
    def __init__(self, text):
        super().__init__(use_llm=False)
        self.model = "stub-model"
        self._text = text

    def _generate(self, question, hits, result=None, web_hits=None, revision=None):
        return self._text, []


def test_a_wrong_model_explanation_never_reaches_the_summary_and_is_corrected_in_the_text():
    prompt = "Solve using SRTF: P1 0 8 P2 1 4 P3 2 9 P4 3 5"
    res = tutor.Tutor(use_llm=False).answer(prompt)["result"]
    wrong = f"Average waiting time = ({' + '.join(str(r['waiting']) for r in res['rows'])}) / 4 = **{res['avg_waiting'] + 1.5:.2f}**"
    out = _Stub(wrong).answer(prompt)
    bad = f"{res['avg_waiting'] + 1.5:.2f}"
    assert bad not in out["summary"] and bad not in out["text"]
    assert f"**{res['avg_waiting']:.2f}**" in out["summary"] and out["corrections"]
    assert ng.validate(out["text"], res).ok

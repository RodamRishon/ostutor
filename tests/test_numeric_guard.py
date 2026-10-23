"""The deterministic simulator is the single source of truth for every scheduling number.

An LLM explanation is checked claim by claim against the simulator result: per-process completion / turnaround /
waiting / response times, the three averages, the Gantt chart and event times. A wrong number is corrected in place,
and the diagnostic names the claim, what the explanation said, what the simulator gives and what it was corrected to.

The explanations used here are generated FROM the simulator result (so the tests are not tied to hand-written
examples), then corrupted one number at a time.
"""
import pytest

import numeric_guard as ng
import tutor
from checker import check_answer, parse_student_answer
from scheduler import Process, gantt_text, solve, table_text

PROCS = [Process("P1", 0, 7, 2), Process("P2", 2, 4, 1), Process("P3", 4, 1, 3), Process("P4", 5, 4, 2)]
GAP = [Process("P1", 0, 2, 1), Process("P2", 6, 3, 2), Process("P3", 7, 1, 1)]          # the CPU idles from 2 to 6
CASES = [("fcfs", None), ("sjf", None), ("srtf", None), ("rr", 2), ("priority", None), ("priority_p", None)]
IDS = [a for a, _ in CASES]


def result(algo, q, procs=PROCS):
    return solve(algo, procs, q)


def explanation(res):
    """What a faithful explanation of `res` looks like, in the formats a model really writes."""
    out = ["Gantt chart:", "```", gantt_text(res["gantt"]), "```",
           "Segments: " + ", ".join(f"{p} ({s}-{e})" for p, s, e in res["gantt"]), "", table_text(res), ""]
    for r in res["rows"]:
        out.append(f"{r['pid']} arrives at t={r['arrival']} and completes at t={r['completion']}.")
        out.append(f"Waiting time of {r['pid']} is {r['turnaround']} - {r['burst']} = {r['waiting']}.")
        out.append(f"- {r['pid']}: CT = {r['completion']}, TAT = {r['completion']} - {r['arrival']} = {r['turnaround']}, "
                   f"WT = {r['waiting']}, RT = {r['start']} - {r['arrival']} = {r['response']}")
    n = len(res["rows"])
    for col, name in (("waiting", "waiting"), ("turnaround", "turnaround"), ("response", "response")):
        vals = " + ".join(str(r[col]) for r in res["rows"])
        out.append(f"Average {name} time = ({vals}) / {n} = **{res['avg_' + col]:.2f}**")
    return "\n".join(out)


# ------------------------------------------------------------------ a faithful explanation is never touched
@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
@pytest.mark.parametrize("procs", [PROCS, GAP], ids=["plain", "idle-gap"])
def test_faithful_explanation_passes_unchanged(algo, q, procs):
    res = result(algo, q, procs)
    text = explanation(res)
    rep = ng.validate(text, res)
    assert rep.ok and rep.text == text, rep.messages
    assert rep.claims >= 6 * len(res["rows"]) + 3        # it really did look at the per-process and average claims


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_the_simulators_own_text_never_trips_the_guard(algo, q):
    res = result(algo, q)
    for text in (tutor.template_numerical(res, []), tutor.numerical_summary(res, []), "\n".join(res["log"])):
        assert ng.validate(text, res).ok


# ------------------------------------------------------------------ process-level metrics, in every format
FORMATS = {
    "prefix": "{pid} {label} = {v}",
    "of": "{label} of {pid} is {v}",
    "abbrev": "- {pid}: {abbr} = {v}",
    "working": None,
}
LABELS = {"completion": ("completion time", "CT"), "turnaround": ("turnaround time", "TAT"),
          "waiting": ("waiting time", "WT"), "response": ("response time", "RT")}


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
@pytest.mark.parametrize("metric", sorted(LABELS))
@pytest.mark.parametrize("fmt", ["prefix", "of", "abbrev"])
def test_wrong_process_metric_is_corrected_with_a_precise_message(algo, q, metric, fmt):
    res = result(algo, q)
    label, abbr = LABELS[metric]
    for row in res["rows"]:
        good = FORMATS[fmt].format(pid=row["pid"], label=label, abbr=abbr, v=row[metric])
        wrong = FORMATS[fmt].format(pid=row["pid"], label=label, abbr=abbr, v=row[metric] + 3)
        assert ng.validate(good, res).ok
        rep = ng.validate(wrong, res)
        assert rep.text == good and not rep.unresolved
        (issue,) = rep.issues
        assert issue.claimed == str(row[metric] + 3) and issue.expected == str(row[metric])
        for must in (row["pid"], str(row[metric] + 3), str(row[metric]), "corrected"):
            assert must in issue.message, (must, issue.message)
        assert ng.validate(rep.text, res).ok            # the corrected text passes on a second look


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_wrong_working_is_replaced_by_the_simulators_working(algo, q):
    res = result(algo, q)
    row = res["rows"][1]
    good = f"Waiting time of {row['pid']} = {row['turnaround']} - {row['burst']} = {row['waiting']}"
    wrong = f"Waiting time of {row['pid']} = {row['turnaround']} - {row['burst'] + 1} = {row['waiting'] - 1}"
    rep = ng.validate(wrong, res)
    assert [i.kind for i in rep.issues] == ["metric"] and rep.text == good.replace(" - ", " − ")
    # an inconsistent chain whose last value is right is still caught
    odd = f"Waiting time of {row['pid']} = {row['turnaround']} - {row['burst'] + 1} = {row['waiting']}"
    assert ng.validate(odd, res).issues


# ------------------------------------------------------------------ averages
@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
@pytest.mark.parametrize("col", ["waiting", "turnaround", "response"])
def test_wrong_average_is_corrected(algo, q, col):
    res = result(algo, q)
    n = len(res["rows"])
    vals = " + ".join(str(r[col]) for r in res["rows"])
    true = res["avg_" + col]
    for good, wrong in ((f"Average {col} time = ({vals}) / {n} = **{true:.2f}**", f"Average {col} time = ({vals}) / {n} = **{true + 0.75:.2f}**"),
                        (f"The average {col} time is {true:.2f}.", f"The average {col} time is {true + 0.75:.2f}.")):
        rep = ng.validate(wrong, res)
        assert rep.text == good and not rep.unresolved
        (issue,) = rep.issues
        assert issue.kind == "average" and issue.claimed == f"{true + 0.75:.2f}" and issue.expected == f"{true:.2f}"
        assert f"said {true + 0.75:.2f}" in issue.message and f"gives {true:.2f}" in issue.message and f"corrected to {true:.2f}" in issue.message


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_average_working_is_not_mistaken_for_the_average(algo, q):
    """The old check read the first number of '(14 + 4 + 5 + 12) / 4 = 8.75' as the average and called a correct
    explanation wrong."""
    res = result(algo, q)
    n = len(res["rows"])
    vals = " + ".join(str(r["turnaround"]) for r in res["rows"])
    text = f"Average turnaround time = ({vals}) / {n} = {res['avg_turnaround']:.2f}"
    assert tutor.verify_llm_numbers(text, res) == []
    assert tutor.verify_llm_numbers(text.replace(f"= {res['avg_turnaround']:.2f}", "= 99.00"), res)


def test_rounding_the_student_states_is_accepted_but_a_different_value_is_not():
    res = result("fcfs", None)
    avg = res["avg_waiting"]
    assert ng.validate(f"Average waiting time = {round(avg, 1)}", res).ok
    assert not ng.validate(f"Average waiting time = {round(avg, 1) + 0.5}", res).ok


# ------------------------------------------------------------------ tables
@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_every_wrong_table_cell_is_found_and_restored(algo, q):
    res = result(algo, q)
    good = table_text(res)
    lines = good.split("\n")
    header = [c.strip() for c in lines[0].strip("|").split("|")]
    checked = 0
    for li in range(2, len(lines)):
        cells = lines[li].strip().strip("|").split("|")
        for ci in range(1, len(cells)):
            if header[ci] == "Priority":
                continue
            wrong_cells = list(cells)
            wrong_cells[ci] = f" {int(cells[ci]) + 2} "
            wrong = "\n".join(lines[:li] + ["|" + "|".join(wrong_cells) + "|"] + lines[li + 1:])
            rep = ng.validate(wrong, res)
            assert rep.text == good and len(rep.issues) == 1 and not rep.unresolved, (li, ci, rep.messages)
            checked += 1
    assert checked == len(res["rows"]) * (len(header) - 1 - ("Priority" in header))      # every metric cell, not the pid


def test_average_row_of_a_table_is_checked():
    res = result("srtf", None)
    rows = "\n".join(f"| {r['pid']} | {r['waiting']} | {r['turnaround']} |" for r in res["rows"])
    good = f"| Process | Waiting | Turnaround |\n|---|---|---|\n{rows}\n| **Average** | {res['avg_waiting']:.2f} | {res['avg_turnaround']:.2f} |"
    assert ng.validate(good, res).ok
    rep = ng.validate(good.replace(f"{res['avg_turnaround']:.2f} |", "12.34 |"), res)
    assert rep.text == good and rep.issues[0].subject == "average turnaround time"


# ------------------------------------------------------------------ Gantt chart
@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_wrong_gantt_bar_is_replaced_by_the_simulators_chart(algo, q):
    res = result(algo, q)
    good = gantt_text(res["gantt"])
    bar, axis = good.split("\n")
    nums = axis.split()
    wrong_axis = axis.replace(nums[1], str(int(nums[1]) + 1), 1)
    rep = ng.validate(f"{bar}\n{wrong_axis}", res)
    assert rep.text == good and rep.issues[0].kind == "gantt"
    assert "simulator's chart" in rep.issues[0].message and wrong_axis.split()[1] in rep.issues[0].message
    # processes in the wrong order
    names = [g[0] for g in res["gantt"]]
    if len(set(names)) > 1:
        swapped = bar.replace(names[0], "@", 1).replace(names[1], names[0], 1).replace("@", names[1], 1)
        if swapped != bar:
            assert ng.validate(f"{swapped}\n{axis}", res).text == good


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_wrong_segment_list_is_corrected(algo, q):
    res = result(algo, q)
    segs = res["gantt"]
    good = ", ".join(f"{p} ({s}-{e})" for p, s, e in segs)
    p, s, e = segs[1]
    wrong = ", ".join(f"{pp} ({ss}-{ee + (1 if k == 1 else 0)})" if k != 1 else f"{pp} ({ss}-{ee + 1})" for k, (pp, ss, ee) in enumerate(segs))
    rep = ng.validate(wrong, res)
    assert rep.text == good and rep.issues[0].kind == "gantt"


def test_a_single_misplaced_segment_is_pointed_at():
    res = result("priority_p", None)
    p, s, e = next(g for g in res["gantt"] if g[0] == "P3")
    rep = ng.validate(f"P3 runs from {s + 1} to {e + 1}.", res)
    assert rep.text == f"P3 runs from {s} to {e}." and f"{s}–{e}" in rep.issues[0].message


# ------------------------------------------------------------------ events and decisions
def test_event_times_are_checked():
    res = result("priority_p", None)
    row = {r["pid"]: r for r in res["rows"]}
    wrong = (f"P2 arrives at t={row['P2']['arrival'] + 1}. At t={row['P3']['completion'] + 2}, P3 completes. "
             f"P2 preempts P1 at t={row['P2']['arrival'] + 1}.")
    rep = ng.validate(wrong, res)
    assert rep.text == (f"P2 arrives at t={row['P2']['arrival']}. At t={row['P3']['completion']}, P3 completes. "
                        f"P2 preempts P1 at t={row['P2']['arrival']}.") and len(rep.issues) == 3


def test_a_wrong_scheduling_decision_cannot_be_patched_and_is_reported_as_unresolved():
    res = result("sjf", None)
    t = 0
    who = res["gantt"][0][0]
    other = next(r["pid"] for r in res["rows"] if r["pid"] != who)
    rep = ng.validate(f"At t={t}, {other} runs because it is the shortest.", res)
    assert not rep.issues and len(rep.unresolved) == 1
    m = rep.unresolved[0].message
    assert other in m and who in m and f"t={t}" in m


def test_a_process_that_is_not_in_the_problem_is_reported():
    res = result("fcfs", None)
    rep = ng.validate("P9 waiting time = 4", res)
    assert rep.unresolved and "P9" in rep.unresolved[0].message


# ------------------------------------------------------------------ the pipeline: generation -> verification -> display
class _Stub(tutor.Tutor):
    """A tutor whose 'model' returns a fixed explanation (so the real generation/verification path runs offline)."""

    def __init__(self, text):
        super().__init__(use_llm=False)
        self.model = "stub-model"
        self._text = text

    def _generate(self, question, hits, result=None, web_hits=None, revision=None):
        return self._text, []


def question(algo, q, procs=PROCS):
    rows = " ".join(f"P{i + 1} {p.arrival} {p.burst}" + (f" {p.priority}" if algo.startswith("priority") else "") for i, p in enumerate(procs))
    name = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": f"Round Robin quantum {q}", "priority": "non-preemptive priority",
            "priority_p": "preemptive priority"}[algo]
    return f"Solve using {name}: {rows}"


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_pipeline_corrects_a_wrong_explanation_before_display(algo, q):
    prompt = question(algo, q)
    t0 = tutor.Tutor(use_llm=False).answer(prompt)
    res = t0["result"]
    assert t0["kind"] == "numerical" and res["algorithm"] == algo
    good = explanation(res)
    wrong = good.replace(f"= **{res['avg_waiting']:.2f}**", f"= **{res['avg_waiting'] + 1.25:.2f}**", 1)
    victim = res["rows"][2]
    wrong = wrong.replace(f"Waiting time of {victim['pid']} is {victim['turnaround']} - {victim['burst']} = {victim['waiting']}.",
                          f"Waiting time of {victim['pid']} is {victim['turnaround']} - {victim['burst']} = {victim['waiting'] + 2}.")
    out = _Stub(wrong).answer(prompt)
    assert out["kind"] == "numerical"
    assert f"{res['avg_waiting'] + 1.25:.2f}" not in out["text"]                  # the wrong value never reaches the student
    assert f"= **{res['avg_waiting']:.2f}**" in out["text"]
    assert len(out["corrections"]) == 2
    assert any("corrected" in n for n in out["notes"])
    assert out["status"]["level"] == "verified" and "2 number(s)" in out["status"]["label"]
    assert out["numeric_check"]["unresolved"] == 0
    # the rest of the explanation, and the simulator's own solution, are still there
    assert "Segments:" in out["text"] and "Verified by the simulator" in out["text"]
    assert ng.validate(out["text"], res).ok                                      # nothing wrong remains anywhere in the response


@pytest.mark.parametrize("algo,q", CASES, ids=IDS)
def test_pipeline_leaves_a_correct_explanation_alone(algo, q):
    prompt = question(algo, q)
    res = tutor.Tutor(use_llm=False).answer(prompt)["result"]
    good = explanation(res)
    out = _Stub(good).answer(prompt)
    assert out["text"].startswith(good) and not out.get("corrections")
    assert not any("corrected" in n or "contradicted" in n for n in out["notes"])
    assert out["status"]["label"].endswith("definitions")


def test_pipeline_withholds_an_explanation_that_contradicts_a_scheduling_decision():
    prompt = question("sjf", None)
    res = tutor.Tutor(use_llm=False).answer(prompt)["result"]
    first = res["gantt"][0][0]
    other = next(r["pid"] for r in res["rows"] if r["pid"] != first)
    out = _Stub(f"At t=0, {other} runs first because it is shortest.").answer(prompt)
    assert "Verified by the simulator" not in out["text"] and out["text"].startswith("**Shortest Job First")
    note = next(n for n in out["notes"] if "left out" in n)
    assert f"{other} runs at t=0" in note and first in note
    assert out["status"]["level"] == "verified"


def test_pipeline_withholds_an_explanation_with_a_wrong_formula():
    prompt = question("fcfs", None)
    out = _Stub("Waiting time = completion time - burst time - 1, so FCFS is simple.").answer(prompt)
    note = next(n for n in out["notes"] if "left out" in n)
    assert "wrong formula" in note and "correct: waiting = turnaround" in note


def test_worked_example_explanation_is_corrected_too():
    t = _Stub("")
    out0 = tutor.Tutor(use_llm=False).answer("Explain round robin with a numerical example")
    res = out0["result"]
    t._text = explanation(res).replace(f"= **{res['avg_waiting']:.2f}**", f"= **{res['avg_waiting'] + 2:.2f}**", 1)
    t._generate = lambda q, hits, result=None, web_hits=None, revision=None: (t._text, [])
    out = t.answer("Explain round robin with a numerical example")
    if out["result"]["rows"] == res["rows"]:                  # (the generated example is random: compare only if identical)
        assert f"{res['avg_waiting'] + 2:.2f}" not in out["text"]
    assert ng.validate(out["text"], out["result"]).ok


# ------------------------------------------------------------------ diagnostics of the answer checker
def test_checker_reads_the_value_of_a_worked_expression_not_its_first_number():
    ans = parse_student_answer("waiting P1 = 14 - 8 = 6, P2 = 0; average waiting time = (6 + 0 + 3 + 9) / 4 = 4.5")
    assert ans["waiting"] == {"P1": 6.0, "P2": 0.0} and ans["avg_waiting"] == 4.5


def test_checker_message_names_the_claim_the_expected_value_and_the_working():
    res = result("fcfs", None)
    wrong = res["avg_waiting"] + 1
    vals = " + ".join(str(r["waiting"]) for r in res["rows"])
    v = check_answer(res, f"average waiting time = ({vals}) / {len(res['rows'])} = {wrong}")
    assert not v["correct"]
    assert f"Your average waiting time is {wrong:g}" in v["first_error"]          # the claim (not the first number of the working)
    assert f"correct is {res['avg_waiting']:.2f}" in v["first_error"]              # the expected value
    right = check_answer(res, f"average waiting time = ({vals}) / {len(res['rows'])} = {res['avg_waiting']}")
    assert right["correct"]


# ------------------------------------------------------------------ nothing else changed
def test_no_model_means_no_numeric_check_and_the_same_answer():
    out = tutor.Tutor(use_llm=False).answer(question("rr", 2))
    assert "corrections" not in out and "numeric_check" not in out
    assert out["status"]["level"] == "verified" and out["text"].startswith("**Round Robin")


# ------------------------------------------------------------------ the phrasings a model really uses
_PP = solve("priority_p", [Process("P1", 0, 8, 3), Process("P2", 2, 4, 1), Process("P3", 3, 2, 2), Process("P4", 5, 3, 4)])

FAITHFUL = [
    "P1 has a burst time of 8 and arrives at time 0 with priority 3.",
    "Process P2 arrives at t=2 (priority 1) and preempts P1 at time 2.",
    "The Gantt chart is P1 (0-2) → P2 (2-6) → P3 (6-8) → P1 (8-14) → P4 (14-17).",
    "Gantt: P1: 0–2, P2: 2–6, P3: 6–8, P1: 8–14, P4: 14–17",
    "Waiting Time (WT) = Turnaround Time − Burst Time, so WT for P1 = 14 − 8 = 6.",
    "Avg WT = 4.5 and Avg TAT = 8.75.",
    "AWT = 4.50, ATAT = 8.75, ART = 3.00",
    "Average waiting time for the 4 processes is 4.50 time units.",
    "Average waiting time for P1, P2, P3 and P4 is (6+0+3+9)/4 = 4.5",
    "TAT(P1) = CT − AT = 14 − 0 = 14",
    "Response time of P3 = 6 − 3 = 3, since P3 first runs at t=6.",
    "- **P2**: WT = 0, TAT = 4, RT = 0",
    "P1 was preempted at t=2 after running for 2 units and resumes at t=8.",
    "Total waiting time = 18, so the average is 18/4 = 4.5.",
    "Waiting time: P1 = 6, P2 = 0, P3 = 3, P4 = 9",
    "Completion times: P1 = 14, P2 = 6, P3 = 8, P4 = 17.",
    "P3 completes at time 8, then P1 resumes and finishes at 14.",
    "At t=2, P2 preempts P1; at t=6, P3 runs.",
]
WRONG = [   # (wrong text, what the guard must turn it into)
    ("P1 has a burst time of 9 and arrives at time 0.", "P1 has a burst time of 8 and arrives at time 0."),
    ("The Gantt chart is P1 (0-2) → P2 (2-6) → P1 (6-12) → P3 (12-14) → P4 (14-17).",
     "The Gantt chart is P1 (0-2) → P2 (2-6) → P3 (6-8) → P1 (8-14) → P4 (14-17)."),
    ("Avg WT = 4.75", "Avg WT = 4.50"),
    ("AWT = 5.00", "AWT = 4.50"),
    ("TAT(P1) = CT − AT = 14 − 0 = 13", "TAT(P1) = CT − AT = 14 − 0 = 14"),
    ("WT = TAT - BT: P2 waiting time = 4 - 4 = 1", "WT = TAT - BT: P2 waiting time = 4 − 4 = 0"),
    ("Response time of P3 = 5 − 3 = 2", "Response time of P3 = 6 − 3 = 3"),
    ("Waiting time: P1 = 6, P2 = 1, P3 = 3, P4 = 9", "Waiting time: P1 = 6, P2 = 0, P3 = 3, P4 = 9"),
    ("Completion times: P1 = 14, P2 = 7, P3 = 8, P4 = 17.", "Completion times: P1 = 14, P2 = 6, P3 = 8, P4 = 17."),
    ("- **P2**: WT = 0, TAT = 5, RT = 0", "- **P2**: WT = 0, TAT = 4, RT = 0"),
    ("Average waiting time for the 4 processes is 4.00 time units.", "Average waiting time for the 4 processes is 4.50 time units."),
    ("Average turnaround time = (14 + 4 + 5 + 12) / 4 = **9.00**.", "Average turnaround time = (14 + 4 + 5 + 12) / 4 = **8.75**."),
]


@pytest.mark.parametrize("text", FAITHFUL)
def test_faithful_phrasings_are_not_flagged(text):
    rep = ng.validate(text, _PP)
    assert rep.ok and rep.text == text, rep.messages


@pytest.mark.parametrize("wrong,fixed", WRONG)
def test_wrong_phrasings_are_corrected(wrong, fixed):
    rep = ng.validate(wrong, _PP)
    assert rep.text == fixed and not rep.unresolved and rep.issues
    assert all(i.claimed != i.expected and "simulator" in i.message for i in rep.issues)
    assert ng.validate(rep.text, _PP).ok

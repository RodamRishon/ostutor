"""Stress test: does the tutor answer exactly what each prompt asks?

Each prompt carries the facts a correct answer must contain (`must`: every regex has to match) and
content that must not appear (`must_not`).  Numerical prompts are checked against simulator values.
The prompts are written the way students really type: abbreviations, typos, "rr vs sjf", one-line
questions with no context.  None of the wording is copied from the training data.

    python evaluate_answers.py                # full pipeline, uses the Ollama model if one is running
    python evaluate_answers.py --no-llm       # retrieval + template mode only (fast)
    python evaluate_answers.py -v             # print every answer
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import time

from tutor import Tutor, bad_formulas, ungrounded_numbers

ROOT = pathlib.Path(__file__).parent

# kind: concept | refuse | numerical
# must: regexes that must ALL match (case-insensitive); must_not: none may match.
CASES = [
    # ---- FCFS
    ("concept", "what is fcfs", [r"first", r"arriv|order|queue"], []),
    ("concept", "how does first come first served pick the next process", [r"arriv|head|queue|order"], []),
    ("concept", "advantages of fcfs", [r"simple", r"starv|fair|overhead"], []),
    ("concept", "what are the drawbacks of FCFS scheduling?", [r"convoy|waiting"], []),
    ("concept", "is fcfs preemptive", [r"non-?preemptive"], []),
    ("concept", "can fcfs starve a process", [r"\bno\b|not|cannot|doesn.t", r"starv|eventually|forever|head"], []),
    ("concept", "explain the convoy effect", [r"long", r"short", r"wait"], []),
    ("concept", "wat is convoy effect in fcfs", [r"long", r"short|wait"], []),
    ("concept", "two processes arrive at the same time in FCFS who goes first", [r"lower|first|list|number|order"], []),
    ("concept", "when would you use fcfs", [r"batch|simple|overhead"], []),
    # ---- SJF
    ("concept", "what is sjf", [r"shortest", r"burst"], []),
    ("concept", "explain shortest job first in simple words", [r"shortest|smallest|fewest", r"burst|next|smallest|pages"], []),
    ("concept", "why is sjf optimal", [r"waiting", r"short|minimum|optimal"], []),
    ("concept", "disadvantages of sjf", [r"starv|predict|know|advance"], []),
    ("concept", "does sjf cause starvation", [r"\byes\b|can|starv", r"long"], []),
    ("concept", "how is next cpu burst predicted", [r"exponential|average|previous|past|α"], []),
    ("concept", "what happens in SJF when two jobs have same burst time", [r"arriv|FCFS|earlier|lower|first"], []),
    ("concept", "is sjf preemptive", [r"non-?preemptive|SRTF|shortest remaining"], []),
    # ---- SRTF
    ("concept", "what is srtf", [r"remaining|preempt"], []),
    ("concept", "difference b/w sjf and srtf", [r"preempt", r"non-?preemptive|SJF"], []),
    ("concept", "how does shortest remaining time first work step by step", [r"remaining", r"preempt|arriv|shorter"], []),
    ("concept", "srtf pros and cons", [r"waiting|response|short", r"context|starv|predict|know"], []),
    # ---- Priority
    ("concept", "what is priority scheduling", [r"priority", r"highest|lower|number|first"], []),
    ("concept", "in priority scheduling does a lower number mean higher priority", [r"lower|smaller|1"], []),
    ("concept", "preemptive vs non preemptive priority scheduling", [r"preempt", r"arriv|immediately|wait|finish"], []),
    ("concept", "what is aging", [r"increase|raise|gradual", r"wait|priority"], []),
    ("concept", "tell me abt aging in scheduling", [r"priority", r"wait|starv"], []),
    ("concept", "what is priority inversion", [r"low", r"high", r"lock|inherit|medium|resource|wait"], []),
    ("concept", "how are priorities assigned to processes", [r"internal|external|importance|memory|time|burst"], []),
    ("concept", "why does priority scheduling starve processes", [r"low", r"higher|keep|arriv"], []),
    # ---- Round Robin
    ("concept", "what is round robin scheduling", [r"quantum|time slice", r"circular|queue|tail|preempt"], []),
    ("concept", "Explain the Time-Quantum Part of the round-robin algo", [r"quantum", r"preempt|slice|queue|expire|context|large|small"], []),
    ("concept", "what is time quantum", [r"time", r"preempt|slice|maximum|queue|expire|context|cpu"], []),
    ("concept", "what happens if time quantum is too large", [r"fcfs|first come", r"convoy|response|poor|behave|same"], []),
    ("concept", "what happens if time quantum is too small", [r"context|overhead|switch"], []),
    ("concept", "how to choose time quantum for round robin", [r"context|80|burst|large|small"], []),
    ("concept", "does round robin cause starvation", [r"\bno\b|not|free", r"starv|every|bound|wait"], []),
    ("concept", "advantages of rr scheduling", [r"fair|response|starv"], []),
    ("concept", "disadvantages of round robin", [r"context|overhead|quantum|turnaround"], []),
    ("concept", "why is round robin good for time sharing", [r"respons|fair|interactive|turn|shar"], []),
    ("concept", "max waiting time in round robin with n processes and quantum q", [r"\(?n\s*[-−]\s*1\)?\s*[×x*]\s*q|n-1"], []),
    ("concept", "what if a process arrives exactly when the quantum ends in rr, who enters the queue first", [r"new|arriv", r"before|first|ahead"], []),
    ("concept", "round robin pseudocode", [r"queue", r"quantum|remaining|min"], []),
    ("concept", "context switch overhead percentage for quantum q and switch time s", [r"s\s*/\s*\(?q\s*\+\s*s|\(q\s*\+\s*s\)|wast|lost|overhead"], []),
    # ---- compare / which / why
    ("concept", "compare fcfs and sjf", [r"fcfs", r"sjf|shortest", r"waiting|burst|starv|convoy"], []),
    ("concept", "rr vs sjf", [r"round|rr", r"sjf|shortest", r"response|waiting|fair|starv"], []),
    ("concept", "difference between preemptive and non preemptive scheduling", [r"preempt", r"timer|take|finish|interrupt|until|forcibly|cpu"], []),
    ("concept", "which algorithm gives minimum average waiting time", [r"sjf|shortest|srtf"], []),
    ("concept", "which scheduling algorithm is best for interactive systems", [r"round|rr|feedback|response"], []),
    ("concept", "which scheduling algorithms can cause starvation", [r"sjf|srtf|priority"], []),
    ("concept", "which algorithms are preemptive", [r"round|srtf|priority"], []),
    ("concept", "why does round robin have higher average turnaround than sjf", [r"turnaround", r"interleav|pause|later|finish|complet"], []),
    ("concept", "is it true that sjf is a special case of priority scheduling", [r"\byes\b|true|correct", r"inverse|burst|priority"], []),
    ("concept", "a friend says rr has no context switches. right?", [r"\bno\b|incorrect|not|wrong|false", r"context|switch|preempt|more"], []),
    # ---- metrics / method
    ("concept", "define waiting time turnaround time and response time", [r"turnaround", r"waiting", r"response"], []),
    ("concept", "formula for turnaround time", [r"completion", r"arrival"], []),
    ("concept", "how to calculate waiting time", [r"turnaround|burst", r"burst|arrival|ready"], []),
    ("concept", "how do i draw a gantt chart", [r"gantt|chart|box|bar", r"time|process"], []),
    ("concept", "what is throughput", [r"per|number|completed", r"time"], []),
    ("concept", "how is cpu utilization calculated", [r"busy|idle|percent|%", r"total|time"], []),
    ("concept", "what is a context switch", [r"sav", r"pcb|state|process|register"], []),
    ("concept", "what does the dispatcher do", [r"context|control|cpu", r"user mode|jump|switch|latency"], []),
    ("concept", "difference between waiting time and response time", [r"first", r"total|preempt|ready|equal"], []),
    ("concept", "what is dispatch latency", [r"stop|time", r"start|process|dispatcher"], []),
    # ---- related algorithms
    ("concept", "what is multilevel feedback queue", [r"queue", r"move|feedback|priority"], []),
    ("concept", "explain hrrn scheduling", [r"response ratio", r"waiting|burst|service"], []),
    ("concept", "what is lottery scheduling", [r"ticket", r"random|probab|proportion"], []),
    ("concept", "what is edf scheduling", [r"deadline", r"earliest|nearest"], []),
    # ---- analogies / examples
    ("concept", "explain round robin with an analogy", [r"queue|line|turn|clerk|counter|customer", r"quantum|time"], []),
    ("concept", "give me a real life example of fcfs", [r"queue|line|counter|customer|canteen|first", r"first|arriv|serv"], []),
    ("concept", "explain sjf with an analogy", [r"shop|operator|customer|pages|photocopy|shortest", r"shortest|fewest|smallest"], []),
    # ---- formulas: the exact kind of question a model gets subtly wrong
    ("concept", "how do i compute waiting time in sjf", [r"turnaround.{0,30}burst|completion.{0,40}arrival.{0,40}burst|start.{0,25}arrival"], [r"[-−]\s*1\b"]),
    ("concept", "formula for turnaround time", [r"completion", r"arrival"], []),
    ("concept", "what is the formula for response time", [r"first|start", r"arrival"], []),
    ("concept", "how to calculate waiting time in round robin", [r"completion|turnaround", r"burst"], [r"[-−]\s*1\b"]),
    ("concept", "waiting time formula for preemptive scheduling", [r"completion", r"arrival", r"burst"], []),
    ("concept", "average waiting time formula", [r"sum|total|add", r"divid|/|\bn\b"], []),
    ("concept", "how to find cpu utilization", [r"busy|running", r"total|elapsed|percent|%"], []),
    ("concept", "formula for response ratio in hrrn", [r"waiting", r"burst", r"/|divid"], []),
    ("concept", "how do i calculate throughput", [r"completed|processes", r"time"], []),
    # ---- exam / short-answer phrasing
    ("concept", "short note on round robin scheduling", [r"quantum|slice", r"queue|preempt"], []),
    ("concept", "write a short note on priority scheduling", [r"priority", r"starv|aging|preempt"], []),
    ("concept", "pls explain sjf", [r"shortest", r"burst|next"], []),
    ("concept", "list the cpu scheduling criteria", [r"utili[sz]ation", r"throughput", r"turnaround|waiting|response"], []),
    ("concept", "what are the types of schedulers", [r"long|job", r"short|cpu", r"medium|swap"], []),
    ("concept", "give two differences between fcfs and round robin", [r"preempt|quantum|convoy|response", r"fcfs|first", r"round|rr"], []),
    ("concept", "can round robin behave like fcfs", [r"yes|large|larger|longer|exceed", r"quantum", r"fcfs|first"], []),
    ("concept", "is srtf optimal", [r"waiting|minimum|lowest", r"optimal|minimum|lowest|yes"], [r"(?m)^\W*(no\b|srtf is not optimal|it is not optimal)"]),
    ("concept", "what is the ready queue", [r"ready", r"process|waiting|cpu"], []),
    ("concept", "what is cpu burst", [r"cpu", r"burst", r"time|execut"], []),
    ("concept", "which process runs next when two have equal priority", [r"fcfs|arriv|first|order|earlier"], []),
    ("concept", "does priority scheduling have convoy effect", [r"."], []),
    ("concept", "difference between cpu bound and io bound process", [r"cpu", r"i/?o"], []),
    # ---- numerical: value must appear in the answer
    ("numerical", "Solve using Round Robin with quantum 4: P1=24, P2=3, P3=3", [r"5\.67"], []),
    ("numerical", "FCFS P1=24, P2=3, P3=3 find the average waiting time", [r"17\.00|17\b"], []),
    ("numerical", "SJF P1 0 6, P2 0 8, P3 0 7, P4 0 3. average waiting time?", [r"7\.00|\b7\b"], []),
    ("numerical", "preemptive sjf burst times 8,4,9,5 arrival times 0,1,2,3 avg waiting time", [r"6\.50"], []),
    ("numerical", "non-preemptive priority: P1 burst 10 priority 3, P2 burst 1 priority 1, P3 burst 2 priority 4, P4 burst 1 priority 5, P5 burst 5 priority 2. average waiting time", [r"8\.20"], []),
    ("numerical", "Round Robin q=4: P1=24, P2=3, P3=3. What is the waiting time of P2?", [r"P2\s*=\s*4"], []),
    ("numerical", "SJF P1 0 6, P2 0 8, P3 0 7, P4 0 3. turnaround time for P3", [r"P3\s*=\s*16"], []),
    ("numerical", "FCFS P1=24, P2=3, P3=3 which process finishes last", [r"P3"], []),
    ("numerical", "FCFS P1=24, P2=3, P3=3 draw the gantt chart only", [r"P1 \(0–24\)", r"P3 \(27–30\)"], []),
    ("numerical", "SRTF P1 0 8, P2 1 4, P3 2 9, P4 3 5. what is the response time of P4?", [r"P4\s*=\s*2"], []),
    # ---- out of scope: must refuse
    ("refuse", "what is the capital of france", [], []),
    ("refuse", "write a python program to reverse a string", [], []),
    ("refuse", "explain deadlock prevention", [], []),
    ("refuse", "how does paging work", [], []),
    ("refuse", "tell me a joke", [], []),
    ("refuse", "who is the prime minister of india", [], []),
]
# applies to every concept answer
ARTEFACTS = [r"\(Source:", r"###", r"\?\.", r"Companion notes|Reference notes|Each section answers|TA would in office"]


def check(tutor, kind, q, must, must_not):
    a = tutor.answer(q)
    text = (a.get("summary") or "") + "\n" + (a.get("text") or "")
    problems = []
    if kind == "refuse":
        if a["in_scope"]:
            problems.append("answered an off-topic question")
        return a, text, problems
    if not a["in_scope"]:
        problems.append("refused an in-scope question")
        return a, text, problems
    if kind == "numerical" and a["kind"] != "numerical":
        problems.append(f"routed as {a['kind']}")
    for pat in must:
        if not re.search(pat, text, re.I):
            problems.append(f"missing /{pat}/")
    for pat in must_not:
        if re.search(pat, text, re.I):
            problems.append(f"contains /{pat}/")
    if kind == "concept":
        for pat in ARTEFACTS:
            if re.search(pat, text):
                problems.append(f"raw-data artefact /{pat}/")
        if len(text.split()) < 12:
            problems.append("answer too short")
        problems += bad_formulas(text)                      # a wrong formula or invented example must never reach the student
        if a.get("guard"):
            a["guard_fired"] = True
    return a, text, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-llm", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--only", help="substring filter on the prompt")
    args = ap.parse_args()
    tutor = Tutor(use_llm=not args.no_llm)
    print(f"generation: {tutor.mode}\n")
    cases = [c for c in CASES if not args.only or args.only.lower() in c[1].lower()]
    fails, t0 = [], time.time()
    stats = {"stored_answers": 0, "model_answers": 0, "guard_replaced_model_answer": 0, "model_timeouts": 0,
             "web_text_used_in_answer": 0, "web_cards_shown": 0}
    for i, (kind, q, must, must_not) in enumerate(cases, 1):
        s = time.time()
        a, text, problems = check(tutor, kind, q, must, must_not)
        fell_back = any("fell back" in n for n in a.get("notes", []))
        if kind == "concept" and a.get("in_scope", True):
            if str(a.get("mode", "")).startswith("stored"):
                stats["stored_answers"] += 1
            else:
                stats["model_answers"] += 1
            stats["guard_replaced_model_answer"] += bool(a.get("guard"))
            stats["model_timeouts"] += fell_back
        if a.get("web_used"):
            stats["web_text_used_in_answer"] += 1
        if a.get("more"):
            stats["web_cards_shown"] += 1
        if fell_back:
            problems.append("LLM timed out / failed -> template fallback")
        flag = "PASS" if not problems else "FAIL"
        print(f"{flag}  [{i:3d}/{len(cases)}] ({time.time() - s:4.1f}s) {q[:80]}")
        if problems:
            fails.append((q, problems, text))
            print("        " + "; ".join(problems))
        if args.verbose or problems:
            print("        > " + text.strip().replace("\n", "\n          ")[:700])
    ok = len(cases) - len(fails)
    print("\nwhere the concept answers came from:", stats)
    print(f"\n{ok}/{len(cases)} prompts answered correctly ({100 * ok / len(cases):.0f}%) "
          f"in {time.time() - t0:.0f}s")
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / "answer_stress_test.json").write_text(json.dumps(
        {"mode": tutor.mode, "total": len(cases), "passed": ok, "stats": stats,
         "failures": [{"prompt": q, "problems": p, "answer": t[:1200]} for q, p, t in fails]}, indent=2))
    raise SystemExit(0 if not fails else 1)


if __name__ == "__main__":
    main()

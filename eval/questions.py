"""The evaluation question set (about 170 phrasings of ~110 distinct questions), written independently of the corpus.

Concept case fields
    id, cat      A fundamentals | B algorithms | D comparisons | E complexity | F failure cases | G exam formats
                 S out-of-scope | M misleading premise | X ambiguous/underspecified
    q            the question exactly as a student would type it
    facts        every entry must match the answer (case-insensitive regex; use | for acceptable wordings)
    bad          none may match: the common errors for this question
    lead         optional regex the first ~220 characters must match (the verdict of a yes/no/true-false question)
    ev           regexes that must appear in the retrieved passages: the evidence needed to answer (retrieval check)
    group        phrasings that ask the same thing share a group; all must pass, with the same verdict (consistency)

Numerical cases are generated from process tables and scored against eval/reference_sim.py, not against stored answers.
"""
from __future__ import annotations

CASES = []


def C(id, cat, q, facts, bad=(), lead=None, ev=(), group=None, kind="concept"):
    CASES.append(dict(id=id, cat=cat, q=q, facts=list(facts), bad=list(bad), lead=lead, ev=list(ev), group=group, kind=kind))


def G(group, cat, qs, facts, bad=(), lead=None, ev=()):
    """The same question in several phrasings."""
    for i, q in enumerate(qs):
        C(f"{group}-{i+1}", cat, q, facts, bad, lead, ev, group)


# ------------------------------------------------------------------ A. fundamentals
G("a-cpusched", "A", ["What is CPU scheduling?", "explain cpu scheduling", "Define CPU scheduling in operating systems."],
  [r"select|choose|decid|decision|pick|alloc", r"ready (queue|process)|processes", r"cpu"], ev=[r"schedul"])
G("a-why", "A", ["Why is CPU scheduling necessary?", "why do we need cpu scheduling in an os"],
  [r"multiprogramming|several (ready )?processes|more ready processes|many processes|multiple processes|share the cpu", r"utili[sz]ation|idle|efficien|throughput|fair|responsive"], ev=[r"schedul"])
C("a-process", "A", "What is a process?", [r"program (in|under) execution|running program|instance of a (running )?program|executing program|active entity"], ev=[r"process"])
C("a-burst", "A", "What is a CPU burst?", [r"cpu", r"burst", r"(period|interval|time|stretch|run).{0,50}(execut|compute|use|run)|execut.{0,40}cpu"], ev=[r"burst"])
G("a-states", "A", ["What are the states of a process?", "Explain the process states in an operating system."],
  [r"ready", r"running", r"(wait|block)", r"new|terminat"], ev=[r"ready", r"running"])
G("a-dispatcher", "A", ["What is a dispatcher?", "what does the dispatcher do"],
  [r"gives? (control|the cpu)|hand|transfer|switch(es|ing)? (the )?cpu|context switch", r"short[- ]term scheduler|selected|chosen"], ev=[r"dispatch"])
G("a-ctx", "A", ["What is a context switch?", "explain context switching"],
  [r"sav(e|ing)", r"restor|load", r"state|pcb|process control block|registers"], ev=[r"context switch"])
G("a-schdisp", "A", ["What is the difference between a scheduler and a dispatcher?", "scheduler vs dispatcher"],
  [r"scheduler.{0,80}(select|decid|choose|pick)|(select|decid|choose|pick).{0,60}scheduler", r"dispatcher.{0,100}(give|hand|transfer|switch|control|context)"], ev=[r"dispatch", r"schedul"])
C("a-queues", "A", "What are ready queues and waiting queues?", [r"ready queue", r"(wait|device|i/o|block).{0,20}queue", r"ready.{0,80}(memory|waiting to|wait for|waiting for).{0,40}cpu|waiting for the cpu|waiting to (be )?(run|execut)"], ev=[r"ready queue"])
G("a-preempt", "A", ["What is preemptive scheduling?", "explain preemptive scheduling"],
  [r"(take|taken|remove|interrupt|forc|preempt).{0,60}cpu|cpu.{0,60}(taken|removed|interrupt)", r"(before|without).{0,40}(finish|complet|termin)|even if|higher|shorter|quantum|timer"], ev=[r"preempt"])
G("a-nonpreempt", "A", ["What is non-preemptive scheduling?", "explain nonpreemptive scheduling"],
  [r"(until|till).{0,40}(finish|terminat|complet|block|i/o|release)|(keep|hold)s? the cpu", r"not (be )?(interrupt|taken|preempt)|never (take|interrupt)|cannot be (taken|preempt)|voluntar|runs? to completion|keeps? it|only when the cpu (becomes|is) free"], ev=[r"non-?preempt"])
C("a-pre-vs-non", "A", "What is the difference between preemptive and non-preemptive scheduling?", [r"preemptive", r"non-?preemptive", r"(take|interrupt|remove|forc).{0,40}cpu|cpu.{0,40}(taken|interrupt|removed)"], ev=[r"preempt"])
G("a-cpuio", "A", ["What is the difference between CPU-bound and I/O-bound processes?", "cpu bound vs io bound"],
  [r"cpu-bound.{0,200}(long|compute|cpu)|compute", r"i/o-bound.{0,200}(short|wait|i/o|input)|wait(s|ing)? for (i/o|input)|frequent i/o|i/o.{0,30}(frequent|waiting)"], ev=[r"i/o-bound|io-bound"])
C("a-dispatchlat", "A", "What is dispatch latency?", [r"time", r"(stop|stops|stopping).{0,40}(one )?process|start.{0,30}(another|running)|dispatcher"], ev=[r"dispatch"])
C("a-criteria", "A", "What are the CPU scheduling criteria?", [r"utili[sz]ation", r"throughput", r"turnaround", r"waiting", r"response"], ev=[r"throughput"])
C("a-metrics-def", "A", "Define turnaround time, waiting time and response time.", [r"completion.{0,25}arrival", r"turnaround.{0,30}burst|waiting.{0,40}ready queue", r"first.{0,40}(cpu|run|start|schedul)"], bad=[r"response time (is|=|equals).{0,30}completion"], ev=[r"response time"])

# ------------------------------------------------------------------ B. algorithms
for key, name, pats in [
    ("fcfs", "FCFS", [r"arriv\w*|order|queue", r"non-?preemptive|until"]),
    ("sjf", "SJF", [r"shortest", r"burst|next cpu|length"]),
    ("srtf", "SRTF", [r"remaining", r"preempt"]),
    ("priority", "priority scheduling", [r"priorit", r"highest|lowest number|higher"]),
    ("rr", "Round Robin", [r"quantum|time slice", r"queue|turn|cyclic|circular", r"preempt"]),
]:
    C(f"b-{key}-what", "B", f"What is {name}?", pats, ev=[pats[0]], group=None)
C("b-fcfs-pros", "B", "What are the advantages and disadvantages of FCFS?", [r"simple|easy", r"convoy|long (waiting|wait)|waiting time|poor"], ev=[r"convoy"])
C("b-sjf-pros", "B", "What are the advantages and disadvantages of SJF?", [r"minimum|lowest|optimal|least", r"starv|predict|burst.{0,40}(know|advance|estimate)"], ev=[r"optimal|minimum"])
C("b-srtf-pros", "B", "Advantages and disadvantages of SRTF", [r"waiting", r"context switch|starv|overhead|burst"], ev=[r"remaining"])
C("b-prio-pros", "B", "What are the pros and cons of priority scheduling?", [r"important|urgent|priorit", r"starv|aging|indefinite"], ev=[r"starv"])
C("b-rr-pros", "B", "What are the advantages and disadvantages of Round Robin?", [r"fair|response|time-?shar|interactive", r"context switch|overhead|quantum|turnaround|waiting"], ev=[r"quantum"])
C("b-sjf-use", "B", "When is SJF appropriate?", [r"batch|known|predict|estimat|burst"], ev=[r"sjf|shortest"])
C("b-rr-use", "B", "Which systems is Round Robin suitable for?", [r"time-?shar|interactive|multi-?user|fair"], ev=[r"round robin"])
C("b-fcfs-use", "B", "Where is FCFS suitable?", [r"batch|simple|non-?interactive|low overhead"], ev=[r"fcfs|first come"])
G("b-srtf-sjf", "B", ["How does SRTF differ from SJF?", "difference between sjf and srtf", "Is SRTF the same as SJF?"],
  [r"preempt", r"remaining", r"non-?preempt"], bad=[r"srtf is non-?preemptive"], ev=[r"remaining"])
G("b-prio-pre", "B", ["How does preemptive Priority Scheduling differ from non-preemptive Priority Scheduling?", "preemptive vs non preemptive priority scheduling"],
  [r"arriv|new", r"(immediate|takes? the cpu|preempt|interrupt)", r"(wait|finish|complet|until)"], ev=[r"priorit", r"preempt"])
C("b-mlq", "B", "What is multilevel queue scheduling?", [r"separate|partition|several|multiple|different", r"queue", r"foreground|background|interactive|batch|priority|own algorithm"], ev=[r"multi-?level queue"])
C("b-mlfq", "B", "What is multilevel feedback queue scheduling?", [r"move|mov(e|ing)|feedback|promot|demot", r"queue", r"quantum|cpu usage|cpu burst|behaviou?r|priorit"], ev=[r"feedback"])
C("b-mlfq-rules", "B", "What are the rules of MLFQ?", [r"priorit", r"(higher|highest).{0,40}(runs|run)|run.{0,40}higher", r"(same|equal) priority.{0,30}(round|rr)|round.?robin"], ev=[r"mlfq|feedback"])
C("b-aging", "B", "What is aging in CPU scheduling?", [r"gradual|increas|rais", r"priorit", r"wait"], bad=[r"aging (lowers|decreases|reduces) the priority"], ev=[r"aging|ageing"])
C("b-hrrn", "B", "What is Highest Response Ratio Next (HRRN)?", [r"response ratio|\(w", r"wait", r"burst|service"], ev=[r"response ratio"])
C("b-edf", "B", "What is Earliest Deadline First scheduling?", [r"deadline", r"real-?time"], ev=[r"deadline"])
C("b-lottery", "B", "How does lottery scheduling work?", [r"ticket", r"random"], ev=[r"lottery|ticket"])
C("b-rr-q", "B", "How is the time quantum chosen in Round Robin?", [r"context switch|overhead", r"response|large|small|too"], ev=[r"quantum"])
C("b-rr-formula", "B", "What is the maximum time a process waits for its next turn in Round Robin?", [r"\(n\s*[−-]\s*1\)\s*[×x*]\s*q|\(n-1\)"], ev=[r"\(n\s*[−-]\s*1\)"])

# ------------------------------------------------------------------ D. comparisons
G("d-minwait", "D", ["Which algorithm minimizes average waiting time?", "which scheduling algorithm gives the lowest average waiting time", "optimal algorithm for average waiting time"],
  [r"sjf|shortest[- ]job|srtf|shortest[- ]remaining"], bad=[r"round robin (gives|has|is) the (lowest|minimum|best) (average )?waiting", r"fcfs (gives|has|is) the (lowest|minimum|best)"], ev=[r"optimal|minimum|lowest"])
G("d-resp", "D", ["Which algorithm provides better response time?", "which cpu scheduling algorithm has the best response time for interactive users"],
  [r"round robin|rr|srtf|preemptive"], ev=[r"response"])
C("d-interactive", "D", "Which algorithm is appropriate for interactive systems?", [r"round robin|multilevel feedback|mlfq|time-?shar"], bad=[r"fcfs is (the )?(best|ideal|most suitable) for interactive"], ev=[r"interactive|time-?shar"])
C("d-batch", "D", "Which algorithm is suitable for batch processing?", [r"fcfs|sjf|shortest|first[- ]come"], ev=[r"batch"])
C("d-fair", "D", "Which algorithm is most fair?", [r"round robin|fcfs|first[- ]come|every process|equal"], bad=[r"sjf is (the )?most fair"], ev=[r"fair"])
G("d-starve", "D", ["Which algorithm can cause starvation?", "which scheduling algorithms can lead to starvation of processes"],
  [r"sjf|shortest", r"priorit"], bad=[r"(only|just) (fcfs|round robin)", r"fcfs (can|may) (cause|lead to) starvation"], ev=[r"starv"])
G("d-convoy", "D", ["Which algorithm can suffer from the convoy effect?", "which scheduling algorithm has the convoy effect"],
  [r"fcfs|first[- ]come"], bad=[r"round robin (suffers|has|causes) the convoy"], ev=[r"convoy"])
G("d-quantum", "D", ["What are the effects of increasing the Round Robin time quantum?", "what happens if the time quantum in round robin is very large", "what if the quantum is too small in rr"],
  [r"fcfs|context switch|response|overhead"], ev=[r"quantum"])
C("d-lowwait-unsuit", "D", "Why can an algorithm with low waiting time still be unsuitable for a system?", [r"starv|response|long (job|process)|burst.{0,30}(predict|know)|fair|interactive|context switch"], ev=[r"starv|response|burst"])
G("d-best", "X", ["Which CPU scheduling algorithm is the most efficient, and why?", "what is the best cpu scheduling algorithm", "which scheduling algorithm is best overall"],
  [r"depend|no single|trade-?off|no (one|algorithm)|workload|goal|objective|criteria|situation"], bad=[r"(sjf|srtf|round robin|fcfs|priority) is (always |universally )?(the )?best (algorithm )?(in all|for all|overall)", r"universally optimal"], ev=[r"depend|trade|best|optimal"])
C("d-sjf-vs-rr", "D", "Compare SJF and Round Robin.", [r"sjf|shortest", r"round robin|quantum", r"waiting|starv|response|fair"], ev=[r"round robin", r"sjf|shortest"])
C("d-fcfs-vs-rr", "D", "Compare FCFS and Round Robin.", [r"fcfs", r"round robin|quantum", r"preempt|response|convoy|time-?shar"], ev=[r"round robin"])
C("d-fcfs-vs-sjf", "D", "difference between fcfs and sjf", [r"arriv|order", r"shortest|burst", r"waiting|starv|optimal"], ev=[r"sjf|shortest"])
C("d-all", "D", "Compare all the CPU scheduling algorithms in a table.", [r"fcfs", r"sjf", r"srtf", r"priority", r"round robin"], ev=[r"fcfs"])
C("d-tat-vs-rt", "D", "What is the difference between waiting time and response time?", [r"wait", r"first", r"response"], bad=[r"response time (is|=|equals) (the )?(total|completion)"], ev=[r"response time"])

# ------------------------------------------------------------------ E. performance and complexity
C("e-sjf-ds", "E", "What data structure is used to implement SJF efficiently?", [r"heap|priority queue|min-?heap"], ev=[r"heap|priority queue"])
C("e-rr-ds", "E", "What data structure does Round Robin use for the ready queue?", [r"circular|fifo|queue"], ev=[r"circular|fifo"])
C("e-sjf-cx", "E", "What is the time complexity of picking the next process in SJF?", [r"o\(log n\)|log n|o\(n\)"], ev=[r"o\(log n\)|log n"])
C("e-ctx-overhead", "E", "How does context switching affect scheduling performance?", [r"overhead|time|wast|no useful work|cost", r"quantum|frequent|many"], ev=[r"context switch"])
C("e-overhead-rr", "E", "Which algorithm has the highest scheduling overhead?", [r"round robin|srtf|preemptive"], ev=[r"overhead"])
C("e-theory-prac", "E", "Why is SJF not practical in real systems even though it is optimal?", [r"predict|estimat|know|burst", r"advance|future|impossible|exponential"], ev=[r"predict|estimat"])
C("e-sim-cx", "E", "What is the time complexity of simulating FCFS for n processes?", [r"o\(n log n\)|o\(n\)|n log n|sort"], bad=[r"o\(1\)\b(?!.{0,30}decision)"], ev=[r"o\(|complexity|sort"])
C("e-space", "E", "What is the space complexity of the ready queue?", [r"o\(n\)|n processes|linear|proportional"], ev=[r"queue"])

# ------------------------------------------------------------------ F. advantages, disadvantages, failure cases
G("f-starv", "F", ["What is starvation in CPU scheduling?", "define starvation"],
  [r"indefinite|never|forever|too long", r"wait|postpon|blocked"], ev=[r"starv"])
G("f-convoy", "F", ["What is the convoy effect?", "explain convoy effect in fcfs"],
  [r"long", r"short.{0,60}(wait|behind|queue)|wait.{0,40}behind", r"fcfs|first[- ]come"], ev=[r"convoy"])
C("f-inversion", "F", "What is priority inversion?", [r"low(er)?[- ]priority", r"high(er)?[- ]priority", r"(lock|resource|mutex|semaphore|hold)"], bad=[r"priority inversion (is|means) (when )?(the )?priority numbers"], ev=[r"priority inversion"])
C("f-inversion-fix", "F", "How can priority inversion be solved?", [r"priority inheritance|inherit|priority ceiling"], ev=[r"inherit|ceiling"])
C("f-ctx-excess", "F", "What problem does excessive context switching cause?", [r"overhead|waste|cpu time|throughput|slow"], ev=[r"context switch"])
C("f-unfair", "F", "How can SJF be unfair?", [r"long", r"starv|wait|postpon|indefinite"], ev=[r"starv"])
C("f-longresp", "F", "Why does FCFS give long response times?", [r"wait|behind|long", r"first|arriv|order|queue"], ev=[r"fcfs|first come"])
C("f-workload", "F", "Why does the performance of a scheduling algorithm depend on the workload?", [r"burst|arriv|mix|workload|process", r"depend|differ|vary|trade"], ev=[r"workload|depend|trade"])
C("f-limits", "F", "What are the limitations of priority scheduling?", [r"starv|indefinite|block", r"aging|priorit"], ev=[r"starv"])
G("f-aging", "F", ["How does aging prevent starvation?", "why is aging used in priority scheduling"],
  [r"gradual|increas|rais", r"wait", r"priorit"], ev=[r"aging|ageing"])
G("f-sjfstarve", "F", ["Can starvation occur in SJF?", "can long jobs starve in shortest job first", "is it possible for a process to starve under sjf"],
  [r"short(er)? (jobs?|processes).{0,50}(keep|continu|repeated|arriv)|keep arriving|continu\w+ arriv", r"long"], lead=r"^\W*(yes|starvation can|sjf can|long jobs? can|it can|can|possible)", bad=[r"^\W*no\b"], ev=[r"starv"])
G("f-fcfsstarve", "F", ["Can starvation occur in FCFS?", "does fcfs cause starvation", "is starvation possible with first come first served"],
  [r"(not|no|never|cannot|doesn't|does not).{0,80}starv|starv.{0,60}(not|never|cannot)", r"finite|eventually|terminat|finish|head|arrival order|in order"], lead=r"^\W*(no|not|standard|fcfs (does|cannot|doesn)|starvation (does|cannot|is not))", bad=[r"^\W*yes\b"], ev=[r"starv", r"fcfs|first"])
G("f-rrstarve", "F", ["Does Round Robin cause starvation?", "can a process starve in rr"],
  [r"(not|no|never|cannot|doesn't|does not).{0,80}starv|starv.{0,60}(not|never|cannot)", r"turn|quantum|\(n\s*[−-]\s*1\)"], lead=r"^\W*(no|not|rr (does|cannot)|round robin (does|cannot)|starvation (does|cannot))", bad=[r"^\W*yes\b"], ev=[r"starv"])
G("f-prio-why", "F", ["Why can starvation occur in Priority Scheduling?", "why do low priority processes starve"],
  [r"low(er)?[- ]priority", r"higher|keep|bypass|repeated|continu", r"aging"], ev=[r"starv"])

# ------------------------------------------------------------------ G. exam formats
C("g-mcq1", "G", "Which of the following algorithms can cause starvation?\n(a) FCFS\n(b) Round Robin\n(c) SJF\n(d) None of these", [r"\bsjf\b|shortest"], lead=r"(\(c\)|\bc\b|\bsjf\b|shortest)", bad=[r"^\W*\(?a\)?[.)\s]", r"^\W*\(?d\)?[.)\s]"], ev=[r"starv"])
C("g-mcq2", "G", "Which scheduling algorithm is optimal for minimum average waiting time?\nA. FCFS\nB. SJF\nC. Round Robin\nD. Priority", [r"\bsjf\b|shortest"], lead=r"(\bb\b|\bsjf\b|shortest)", ev=[r"optimal|minimum"])
C("g-mcq3", "G", "In Round Robin, if the time quantum is very large, the algorithm behaves like:\n(a) SJF\n(b) FCFS\n(c) Priority\n(d) SRTF", [r"fcfs|first[- ]come"], lead=r"(\(b\)|\bb\b|fcfs|first[- ]come)", ev=[r"larger than|fcfs|quantum"])
C("g-mcq4", "G", "The convoy effect is associated with which algorithm?\n(a) Round Robin\n(b) SJF\n(c) FCFS\n(d) Priority", [r"fcfs|first[- ]come"], lead=r"(\(c\)|\bc\b|fcfs|first[- ]come)", ev=[r"convoy"])
C("g-mcq5", "G", "Which of these is a preemptive algorithm?\n(a) FCFS\n(b) non-preemptive SJF\n(c) Round Robin\n(d) non-preemptive priority", [r"round robin"], lead=r"(\(c\)|\bc\b|round robin)", ev=[r"preempt"])
G("g-tf1", "G", ["True or false: Round Robin can cause starvation.", "True/False: Round Robin leads to starvation of processes."],
  [r"false|incorrect|not|no\b"], lead=r"^\W*(false|incorrect|no|not)", bad=[r"^\W*(true|correct|yes)\b"], ev=[r"starv"])
G("g-tf2", "G", ["True or false: SJF is a non-preemptive algorithm.", "True/False: shortest job first (non-preemptive version) never interrupts a running process."],
  [r"true|correct|yes"], lead=r"^\W*(true|correct|yes)", bad=[r"^\W*(false|incorrect|no)\b"], ev=[r"non-?preempt"])
C("g-tf3", "G", "True or false: In FCFS, a short process can wait a long time behind a long process.", [r"true|yes|correct", r"convoy|long"], lead=r"^\W*(true|correct|yes)", ev=[r"convoy"])
C("g-tf4", "G", "True or false: SRTF is the preemptive version of SJF.", [r"true|yes|correct"], lead=r"^\W*(true|correct|yes)", ev=[r"srtf|remaining"])
C("g-fill1", "G", "Fill in the blank: The _____ effect occurs in FCFS when short processes wait behind a long process.", [r"convoy"], ev=[r"convoy"])
C("g-fill2", "G", "Fill in the blank: _____ is a technique that gradually increases the priority of waiting processes.", [r"aging|ageing"], ev=[r"aging|ageing"])
C("g-fill3", "G", "Fill in the blank: Turnaround time = Completion time - _____ time.", [r"arrival"], ev=[r"completion.{0,20}arrival"])
C("g-short1", "G", "Write a short note on Round Robin scheduling.", [r"quantum", r"queue|turn|circular", r"preempt|time-?shar|fair"], ev=[r"round robin"])
C("g-long1", "G", "Explain priority scheduling in detail, with its types, advantages, disadvantages and the problem of starvation.", [r"preemptive", r"non-?preemptive", r"starv", r"aging"], ev=[r"priorit"])
C("g-compare1", "G", "Differentiate between FCFS and SJF with respect to waiting time, starvation and preemption.", [r"fcfs", r"sjf|shortest", r"starv", r"preempt"], ev=[r"sjf|shortest"])
C("g-ar1", "G", "Assertion (A): Round Robin has no starvation. Reason (R): Every ready process receives the CPU within (n-1)*q time units. Is A true, R true, and R the correct explanation of A?", [r"true|correct|yes", r"explain|correct reason|because"], lead=r"(both|true|correct|yes)", bad=[r"^\W*(false|incorrect|no\b)"], ev=[r"\(n\s*[−-]\s*1\)"])
C("g-ar2", "G", "Assertion (A): SJF never causes starvation. Reason (R): SJF always picks the shortest job. Choose: A true R true; A false R true; A true R false; both false.", [r"a is false|assertion.{0,20}false|false", r"starv"], lead=r"(false|incorrect|not|no\b|a is false|assertion.{0,30}false)", bad=[r"^\W*(a is true|assertion is true)"], ev=[r"starv"])
C("g-incorrect1", "G", "Which statement is incorrect? (a) FCFS is non-preemptive (b) Round Robin is preemptive (c) SJF never starves a long job (d) Priority scheduling can starve processes", [r"\(c\)|\bc\b|sjf never starves|sjf.{0,40}(can|may) starv"], lead=r"(\(c\)|\bc\b|sjf)", ev=[r"starv"])
C("g-concise", "G", "In one line, what is the formula for waiting time?", [r"turnaround.{0,20}burst|completion.{0,25}arrival.{0,25}burst"], bad=[r"waiting time (=|is|equals) (the )?completion time [-−] burst time\b(?! [-−] )"], ev=[r"waiting time"])
C("g-steps", "G", "Explain step by step how Round Robin selects the next process.", [r"queue", r"quantum|time slice", r"back|end|tail"], ev=[r"round robin"])

# ------------------------------------------------------------------ M. misleading premises
G("m-rr-starve", "M", ["Why does Round Robin cause starvation?", "Explain how round robin starves long processes."],
  [r"(not|no|doesn't|does not|never|cannot|misconception|incorrect|false).{0,100}starv|starv.{0,100}(not|never|cannot)"], lead=r"^\W*(round robin|rr|no|actually|that|it|starvation|in fact|this)", bad=[r"^\W*round robin causes starvation because", r"round robin (causes|leads to) starvation because"], ev=[r"starv"])
C("m-sjf-nostarve", "M", "Why is SJF free from starvation?", [r"(not|isn't|is not|can|may|incorrect|false|misconception).{0,100}starv|starv.{0,80}(can|may|possible)"], bad=[r"sjf is free from starvation because", r"^\W*sjf (never|does not|doesn't) (cause|suffer)"], ev=[r"starv"])
C("m-fcfs-pre", "M", "Why is FCFS a preemptive algorithm?", [r"non-?preemptive|not preemptive|isn't preemptive|is not preemptive|cannot be preempt"], bad=[r"fcfs is preemptive because"], ev=[r"non-?preempt"])
C("m-srtf-nonpre", "M", "Since SRTF is non-preemptive, how does it handle a new shorter job?", [r"preemptive|not non-?preemptive|is preemptive|preempts"], bad=[r"srtf is non-?preemptive, so"], ev=[r"srtf|remaining"])
C("m-rr-short", "M", "Round Robin always runs the shortest process first, right?", [r"no|not|doesn't|does not", r"quantum|queue|turn|cyclic|order"], lead=r"^\W*(no|not|incorrect|that|round robin (does|doesn)|actually)", bad=[r"^\W*yes"], ev=[r"round robin"])
C("m-tat", "M", "Waiting time is the same as response time in every algorithm, correct?", [r"no|not|only|non-?preemptive|differ"], lead=r"^\W*(no|not|incorrect|only|waiting|actually|the two)", bad=[r"^\W*yes\b"], ev=[r"response time"])
C("m-prio", "M", "In priority scheduling a higher priority number always means the process runs first, correct?", [r"depend|convention|lower (number|value)|not always|no\b"], bad=[r"^\W*yes,? a higher number always"], ev=[r"lower (number|priority number)|convention"])
C("m-bigq", "M", "A smaller time quantum always improves Round Robin performance. Is that right?", [r"no|not always|context switch|overhead|too small"], lead=r"^\W*(no|not|incorrect|false|a smaller|actually)", bad=[r"^\W*yes\b"], ev=[r"quantum"])

# ------------------------------------------------------------------ S. out of scope
for i, q in enumerate(["What is the capital of France?", "How do I make pasta?", "Write a poem about the sea.", "Who won the cricket world cup?",
                       "What is paging in virtual memory?", "Explain how deadlock detection works.", "What is the best programming language?",
                       "How do I install Python on Windows?", "What is a B-tree?", "Tell me a joke."]):
    C(f"s-{i+1}", "S", q, [], kind="scope")

# ------------------------------------------------------------------ N. numerical (generated, scored against the reference simulator)
NUM = []     # dicts: id, algo, procs [(pid, at, bt, pr)], q, style, ask


def N(id, algo, procs, q=None, style="table", ask="Calculate the average waiting time and average turnaround time.", **kw):
    NUM.append(dict(id=id, algo=algo, procs=procs, q=q, style=style, ask=ask, **kw))


P1 = [("P1", 0, 5, 0), ("P2", 1, 3, 0), ("P3", 2, 8, 0), ("P4", 3, 6, 0)]
P2 = [("P1", 0, 7, 0), ("P2", 2, 4, 0), ("P3", 4, 1, 0), ("P4", 5, 4, 0)]
P3 = [("P1", 0, 8, 3), ("P2", 1, 4, 1), ("P3", 2, 9, 4), ("P4", 3, 5, 2)]
P4 = [("P1", 0, 24, 0), ("P2", 0, 3, 0), ("P3", 0, 3, 0)]
P5 = [("P1", 0, 3, 2), ("P2", 6, 4, 1), ("P3", 7, 2, 3)]                       # idle gap
P6 = [("P1", 0, 4, 2), ("P2", 0, 3, 2), ("P3", 0, 5, 1), ("P4", 2, 2, 1)]       # priority ties, simultaneous arrivals
P7 = [("P1", 0, 10, 3), ("P2", 0, 1, 1), ("P3", 0, 2, 4), ("P4", 0, 1, 5), ("P5", 0, 5, 2)]
P8 = [("P1", 2, 6, 0), ("P2", 5, 2, 0), ("P3", 5, 4, 0), ("P4", 12, 3, 0)]      # starts idle, simultaneous arrivals
for algo, base, q in [("fcfs", P1, None), ("sjf", P2, None), ("srtf", P2, None), ("priority", P3, None), ("priority_p", P3, None), ("rr", P4, 4)]:
    N(f"n-{algo}-basic", algo, base, q)
N("n-fcfs-gantt", "fcfs", P4, ask="Draw the Gantt chart.", want="gantt")
N("n-fcfs-idle", "fcfs", P5, ask="Find the completion, turnaround and waiting time of each process.")
N("n-sjf-idle", "sjf", P8, ask="Compute the average waiting time.")
N("n-srtf-idle", "srtf", P8, ask="Compute the average turnaround time.", want="tat")
N("n-prio-ties", "priority", P6, ask="Find the average waiting time.")
N("n-priop-ties", "priority_p", P6, ask="Find the average waiting time.")
N("n-prio-textbook", "priority", P7, ask="What is the average waiting time?")
N("n-rr-q2", "rr", P1, 2, ask="What is the average waiting time?")
N("n-rr-q3-arr", "rr", [("P1", 0, 6, 0), ("P2", 3, 2, 0), ("P3", 3, 4, 0)], 3, ask="Find the average waiting time.")
N("n-rr-idle", "rr", P8, 3, ask="Find the average turnaround time.", want="tat")
N("n-rr-big-q", "rr", P4, 30, ask="Find the average waiting time.")
N("n-rr-q1", "rr", P2, 1, ask="Find the average waiting time.")
N("n-resp-rr", "rr", P4, 4, ask="What is the average response time?", want="rt")
N("n-resp-srtf", "srtf", P2, ask="What is the average response time?", want="rt")
N("n-resp-fcfs", "fcfs", P1, ask="Calculate the response time of P3.", want="rt-P3")
N("n-wait-p2", "sjf", P2, ask="What is the waiting time of P2?", want="wt-P2")
N("n-util", "fcfs", P5, ask="What is the CPU utilization?", want="util")
N("n-thru", "fcfs", P5, ask="What is the throughput?", want="thru")
N("n-list", "sjf", P2, style="list", ask="Find the average waiting time.")
N("n-parallel", "fcfs", P1, style="parallel", ask="Find the average waiting time.")
N("n-label", "priority", P3, style="label", ask="Find the average waiting time.")
N("n-bursts-only", "fcfs", [("P1", 0, 9, 0), ("P2", 0, 2, 0), ("P3", 0, 1, 0)], style="bursts", ask="Calculate waiting time for each process.")
N("n-compare3", "multi", P4, 4, ask="Compare FCFS, SJF and Round Robin on average waiting time.", algos=["fcfs", "sjf", "rr"])
N("n-compare2", "multi", P2, ask="Which is better for this workload, FCFS or SRTF, on average waiting time?", algos=["fcfs", "srtf"])

# Missing or invalid information: the tutor must ask or state its assumption, never silently invent, never crash.
MISSING = [
    ("n-miss-quantum", "Round Robin: P1 0 5, P2 1 3, P3 2 8. Find the average waiting time.", r"quantum.{0,60}(assum|\bq\s*=|not (given|specified)|missing|need)|assum.{0,60}quantum|q\s*=\s*2.{0,40}assum"),
    ("n-miss-noprio", "Priority scheduling: P1 0 5, P2 1 3, P3 2 8. Find the average waiting time.", r"priorit.{0,80}(not (given|specified|found)|no priorit|missing|need|assum|were found)|no priorit"),
    ("n-miss-arrival", "FCFS: P1=5, P2=3, P3=8. Find the average waiting time.", r"arrive at t=0|arrival.{0,40}(assum|t=0|0)|assum.{0,40}arriv"),
    ("n-miss-all", "Solve this SJF problem and calculate the average waiting time.", r"arrival and burst|need.{0,40}(burst|process)|send.{0,40}(burst|process)|process data"),
    ("n-bad-zero", "FCFS: P1 0 0, P2 1 3, P3 2 8. Find the average waiting time.", r"burst|positive|invalid|cannot|can't|couldn't|zero"),
    ("n-bad-q0", "Round Robin with quantum 0: P1 0 5, P2 1 3. Find the average waiting time.", r"quantum.{0,50}(positive|invalid|zero|0|cannot|greater)"),
]

# Evaluation `template` (grounded template (no LLM running))

**157/185 passed (84.9%)** over 151 distinct questions. Retrieval evidence present for 100.0% of concept questions. Inconsistent paraphrase groups: 4/27.

| Category | Passed | Total |
|---|---|---|
| A | 26 | 26 |
| B | 27 | 27 |
| D | 16 | 21 |
| E | 8 | 8 |
| F | 19 | 23 |
| G | 7 | 22 |
| M | 5 | 9 |
| N | 36 | 36 |
| S | 10 | 10 |
| X | 3 | 3 |

Failures by stage: generation 28

## Failures

- `d-batch` [generation] missing fact: fcfs|sjf|shortest|first[- ]come — 'Which algorithm is suitable for batch processing?'
- `d-starve-2` [generation] missing fact: sjf|shortest — 'which scheduling algorithms can lead to starvation of processes'
- `d-quantum-1` [generation] missing fact: fcfs|context switch|response|overhead — 'What are the effects of increasing the Round Robin time quantum?'
- `d-quantum-3` [generation] missing fact: fcfs|context switch|response|overhead — 'what if the quantum is too small in rr'
- `d-lowwait-unsuit` [generation] missing fact: starv|response|long (job|process)|burst.{0,30}(predict|know)|fair|inte — 'Why can an algorithm with low waiting time still be unsuitable for a system?'
- `f-unfair` [generation] missing fact: long — 'How can SJF be unfair?'
- `f-longresp` [generation] missing fact: first|arriv|order|queue — 'Why does FCFS give long response times?'
- `f-workload` [generation] missing fact: burst|arriv|mix|workload|process — 'Why does the performance of a scheduling algorithm depend on the workload?'
- `f-aging-1` [generation] missing fact: gradual|increas|rais — 'How does aging prevent starvation?'
- `g-mcq1` [generation] missing fact: \bsjf\b|shortest — 'Which of the following algorithms can cause starvation?\n(a) FCFS\n(b) Round Robin\n(c) SJF\n('
- `g-mcq4` [generation] missing fact: fcfs|first[- ]come — 'The convoy effect is associated with which algorithm?\n(a) Round Robin\n(b) SJF\n(c) FCFS\n(d)'
- `g-tf1-1` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'True or false: Round Robin can cause starvation.'
- `g-tf1-2` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'True/False: Round Robin leads to starvation of processes.'
- `g-tf2-1` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'True or false: SJF is a non-preemptive algorithm.'
- `g-tf2-2` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'True/False: shortest job first (non-preemptive version) never interrupts a running process'
- `g-tf3` [generation] missing fact: convoy|long — 'True or false: In FCFS, a short process can wait a long time behind a long process.'
- `g-tf4` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'True or false: SRTF is the preemptive version of SJF.'
- `g-fill1` [generation] missing fact: convoy — 'Fill in the blank: The _____ effect occurs in FCFS when short processes wait behind a long'
- `g-fill2` [generation] missing fact: aging|ageing — 'Fill in the blank: _____ is a technique that gradually increases the priority of waiting p'
- `g-fill3` [generation] missing fact: arrival — 'Fill in the blank: Turnaround time = Completion time - _____ time.'
- `g-long1` [generation] missing fact: non-?preemptive — 'Explain priority scheduling in detail, with its types, advantages, disadvantages and the p'
- `g-ar1` [generation] missing fact: true|correct|yes — 'Assertion (A): Round Robin has no starvation. Reason (R): Every ready process receives the'
- `g-ar2` [generation] missing fact: a is false|assertion.{0,20}false|false — 'Assertion (A): SJF never causes starvation. Reason (R): SJF always picks the shortest job.'
- `g-incorrect1` [generation] missing fact: \(c\)|\bc\b|sjf never starves|sjf.{0,40}(can|may) starv — 'Which statement is incorrect? (a) FCFS is non-preemptive (b) Round Robin is preemptive (c)'
- `m-rr-short` [generation] wrong or missing verdict (starts: 'SJF deliberately favours short processes: it picks the shortest burst ') — 'Round Robin always runs the shortest process first, right?'
- `m-tat` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'Waiting time is the same as response time in every algorithm, correct?'
- `m-prio` [generation] missing fact: depend|convention|lower (number|value)|not always|no\b — 'In priority scheduling a higher priority number always means the process runs first, corre'
- `m-bigq` [generation] wrong or missing verdict (starts: 'This is a true/false question. Judging it needs the language model, wh') — 'A smaller time quantum always improves Round Robin performance. Is that right?'
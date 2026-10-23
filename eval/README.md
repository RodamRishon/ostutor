# Evaluation suite

185 phrasings of 151 distinct questions, written independently of the corpus and never used to tune answers.

| Category | What it tests |
|---|---|
| A | Fundamentals: process, states, queues, dispatcher, context switch, preemption, CPU/I/O-bound |
| B | The five algorithms plus MLQ, MLFQ, aging, HRRN, EDF, lottery: definitions, pros/cons, use cases |
| D | Comparisons and "which algorithm ..." questions; underspecified "which is best?" questions (category X) |
| E | Complexity, data structures, overhead, theory versus practice |
| F | Starvation, aging, convoy effect, priority inversion, unfairness |
| G | Exam formats: MCQ, true/false, fill in the blank, assertion-reason, "incorrect statement", one-liners |
| M | Questions with a false premise (the tutor must correct it) |
| S | Out of scope (must be declined, with no fabricated citations) |
| N | Numerical: 24 generated problems, 6 missing/invalid-input cases |

## How a case is scored

* **Concept cases pass** only if the question is accepted, *every* required fact matches, *no* forbidden claim matches, the verdict
  (yes/no/true/false) matches where the question has one, `concept_check`'s fact rules find nothing wrong, and the answer is not
  an empty "see the sources" fallback. Keywords alone are not enough: forbidden claims and verdicts are part of every rubric.
* **Retrieval is scored separately** (`ev`): were the passages that contain the needed evidence retrieved? A failed case is blamed on
  *retrieval* if the evidence was absent, on *generation* if it was present.
* **Numerical cases pass** only if every completion/turnaround/waiting/response time and the Gantt chart equal an **independent
  reference simulator** (`eval/reference_sim.py`, a different algorithm from `scheduler.py`) *and* the number the student asked
  for is actually shown. Question text is generated in six layouts (table, list, parallel lists, labelled, bursts only).
* **Consistency**: questions in a paraphrase group must all pass with the same verdict.

## Run it

```bash
python -m eval.run_eval --no-llm --tag template   # fast; vetted/extractive path, no Ollama needed
python -m eval.run_eval --tag llm                 # the real pipeline (needs Ollama; about 30-40 minutes)
python -m eval.run_eval --only B,F -v             # some categories, print each failure
python -m pytest tests -q                         # unit/regression tests (simulator vs reference, routing, verification)
```
Reports are written to `eval/results/<tag>.json` and `.md`.

## Limits of the method

Regex rubrics are a proxy for correctness: they catch missing facts and known wrong claims, not every possible error, and a
paraphrase the rubric did not anticipate can fail a correct answer (or pass a subtly wrong one). Numerical checks are exact.

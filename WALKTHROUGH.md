# How this project was built (explain-to-the-professor guide)

## The one-sentence pitch
ChatGPT-style tutors *guess* scheduling answers. This tutor **computes** every number with a
simulator and **quotes** every explanation from course material, and it refuses questions it
has no source for.

## The idea in one picture

```
student question
      │
   router.py ── has process data? ──► scheduler.py  (computes Gantt, waiting, turnaround)
      │                                      │
      └──────────► retriever.py (finds top-3 course passages)
                         │
                     tutor.py ──► answer + citations ──► app.py (Streamlit UI)
```

Two phases, as in your report:
- **Phase A (once):** clean the course text → cut into chunks → build a search index; write and validate the instruction dataset.
- **Phase B (every question):** route → simulate (if numbers) → retrieve → answer.

## Build order (what I did and why)

| Step | File | What it does, simply | Why this order |
|---|---|---|---|
| 1 | `scheduler.py` | Runs FCFS, SJF, SRTF, Priority, Round Robin one decision at a time and records a log | Everything else depends on correct numbers, so it came first and was checked against your Table 6 |
| 2 | `clean_chunk.py` | Removes page numbers, joins hyphenated words, cuts text into 300-word chunks with 45 words of overlap | Search works better on clean, same-sized pieces; overlap stops a worked example being cut in half |
| 3 | `build_index.py` | Turns each chunk into a vector and saves an index. Uses bge + FAISS if installed, otherwise TF-IDF | The report's design; the TF-IDF fallback means it runs on any laptop |
| 4 | `retriever.py` | Finds the 3 most similar chunks; if the best match is too weak, says "outside my knowledge base" | Stops made-up answers |
| 5 | `router.py` | Reads a message and decides: numerical / concept / practice / check. Parses "P1 0 5, P2 1 3…" out of free text | Numbers and explanations need different handling |
| 6 | `checker.py` | Compares a student's Gantt chart with the simulator and finds the **first** step where they differ | Students lose marks on one wrong tie-break |
| 7 | `practice.py` | Makes a random problem, solves it, and re-reads it with the router to be sure it parses | Never hands out a problem the tutor would misread |
| 8 | `dataset_concepts.py`, `generate_dataset.py`, `prepare_dataset.py` | 46 hand-written + 91 reference Q&As + 124 simulator-generated records, then validate, dedupe, split | Training data must not contain a wrong solution |
| 9 | `evaluate.py` | Scores the system on 55 held-out questions | Objective 8 of your report |
| 10 | `tutor.py`, `viz.py`, `app.py` | Glue: runs the pipeline, draws Gantt charts, Streamlit tabs | Last, because it only wires up the rest |
| 11 | `run_demo_checks.py` | 23 PASS/FAIL checks, one per claim in the report | Proof for the demo |
| 12 | `finetune/` | Colab QLoRA script and Ollama Modelfile | Written but **not run yet** |

## The key pieces, with the code

### 1. The simulator: the part that guarantees correct numbers
Round Robin is where students go wrong, so the rule is explicit: **processes that arrive during a
time slice join the queue before the preempted process goes back.**

```python
# scheduler.py, inside round_robin()
cur = queue.popleft()
span = min(quantum, cur.remaining)
time += span
cur.remaining -= span
while i < n and order[i].arrival <= time:   # arrivals during the slice
    queue.append(order[i]); i += 1          # ...join FIRST
if cur.remaining > 0:
    queue.append(cur)                       # ...then the preempted process goes to the back
```

Every algorithm also writes a plain-English log ("t=4: quantum expires, P2 goes to the back").
That log is what the tutor and the checker use to *explain*.

Formulas used everywhere: `turnaround = completion − arrival`, `waiting = turnaround − burst`,
`response = first start − arrival`. Lower priority number = higher priority.

### 2. Chunking: why 300 words with overlap
```python
# clean_chunk.py
def chunk_text(text, chunk_words=300, overlap_words=45):
    # fill a chunk paragraph by paragraph; when full, start the next
    # chunk with the last 45 words of the previous one
```

### 3. Retrieval: cosine similarity, plus a "don't know" gate
Each chunk and the question become vectors; the closest 3 chunks are returned. Two safety checks
make it refuse "What is the capital of France?":
1. the best score must beat a threshold;
2. the question must contain at least one scheduling term.

### 4. The router: how a message becomes data
It recognises four ways students type process data: table rows (`P1 0 5`), labelled
(`P1: burst 10, priority 3`), parallel lists (`burst times 8,4,9,5 arrival times 0,1,2,3`) and
`P1=24, P2=3`. It also detects the algorithm ("preemptive SJF" → SRTF, "non-preemptive priority"
→ priority) and the quantum.

### 5. The answer checker: the "tutor" part
```python
# checker.py: compare time unit by time unit
for t in range(end):
    if mine.get(t) != truth.get(t):
        # "Your Gantt chart first diverges at t=4: you have P1, but P3 should run."
        # then print the simulator's decisions around t=4
        break
```
Stopping at the *first* difference matters: everything after it is a knock-on error.

### 6. Dataset validation (your report's Section 5.3)
Four filters in order: schema check → dedupe (so "context-switch" and "context switch" collide)
→ drop short/truncated answers → **recompute every numerical record with the simulator and reject
it if the stated average is wrong.** The sample file reproduces your Listing 5 exactly.

### 7. The "never trust the LLM" rule (`tutor.py`)
If an LLM is running, its text is scanned for "average waiting time = X"; if X disagrees with the
simulator the app flags it, and the simulator's table is always shown underneath. With no LLM the
tutor quotes sentences from the retrieved sources instead ("grounded template mode").

## Results you can quote
- Simulator matches all 5 textbook cases (17.00, 7.00, 6.50, 5.67, 8.20).
- Held-out set: numerical 30/30, router 55/55, off-topic refusals 5/5.
- Dataset: 1,027 records, 924 train / 103 validation, all numerical ones verified.
- Knowledge base: 372 chunks from 14 sources; every stored Q&A is its own retrievable unit.

## Be upfront about these (professors ask)
1. **QLoRA fine-tuning is not done**, the script is ready for Colab. That matches the report's "Pending".
2. **No LLM is running** on this laptop, so the demo is in grounded-template mode. Numbers are still computed.
3. **Retrieval uses TF-IDF**, not bge + FAISS, because those packages aren't installed. The bge code path exists.
4. The 20 concept questions in the eval set were written while tuning, so that 100% is optimistic; the
   numerical 100% is solid because the reference answers come from the simulator on unseen problems.

## Likely questions
- **Why a simulator instead of the LLM?** LLMs are unreliable at multi-step arithmetic; the simulator is exact and repeatable.
- **Why chunk overlap?** So a worked example isn't split between two chunks.
- **Why normalise vectors?** Then inner product equals cosine similarity, so a fast flat inner-product index works.
- **How do you stop hallucination?** Retrieval threshold + domain gate + citations + simulator-checked numbers.
- **Why not train on wrong solutions?** The model would learn the mistake; hence numerical verification before training.
- **What would you do next?** Run QLoRA on Colab, install bge + FAISS, add faculty slides to `corpus/institutional/`, compare against the base model with `python evaluate.py --baseline qwen3:4b`.

## Demo script (3 minutes)
1. `python run_demo_checks.py` → all PASS.
2. `streamlit run app.py` → Tutor tab → click the Round Robin q=4 example (5.67, Gantt chart, step log).
3. Click "A student says Round Robin causes starvation" → cited answer.
4. Click "What is the capital of France?" → refusal.
5. **Check my answer** tab → Check → "diverges at t=4".
6. **Pipeline & evaluation** tab → show the evaluation table.

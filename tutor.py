"""Query pipeline, Phase B of the architecture (report Section 6.1):

    question -> router -> [simulator] -> retrieval -> generation -> verified answer

Generation uses the fine-tuned Qwen 3 model served by Ollama when it is
running.  Without it the tutor still works in "grounded template" mode: numbers
come from the simulator and explanations are quoted from the retrieved course
material, so nothing is invented.  Either way the numbers shown to the student
are the simulator's, and an LLM answer that states a different average is
flagged and corrected.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import threading
import urllib.request

from build_index import tokenize
from intent import EXAM_INTENTS, detect_intent, direct_answer, examples_block, format_directive
import concept_check
import rich_answers
from checker import check_answer
from practice import verified_problem
from retriever import QUESTION_WORDS, Retriever, canon_tokens, cite
from router import route
from scheduler import check_invariants, gantt_text, solve, table_text

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# First model found is used: the fine-tuned adapter first, then the base model.
PREFERRED_MODELS = [m for m in [os.environ.get("OSTUTOR_MODEL"), "ostutor", "qwen2.5:3b-instruct",
                                 "qwen3:4b", "qwen3:8b"] if m]

SYSTEM_PROMPT = (
    "You are an Operating Systems tutor for a CPU-scheduling course. Write concise, exam-ready answers a student "
    "can learn from.\n"
    "- Answer the question directly in the first sentence, then define the concepts it asks about.\n"
    "- Use ONLY the numbered context passages and cite them as [1], [2]. If a claim is not supported by the context, "
    "leave it out. If the context does not answer the question, say so plainly instead of guessing.\n"
    "- Keep related concepts distinct (for example the convoy effect is not starvation) and never contradict "
    "yourself.\n"
    "- State the assumption behind any claim that holds only under conditions. Do not write 'always' or 'never' "
    "unless the context does.\n"
    "- Mention only the algorithms the question concerns; for numerical results use only the simulator output.")

NEEDS_MODEL = {"mcq", "true_false", "fill_blank", "incorrect_statement", "assertion_reason"}
MAX_REGENERATIONS = 1          # a failed fact check gets one corrected retry, then the vetted course answer is used


# --------------------------------------------------------------------------- #
# Generation backends                                                          #
# --------------------------------------------------------------------------- #
def ollama_model():
    """Name of an available tutor model in the local Ollama, or None."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.5) as r:
            names = [m["name"] for m in json.load(r).get("models", [])]
    except Exception:
        return None
    for want in PREFERRED_MODELS:
        for have in names:
            if have == want or have.split(":")[0] == want or have == want + ":latest":
                return have
    return None


KEEP_ALIVE = "60m"          # an idle model is otherwise unloaded after 5 min -> 1 min reload on next question


def ollama_chat(model, user_prompt, timeout=300, retries=1, system=None):
    body = json.dumps({
        "model": model, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.2, "num_predict": 600, "num_ctx": 4096},
        "messages": [{"role": "system", "content": system or SYSTEM_PROMPT},
                     {"role": "user", "content": user_prompt}],
    }).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    last = None
    for _ in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = json.load(r)["message"]["content"]
            return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
        except Exception as e:      # cold start / busy machine: the second try finds the model loaded
            last = e
    raise last


def warm_up(model):
    """Load the model into memory now (in the background) so the first question is not the slow one."""
    def _load():
        try:
            body = json.dumps({"model": model, "prompt": "", "keep_alive": KEEP_ALIVE}).encode()
            urllib.request.urlopen(urllib.request.Request(
                f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"}),
                timeout=300).read()
        except Exception:
            pass
    threading.Thread(target=_load, daemon=True).start()


FACT_CARD = ("Definitions used in this course (always correct; never change or restate them differently): "
             "turnaround time = completion time − arrival time; "
             "waiting time = turnaround time − burst time (= completion − arrival − burst); "
             "response time = time of first start on the CPU − arrival time; "
             "a LOWER priority number means a HIGHER priority; ties are broken by arrival time, then process number; "
             "FCFS, non-preemptive SJF and non-preemptive priority never interrupt a running process, "
             "while SRTF, preemptive priority and Round Robin can.")


CONCEPT_FACTS = (
    "Scheduling facts for explanations (state their assumptions; never contradict them): "
    "the convoy effect is a performance problem classically seen in FCFS, where short processes wait behind one long "
    "CPU-bound process (higher average waiting time, idle I/O devices); the wait is long but finite, and it is not "
    "starvation. Starvation means indefinite postponement of a process that keeps waiting for the CPU. It can occur in "
    "SJF/SRTF when shorter jobs keep arriving ahead of a long job, and in preemptive or non-preemptive Priority "
    "scheduling when low-priority processes are repeatedly bypassed; aging (gradually raising the priority of waiting "
    "processes) mitigates it. Standard FCFS does not normally starve a process, assuming the processes ahead of it "
    "terminate. Round Robin gives every ready process a bounded time quantum in cyclic order, so under standard "
    "assumptions it avoids starvation; it does not prioritise short processes (short jobs just finish in fewer turns).")


def _context_text(h, result):
    """The chunk text handed to the LLM. For a concept question (no verified
    `result` of its own) strip worked-example sentences out of the context:
    a small instruction-tuned model asked to "explain SJF" will otherwise copy
    the numbers from an unrelated solved instance in the retrieved chunk and
    mangle them into a fabricated, wrong worked example of its own."""
    if result:
        return h["text"]
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", h["text"])
    return " ".join(p for p in parts if not _is_worked_example(p))


def build_prompt(question, hits, result=None, idf=None, examples=True, web_hits=None, revision=None):
    ctx = "\n\n".join(f"[{i+1}] ({cite(h)})\n{_context_text(h, result)}" for i, h in enumerate(hits))
    parts = [FACT_CARD] + ([CONCEPT_FACTS] if not result else []) + [f"Context from the course material:\n{ctx}"]
    if web_hits and not result:
        n0 = len(hits)
        web = "\n\n".join(f"[{n0 + i + 1}] (web: {web_title(h)})\n{h['text']}" for i, h in enumerate(web_hits))
        parts.append("Additional material from the web (GeeksforGeeks). It is NOT vetted course material. Use it only to "
                     "add detail that the course material above lacks, in your own words. The course material and the "
                     "definitions above always win if they differ. If you use it, cite it as "
                     + ", ".join(f"[{n0 + i + 1}]" for i in range(len(web_hits))) + f".\n\n{web}")
    if result:
        parts.append("Simulator output (verified, do not change any number):\n"
                     f"Algorithm: {result['algorithm_name']}"
                     + (f", quantum {result['quantum']}" if result["quantum"] else "") + "\n"
                     f"Decisions:\n" + "\n".join(result["log"]) + "\n"
                     f"Gantt chart:\n{gantt_text(result['gantt'])}\n{table_text(result)}\n"
                     f"Average waiting time = {result['avg_waiting']:.2f}, "
                     f"average turnaround time = {result['avg_turnaround']:.2f}")
        parts.append(f"Student question: {question}\n\nAnswer exactly what was asked, using only the simulator "
                     "output for numbers. Explain how the answer follows from the Gantt chart, step by step. "
                     "Cite the context as [1], [2], [3] where you use it.")
    else:
        ex = examples_block(question, idf) if examples else ""
        if ex:
            parts.append(ex)
        parts.append(f"Student question: {question}\n\n{format_directive(question)}\n"
                     "Cite the context as [1], [2], [3] where you use it. Do not invent a numeric example "
                     "(process list, burst times, a Gantt chart, or waiting/turnaround numbers): the student "
                     "gets verified numbers from the simulator separately, never from you.")
    if revision:                                   # (rejected answer, what was wrong with it)
        parts.append(f"Rejected answer:\n{revision[0]}\n\n{revision[1]}")
    return "\n\n".join(parts)


WEB_MIN_SCORE = 0.20       # how relevant a web passage must be (web-only search scale)
# A web page may supplement an answer only if it is about the same topic as the question.
TOPIC_PAGES = [
    (r"round[- ]robin|\brr\b|quantum|time[- ]slice", "round-robin"),
    (r"\bsrtf\b|shortest remaining|preemptive sjf", "shortest-remaining"),
    (r"\bsjf\b|shortest job|\bsjn\b", "shortest-job-first"),
    (r"priorit", "priority-scheduling"),
    (r"\bhrrn\b|response ratio", "highest-response-ratio"),
    (r"multi-?level feedback|\bmlfq\b", "multilevel-feedback"),
    (r"multi-?level queue|\bmlq\b", "multilevel-queue"),
    (r"pre-?emptive|non-?pre-?emptive", "preemptive-and-non-preemptive"),
    (r"cpu scheduling|scheduling criteria|scheduler\b|dispatcher", "cpu-scheduling-in-operating-systems"),
]
_TOPIC_WORDS = {t for w in ("fcfs sjf srtf rr hrrn mlfq mlq edf priority round robin shortest job first remaining time "
                           "multilevel feedback queue response ratio next process processes algorithm scheduling "
                           "schedule cpu operating system").split() for t in tokenize(w)}


_GENERIC_ASKS = {t for w in ("characteristic characteristics feature features property properties work works working "
                             "handle handles handled detail details aspect aspects behaviour behavior important key "
                             "main basic basics idea concept").split() for t in tokenize(w)}


def specific_terms(question):
    """The part of the question beyond naming an algorithm: 'optimal', 'preemptive', 'quantum', 'starvation'..."""
    return {t for t in canon_tokens(question)
            if t not in _TOPIC_WORDS and t not in QUESTION_WORDS and t not in _GENERIC_ASKS}


def touches(sentence, terms):
    """True if the sentence uses one of the terms, allowing different word forms ('moved' ~ 'move')."""
    toks = set(tokenize(sentence))
    return any(t in toks or any(min(len(t), len(u)) >= 4 and t[:4] == u[:4] for u in toks) for t in terms)


SKIP_SECTIONS = re.compile(r"example|problem|conclusion|quiz|faq|summary|solution|practice|question", re.I)
WEB_MIN_NEW = 0.40         # share of its key terms that the vetted answer does not already contain
_WEB_META = {}


def web_meta(source):
    """{'url', 'title'} for a saved web page (read from the .meta.json written by the fetcher), else {}."""
    if source not in _WEB_META:
        path = pathlib.Path(__file__).parent / "corpus" / source
        try:
            _WEB_META[source] = json.loads(path.with_suffix(".meta.json").read_text())
        except (OSError, ValueError):
            _WEB_META[source] = {}
    return _WEB_META[source]


def web_title(hit):
    return web_meta(hit["source"]).get("title") or hit["source"].rsplit("/", 1)[-1]


def new_info_share(web_text, reference_texts):
    """Share of the web passage's key terms that the reference (vetted) text does not contain."""
    terms = {t for t in tokenize(web_text) if "_" not in t}
    known = {t for ref in reference_texts for t in tokenize(ref) if "_" not in t}
    return len(terms - known) / len(terms) if terms else 0.0


def _tidy(x):
    """The indexed web text was flattened (list bullets joined with ' - '), so repair the joins."""
    x = re.sub(r"\s-\s(?=[A-Z])", ". ", x)
    x = re.sub(r"^[-*•]\s*", "", x.strip())
    x = re.sub(r":\.", ":", x)
    x = re.sub(r"\s+([.,;:!?])", r"\1", x)            # "starvation ." -> "starvation."
    return re.sub(r"\.{2,}", ".", x).strip()


def excerpt(question, hit, idf=None, known=(), n=3, max_words=95, must_touch=()):
    """A short quote: the sentences of the passage that best answer the question AND add something the
    vetted answer ('known') does not already say."""
    flat = _tidy(hit["text"]).replace(".. ", ". ")
    sents = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", flat) if 5 <= len(x.split()) <= 70
             and "|" not in x and len(re.findall(r"\d", x)) <= 4 and " = " not in x]   # no table rows or worked arithmetic
    ranked = [x for _, x in best_sentences(question, [dict(hit, text=" ".join(sents))], n=8, idf=idf)] or sents[:3]
    fresh = [_tidy(x) for x in ranked if new_info_share(x, known) >= 0.35 and len(x.split()) >= 8
             and (not must_touch or touches(x, must_touch))]
    out, words = [], 0
    for x in fresh[:n]:
        if out and words + len(x.split()) > max_words:
            break
        out.append(x)
        words += len(x.split())
    return " ".join(out)


def bad_formulas(text):
    """Wrong textbook formulas in an LLM answer, e.g. 'waiting time = completion time - burst time - 1'."""
    problems = []
    for m in re.finditer(r"\b(waiting|turnaround|response)\s+time\s*(?:=|is calculated as|is given by|equals)\s*"
                         r"([^\n.;]*)", text, re.I):
        metric, rhs = m.group(1).lower(), m.group(2).lower()
        if re.search(r"(average|avg|mean|total|sum of)\s*$", text[max(0, m.start() - 12):m.start()].lower()):
            continue                                   # "average waiting time = (sum ...) / n" is a different formula
        w = set(re.findall(r"[a-z]+", rhs))
        if metric == "waiting":
            ok = ({"turnaround", "burst"} <= w and "completion" not in w) or {"completion", "arrival", "burst"} <= w \
                or ({"start", "arrival"} <= w and "burst" not in w)
        elif metric == "turnaround":
            ok = ({"completion", "arrival"} <= w and "burst" not in w) or {"waiting", "burst"} <= w
        else:
            ok = ("arrival" in w and bool(w & {"first", "start", "scheduled", "response"})) \
                or "waiting" in w                       # "equals waiting time" for non-preemptive algorithms
        if re.search(r"[-−+*/×]\s*\d", rhs):          # a stray constant such as "- 1"
            ok = False
        if not ok:
            problems.append(f"wrong formula: {m.group(0).strip()[:70]}")
    return problems


_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])")


def ungrounded_numbers(text, context, question):
    """Numbers in a concept answer that appear neither in the question nor in the retrieved course text:
    a sign the model invented an example. (Citation markers and list numbering are ignored.)"""
    body = re.sub(r"\[\d+\]", " ", text)
    body = re.sub(r"(?m)^\s*\d+[.)]\s", " ", body)
    known = set(_NUM.findall(context)) | set(_NUM.findall(question)) | {"0", "1"}
    return sorted(set(_NUM.findall(body)) - known)


def verify_llm_numbers(text, result):
    """Flag any 'average waiting/turnaround' in the LLM text that disagrees with the simulator."""
    problems = []
    for key, label in (("avg_waiting", "waiting"), ("avg_turnaround", "turnaround")):
        for m in re.finditer(r"average\s+" + label + r"[^\d\n]{0,40}?(\d+(?:\.\d+)?)", text, re.I):
            if abs(float(m.group(1)) - result[key]) > 0.011:
                problems.append(f"the model wrote average {label} time {m.group(1)}, "
                                f"the simulator computes {result[key]:.2f}")
    return problems


# --------------------------------------------------------------------------- #
# Grounded template mode (no LLM): extractive, cited, never invents content    #
# --------------------------------------------------------------------------- #
TOPIC_WORDS = {t for w in ("round robin sjf srtf fcfs priority scheduling schedule cpu process processes "
                            "algorithm algorithms").split() for t in tokenize(w)} | {"round_robin"}


ALGO_WORDS = {"FCFS": r"fcfs|first[- ]come|fifo", "SJF": r"\bsjf\b|srtf|shortest", "Priority": r"priorit",
              "Round Robin": r"round[- ]robin|\brr\b|quantum"}


def _is_worked_example(s):
    """True for a numeric walkthrough sentence ("SJF worked example. P1 = 6, ...
    average waiting time is (3 + 16 + 9 + 0) / 4 = 7.00") rather than a definition.
    Concept answers should explain the algorithm, not dump a solved instance of it —
    the simulator is where a student gets numbers, already solved step by step."""
    if re.search(r"\bworked example\b", s, re.I):
        return True
    if re.search(r"\b(gives?|is)\s+\d+(\.\d+)?\.?\s*$", s, re.I):   # "... gives 7.75." / "... is 6.50."
        return True
    digits = len(re.findall(r"\d+", s))
    return digits >= 4 and bool(re.search(r"[=–-]\s*\d|average (waiting|turnaround)", s, re.I))


DEFINITION_QUESTION = re.compile(r"\b(explain|what\s+is|what's|describe|define|tell me about)\b", re.I)


def best_sentences(question, hits, n=4, idf=None, topic=None):
    """Pick the n sentences that best answer the question, kept in reading order.

    Query words are weighted by rarity (IDF), and the algorithm's own name counts
    for little, so "Does RR cause starvation?" prefers the sentence about
    starvation over any sentence that merely says "round robin".
    """
    idf = idf or {}
    q = set(tokenize(question))
    weight = {t: (0.3 if t in TOPIC_WORDS else 1.0) * idf.get(t, 1.0) for t in q}
    # "Explain SJF" / "what is round robin" carry almost no query signal once the
    # algorithm's own name is down-weighted as a topic word, so the generic
    # relevance score can't tell a real definition from an unrelated fragment that
    # happens to mention the name too. Give definitional sentences ("X is a ...",
    # "X is the process of ...") a direct boost for this kind of question.
    definitional = bool(DEFINITION_QUESTION.search(question))
    # Find the opening, on-topic sentence of the single most relevant chunk: in
    # practice it is almost always the textbook definition, even when it scores
    # low on raw term overlap because it's long and doesn't repeat query words.
    # A chunk can open with a title/header line, so skip past anything too short
    # or (for an algorithm-specific question) that doesn't name the algorithm.
    def_anchor = None
    if definitional and hits:
        first_split = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", hits[0]["text"])
        for si0, s0 in enumerate(first_split):
            w0 = s0.split()
            if len(w0) < 6 or len(w0) > 70:
                continue
            if topic in ALGO_WORDS and not re.search(ALGO_WORDS[topic], s0, re.I):
                continue
            def_anchor = si0
            break
    # If the question asks about something beyond the algorithm's name, a sentence
    # must mention that something to be picked.
    specific = {t for t in q if t not in TOPIC_WORDS and t not in QUESTION_WORDS and "_" not in t}
    specific = {t for t in specific if any(t in tokenize(h["text"]) for h in hits)}
    scored, split = [], {}
    for hi, h in enumerate(hits):
        split[hi] = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", h["text"])
        for si, s in enumerate(split[hi]):
            words = s.split()
            if (len(words) < 3 or len(words) > 70 or s.count("|") > 2 or s.rstrip().endswith("?")
                    or re.search(r"https?://|\.org\b|\bISBN\b|\[\w+\d\d\]", s) or _is_worked_example(s)):
                continue
            hit_terms = q & set(tokenize(s))
            if specific and not hit_terms & specific:
                continue
            if topic in ALGO_WORDS:
                low = s.lower()
                about_other = any(re.search(pat, low) for t, pat in ALGO_WORDS.items() if t != topic)
                if about_other and not re.search(ALGO_WORDS[topic], low):
                    continue              # sentence is about a different algorithm
            score = sum(weight[t] for t in hit_terms)
            if definitional and score:
                if hi == 0 and si == def_anchor:
                    score += 2.0
                elif re.match(r"^[\w\s(),/-]{1,40}\bis\s+(a|an|the)\b", s, re.I):
                    score += 1.0
            if score:
                scored.append((score - 0.4 * hi - 0.01 * len(words), hi, si, s))
    top, seen = [], set()
    ranked = sorted(scored, reverse=True)
    best = ranked[0][0] if ranked else 0
    for item in ranked:
        if item[0] < 0.5 * best:           # weakly related: leave it out
            break
        key = item[3].strip().lower()
        if key not in seen:
            seen.add(key)
            top.append(item)
        if len(top) == n:
            break
    picked = {(hi, si): s for _, hi, si, s in top}
    # A very short sentence ("Round Robin does not cause starvation.") is usually
    # followed by its reason, so bring the next sentence along.
    for (hi, si), s in list(picked.items()):
        if len(s.split()) < 8 and si + 1 < len(split[hi]) and len(split[hi][si + 1].split()) <= 70:
            nxt = split[hi][si + 1]
            if not _is_worked_example(nxt):
                picked.setdefault((hi, si + 1), nxt)
    return [(hi, picked[(hi, si)]) for hi, si in sorted(picked)]


QUESTION_TITLE = re.compile(r"^(what|how|why|which|is|are|does|do|can|when|who|compare|explain|define|give|list|"
                            r"summari[sz]e|describe|a student says|should|would)\b", re.I)


def is_qa_title(title):
    """A stored Q&A has a question-style title. Section headings such as 'Round Robin (RR)' are not
    questions: showing their whole section as 'the answer' dumps worked examples nobody asked for."""
    t = (title or "").strip()
    return bool(t) and t != "Introduction" and (t.endswith("?") or bool(QUESTION_TITLE.match(t)))


_LEAD_CLASS = {"why": "why", "how": "how", "what": "what", "which": "which", "when": "when", "compare": "compare",
               "explain": "explain", "describe": "explain", "define": "explain", "tell": "explain", "give": "explain",
               **{w: "polar" for w in ("is", "are", "does", "do", "can", "should", "would", "will")}}


def _lead_class(text):
    """The kind of question: why / how / what / yes-no ... Used to break ties between titles with the same concepts."""
    m = re.match(r"^\W*(?:(?:pls|please|quick question|answer for an exam|in simple words)\W+)*([a-z]+)", text.lower())
    return _LEAD_CLASS.get(m.group(1)) if m else None


def display_title(title):
    t = title.strip().rstrip("?.")
    return t + ("?" if QUESTION_TITLE.match(t) and not t.lower().startswith(("compare", "explain", "define", "give",
                "list", "summarise", "summarize", "describe")) else "")


def qa_direct(question, hits):
    """No-LLM fallback: if the best-ranked passage is a stored, vetted Q&A, show it whole under its own
    question, so the student sees exactly which question is being answered. Returns (text, hit) or None."""
    if not hits:
        return None
    # hits is already sorted by score, which has the title match folded in; take the
    # first titled one, don't re-rank by title_boost alone (that ignores how well the
    # body itself matches and can pick a worse-fitting Q&A with a narrower title). But
    # when two titles are within noise of each other (e.g. "what is the time quantum"
    # vs "how should the time quantum be chosen" for "how to choose a time quantum"),
    # prefer whichever title more specifically matches the question.
    qa = [h for h in hits if is_qa_title(h.get("title"))]
    if not qa:
        return None
    close = [h for h in qa if qa[0]["score"] - h["score"] <= 0.05]
    top = max(close, key=lambda h: h.get("title_boost", 0))
    title = top["title"]
    if top["score"] < 0.2:
        return None
    return f"**{display_title(title)}**\n\n{top['text']} [1]", top


def template_concept(question, hits, idf=None, topic=None):
    picked = best_sentences(question, hits, idf=idf, topic=topic)
    if not picked:
        return None
    lines, lead = ["Here is what the course material says:\n"], None
    for k, (hi, s) in enumerate(picked):
        s = s.strip()
        nxt = picked[k + 1] if k + 1 < len(picked) else None
        if (len(s.split()) < 6 and nxt and nxt[0] == hi        # a label like "Starvation under SJF."
                and not re.match(r"(This|That|It|These|The|There)\b", s)):
            lead = s.rstrip(".")
            continue
        lines.append(f"- {'**' + lead + ':** ' if lead else ''}{s} [{hi+1}]")
        lead = None
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# "Which algorithm ...?" questions: the answer is a name, backed by a sentence #
# --------------------------------------------------------------------------- #
ALGO_NAMES = [      # (key, pattern, display name); a sentence "names" the algorithms whose pattern it contains
    ("srtf", r"\bsrtf\b|shortest[- ]remaining", "SRTF (Shortest Remaining Time First)"),
    ("rr", r"\brr\b|round[- ]robin", "Round Robin"),
    ("sjf", r"\bsjf\b|shortest[- ]job", "SJF (Shortest Job First)"),
    ("fcfs", r"\bfcfs\b|first[- ]come|\bfifo\b", "FCFS (First Come First Served)"),
    ("hrrn", r"\bhrrn\b|response ratio", "HRRN (Highest Response Ratio Next)"),
    ("mlfq", r"\bmlfq\b|multi-?level feedback", "MLFQ (Multilevel Feedback Queue)"),
    ("edf", r"\bedf\b|earliest deadline", "EDF (Earliest Deadline First)"),
    ("priority", r"\bpriority\b", "Priority Scheduling"),
]
ALGO_LABEL_FULL = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "priority": "Priority", "priority_p": "preemptive Priority",
                   "rr": "Round Robin"}
ALGO_LABEL_BY_TAG = {"FCFS": "fcfs", "SJF": "sjf", "Round Robin": "rr", "Priority": "priority", "MLFQ": "mlfq"}
ALGO_DISPLAY = {k: label for k, _, label in ALGO_NAMES}
CANON_ALGOS = {"fcfs", "rr", "sjf", "srtf", "hrrn", "mlfq", "edf"}
EVIDENCE_MIN = 0.5         # share of the question's (weighted) terms the best sentence must contain
TOP_K_SHOWN = 3           # passages shown and sent to the model, as for every other concept question
MAX_CONCEPT_PASSAGES = 5     # passages sent to the model for a multi-concept question (num_ctx is 4096 tokens)
IDENTIFY_POOL = 12         # passages searched for evidence; only the ones actually used are shown


_MAIN_ALGO_END = re.compile(r"(?:\bfcfs|\bsjf|\bsrtf|round[- ]robin|\bpriority)\??\s*$", re.I)   # "... overhead of SJF?"


def algorithms_in(text):
    """[(position, key)] for every algorithm the text names, in reading order."""
    found = [(m.start(), key) for key, pat, _ in ALGO_NAMES if (m := re.search(pat, text, re.I))]
    return sorted(found)


def selection_evidence(question, hits, idf=None):
    """Which algorithm does the course material say matches what the question describes?

    Every sentence of the retrieved passages is scored on how much of the question's *content* it
    states ("arrived earliest" ~ "arrived first, strictly in arrival order"); the algorithm each good
    sentence names then votes for itself.  Returns {key, label, sentences: [(hit, sentence)], coverage}
    or None when no sentence states enough of the question to answer it (the caller must then say so)."""
    idf = idf or {}
    default = sum(idf.values()) / len(idf) if idf else 1.0
    w = lambda t: idf.get(t, default)
    pool = set().union(*(canon_tokens(h["text"]) for h in hits)) if hits else set()
    # A word the course material never uses ("fixed") cannot be matched, so it is not held against a sentence.
    terms = {t for t in canon_tokens(question) if t not in QUESTION_WORDS} & pool
    if not terms or (len(terms) < 2 and len(canon_tokens(question)) > 1):
        return None
    total = sum(w(t) for t in terms)
    q_neg = bool(re.search(r"\b(?:not|no|never|cannot|can't|n't|without|doesn't|don't)\b", question, re.I))
    asked = terms & CANON_ALGOS                 # the question itself describes the algorithm by name ("shortest remaining")
    scored, seen = [], set()
    for hi, h in enumerate(hits):
        for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", h["text"]):
            words = sent.split()
            key = sent.strip().lower()
            if (not 4 <= len(words) <= 70 or key in seen or sent.rstrip().endswith("?") or sent.count("|") > 2
                    or re.search(r"https?://|\bISBN\b", sent) or _is_worked_example(sent)):
                continue
            seen.add(key)
            if not q_neg and re.search(r"\b(?:not|no|never|cannot|can't|n't|without)\b", sent, re.I):
                continue                 # "FCFS and Round Robin do NOT cause starvation" does not answer "which algorithm causes starvation"
            if re.match(r"(?:It|This|That|They|Then|In that case)\b", sent.strip()) and re.search(
                    r"\bif\b|what happens|very (?:large|small)", (h.get("title") or ""), re.I):
                continue                 # "It then has the convoy effect": about a hypothetical case, not the passage's own algorithm
            toks = canon_tokens(sent)
            hit_w = sum(w(t) for t in terms & toks)
            if not hit_w:
                continue
            recall = hit_w / total
            precision = hit_w / max(1e-9, sum(w(t) for t in toks))     # a focused sentence beats a long one that also matches
            named = algorithms_in(sent)
            if named:       # the algorithm the question describes, else the one the sentence is about (named first)
                algo = next((k for _, k in named if k in asked), named[0][1])
            else:           # "Each process gets a small unit of CPU time called the quantum": the passage's topic
                algo = ALGO_LABEL_BY_TAG.get(h["algorithm"])
            scored.append((0.8 * recall + 0.2 * precision - 0.01 * hi, recall, algo, h, sent.strip()))
    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    best = scored[0][0]
    votes = {}
    for sc, rc, algo, h, sent in scored[:6]:
        if sc >= 0.8 * best and algo:
            votes[algo] = votes.get(algo, 0) + sc
    if not votes or max(rc for _, rc, *_ in scored[:6]) < EVIDENCE_MIN:
        return None
    key = max(votes, key=votes.get)
    support = [(h, sent) for sc, rc, algo, h, sent in scored if algo == key and sc >= 0.8 * best][:1]
    return {"key": key, "label": ALGO_DISPLAY[key], "sentences": support, "coverage": round(max(rc for _, rc, *_ in scored[:6]), 2)}


def template_identify(ev, used):
    """The no-LLM answer to 'which algorithm ...': the name first, then the course's own sentence(s)."""
    lines = [f"**Answer: {ev['label']}**", ""]
    lines += [f"- {sent} [{used.index(h) + 1}]" for h, sent in ev["sentences"]]
    return "\n".join(lines)


NO_EVIDENCE = ("I couldn't find a passage in the course material that says which algorithm that describes, "
               "so I won't guess. Try naming the rule (for example *shortest burst*, *time quantum*, "
               "*arrival order*) or the algorithms you are choosing between.")


def numerical_summary(result, notes):
    """Short chat text for the UI, which draws the Gantt chart and table itself."""
    q = f" with time quantum {result['quantum']}" if result["quantum"] else ""
    n = len(result["rows"])
    w = " + ".join(str(r["waiting"]) for r in result["rows"])
    t = " + ".join(str(r["turnaround"]) for r in result["rows"])
    return (f"**{result['algorithm_name']}{q}**: solved by the scheduling simulator (computed, not generated).\n\n"
            f"- Average waiting time = ({w}) / {n} = **{result['avg_waiting']:.2f}**\n"
            f"- Average turnaround time = ({t}) / {n} = **{result['avg_turnaround']:.2f}**\n\n"
            "Waiting = turnaround − burst, turnaround = completion − arrival. "
            "Open *Walk me through it, step by step* to replay every choice the scheduler makes.")


def comparison_text(results, route):
    """Several algorithms run on the SAME validated process data: a table of the averages, which is lowest on this
    workload (never 'the best algorithm'), and each Gantt chart. Every number comes from the simulator."""
    rows = ["| Algorithm | Avg waiting | Avg turnaround | Avg response |", "|---|---|---|---|"]
    for r in results:
        q = f" (q={r['quantum']})" if r["quantum"] else ""
        rows.append(f"| {r['algorithm_name']}{q} | {r['avg_waiting']:.2f} | {r['avg_turnaround']:.2f} | {r['avg_response']:.2f} |")
    best = min(results, key=lambda r: r["avg_waiting"])
    tied = [r for r in results if r["avg_waiting"] == best["avg_waiting"]]
    verdict = (f"On these processes, **{' and '.join(r['algorithm_name'] for r in tied)}** "
               f"{'give' if len(tied) > 1 else 'gives'} the lowest average waiting time ({best['avg_waiting']:.2f}). "
               "That holds for this workload and this metric only: another metric (response time, fairness) or another "
               "set of processes can favour a different algorithm.")
    charts = "\n\n".join(f"**{r['algorithm_name']}**\n```\n{gantt_text(r['gantt'])}\n```" for r in results)
    note = ("\n\nAssumptions: " + "; ".join(route.notes) + ".") if route.notes else ""
    return ("Solved by the scheduling simulator (computed, not generated), all algorithms on the same data:\n\n"
            + "\n".join(rows) + "\n\n" + verdict + note + "\n\n" + charts)


def template_numerical(result, notes):
    q = f" with time quantum {result['quantum']}" if result["quantum"] else ""
    out = [f"**{result['algorithm_name']}{q}**: solved by the scheduling simulator "
           "(computed, not generated).\n"]
    if notes:
        out.append("Assumptions: " + "; ".join(notes) + ".\n")
    out.append("**Step 1: scheduling decisions**")
    out += [f"- {line}" for line in result["log"]]
    out.append("\n**Step 2: Gantt chart**\n```\n" + gantt_text(result["gantt"]) + "\n```")
    out.append("**Step 3: times** (turnaround = completion − arrival, waiting = turnaround − burst, "
               "response = first run − arrival)\n\n" + table_text(result))
    n = len(result["rows"])
    w = " + ".join(str(r["waiting"]) for r in result["rows"])
    t = " + ".join(str(r["turnaround"]) for r in result["rows"])
    out.append(f"\n**Step 4: averages**\n- Average waiting time = ({w}) / {n} = **{result['avg_waiting']:.2f}**"
               f"\n- Average turnaround time = ({t}) / {n} = **{result['avg_turnaround']:.2f}**"
               f"\n- Average response time = **{result['avg_response']:.2f}**")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
# ---- multi-part questions: "Why is SJF optimal, and why can't real systems use it?" -----------------------------------
_WH = r"(?:why|how|when|what|which|where|who|can|could|does|do|is|are|should|would|will)"
_JOIN = re.compile(r"\s*(?:\?+\s+|;\s+|,?\s+and\s+(?:also\s+|then\s+)?(?=" + _WH + r"\b)|,?\s+(?:also|plus)\s+(?=" + _WH + r"\b))", re.I)
_POSSESSIVE = re.compile(r"\b(?:its|their)\b", re.I)
_PRONOUN = re.compile(r"\b(?:it|they|them|this algorithm|that algorithm|this one|that one)\b", re.I)
MAX_PARTS = 3
# "What is context switching? Why does it ..." -> the concept the first part asks about is what "it" means
_ASKED_ABOUT = re.compile(r"^\W*(?:what\s+(?:is|are|was|does)|what's|explain|define|describe|tell\s+me\s+about)\s+"
                          r"(?:the\s+|a\s+|an\s+)?(.+?)(?:\s+mean|\s+work)?\W*$", re.I)


def split_parts(question, in_domain=None):
    """Split a compound concept question into standalone questions, or return [question] for a single one.

    Every part must be a real question of its own (>= 3 words, opening with a question word or a verb like
    "explain"). A pronoun, or a missing subject, in a later part is filled in from the algorithm named earlier
    ("why can't real systems use it" -> "why can't real systems use SJF"), so each part can be retrieved and
    answered on its own. `in_domain(text)` keeps a long off-topic part ("how does B-tree indexing work") from borrowing
    the algorithm of an on-topic part and passing as in scope."""
    q = question.strip()
    if re.search(r"\d", q) and re.search(r"\bP\d|burst|arriv|quantum", q, re.I):
        return [q]                                            # a scheduling problem, not a compound question
    pieces = [x.strip(" ,;?") for x in _JOIN.split(q) if x and x.strip(" ,;?")]
    if not 2 <= len(pieces) <= MAX_PARTS:
        return [q]
    opener = re.compile(r"^\W*(?:" + _WH + r"|explain|describe|compare|define|give|tell|list|state)\b", re.I)
    if len(pieces[0].split()) < 2 or any(len(x.split()) < 3 for x in pieces[1:]) or not all(opener.match(x) for x in pieces[1:]):
        return [q]
    named = []
    for key, pat, _ in ALGO_NAMES:
        m = re.search(pat, pieces[0], re.I)
        if m:
            named.append((m.start(), m.group(0)))
    names = [t for _, t in sorted(named)]
    parts = [pieces[0]]
    concept = _ASKED_ABOUT.match(pieces[0])
    concept = concept.group(1) if concept and len(concept.group(1).split()) <= 5 else None
    algos = " and ".join(dict.fromkeys(names)) if names else None
    subject = concept or algos          # "What is priority inversion? How is it solved?": 'it' is the concept, not 'priority'
    for x in pieces[1:]:
        if _PRONOUN.search(x) or _POSSESSIVE.search(x):
            if subject:
                x = _POSSESSIVE.sub(subject + "'s", x, count=1)
                x = _PRONOUN.sub(subject, x, count=1)
            elif not algorithms_in(x):
                return [q]                                    # "how can it be fixed" with nothing for "it" to mean
        elif algos and not algorithms_in(x) and (in_domain is None or len(x.split()) <= 4 or in_domain(x)):
            x = f"{x} ({algos})"
        parts.append(x)
    wh = re.compile(r"^\W*" + _WH + r"\b", re.I)
    return [x + "?" if wh.match(x) and not x.endswith("?") else x for x in parts]


_LEVEL_RANK = {"error": 0, "unverified": 1, "none": 2, "checked": 3, "stored": 4, "verified": 5}


def _shift_citations(text, offset):
    """Part 2's [1] must point at its own passage once the passages of part 1 come first in the source list."""
    return re.sub(r"\[(\d+)\]", lambda m: f"[{int(m.group(1)) + offset}]", text) if offset else text


class Tutor:
    def __init__(self, use_llm=True):
        self.retriever = Retriever()
        self.model = ollama_model() if use_llm else None
        if self.model:
            warm_up(self.model)

    @property
    def mode(self):
        return f"LLM: {self.model} via Ollama" if self.model else "grounded template (no LLM running)"

    def _related(self, question, hits, n=3):
        """Other stored questions on the same topic, offered as follow-ups."""
        seen, out = set(), []
        for h in self.retriever.search(question, k=10):
            t = h.get("title")
            if is_qa_title(t) and t not in seen and h.get("title_match", 0) < 0.999:
                seen.add(t)
                out.append(t)
            if len(out) == n:
                break
        return out

    def _identify_hits(self, question, topic, hits):
        """For 'which algorithm ...?': search a wider pool, find the sentence that states the rule the question
        describes, and put the passages that state it first so the prompt, the citations and the sources agree."""
        pool = self.retriever.search(question, k=IDENTIFY_POOL, algorithm=topic)
        evidence = selection_evidence(question, pool, self.retriever.idf_lookup())
        if not evidence:
            return hits, None
        used = [h for h, _ in evidence["sentences"]]
        ordered = used + [h for h in pool if all(h is not u for u in used)]
        return ordered[:max(TOP_K_SHOWN, len(used))], evidence

    def web_passages(self, question, reference_texts, topic=None, k=2):
        """Up to k GeeksforGeeks passages that are about the same topic, relevant, and add information the
        vetted material lacks. Example problems and summaries are skipped (their numbers and conventions
        may differ from the course)."""
        low = question.lower()
        pages = [page for pat, page in TOPIC_PAGES if re.search(pat, low)]
        if not pages:
            return []                              # cannot tell which web page would be on-topic: add nothing
        found = self.retriever.search(question, k=12, algorithm=topic, origin="web")
        good = [h for h in found
                if any(pg in h["source"] for pg in pages) and h["score"] >= WEB_MIN_SCORE
                and not SKIP_SECTIONS.search(str(h["page"])) and len(h["text"].split()) >= 40
                and (specific_terms(question) or not re.match(r"(Introduction|What is)", str(h["page"]), re.I))
                and new_info_share(h["text"], reference_texts) >= WEB_MIN_NEW]
        return good[:k]

    def _more_detail(self, question, reference, topic=None):
        """The 'More detail' card shown under an answer: the single best web passage, quoted briefly.
        `reference` is the text already given to the student (a string or a list of strings)."""
        reference = [reference] if isinstance(reference, str) else list(reference)
        # a web passage only "adds" something if the WHOLE vetted neighbourhood lacks it, not just the 3 shown passages
        reference += [h["text"] for h in self.retriever.search(question, k=8, algorithm=topic)]
        if detect_intent(question)[0] in ("analogy", "formula"):
            return None                             # a web page's analogy or formula may differ from the course's
        best = self.web_passages(question, reference, topic, k=1)
        if not best:
            return None
        h = best[0]
        meta = web_meta(h["source"])
        spec = {t for t in specific_terms(question)}
        quote = excerpt(question, h, self.retriever.idf_lookup(), known=reference, must_touch=spec)
        if len(quote.split()) < 12:                # nothing worth quoting: show no card
            return None
        return {"title": web_title(h), "url": meta.get("url"), "section": h["page"] if isinstance(h["page"], str) else "",
                "excerpt": quote, "source": h["source"]}

    def _generate(self, question, hits, result=None, web_hits=None, revision=None):
        """LLM answer if available, with the numbers checked; else None."""
        if not self.model:
            return None, []
        try:
            text = ollama_chat(self.model, build_prompt(question, hits, result, self.retriever.idf_lookup(),
                                                      examples=not self.model.startswith("ostutor"),
                                                      web_hits=web_hits, revision=revision))
        except Exception as e:  # model crashed / timed out: degrade, don't fail the student
            return None, [f"LLM unavailable ({type(e).__name__}); fell back to template mode"]
        problems = verify_llm_numbers(text, result) if result else []
        return text, problems

    def _concept_hits(self, question, hits, topic):
        """A question about two or more concepts ("convoy effect vs starvation") needs the passage that defines
        EACH of them, not five passages about whichever the query words match best.  Keep the passages the question
        itself retrieved, add the best defining passage per named concept, drop duplicates, cap the context."""
        concepts = concept_check.concepts_in(question)
        if len(concepts) < 2:
            return hits
        picked, seen = [], set()
        def add(h):
            key = (h["source"], h.get("title") or h["text"][:60])
            if key not in seen:
                seen.add(key)
                picked.append(h)
        for h in hits[:2]:
            add(h)
        for c in concepts:
            for h in self.retriever.search(concept_check.CONCEPT_QUERIES[c][1], k=1, algorithm=topic):
                add(dict(h, title_match=0, title_boost=0))      # matched the concept query, not the student's question
        for h in hits[2:]:
            add(h)
        return picked[:MAX_CONCEPT_PASSAGES]

    def _pros_cons_hits(self, question):
        """"Advantages and disadvantages of X" needs the advantages passage AND the disadvantages passage; one ranked
        list tends to return only one of them. Returns (advantages_hit, disadvantages_hit), either may be None."""
        found = algorithms_in(question)
        if not found or not re.search(r"advantage|pros|benefit|merit", question, re.I) \
                or not re.search(r"disadvantage|cons\b|drawback|demerit|limitation", question, re.I):
            return None, None
        name = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": "Round Robin", "priority": "Priority scheduling",
                "hrrn": "HRRN scheduling", "mlfq": "multilevel feedback queue scheduling", "edf": "EDF"}[found[0][1]]
        pick = []
        for kind in ("advantages", "disadvantages"):
            want = f"What are the {kind} of {name}?"
            hs = [h for h in self.retriever.search(want, k=3) if h.get("title_match", 0) >= 0.8 and is_qa_title(h.get("title"))
                  and re.search(r"\b" + kind + r"\b", h["title"], re.I) and not re.search(r"\badvantages and", h["title"], re.I)]
            pick.append(hs[0] if hs else None)
        return tuple(pick)

    @staticmethod
    def _supported(question, hit):
        """A stored passage may stand as THE answer only if it contains what this kind of question needs and passes the
        same fact rules as a model answer. (Questions without a registered spec are not filtered.)"""
        if concept_check.spec_for(question)[0] is None or detect_intent(question)[0] in EXAM_INTENTS:
            return True
        return not concept_check.missing_points(question, hit["text"]) and not concept_check.rule_problems(hit["text"])

    def _verified_concept_answer(self, question, hits, web_hits, out):
        """LLM answer for a concept question after the conceptual fact check: a failed check gets one corrected
        retry, then the answer is dropped (caller falls back to the vetted course text). Every failure is logged."""
        llm, problems = self._generate(question, hits, web_hits=web_hits)
        out["notes"] += problems
        context = " ".join(h["text"] for h in hits + web_hits)
        for attempt in range(MAX_REGENERATIONS + 1):
            if not llm:
                return None
            verdict = concept_check.verify(question, llm, context, require_points=detect_intent(question)[0] not in EXAM_INTENTS)
            if verdict["ok"]:
                break
            last = attempt == MAX_REGENERATIONS
            concept_check.log_failure(question, llm, verdict, f"attempt {attempt + 1}", "fallback" if last else "regenerate")
            out.setdefault("verification", []).append(verdict["problems"] + verdict["missing"])
            if last:
                out["guard"] = verdict["problems"] + verdict["missing"]
                out["notes"].append("The model's answer failed the conceptual fact check twice, so the course answer "
                                    "is shown instead (" + "; ".join((verdict["problems"] + verdict["missing"])[:2])[:240] + ").")
                return None
            llm, more = self._generate(question, hits, web_hits=web_hits,
                                       revision=(llm, concept_check.correction_note(verdict)))
            out["notes"] += more
        judge_model = os.environ.get("OSTUTOR_JUDGE_MODEL")        # optional second opinion; advisory, never blocks
        if judge_model and llm:
            try:
                issues = concept_check.parse_judge(ollama_chat(
                    judge_model, concept_check.judge_prompt(question, llm, context), system="You are a strict fact checker."))
            except Exception:
                issues = []
            if issues:
                concept_check.log_failure(question, llm, {"problems": issues, "missing": []}, "judge", "advisory")
                out["notes"].append("Independent model check (advisory, may be wrong): " + "; ".join(issues))
        return llm

    _CHATTY = [(re.compile(r"^\W*(?:i\s*)?(?:do\s*n'?o?t|dont|don'?t|can'?t|cannot|cant|am not able to)\s+"
                           r"(?:really\s+)?(?:understand|get|follow)\s+(?:how\s+|what\s+|why\s+)?(.+)$", re.I), "explain "),
               (re.compile(r"^\W*i(?:'m| am)\s+(?:so\s+|really\s+)?(?:confused|lost|stuck)\s+(?:about|on|with|by)\s+(.+)$",
                           re.I), "explain "),
               (re.compile(r"^\W*(?:i\s+)?(?:need|want)\s+(?:help|to learn|to understand)\s+(?:with|about|on)?\s*(.+)$", re.I),
                "explain ")]

    @classmethod
    def _plain(cls, question):
        """"I don't understand round robin" -> "explain round robin": the student is asking for an explanation."""
        for pat, lead in cls._CHATTY:
            m = pat.match(question.strip())
            if m:
                return lead + m.group(1).strip().rstrip(".!")
        return question

    def answer(self, question):
        """The public entry point: never raises, and says honestly how far the answer was verified (out["status"])."""
        try:
            parts = split_parts(self._plain(question), self.retriever.in_domain)
            out = self._answer_parts(question, parts) if len(parts) > 1 else self._answer(question)
        except Exception as e:                       # retrieval / parsing / simulation bug: a controlled message, logged
            concept_check.log_failure(question, "", {"problems": [f"{type(e).__name__}: {e}"], "missing": []}, "pipeline", "error")
            return {"kind": "error", "algorithm": None, "result": None, "hits": [], "notes": [], "mode": self.mode,
                    "in_scope": True, "text": "Something went wrong while answering that, so I won't guess. "
                    "Please try rephrasing, or paste the process table directly. (The error was logged.)",
                    "status": {"level": "error", "label": "Error: no answer produced"}}
        if "status" not in out:
            out["status"] = self._status(question, out)
        return out

    def _answer_parts(self, question, parts):
        """Answer each part of a compound question on its own, then join the answers under the part they answer."""
        subs = []
        for part in parts:
            o = self._answer(part)
            o["status"] = self._status(part, o)
            subs.append((part, o))
        answered = [(q, o) for q, o in subs if o.get("in_scope", True) and o["kind"] == "concept" and o.get("text")]
        seen, unique = set(), []
        for q, o in answered:                                 # "What is a CPU burst? What is an I/O burst?" -> one passage
            key = o["text"][:200]
            if key not in seen:
                seen.add(key)
                unique.append((q, o))
        dropped = [o for _, o in answered if not any(o is u for _, u in unique)]
        answered = unique
        if not answered:
            return self._answer(question)                     # nothing in scope: the ordinary refusal is the honest answer
        skipped = [q for q, o in subs if not any(o is a for _, a in answered) and not any(o is d for d in dropped)]
        if len(answered) == 1:
            q, o = answered[0]
            if skipped:                                       # (parts that merely share this answer need no note)
                o["notes"] = o["notes"] + ["Your question had more than one part; the course material only answers: " + q]
            return o
        hits, blocks, notes, offset = [], [], [], 0
        for i, (q, o) in enumerate(answered, 1):
            body = _shift_citations(o["text"], offset)
            m = re.match(r"\*\*(.+?)\*\*\n\n", body)         # the stored answer already carries its own bold title
            blocks.append(f"**Part {i}: {m.group(1)}**\n\n{body[m.end():]}" if m else f"**Part {i}: {q}**\n\n{body}")
            hits += o.get("hits", [])
            offset = len(hits)
            notes += [n for n in o.get("notes", []) if n not in notes]
        if skipped:
            notes.append("I could not answer from the course material: " + "; ".join(skipped))
        text = "\n\n---\n\n".join(blocks)
        worst = min((o["status"] for _, o in answered), key=lambda st_: _LEVEL_RANK[st_["level"]])
        first = answered[0][1]
        return {"kind": "multi", "algorithm": first.get("algorithm"), "result": None, "hits": hits, "notes": notes,
                "mode": first["mode"], "in_scope": True, "text": text, "summary": text,
                "related": first.get("related", []),
                "status": {"level": worst["level"], "label": f"Answered in {len(answered)} parts. " + worst["label"]}}

    def _status(self, question, out):
        """How was this answer checked? Only claim what actually happened."""
        results = [x for x in ([out.get("result")] + list(out.get("results") or [])) if x]
        if results:
            bad = [p for r in results for p in check_invariants(r)]
            if bad:
                out["text"] = ("The simulator's own consistency check failed (" + "; ".join(bad[:2]) + "), so I am not showing "
                               "these numbers as verified. Please report this input.")
                out["summary"] = out["text"]
                return {"level": "error", "label": "Simulator self-check failed: numbers withheld"}
            return {"level": "verified", "label": "Verified: computed by the deterministic simulator; turnaround, waiting, "
                    "response times and the Gantt chart were re-checked against their definitions"}
        if out["kind"] in ("needs_data", "invalid"):
            return {"level": "none", "label": "Nothing to verify: more or corrected input is needed"}
        if out["kind"] != "concept" or not out.get("in_scope", True):
            return {"level": "none", "label": "Out of scope: nothing to verify" if not out.get("in_scope", True) else "Not verified"}
        if out.get("generated"):
            v = concept_check.verify(question, out["text"], " ".join(h["text"] for h in out.get("hits", [])),
                                     require_points=detect_intent(question)[0] not in EXAM_INTENTS)
            return {"level": "checked" if v["ok"] else "unverified",
                    "label": "Generated answer; passed the automatic fact-rule check (rule-based, not a guarantee)" if v["ok"]
                    else "Generated answer; the fact-rule check found issues: " + "; ".join((v["problems"] + v["missing"])[:2])}
        if out.get("mode", "").startswith("retrieval only"):
            return {"level": "none", "label": "No answer given: only the relevant passages are listed"}
        if out.get("mode", "").startswith("stored"):
            return {"level": "stored", "label": "Vetted course text, shown as written (not generated)"}
        return {"level": "stored", "label": "Sentences quoted from the course material (not generated)"}

    def _answer(self, question):
        question = self._plain(question)
        question, typos = self.retriever.autocorrect(question)     # "algortihms" -> "algorithms", "robbin" -> "robin"
        r = route(question)
        out = {"kind": r.kind, "algorithm": r.algorithm, "result": None, "hits": [],
               "notes": list(r.notes), "mode": self.mode, "in_scope": True, "text": ""}
        if typos:
            out["notes"].append("Read your question with spelling fixed: " + ", ".join(dict.fromkeys(f"{a} → {b}" for a, b in typos)) + ".")

        if r.kind == "practice":
            text, result, _ = verified_problem(r.algorithm)
            out.update(result=result, problem=text,
                       text="Here is a new practice problem (generated and checked by the simulator):\n\n"
                            "```\n" + text + "\n```\nTry it yourself, then open the solution below "
                            "or paste your answer in **Check my answer**.")
            return out

        if r.kind == "needs_data":
            name = ALGO_LABEL_FULL.get(r.algorithm, "that algorithm")
            out.update(in_scope=True, text=(
                f"I can solve that with the scheduling simulator, but I need the process data. "
                f"Send the {name} problem with each process's arrival and burst time, for example "
                f"`P1 0 5, P2 1 3, P3 2 8` (pid arrival burst){' and the time quantum, e.g. `quantum 2`' if r.algorithm == 'rr' else ''}. "
                "If you leave out arrival times I assume every process arrives at t=0"
                + (", and if you leave out the quantum I assume q = 2" if r.algorithm == "rr" else "")
                + ". Or ask for *a practice problem* and I will generate one and solve it."))
            return out

        if r.kind == "invalid":
            out.update(in_scope=True, text="I can't run the simulator on that input: " + "; ".join(r.notes) + ". "
                       "Please correct it (every burst time must be a positive whole number, arrival times 0 or more, "
                       "and a Round Robin time quantum a positive whole number) and send it again.")
            return out

        if r.kind == "compare_numerical":
            try:
                results = [solve(a, r.processes, r.quantum if a == "rr" else None) for a in r.algorithms]
            except ValueError as e:
                out.update(text=f"I can't run the simulator on that input: {e}.")
                return out
            out.update(results=results, notes=out["notes"] + list(r.notes), text=comparison_text(results, r))
            out["summary"] = out["text"]
            return out

        if r.kind == "worked_example":
            text, result, _ = verified_problem(r.algorithm, quantum=r.quantum)
            topic_q = f"{result['algorithm_name']} scheduling algorithm how it works"
            hits = self.retriever.search(topic_q, algorithm=r.topic)
            out.update(result=result, problem=text, hits=hits)
            llm, problems = self._generate(question, hits, result)
            worked = ("Here's a worked example, generated and verified by the simulator:\n\n"
                     "```\n" + text + "\n```\n\n" + template_numerical(result, r.notes))
            out["text"] = worked
            out["summary"] = llm or (f"Here's a worked example of {result['algorithm_name']}, solved and "
                                     "verified by the simulator. Open *Walk me through it, step by step* "
                                     "below to see exactly how each decision was made.")
            if llm:
                out["text"] = llm + "\n\n---\n**Verified by the simulator:**\n\n" + worked
            if problems:
                out["notes"] += problems
            return out

        if r.kind == "check":
            problem, _, mine = re.split(r"(my answer|answer\s*:|i got)", question, maxsplit=1, flags=re.I) \
                if re.search(r"(my answer|answer\s*:|i got)", question, re.I) else (question, "", question)
            rp = route(problem)
            procs = rp.processes or r.processes
            algo = rp.algorithm or r.algorithm or "fcfs"
            result = solve(algo, procs, rp.quantum or r.quantum or (2 if algo == "rr" else None))
            verdict = check_answer(result, mine)
            out.update(result=result, check=verdict,
                       text=("✅ Your answer matches the simulator." if verdict["correct"] else
                             "❌ Not quite. " + (verdict["first_error"] or "")) + "\n\n" +
                            "\n".join(f"- {f}" for f in verdict["findings"]))
            return out

        if r.kind == "numerical":
            try:
                result = solve(r.algorithm, r.processes, r.quantum)
            except ValueError as e:
                out.update(text=f"I can't run the simulator on that input: {e}.")
                return out
            topic_q = f"{result['algorithm_name']} scheduling algorithm how it works"
            hits = self.retriever.search(topic_q, algorithm=r.topic)
            out.update(result=result, hits=hits)
            llm, problems = self._generate(question, hits, result)
            out["text"] = template_numerical(result, r.notes)
            direct = direct_answer(question, result)
            if llm:
                problems = problems + bad_formulas(llm)
                if problems:                      # never show an explanation that contradicts the simulator
                    llm = None
                    out["notes"].append("The model's explanation contradicted the simulator, so only the "
                                        "verified numbers are shown.")
            body = llm or numerical_summary(result, r.notes)
            out["summary"] = (direct + "\n\n" + body) if direct else body
            if llm:
                out["text"] = llm + "\n\n---\n**Verified by the simulator:**\n\n" + template_numerical(result, r.notes)
            if problems:
                out["notes"] += problems
            return out

        # concept question
        intent = detect_intent(question)[0]
        hits = self.retriever.search(question, algorithm=r.topic)
        if not r.topic and not algorithms_in(question) and intent not in ("identify", "compare", "recommend"):
            # a general question ("why does context switching introduce overhead?") must not be answered by the
            # per-algorithm passage ("... of SJF") that merely shares its words: demote those, searching deeper first
            # because the general passage can sit below five per-algorithm ones
            pool = self.retriever.search(question, k=20, algorithm=r.topic)
            for h in pool:
                if _MAIN_ALGO_END.search(h.get("title") or "") and h.get("title_match", 0) < 0.999:
                    h["score"] -= 0.35
            hits = sorted(pool, key=lambda h: -h["score"])[:len(hits) or TOP_K_SHOWN]
        if intent == "identify" and any(is_qa_title(h.get("title")) and h.get("title_match", 0) >= 0.999 for h in hits):
            intent = "answer"      # the question IS a stored question: its vetted answer beats matching rule sentences,
                                   # which cannot tell "X causes starvation" from "X does not cause starvation"
        evidence = None
        if intent != "identify":
            hits = self._concept_hits(question, hits, r.topic)
        if intent == "identify":       # "which algorithm ...?": find the passage that states the rule, don't match topics
            hits, evidence = self._identify_hits(question, r.topic, hits)
        adv = dis = None
        if intent == "pros_cons":
            adv, dis = self._pros_cons_hits(question)
            hits = [h for h in (adv, dis) if h] + [h for h in hits if h is not adv and h is not dis]
        out["hits"] = hits
        if not self.retriever.in_scope(question, hits) and not (
                evidence and self.retriever.in_domain(question) and not self.retriever.other_topic(question)):
            out.update(in_scope=False, hits=[],
                       text="That question is outside my scope: I only answer questions about CPU scheduling from the "
                            "course material, and I couldn't find anything relevant to it in my knowledge base. "
                            "Try asking about FCFS, SJF/SRTF, Priority, Round Robin, or paste a "
                            "scheduling problem to solve.")
            return out
        out["related"] = self._related(question, hits)
        out["intent"] = intent
        if not self.model and intent in NEEDS_MODEL:         # extractive mode cannot judge options or a verdict: say so
            label = intent.replace("_", " ").replace("mcq", "multiple-choice").replace("true false", "true/false")
            out["text"] = (f"This is a {label} question. Judging it needs the language model, which is not running, so I "
                           "won't guess an answer. The course passages most relevant to it are listed below.")
            out["mode"] = "retrieval only (language model not running)"
            return out
        if self.retriever.partial_coverage(question, hits):
            out["notes"].append("The course material covers only part of this question, so the answer is based on the "
                                "closest passages. Check the cited sources.")
        rich = rich_answers.find(question, canon_tokens)
        if rich and not os.environ.get("OSTUTOR_NO_SHORTCUT"):          # a hand-written side-by-side table
            out["rich"] = rich_answers.to_markdown(rich)
            out["title"], out["body"] = rich["title"], rich_answers.flat_text(rich)
            out["text"] = f"**{rich['title']}**\n\n{out['body']}"
            out["mode"] = "stored course answer (structured comparison table)"
            out["related"] = [t for t in out["related"] if t != rich["title"]]
            out["more"] = self._more_detail(question, [out["body"]] + [h["text"] for h in hits[:3]], r.topic)
            return out
        if adv and dis and not os.environ.get("OSTUTOR_NO_SHORTCUT"):         # both halves are vetted: show both
            out["title"] = display_title(question.strip().rstrip("?.")) 
            out["body"] = f"**Advantages.** {adv['text']}\n\n**Disadvantages.** {dis['text']}"
            out["text"] = out["body"] + " [1][2]"
            out["mode"] = "stored course answers (advantages + disadvantages)"
            out["more"] = None
            return out
        # The question is (nearly) a stored course question: the vetted answer beats a small model's paraphrase.
        exact = [h for h in hits if is_qa_title(h.get("title")) and h.get("title_match", 0) >= 0.999
                 and self._supported(question, h)]
        if exact and not os.environ.get("OSTUTOR_NO_SHORTCUT"):   # set to test the model itself, not the stored answers
            top = max(exact, key=lambda h: (h.get("title_boost", 0),
                                            _lead_class(h["title"]) == _lead_class(question) is not None,
                                            out["intent"] == "compare" and h["title"].endswith("in detail")))   # that one renders as a table
            out["title"], out["body"] = display_title(top["title"]), top["text"]
            out["text"] = f"**{out['title']}**\n\n{top['text']} [1]"
            out["mode"] = "stored course answer (question matches a vetted Q&A exactly)"
            out["hits"] = [top] + [h for h in hits if h is not top]
            out["related"] = [t for t in out["related"] if t != top["title"]]
            out["more"] = self._more_detail(question, [top["text"]] + [h["text"] for h in hits[:3]], r.topic)
            return out
        web_hits = self.web_passages(question, [h["text"] for h in hits], r.topic) if self.model else []
        llm = self._verified_concept_answer(question, hits, web_hits, out)
        if llm:
            bad = bad_formulas(llm)
            invented = ungrounded_numbers(llm, " ".join(h["text"] for h in hits + web_hits), question)
            if invented:
                bad.append("numbers not found in the course material: " + ", ".join(invented))
            if bad:
                out["guard"] = bad
                out["notes"].append("The model's answer was replaced by the course answer because it contained "
                                    + "; ".join(bad) + ".")
                llm = None
            else:                                  # say so when the answer actually draws on web text
                n0 = len(hits)
                used = [h for i, h in enumerate(web_hits) if f"[{n0 + i + 1}]" in llm]
                if used:
                    out["web_used"] = [{"title": web_title(h), "url": web_meta(h["source"]).get("url")} for h in used]
                    out["hits"] = hits + web_hits
                    out["notes"].append("ℹ️ This answer includes detail from GeeksforGeeks (web, not vetted course material): "
                                        + "; ".join(web_title(h) for h in used) + ".")
        if llm and evidence and evidence["key"] not in {k for _, k in algorithms_in(llm)}:
            out["guard"] = ["the algorithm named in the course material"]
            out["notes"].append(f"The model's answer did not name {evidence['label']}, which the course material "
                                "identifies, so the course answer is shown instead.")
            llm = None
        # A whole stored Q&A is only the answer when the question asks for what its title asks; a "which algorithm"
        # question is answered from the evidence sentence, never by the nearest definition.
        direct = None if llm or intent == "identify" else qa_direct(question, [h for h in hits if self._supported(question, h)])
        if direct:
            out["text"], top = direct
            out["title"], out["body"] = display_title(top["title"]), top["text"]
            out["related"] = [t for t in out["related"] if t != top["title"]]
            out["hits"] = [top] + [h for h in hits if h is not top]
            out["more"] = self._more_detail(question, [top["text"]] + [h["text"] for h in hits[:3]], r.topic)
            return out
        if intent == "identify" and not evidence and not llm:
            # No sentence states a rule that identifies one algorithm. Before giving up, use the stored Q&A whose
            # title is clearly the question asked; otherwise say there is nothing (never guess).
            stored = qa_direct(question, [h for h in hits if self._supported(question, h) and h.get("title_match", 0) >= 0.5])
            if stored:
                out["text"], top = stored
                out["title"], out["body"] = display_title(top["title"]), top["text"]
                out["related"] = [t for t in out["related"] if t != top["title"]]
                out["hits"] = [top] + [h for h in hits if h is not top]
                return out
            fallback = NO_EVIDENCE      # never show loose passages as if they named the algorithm
        elif intent == "identify":
            fallback = template_identify(evidence, hits) if evidence else NO_EVIDENCE
        else:
            fallback = template_concept(question, hits, self.retriever.idf_lookup(), r.topic) \
                or "The material I found is listed below."
        out["text"] = llm or fallback
        out["generated"] = bool(llm)
        if not out.get("web_used"):               # the answer did not draw on the web page: still offer what it adds
            out["more"] = self._more_detail(question, [out["text"]] + [h["text"] for h in hits], r.topic)
        return out

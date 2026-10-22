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
from intent import detect_intent, direct_answer, examples_block, format_directive
import rich_answers
from checker import check_answer
from practice import verified_problem
from retriever import QUESTION_WORDS, Retriever, canon_tokens, cite
from router import route
from scheduler import gantt_text, solve, table_text

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
# First model found is used: the fine-tuned adapter first, then the base model.
PREFERRED_MODELS = [m for m in [os.environ.get("OSTUTOR_MODEL"), "ostutor", "qwen2.5:3b-instruct",
                                 "qwen3:4b", "qwen3:8b"] if m]

SYSTEM_PROMPT = ("You are an Operating Systems tutor. Explain CPU scheduling step by step, "
                 "using only the context provided, and cite the source note.")


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


def ollama_chat(model, user_prompt, timeout=300, retries=1):
    body = json.dumps({
        "model": model, "stream": False, "think": False, "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0.2, "num_predict": 600, "num_ctx": 4096},
        "messages": [{"role": "system", "content": SYSTEM_PROMPT},
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


def build_prompt(question, hits, result=None, idf=None, examples=True, web_hits=None):
    ctx = "\n\n".join(f"[{i+1}] ({cite(h)})\n{_context_text(h, result)}" for i, h in enumerate(hits))
    parts = [FACT_CARD, f"Context from the course material:\n{ctx}"]
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
    close = [h for h in qa if qa[0]["score"] - h["score"] <= 0.02]
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
ALGO_LABEL_BY_TAG = {"FCFS": "fcfs", "SJF": "sjf", "Round Robin": "rr", "Priority": "priority", "MLFQ": "mlfq"}
ALGO_DISPLAY = {k: label for k, _, label in ALGO_NAMES}
CANON_ALGOS = {"fcfs", "rr", "sjf", "srtf", "hrrn", "mlfq", "edf"}
EVIDENCE_MIN = 0.5         # share of the question's (weighted) terms the best sentence must contain
TOP_K_SHOWN = 3           # passages shown and sent to the model, as for every other concept question
IDENTIFY_POOL = 12         # passages searched for evidence; only the ones actually used are shown


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

    def _generate(self, question, hits, result=None, web_hits=None):
        """LLM answer if available, with the numbers checked; else None."""
        if not self.model:
            return None, []
        try:
            text = ollama_chat(self.model, build_prompt(question, hits, result, self.retriever.idf_lookup(),
                                                      examples=not self.model.startswith("ostutor"),
                                                      web_hits=web_hits))
        except Exception as e:  # model crashed / timed out: degrade, don't fail the student
            return None, [f"LLM unavailable ({type(e).__name__}); fell back to template mode"]
        problems = verify_llm_numbers(text, result) if result else []
        return text, problems

    def answer(self, question):
        r = route(question)
        out = {"kind": r.kind, "algorithm": r.algorithm, "result": None, "hits": [],
               "notes": list(r.notes), "mode": self.mode, "in_scope": True, "text": ""}

        if r.kind == "practice":
            text, result, _ = verified_problem(r.algorithm)
            out.update(result=result, problem=text,
                       text="Here is a new practice problem (generated and checked by the simulator):\n\n"
                            "```\n" + text + "\n```\nTry it yourself, then open the solution below "
                            "or paste your answer in **Check my answer**.")
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
            result = solve(r.algorithm, r.processes, r.quantum)
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
        evidence = None
        if intent == "identify":       # "which algorithm ...?": find the passage that states the rule, don't match topics
            hits, evidence = self._identify_hits(question, r.topic, hits)
        out["hits"] = hits
        if not self.retriever.in_scope(question, hits) and not (evidence and self.retriever.in_domain(question)):
            out.update(in_scope=False, hits=[],
                       text="I can only answer questions about CPU scheduling from the course material, "
                            "and I couldn't find anything relevant to that in my knowledge base. "
                            "Try asking about FCFS, SJF/SRTF, Priority, Round Robin, or paste a "
                            "scheduling problem to solve.")
            return out
        out["related"] = self._related(question, hits)
        out["intent"] = intent
        rich = rich_answers.find(question, canon_tokens)
        if rich and not os.environ.get("OSTUTOR_NO_SHORTCUT"):          # a hand-written side-by-side table
            out["rich"] = rich_answers.to_markdown(rich)
            out["title"], out["body"] = rich["title"], rich_answers.flat_text(rich)
            out["text"] = f"**{rich['title']}**\n\n{out['body']}"
            out["mode"] = "stored course answer (structured comparison table)"
            out["related"] = [t for t in out["related"] if t != rich["title"]]
            out["more"] = self._more_detail(question, [out["body"]] + [h["text"] for h in hits[:3]], r.topic)
            return out
        # The question is (nearly) a stored course question: the vetted answer beats a small model's paraphrase.
        exact = [h for h in hits if is_qa_title(h.get("title")) and h.get("title_match", 0) >= 0.999]
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
        llm, problems = self._generate(question, hits, web_hits=web_hits)
        out["notes"] += problems
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
        direct = None if llm or intent == "identify" else qa_direct(question, hits)
        if direct:
            out["text"], top = direct
            out["title"], out["body"] = display_title(top["title"]), top["text"]
            out["related"] = [t for t in out["related"] if t != top["title"]]
            out["hits"] = [top] + [h for h in hits if h is not top]
            out["more"] = self._more_detail(question, [top["text"]] + [h["text"] for h in hits[:3]], r.topic)
            return out
        if intent == "identify":
            fallback = template_identify(evidence, hits) if evidence else NO_EVIDENCE
        else:
            fallback = template_concept(question, hits, self.retriever.idf_lookup(), r.topic) \
                or "The material I found is listed below."
        out["text"] = llm or fallback
        if not out.get("web_used"):               # the answer did not draw on the web page: still offer what it adds
            out["more"] = self._more_detail(question, [out["text"]] + [h["text"] for h in hits], r.topic)
        return out

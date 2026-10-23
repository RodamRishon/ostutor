"""Retrieval layer: top-k cosine search over the saved index (report Section 6.2).

If the best match falls below a threshold the tutor says the question is
outside its knowledge base instead of making up an answer.
"""
from __future__ import annotations

import json
import re
from collections import Counter
import math

import numpy as np

from build_index import EMBED_MODEL, INDEX_DIR, build, stem, tokenize

TOP_K = 3
# Cosine thresholds differ by backend: dense BGE scores sit much higher than sparse TF-IDF.
THRESHOLD = {"bge": 0.55, "tfidf": 0.05}
# TF-IDF only: share of the query's content words that must appear in the top hits.
MIN_COVERAGE = 0.5
# A question must mention at least one of these (stemmed) to be in scope at all.
DOMAIN_TERMS = {"schedul", "scheduler", "cpu", "process", "burst", "quantum", "quanta", "slice", "preempt",
                "preemptive", "preemption", "starvation", "starve", "aging", "ageing", "convoy", "fcfs", "fifo",
                "sjf", "srtf", "sjn", "stcf", "rr", "round", "robin", "priority", "prioriti", "waiting",
                "turnaround", "response", "throughput", "context", "switch", "dispatcher", "dispatch",
                "gantt", "queue", "ready", "mlfq", "multilevel", "feedback", "utilization", "utilisation",
                "job", "interactive", "latency", "shortest", "first", "come", "served", "arrival", "fairness",
                "fair", "overhead", "exponential", "average", "pcb", "thread", "multiprogramming",
                "sharing", "timesharing", "multitasking", "batch", "dispatch", "short-term",
                "affinity", "cache", "migrate", "migration", "linux", "balance", "balancing", "load",
                "multiprocessor", "symmetric", "asymmetric", "smp", "gang", "lottery", "stride", "ticket",
                "hrrn", "edf", "deadline", "periodic", "monotonic", "degree", "cfs"}
DOMAIN_STEMS = {t for term in DOMAIN_TERMS for t in tokenize(term) if "_" not in t} | DOMAIN_TERMS
# Course notes and institutional material outrank general references (textbook-style conventions).
SOURCE_WEIGHT = {"notes": 1.25, "institutional": 1.3}   # web text is searched separately, never mixed in with these

# Words that frame a question rather than name its topic; ignored by the coverage test.
QUESTION_WORDS = {"student", "say", "says", "correct", "true", "false", "explain", "describe", "define",
                  "definition", "difference", "differ", "compare", "comparison", "mean", "meant", "tell",
                  "give", "example", "analogy", "why", "happen", "work", "use", "used", "what", "right",
                  "wrong", "claim", "friend", "think", "note", "between", "versu", "vs"}
QUESTION_WORDS |= {"pros", "cons", "pro", "con", "advantage", "disadvantage", "drawback", "benefit", "limitation",
                   "weakness", "strength", "analogy", "real", "life", "simple", "word", "easy", "step", "example",
                   "formula", "pseudocode", "friend", "right", "mean", "meaning", "better", "best", "choose", "when",
                   "would", "should", "need", "needed", "good", "bad", "pick", "tell", "abt", "wat", "diff", "b/w",
                   "vs", "versus", "part", "algo", "write", "short", "brief", "briefly", "notes", "answer", "marks",
                   "detail", "detailed", "list", "give", "state", "mention", "discuss", "elaborate", "summarize",
                   "summary", "overview", "introduction", "concept", "concepts", "topic", "pls", "plz", "please"}
QUESTION_WORDS |= {"using", "mentioned", "stated", "according", "my", "our"}
QUESTION_WORDS |= {stem(w) for w in QUESTION_WORDS}


# Student shorthand and abbreviations: the query is searched with both forms so "rr" finds "Round Robin".
ALIASES = [
    (r"\brr\b|round[- ]robin", "round robin rr"),
    (r"\bfcfs\b|first[- ]come", "first come first served fcfs"),
    (r"\bsjf\b|shortest[- ]job", "shortest job first sjf"),
    (r"\bsrtf\b|shortest[- ]remaining|preemptive sjf", "shortest remaining time first srtf preemptive sjf"),
    (r"\bhrrn\b|response ratio", "highest response ratio next hrrn"),
    (r"\bmlfq\b|multi-?level feedback", "multilevel feedback queue mlfq"),
    (r"\bedf\b|earliest deadline", "earliest deadline first edf"),
    (r"drawback|demerit|\bcons\b|weakness|limitation|downside|problem with", "disadvantages"),
    (r"\bpros\b|merit|benefit|strength|upside|good about", "advantages"),
    (r"pros and cons|pros & cons", "advantages disadvantages"),
    (r"real[- ]life|everyday|real[- ]world|layman|like i'?m (5|five)", "analogy"),
    (r"\bwat\b", "what"), (r"\babt\b", "about"), (r"\bb/?w\b", "between"), (r"\bdiff\b", "difference"),
    (r"\bvs\.?\b|\bversus\b", "compare difference"),
    (r"starv", "starvation indefinite blocking"),
    (r"utili[sz]ation", "utilisation utilization"),
    (r"time[- ]slice|time quantum|\bquantum\b", "time quantum time slice"),
    (r"non[- ]?preemptive|cooperative", "non-preemptive"),
    (r"\bpreempt", "preemptive preemption"),
    (r"\bmax\b", "maximum"), (r"\bmin\b", "minimum"),
    (r"fastest|quickest|efficien\w*", "best efficient fastest"),
    (r"recommend\w*|suggest\w*|most suitable|\bideal\b|preferred", "best"),
    (r"choose|chosen|choice|select|pick", "choose chosen selected"),
]
TITLE_BOOST = 0.7
DIVERSITY_BONUS = 0.45      # a later passage earns this much for covering ALL still-uncovered question terms
COVERAGE_BONUS = 0.3        # added when a passage contains every content word of the question (scaled by their rarity)
_FRAME = {t for w in ("what is are the of a an how does do why which explain describe define tell me about "
                      "please give simple words in easy scheduling schedule algorithm algorithms cpu "
                      "difference compare should would could can will may use used write short note brief "
                      "vs versus between differ differences contrast comparison detail detailed briefly").split()
          for t in tokenize(w)}


# Many spellings -> one concept token, used only for title matching so abbreviations don't add noise.
# "types of CPU scheduling algorithms", "list the scheduling algorithms" ... all ask for the list of algorithms.
# Without a concept of their own, "cpu", "scheduling" and "algorithms" are stripped as framing words and the
# question shrinks to {type}, which then matches "What are the types of schedulers?" (long/medium/short-term).
_SCHED_ALGO = r"(?:(?:cpu|process)\s+)?scheduling\s+(?:algorithms?|algos?|policies)|cpu\s+(?:algorithms?|algos?)"
_SCHED_ALGO_PL = r"(?:(?:cpu|process)\s+)?scheduling\s+(?:algorithms|algos|policies)|cpu\s+(?:algorithms|algos)"
CANON = [
    (r"\b(?:introduces?|incurs?)\b", " cause "),            # "why does X introduce overhead" = "why does X cause overhead"
    (r"compare\s+(?:all|every)\s+(?:the\s+)?(?:" + _SCHED_ALGO_PL + r")\b", " compareall "),
    (r"\b(?:(?:different|various|diff|main|major|basic|common|all|the)\s+)*"
     r"(?:types?|kinds?|categories|classes|classification)\s+of\s+(?:" + _SCHED_ALGO + r"|(?:cpu|process)\s+scheduling)\b",
     " algolist "),
    (r"\bscheduling\s+(?:algorithms?|algos?)\s+list\b|\b(?:all|every)\s+(?:the\s+)?(?:" + _SCHED_ALGO_PL + r")\b",
     " algolist "),
    (r"\b(?:list|name|enumerate|mention|state)\s+(?:out\s+)?(?:all\s+)?(?:the\s+)?(?:(?:different|various)\s+)?"
     r"(?:" + _SCHED_ALGO_PL + r")\b(?=\s*(?:[?.,]|$|in\b|used\b|with\b|and\b|along\b|briefly\b))", " algolist "),
    (r"\b(?:how many|what|which)\s+(?:" + _SCHED_ALGO_PL + r")\s+(?:are there|exist|do we have|are available|are used)\b",
     " algolist "),
    (r"operating[- ]systems?|\bos\b", " "),                      # every passage is about an OS: the words carry no signal
    (r"first[- ]come[- ]first[- ]served|first[- ]come|\bfcfs\b", " fcfs "),
    (r"round[- ]robin|\brr\b", " rr "),
    (r"shortest[- ]remaining[- ]time[- ]first|shortest[- ]remaining|\bsrtf\b|preemptive sjf|preemptive shortest",
     " srtf "),
    (r"shortest[- ]job[- ]first|shortest[- ]job[- ]next|\bsjf\b|\bsjn\b", " sjf "),
    (r"highest[- ]response[- ]ratio[- ]next|\bhrrn\b", " hrrn "),
    (r"multi-?level[- ]feedback[- ]queue|\bmlfq\b", " mlfq "),
    (r"earliest[- ]deadline[- ]first|\bedf\b", " edf "),
    (r"time[- ]quantum|time[- ]slice|\bquantum\b|\bquanta\b", " quantum "),
    (r"disadvantages?|drawbacks?|\bcons\b|demerits?|weakness(es)?|limitations?|downsides?|pros and cons",
     " disadvantage "),
    (r"advantages?|\bpros\b|merits?|benefits?|strengths?", " advantage "),
    (r"utili[sz]ation", " utilisation "),
    (r"non[- ]?preemptive|cooperative", " nonpreempt "),
    (r"\bpre-?empt\w*", " preempt "),   # \b: do not re-match inside the " nonpreempt " token above
    (r"starv\w*|indefinite blocking", " starve "),
    (r"most efficient|more efficient|efficien\w*|fastest|quickest|speediest", " best "),
    (r"most fair|fairest|fairer", " fair "),
    (r"like i'?m (?:5|five)|like i am (?:5|five)|\beli5\b|layman\w*|plain english|in simple (?:words|terms)", " analogy "),
    (r"\bpurpose\b|\bgoals?\b|\baims?\b|\bobjectives?\b|\bused for\b|\brole\b", " purpose "),
    (r"\bneeded\b|\bneed\b|\bnecessary\b|\bimportance\b|\bimportant\b", " need "),
    (r"summar\w*|overview|\bnotes? (?:on|about|for)\b|short note|\bintroduction to\b|tell me about|everything about",
     " overview "),
    (r"recommend\w*|suggest\w*|most suitable|ideal|preferred", " best "),
    (r"\blead(?:s|ing)?\s+to\b|\bresult(?:s|ing)?\s+in\b|\bbring(?:s|ing)?\s+about\b|\bcauses?\b|\bcausing\b", " cause "),
    (r"types?|kinds?|categories|classes", " type "),
    (r"real[- ]life|everyday|real[- ]world|analog\w*", " analogy "),
    (r"\bwat\b", " what "), (r"\babt\b", " about "), (r"\bb/?w\b", " between "), (r"\bmax\b|maximum", " maximum "),
    (r"choose|chosen|choice|select\w*|picked?", " choose "),
    (r"\bsuitab\w*|appropriate|\bused?\b|use[- ]cases?|\bapplications?\b|best suited|ideal for", " usecase "),
    (r"comput\w*|calculat\w*|work(ing)? out|\bfind(ing)?\b|\bdetermine\b|\bformula\b|\bequation\b", " calculate "),
    (r"\bwait\w*", " waiting "), (r"turn\s*-?around|\btat\b", " turnaround "),
    (r"\btie\w*\b|\bsame\s+(burst|arrival|priority)\w*|equal\s+(burst|arrival|priority)\w*", " tiebreak "),
    # "arrived earliest" in a question and "arrival order ... arrived first" in the notes are the same idea
    (r"\barriv\w*", " arrival "), (r"\b(?:earliest|soonest|first)\b", " earliest "), (r"\bsmallest\b", " shortest "),
]


def _osa(a, b, limit):
    """Edit distance counting insert / delete / substitute / adjacent swap each as 1 ("algortihm" -> "algorithm" = 1).
    Returns limit + 1 as soon as the distance is known to exceed `limit`."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2, prev = None, list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


# Words that frame a question or are student shorthand. They are never "corrected", even when the course
# text happens not to contain them.
_KNOWN_EXTRA = {"explain", "describe", "define", "compare", "difference", "differences", "between", "example",
                "examples", "simple", "easily", "please", "working", "works", "algorithm", "algorithms", "which",
                "different", "types", "kinds", "everything", "details", "detail", "overview", "students",
                "student", "numerical", "problem", "problems", "solve", "solution", "answer", "question"}


def canon_tokens(text):
    low = text.lower()
    for pat, rep in CANON:
        low = re.sub(pat, rep, low)
    return {t for t in tokenize(low) if "_" not in t and t not in _FRAME}


_FALLBACK_FRAME = {t for w in ("what is are the of a an how does do why which explain describe define tell me about please give "
                              "in simple words operating system systems os") .split() for t in tokenize(w)}


def title_tokens(text):
    """canon_tokens, but a question such as "explain CPU scheduling" (nothing left once framing words are removed) keeps its
    topic words, so it can still be matched against the title "What is CPU scheduling?"."""
    toks = canon_tokens(text)
    if toks:
        return toks
    return {t for t in tokenize(text) if "_" not in t and t not in _FALLBACK_FRAME}


CANON_ALGOS = {"fcfs", "rr", "sjf", "srtf", "hrrn", "mlfq", "edf"}
CANON_DOMAIN = {"fcfs", "rr", "sjf", "srtf", "hrrn", "mlfq", "edf", "quantum", "starve", "preempt", "nonpreempt",
                "utilisation", "waiting", "turnaround", "calculate"}


def expand_query(query):
    low = query.lower()
    extra = [add for pat, add in ALIASES if re.search(pat, low)]
    return query + " " + " ".join(extra) if extra else query


class Retriever:
    def __init__(self, index_dir=INDEX_DIR):
        self.index_dir = index_dir
        if not (index_dir / "backend.json").exists():
            build(index_dir=index_dir, quiet=True)
        info = json.loads((index_dir / "backend.json").read_text())
        self.backend = info["backend"]
        self.records = json.loads((index_dir / "metadata.json").read_text())
        if self.backend == "bge":
            import faiss
            from sentence_transformers import SentenceTransformer
            self.index = faiss.read_index(str(index_dir / "scheduling.faiss"))
            self.model = SentenceTransformer(EMBED_MODEL)
        else:
            self.matrix = np.load(index_dir / "tfidf_matrix.npy")
            self.idf = np.load(index_dir / "tfidf_idf.npy")
            self.vocab = json.loads((index_dir / "tfidf_vocab.json").read_text())
        self.threshold = THRESHOLD[self.backend]
        # How rare each concept is among the stored Q&A titles: "choose" is rare, "round robin" is everywhere.
        titles = [canon_tokens(r["title"]) for r in self.records if r.get("title")]
        df = Counter(t for ts in titles for t in ts)
        self.title_weight = {t: math.log((len(titles) + 1) / (c + 1)) + 1.0 for t, c in df.items()}

    def _scores(self, query, n=50):
        if self.backend == "bge":
            # bge models recommend this instruction prefix for short retrieval queries
            q = self.model.encode(["Represent this sentence for searching relevant passages: " + query],
                                  normalize_embeddings=True).astype("float32")
            scores, ids = self.index.search(q, min(n, len(self.records)))
            return list(zip(ids[0].tolist(), scores[0].tolist()))
        vec = np.zeros(len(self.vocab), dtype="float32")
        for t, c in Counter(tokenize(query)).items():
            if t in self.vocab:
                vec[self.vocab[t]] = (1 + math.log(c)) * self.idf[self.vocab[t]]
        norm = np.linalg.norm(vec)
        if norm == 0:
            return []
        sims = self.matrix @ (vec / norm)
        top = np.argsort(-sims)[:n]
        return [(int(i), float(sims[i])) for i in top]

    def search(self, query, k=TOP_K, algorithm=None, origin="vetted"):
        """Return up to k hits: dicts with text, source, page, algorithm, score.

        `origin`: "vetted" (default) = your notes, OSTEP and Wikipedia; "web" = scraped web pages only;
        "all" = both mixed. Web text is kept apart so it can supplement an answer but never displace one.

        `algorithm` (e.g. "Round Robin") prefers chunks tagged with that topic,
        which the router sets when the question names an algorithm.
        """
        hits = []
        q_tokens = title_tokens(query)
        q_low = query.lower()
        q_neg = bool(re.search(r"\bnot\b|n't|\bnever\b|\bwithout\b", q_low))
        q_terms = {t for t in q_tokens if t not in QUESTION_WORDS}
        q_words = " ".join(re.findall(r"[a-z0-9]+", query.lower()))
        query = expand_query(query)
        candidates = self._scores(query, n=len(self.records) if origin == "web" else 50)
        if origin != "web" and q_tokens:
            # A stored question that says the same thing in other words ("give me a summary" = "overview of ...")
            # may share no word with the question, so keyword search alone never reaches it. Add every stored
            # question whose concept words overlap strongly; the title boost below then ranks it.
            if not hasattr(self, "_title_sets"):
                self._title_sets = [(i, canon_tokens(rec["title"])) for i, rec in enumerate(self.records) if rec.get("title")]
            have = {i for i, _ in candidates}
            candidates = list(candidates) + [(i, 0.0) for i, ts in self._title_sets
                                              if i not in have and ts and len(q_tokens & ts) / len(q_tokens | ts) >= 0.6]
        for i, s in candidates:
            r = dict(self.records[i])
            is_web = r["source"].startswith("web/")
            if (origin == "vetted" and is_web) or (origin == "web" and not is_web):
                continue
            title = r.get("title") or ""
            if title and q_tokens:        # a stored Q&A whose title says what the student asked
                t_tokens = title_tokens(title)
                if t_tokens:
                    r["title_match"] = round(len(q_tokens & t_tokens) / len(q_tokens | t_tokens), 3)  # 1.0 = identical
                    w = lambda ts: sum(self.title_weight.get(t, 2.0) for t in ts)   # rare concepts count more
                    both = w(q_tokens & t_tokens)
                    # half "how similar are they", half "how much of the question does this title cover"
                    boost = TITLE_BOOST * (0.5 * both / w(q_tokens | t_tokens) + 0.5 * both / w(q_tokens))
                    r["title_boost"] = round(boost, 3)
                    s += boost
                    extra_algos = (t_tokens & CANON_ALGOS) - q_tokens
                    if extra_algos and q_tokens & CANON_ALGOS:
                        s *= 0.85 ** len(extra_algos)      # the title is about an algorithm the student did not ask about
                    if re.search(r"\bnot\b|n't|\bnever\b", title.lower()) and not q_neg:
                        s *= 0.85                  # "Why is FCFS NOT suitable ..." does not answer "Where is FCFS suitable?"
            if q_terms and origin == "vetted":     # (web text keeps its own score scale: WEB_MIN_SCORE is calibrated on it)
                                                   # how much of the question's (rare-weighted) content does the passage contain?
                have = self._terms(r)
                w = lambda t: self.title_weight.get(t, 2.0)
                s += COVERAGE_BONUS * sum(w(t) for t in q_terms if t in have) / sum(w(t) for t in q_terms)
            if title and q_words and q_words == " ".join(re.findall(r"[a-z0-9]+", title.lower())):
                s += 1.0                         # the question word for word: its own stored answer, not a near neighbour
                r["title_match"] = 1.0
            s *= SOURCE_WEIGHT.get(r["source"].split("/")[0], 1.0)
            if algorithm and r["algorithm"] == algorithm:
                s *= 1.15                          # small boost, not a hard filter
            r["score"] = round(s, 3)
            hits.append(r)
        hits.sort(key=lambda h: -h["score"])
        return self._diversify(hits, q_terms, k) if origin == "vetted" else hits[:k]

    def _terms(self, rec):
        """Canonical + plain stemmed tokens of a passage's title and text, cached (searches run on every question)."""
        cache = self.__dict__.setdefault("_term_cache", {})
        key = (rec["source"], rec.get("title"), rec["text"][:80], len(rec["text"]))
        if key not in cache:
            blob = (rec.get("title") or "") + " " + rec["text"]
            cache[key] = frozenset(canon_tokens(blob) | set(tokenize(blob)))
        return cache[key]

    def _diversify(self, hits, q_terms, k):
        """Pick k passages so that together they cover the question's content words (greedy set cover on top of the score):
        the best passage first, then the passage that adds the most not-yet-covered question terms.  Stops "How does aging
        prevent starvation?" from returning three passages about starvation and none about aging."""
        if k <= 1 or k > 6 or len(q_terms) < 2:        # wide pools are scanned for evidence, not shown: leave their order alone
            return hits[:k]
        w = lambda t: self.title_weight.get(t, 2.0)
        total = sum(w(t) for t in q_terms)
        pool = hits[:max(4 * k, 12)]
        have = {id(h): self._terms(h) for h in pool}
        chosen, covered = [], set()
        while pool and len(chosen) < k:
            def gain(h):
                new = sum(w(t) for t in q_terms if t in have[id(h)] and t not in covered)
                return h["score"] + (DIVERSITY_BONUS * new / total if chosen else 0.0)
            best = max(pool, key=gain)
            pool.remove(best)
            chosen.append(best)
            covered |= {t for t in q_terms if t in have[id(best)]}
        rest = [h for h in hits if h not in chosen]
        return chosen

    def _speller(self):
        """{word: count} over the course material plus the words the router/retriever already know."""
        if not hasattr(self, "_vocab_counts"):
            counts = Counter()
            for r in self.records:
                counts.update(re.findall(r"[a-z]{3,}", ((r.get("title") or "") + " " + r["text"]).lower()))
            known = set(_KNOWN_EXTRA) | {w for w in QUESTION_WORDS if w.isalpha()} | _FRAME
            for _, add in ALIASES:
                known |= set(re.findall(r"[a-z]+", add))
            self._vocab_counts, self._known_words = counts, known
        return self._vocab_counts, self._known_words

    def autocorrect(self, text):
        """Fix likely typos in a question using the course vocabulary. Returns (fixed_text, [(old, new), ...]).

        Deliberately conservative: only words of 5+ letters that appear nowhere in the course material, whose
        nearest course word is one edit away (two for words of 9+ letters, same first letter), and which the
        course uses at least 3 times. Anything already spelled like a course word is left alone."""
        counts, known = self._speller()
        by_len = getattr(self, "_by_len", None)
        if by_len is None:
            by_len = self._by_len = {}
            for w, c in counts.items():
                if c >= 3 and len(w) >= 5:      # 5+: a 5-letter typo must not collapse onto a 4-letter word (pasta -> past)
                    by_len.setdefault(len(w), []).append(w)
        changes = []

        def fix(m):
            word = m.group(0)
            low = word.lower()
            if len(low) < 5 or low in counts or low in known or (low.endswith("s") and low[:-1] in counts):
                return word
            limit = 2 if len(low) >= 9 else 1
            best = None
            for n in range(len(low) - limit, len(low) + limit + 1):
                for cand in by_len.get(n, ()):
                    if limit == 2 and cand[0] != low[0]:
                        continue
                    d = _osa(low, cand, limit)
                    if d <= limit and (best is None or (d, -counts[cand]) < (best[0], -counts[best[1]])):
                        best = (d, cand)
            if not best:
                return word
            changes.append((word, best[1]))
            return best[1]

        return re.sub(r"(?<![A-Za-z0-9])[A-Za-z]{5,}(?![A-Za-z0-9])", fix, text), changes

    def idf_lookup(self):
        """{token: idf} for answer-sentence weighting (TF-IDF backend only)."""
        if self.backend != "tfidf":
            return {}
        if not hasattr(self, "_idf_map"):
            self._idf_map = {t: float(self.idf[i]) for t, i in self.vocab.items()}
        return self._idf_map

    _CORE = re.compile(
        r"\b(?:cpu|process|job|thread|task)\s+scheduling\b|\bscheduling\s+algorithms?\b|\bscheduler\b|"
        r"\bfcfs\b|\bsjf\b|\bsjn\b|\bsrtf\b|\bstcf\b|\bhrrn\b|\bmlfq\b|\bedf\b|\brr\b|"
        r"round[- ]?robin|first[- ]come|shortest[- ](?:job|remaining)|time[- ]?quantum|time[- ]?slice|"
        r"multi-?level (?:feedback )?queue|response ratio|context[- ]switch|dispatcher|dispatch latency|gantt|"
        r"convoy effect|starvation|turnaround time|burst time|cpu burst|preemptive|preemption|ready queue|"
        r"multiprogramming|priority scheduling|lottery scheduling|rate[- ]monotonic|earliest deadline|"
        r"completion time|arrival time|waiting time|response time", re.I)
    # A bare "which algorithm is the fastest?" put to a CPU-scheduling tutor means scheduling, unless the question
    # names some other kind of algorithm.
    _ALGO_WORD = re.compile(r"\balgorithms?\b", re.I)
    _OTHER_ALGO = re.compile(r"\b(?:sort\w*|search\w*|graph|tree|hash\w*|encrypt\w*|crypto\w*|compress\w*|machine|"
                             r"learning|neural|path|dijkstra|string|matrix|dynamic programming|greedy|recursi\w*|"
                             r"page replacement|paging|disk|deadlock|banker\w*|memory|cache)\b", re.I)
    _SCHED_WITH = re.compile(r"\bschedul\w*\b.*\b(?:cpu|processes|process|processor|algorithms?|burst|quantum|kernel|"
                             r"operating|ready)\b|\b(?:cpu|processes|process|processor|algorithms?|burst|quantum|kernel|"
                             r"operating|ready)\b.*\bschedul\w*\b", re.I)

    # Other topics that share a word with this one ("priority queue", "disk scheduling", "CPU cache", "response time of
    # a web server"). Out of scope unless the question also names something specific to CPU scheduling.
    _OTHER_TOPIC = re.compile(
        r"priority queue|\bheap\b|cpu cache|cache (?:memory|miss|hit)|\bl[123] cache|cpu registers?|\bregisters?\b|"
        r"pipelin\w*|\bcron\b|web ?server|\bapi\b|\bhttp\w*|flight|airline|train station|\bhotel|"
        r"disk scheduling|\bdisk\b|\bsort\w*|quicksort|mergesort|shortest path|dijkstra|hash (?:table|map)|"
        r"binary tree|linked list|machine learning|neural network|page replacement|\bpaging\b|virtual memory|"
        r"segmentation|deadlock|semaphore|mutex|serializ\w*|transaction|"
        r"\bpython\b|\bjava(?:script)?\b|\bsql\b|\bdatabases?\b|\bb[- ]?tree|\bdocker\b", re.I)
    _SPECIFIC = re.compile(
        r"cpu scheduling|process scheduling|fcfs|sjf|srtf|round[- ]?robin|time[- ]?quantum|time[- ]?slice|burst|gantt|"
        r"convoy|starvation|preempt|affinity|mlfq|multi-?level|hrrn|lottery|rate[- ]monotonic|earliest deadline|"
        r"dispatcher|context[- ]switch|ready queue|turnaround", re.I)

    @classmethod
    def other_topic(cls, query):
        """True when the question is clearly about another subject that merely shares a word with CPU scheduling."""
        return bool(cls._OTHER_TOPIC.search(query) and not cls._SPECIFIC.search(query))

    @classmethod
    def in_core_domain(cls, query):
        """Stricter than in_domain(): the question names a CPU-scheduling concept or algorithm, or says "scheduling"
        next to a process/CPU word. "serializable schedule", "priority queue" and "CPU cache" do not qualify."""
        return bool(cls._CORE.search(query) or cls._SCHED_WITH.search(query)
                    or (cls._ALGO_WORD.search(query) and not cls._OTHER_ALGO.search(query)))

    @staticmethod
    def in_domain(query):
        """True if the question mentions at least one CPU-scheduling term."""
        return any(t in DOMAIN_STEMS or t.rstrip("s") in DOMAIN_STEMS for t in tokenize(query)) \
            or bool(canon_tokens(query) & CANON_DOMAIN)

    def in_scope(self, query, hits):
        """True if the knowledge base can answer this question."""
        if not hits or hits[0]["score"] < self.threshold:
            return False
        if self.backend == "bge":
            return True
        asked = {t for t in canon_tokens(query) if t not in QUESTION_WORDS}
        if self.other_topic(query):
            return False
        top = hits[0]
        if (top.get("score", 0) >= 1.0 and top.get("title_match", 0) >= 0.4 and top.get("title")
                and not self.in_domain(query)):
            return True       # a stored Q&A whose own question is this question ("Why is swapping used?"): in the notes
        if not self.in_domain(query) and not self.in_core_domain(query):
            return False
        if not asked:                                   # "what is CPU scheduling?": nothing but framing words
            return True
        seen = set()
        for h in hits:                                  # title + text, so a stored Q&A's own question counts
            seen |= canon_tokens((h.get("title") or "") + " " + h["text"])
        found = asked & seen
        if len(found) / len(asked) >= MIN_COVERAGE:
            return True
        # Some of the question's words are missing from the best passages ("purpose", "efficient", "i'm 5"). That is
        # not a reason to refuse a question that is plainly about CPU scheduling: answer from the closest passages
        # (the caller adds a note), and keep refusing the ones that only share a word ("serializable schedule").
        return self.in_core_domain(query)

    def partial_coverage(self, query, hits):
        """True when in_scope() let the question through only because it is about CPU scheduling."""
        if self.backend == "bge" or not hits:
            return False
        asked = {t for t in canon_tokens(query) if t not in QUESTION_WORDS}
        if not asked:
            return False
        seen = set()
        for h in hits:
            seen |= canon_tokens((h.get("title") or "") + " " + h["text"])
        return len(asked & seen) / len(asked) < MIN_COVERAGE


def cite(hit):
    """Human-readable source label: 'ostep/ostep-cpu-sched.txt p.4 [Round Robin]'
    or 'notes/cpu_scheduling_notes.md § Round Robin (RR)'."""
    where = f"p.{hit['page']}" if isinstance(hit["page"], int) else f"§ {hit['page']}"
    return f"{hit['source']} {where} [{hit['algorithm']}]"

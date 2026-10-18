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
    (r"choose|chosen|choice|select|pick", "choose chosen selected"),
]
TITLE_BOOST = 0.7
_FRAME = {t for w in ("what is are the of a an how does do why which explain describe define tell me about "
                      "please give simple words in easy scheduling schedule algorithm algorithms cpu "
                      "difference compare should would could can will may use used write short note brief "
                      "vs versus between differ differences contrast comparison detail detailed briefly").split()
          for t in tokenize(w)}


# Many spellings -> one concept token, used only for title matching so abbreviations don't add noise.
CANON = [
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
    (r"types?|kinds?|categories|classes", " type "),
    (r"real[- ]life|everyday|real[- ]world|analog\w*", " analogy "),
    (r"\bwat\b", " what "), (r"\babt\b", " about "), (r"\bb/?w\b", " between "), (r"\bmax\b|maximum", " maximum "),
    (r"choose|chosen|choice|select\w*|picked?", " choose "),
    (r"comput\w*|calculat\w*|work(ing)? out|\bfind(ing)?\b|\bdetermine\b|\bformula\b|\bequation\b", " calculate "),
    (r"\bwait\w*", " waiting "), (r"turn\s*-?around|\btat\b", " turnaround "),
    (r"\btie\w*\b|\bsame\s+(burst|arrival|priority)\w*|equal\s+(burst|arrival|priority)\w*", " tiebreak "),
]


def canon_tokens(text):
    low = text.lower()
    for pat, rep in CANON:
        low = re.sub(pat, rep, low)
    return {t for t in tokenize(low) if "_" not in t and t not in _FRAME}


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
        q_tokens = canon_tokens(query)
        query = expand_query(query)
        for i, s in self._scores(query, n=len(self.records) if origin == "web" else 50):
            r = dict(self.records[i])
            is_web = r["source"].startswith("web/")
            if (origin == "vetted" and is_web) or (origin == "web" and not is_web):
                continue
            title = r.get("title") or ""
            if title and q_tokens:        # a stored Q&A whose title says what the student asked
                t_tokens = canon_tokens(title)
                if t_tokens:
                    r["title_match"] = round(len(q_tokens & t_tokens) / len(q_tokens | t_tokens), 3)  # 1.0 = identical
                    w = lambda ts: sum(self.title_weight.get(t, 2.0) for t in ts)   # rare concepts count more
                    both = w(q_tokens & t_tokens)
                    # half "how similar are they", half "how much of the question does this title cover"
                    boost = TITLE_BOOST * (0.5 * both / w(q_tokens | t_tokens) + 0.5 * both / w(q_tokens))
                    r["title_boost"] = round(boost, 3)
                    s += boost
            s *= SOURCE_WEIGHT.get(r["source"].split("/")[0], 1.0)
            if algorithm and r["algorithm"] == algorithm:
                s *= 1.15                          # small boost, not a hard filter
            r["score"] = round(s, 3)
            hits.append(r)
        hits.sort(key=lambda h: -h["score"])
        return hits[:k]

    def idf_lookup(self):
        """{token: idf} for answer-sentence weighting (TF-IDF backend only)."""
        if self.backend != "tfidf":
            return {}
        if not hasattr(self, "_idf_map"):
            self._idf_map = {t: float(self.idf[i]) for t, i in self.vocab.items()}
        return self._idf_map

    def in_scope(self, query, hits):
        """True if the knowledge base can answer this question."""
        if not hits or hits[0]["score"] < self.threshold:
            return False
        if self.backend == "bge":
            return True
        asked = {t for t in canon_tokens(query) if t not in QUESTION_WORDS}
        in_domain = any(t in DOMAIN_STEMS or t.rstrip("s") in DOMAIN_STEMS for t in tokenize(query)) \
            or bool(canon_tokens(query) & CANON_DOMAIN)
        if not in_domain:
            return False
        if not asked:                                   # "what is CPU scheduling?": nothing but framing words
            return True
        seen = set()
        for h in hits:                                  # title + text, so a stored Q&A's own question counts
            seen |= canon_tokens((h.get("title") or "") + " " + h["text"])
        found = asked & seen
        return len(found) / len(asked) >= MIN_COVERAGE


def cite(hit):
    """Human-readable source label: 'ostep/ostep-cpu-sched.txt p.4 [Round Robin]'
    or 'notes/cpu_scheduling_notes.md § Round Robin (RR)'."""
    where = f"p.{hit['page']}" if isinstance(hit["page"], int) else f"§ {hit['page']}"
    return f"{hit['source']} {where} [{hit['algorithm']}]"

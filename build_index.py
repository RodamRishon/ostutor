"""Build the retrieval index (report Section 5.2).

Primary backend (as designed): bge-small-en-v1.5 embeddings, L2-normalised,
stored in a FAISS IndexFlatIP so inner product == cosine similarity.

Fallback backend: if sentence-transformers / faiss are not installed (e.g. on
a fresh laptop with only the demo requirements), a TF-IDF index is built with
numpy instead. Same chunks, same metadata, same cosine search, so the rest of
the system does not care which one is in use.

    python build_index.py                 # auto: BGE+FAISS if available, else TF-IDF
    python build_index.py --backend tfidf
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
from collections import Counter

import numpy as np

from clean_chunk import chunk_text, clean_text, load_documents

ROOT = pathlib.Path(__file__).parent
CORPUS_DIR = ROOT / "corpus"
INDEX_DIR = ROOT / "index"
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
MIN_CHUNK_WORDS = 25
MIN_QA_WORDS = 8

STOPWORDS = set("""a an the and or of to in on for is are was were be been being it its this that
these those with as by at from into than then so such can could will would may might do does did
not no but if each which who whom what when where why how all any both more most other some
we you they he she i our your their there here also only very just about over under after before
""".split())


def tag_algorithm(text: str) -> str:
    """Attach a coarse topic label used for citation and optional filtering.

    The label is the topic mentioned most often in the chunk, so a chunk that
    is mostly about Round Robin is not labelled FCFS just because it says "FIFO" once.
    """
    low = text.lower()
    topics = {
        "Round Robin": ["round robin", "round-robin", "time quantum", "time slice"],
        "SJF": ["shortest job", "shortest remaining", "sjf", "srtf", "stcf"],
        "FCFS": ["first come", "first-come", "fcfs", "fifo", "convoy"],
        "Priority": ["priority", "aging", "ageing"],
        "MLFQ": ["multi-level feedback", "multilevel feedback", "mlfq"],
        "Context switch": ["context switch"],
    }
    counts = {label: sum(low.count(k) for k in keys) for label, keys in topics.items()}
    best = max(counts, key=counts.get)
    if counts[best] == 0:
        return "General"
    # Several algorithms with none dominant: a comparison passage.
    present = sum(1 for c in counts.values() if c > 0)
    if present >= 3 and counts[best] < 0.4 * sum(counts.values()):
        return "Comparison"
    return best


# Word families the suffix rules below cannot join.
FAMILIES = {"starvation": "starv", "starve": "starv", "starved": "starv", "starving": "starv",
            "starves": "starv", "preemption": "preempt", "preempted": "preempt", "preempts": "preempt",
            "preemptive": "preemptive", "fcfs": "fcfs", "srtf": "srtf", "ageing": "aging"}


def stem(w: str) -> str:
    """Tiny suffix stripper so 'causes'/'cause' and 'processes'/'process' match."""
    if w in FAMILIES:
        return FAMILIES[w]
    if len(w) > 4 and w.endswith("ies"):
        return w[:-3] + "y"
    if len(w) > 4 and w.endswith(("sses", "xes", "ches", "shes")):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    if len(w) > 6 and w.endswith("ing"):
        return w[:-3]
    return w


def tokenize(text: str):
    """Lowercase stemmed word tokens plus bigrams; used by the TF-IDF backend."""
    out = [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) >= 2]
    # bigrams help with "round robin", "time quantum", "context switch"
    return out + [f"{a}_{b}" for a, b in zip(out, out[1:])]


# Scraped text may use a convention that differs from the course's. A passage that states the OPPOSITE
# priority rule (higher number = higher priority) would teach the wrong thing, so it is not indexed.
CONFLICTS = re.compile(r"(higher|larger|greater|bigger) (number|value|integer)[^.]{0,40}(higher|highest) priority|"
                       r"(lower|smaller) (number|value|integer)[^.]{0,40}(lower|lowest) priority", re.I)


def prepare_records(corpus_dir=CORPUS_DIR):
    records, skipped = [], []
    for source, page_no, raw in load_documents(corpus_dir):
        for chunk in chunk_text(clean_text(raw)):
            title = page_no if isinstance(page_no, str) else ""
            if source.startswith("web/"):
                title = ""        # scraped web text is never a vetted Q&A: no exact-match shortcut, no title boost
            # A stored Q&A is a complete answer however short; only loose text fragments are dropped.
            if len(chunk.split()) < (MIN_QA_WORDS if title else MIN_CHUNK_WORDS):
                continue
            if source.startswith("web/") and CONFLICTS.search(chunk):
                skipped.append((source, page_no if isinstance(page_no, str) else ""))
                continue
            records.append({"text": chunk, "title": title, "source": source,
                            "page": page_no, "algorithm": tag_algorithm(title + " " + chunk)})
    for src, sec in skipped:
        print(f"  not indexed (opposite priority convention): {src} § {sec}")
    return records


def build_tfidf(records, index_dir):
    # The section title (often the exact question) is matched but never quoted as an answer.
    docs = [tokenize(r.get("title", "") + ". " + r["text"]) for r in records]
    df = Counter(t for d in docs for t in set(d))
    n = len(docs)
    vocab = {t: i for i, t in enumerate(sorted(t for t, c in df.items() if c >= 1))}
    idf = np.zeros(len(vocab), dtype="float32")
    for t, i in vocab.items():
        idf[i] = math.log((1 + n) / (1 + df[t])) + 1.0
    mat = np.zeros((n, len(vocab)), dtype="float32")
    for r, d in enumerate(docs):
        for t, c in Counter(d).items():
            mat[r, vocab[t]] = (1 + math.log(c)) * idf[vocab[t]]
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9   # cosine == dot
    np.save(index_dir / "tfidf_matrix.npy", mat)
    np.save(index_dir / "tfidf_idf.npy", idf)
    (index_dir / "tfidf_vocab.json").write_text(json.dumps(vocab))
    return mat.shape


def build_bge(records, index_dir):
    import faiss
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(EMBED_MODEL)
    vectors = model.encode([r.get("title", "") + ". " + r["text"] for r in records], batch_size=32,
                           show_progress_bar=True, normalize_embeddings=True)  # cosine == dot
    vectors = np.asarray(vectors, dtype="float32")
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(index_dir / "scheduling.faiss"))
    return vectors.shape


def bge_available():
    try:
        import faiss  # noqa: F401
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def build(corpus_dir=CORPUS_DIR, index_dir=INDEX_DIR, backend="auto", quiet=False):
    corpus_dir, index_dir = pathlib.Path(corpus_dir), pathlib.Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)
    records = prepare_records(corpus_dir)
    log = print if not quiet else (lambda *a, **k: None)
    log(f"{len(records)} chunks prepared from {len({r['source'] for r in records})} documents")
    if backend == "auto":
        backend = "bge" if bge_available() else "tfidf"
    shape = build_bge(records, index_dir) if backend == "bge" else build_tfidf(records, index_dir)
    (index_dir / "metadata.json").write_text(json.dumps(records, indent=1))
    (index_dir / "backend.json").write_text(json.dumps({"backend": backend, "chunks": len(records),
                                                        "dim": int(shape[1])}))
    log(f"index saved: backend={backend}, {shape[0]} vectors, dim {shape[1]}")
    return backend, len(records)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["auto", "bge", "tfidf"], default="auto")
    args = ap.parse_args()
    build(backend=args.backend)

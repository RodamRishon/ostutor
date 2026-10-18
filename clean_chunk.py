"""Corpus cleaning and boundary-aware chunking (report Section 5.1)."""
from __future__ import annotations

import pathlib
import re
import unicodedata

# Lines that are slide/page furniture rather than content.
HEADER_NOISE = [
    r"^\s*\d+\s*$",                                   # bare page numbers
    r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$",              # "Page 3 of 40"
    r"^\s*\d+\s+[A-Z][A-Z :\-]{6,}$",                 # OSTEP running head "12 S CHEDULING : I NTRO"
    r"^\s*[A-Z][A-Z :\-]{6,}\s+\d+\s*$",              # running head with trailing page number
    r"^\s*OPERATING\s*SYSTEMS\s*\[VERSION.*$",        # OSTEP footer
    r"^\s*WWW\.OSTEP\.ORG\s*$",
    r"^\s*©.*$",                                      # copyright footers on slides
    r"^\s*source:\s*https?://\S+\s*$",                # fetch provenance line in wiki dumps
]


def clean_text(raw: str) -> str:
    """Remove slide/page artefacts, fix hyphenation, normalise whitespace."""
    text = unicodedata.normalize("NFKC", raw)          # "ﬁ" ligature -> "fi"
    text = text.replace("\r\n", "\n").replace(" ", " ")
    # join words broken across a line by a hyphen: sched-\nuling -> scheduling
    text = re.sub(r"(\w+)-\n(\w+)", r"\1\2", text)
    lines = []
    for line in text.split("\n"):
        if any(re.match(p, line, flags=re.IGNORECASE) for p in HEADER_NOISE):
            continue
        lines.append(line.strip())
    text = "\n".join(lines)
    text = re.sub(r"\s*\(Source:[^)]*\)", "", text)  # citation tags are re-added from metadata
    text = re.sub(r"^=+\s*(.*?)\s*=+$", r"\n\1.", text, flags=re.MULTILINE)  # wiki "== Heading =="
    text = re.sub(r"^#+\s*(.*?)([.?!:]?)$", lambda m: m.group(1) + (m.group(2) or "."),
                  text, flags=re.MULTILINE)                                 # markdown "## Heading"
    text = re.sub(r"\n{3,}", "\n\n", text)             # collapse blank runs
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def chunk_text(text: str, chunk_words: int = 300, overlap_words: int = 45):
    """Split into overlapping chunks, preferring paragraph boundaries.

    300 words is roughly 400 tokens for English technical prose; the 45-word
    overlap (~60 tokens) stops a worked example being cut in half.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], []
    for para in paragraphs:
        words = para.split()
        if len(current) + len(words) <= chunk_words:
            current.extend(words)
            continue
        if current:
            chunks.append(" ".join(current))
        if len(words) > chunk_words:                   # paragraph alone is too long
            step = chunk_words - overlap_words
            for i in range(0, len(words), step):
                piece = words[i:i + chunk_words]
                if piece:
                    chunks.append(" ".join(piece))
                if i + chunk_words >= len(words):
                    break
            current = []
        else:
            tail = current[-overlap_words:] if current else []
            current = tail + words
    if current:
        chunks.append(" ".join(current))
    return chunks


def load_documents(corpus_dir):
    """Yield (source, page, raw_text) for every document in the corpus.

    .md files: one unit per "##"/"###" section, page = the section title.
    .txt files: pages are separated by form feeds (\\f) when they came from
    a PDF; otherwise the whole file is page 1.  .pdf files are read with pypdf
    if it is installed (drop slides/notes exported to PDF into corpus/institutional).
    """
    corpus_dir = pathlib.Path(corpus_dir)
    for path in sorted(corpus_dir.rglob("*")):
        if path.name.startswith(".") or path.name.lower() == "readme.md" or not path.is_file():
            continue
        source = str(path.relative_to(corpus_dir))
        suffix = path.suffix.lower()
        if suffix == ".md":
            # Markdown notes: each "## Section" is its own unit and is cited by name.
            text = path.read_text(encoding="utf-8", errors="ignore")
            parts = re.split(r"^#{2,3}\s+(.+)$", text, flags=re.MULTILINE)
            sections = [("Introduction", parts[0])] + list(zip(parts[1::2], parts[2::2]))
            for title, body in sections:
                if body.strip():
                    yield source, title.strip(), body
            continue
        if suffix == ".txt":
            pages = path.read_text(encoding="utf-8", errors="ignore").split("\f")
        elif suffix == ".pdf":
            try:
                import pypdf
            except ImportError:
                print(f"skipping {source}: pip install pypdf to index PDFs")
                continue
            pages = [p.extract_text() or "" for p in pypdf.PdfReader(str(path)).pages]
        else:
            continue
        for page_no, raw in enumerate(pages, start=1):
            if raw.strip():
                yield source, page_no, raw

"""Fetch a web page and save its readable text into the knowledge base folder.

    from rag.fetch_wiki import fetch_webpage
    path = fetch_webpage("https://...")          # -> corpus/web/geeksforgeeks/<slug>.md

What it does, and does not do
  * checks the site's robots.txt first and refuses paths it disallows
  * identifies itself honestly (it does not pretend to be a browser) and waits between requests
  * keeps only the article text: headings, paragraphs, lists, tables; drops navigation, ads, "related
    articles", comments, share buttons and code listings
  * writes <slug>.md (text only) and <slug>.meta.json (url, title, date, license note, checksum)
  * is safe to re-run: a page already saved is skipped unless force=True

Copyright: the text belongs to the site. It is kept in corpus/web/ for your own study and for retrieval in
this local project. Do not publish it; the build_index step marks it as unvetted web text so it can never
replace a vetted course answer.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import re
import time
import urllib.parse
import urllib.robotparser

import requests
from bs4 import BeautifulSoup

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "corpus" / "web" / "geeksforgeeks"
USER_AGENT = "OSTutorStudentProject/1.0 (university OS lab project; low-volume, honours robots.txt)"
DELAY_SECONDS = 2.0

_last_request = [0.0]
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

DROP_TAGS = ["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "button", "iframe",
             "svg", "img", "figure", "select", "input", "pre"]
DROP_CLASS = re.compile(r"(^|[-_ ])(ads?|advert\w*|sponsor\w*|related|recommend\w*|comment\w*|sidebar|share|sharing|"
                        r"breadcrumb\w*|newsletter|cookie|footer|navbar|menu|login|popup|banner|promo\w*|"
                        r"toc|table-of-content\w*|article-pgn|read-more|suggest\w*|tags?|author\w*|upvote\w*)($|[-_ ])", re.I)
BOILERPLATE = re.compile(r"^(last updated|improve|suggest changes|like article|save article|share your thoughts|"
                         r"comment|read more|table of content|similar reads|explore offer|enjoy 100% free|"
                         r"we use cookies|geeksforgeeks|follow us|advertisement|skip to|sign in|log in|"
                         r"\d+ likes?|please login|my personal notes|a computer science portal)\b", re.I)


def slug(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/").split("/")
    return re.sub(r"[^a-z0-9]+", "-", path[-1].lower()).strip("-") or "page"


def _wait():
    gap = DELAY_SECONDS - (time.time() - _last_request[0])
    if gap > 0:
        time.sleep(gap)
    _last_request[0] = time.time()


def allowed(url: str) -> bool:
    """True if robots.txt lets a generic client fetch this URL (unknown robots.txt means allowed)."""
    parts = urllib.parse.urlparse(url)
    base = f"{parts.scheme}://{parts.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            _wait()
            r = requests.get(base + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=20)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                _robots[base] = rp
            else:
                _robots[base] = None               # no robots.txt: nothing is disallowed
        except requests.RequestException:
            _robots[base] = None
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()


def extract(html: str):
    """(title, markdown body, license note) from an article page."""
    soup = BeautifulSoup(html, "lxml")
    title = _text(soup.find("h1")) if soup.find("h1") else (soup.title.string.strip() if soup.title else "")
    page_text = soup.get_text(" ", strip=True)
    m = re.search(r"(Creative Commons[^.]{0,80}|CC BY[- ]SA[^.]{0,40}|All rights reserved|Some rights reserved)", page_text)
    license_note = m.group(1).strip() if m else "no license statement found on the page"

    # The article body has its own container; the site menu, header and footer sit outside it. (GeeksforGeeks
    # uses a hashed CSS-module class that always starts with "MainArticleContent_".)
    root = (soup.select_one('[class*="MainArticleContent"]') or soup.find("article") or soup.find("main")
            or soup.body)
    for tag in root.find_all(DROP_TAGS):
        tag.decompose()
    for el in root.find_all(True):
        if el.attrs is None:
            continue
        marks = " ".join(el.get("class", []) + [el.get("id") or ""])
        if marks.strip() and DROP_CLASS.search(marks):
            el.decompose()

    lines, seen = [], set()
    for el in root.find_all(["h1", "h2", "h3", "h4", "p", "li", "table"]):
        if el.name == "table":
            rows = [" | ".join(_text(c) for c in tr.find_all(["th", "td"])) for tr in el.find_all("tr")]
            text = "\n".join(r for r in rows if r.strip(" |"))
        else:
            if el.name == "p" and el.find_parent("li"):
                continue
            text = _text(el)
        if not text or BOILERPLATE.match(text) or len(text) < 3:
            continue
        key = (el.name, text)
        if key in seen:
            continue
        seen.add(key)
        if el.name in ("h1",):
            continue                                     # the title is stored separately
        if el.name == "h2":
            lines.append(f"\n## {text}\n")
        elif el.name in ("h3", "h4"):
            lines.append(f"\n### {text}\n")
        elif el.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text + "\n" if el.name == "p" else text)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return title, body, license_note


def fetch_webpage(url: str, out_dir=None, force: bool = False, timeout: int = 30) -> pathlib.Path:
    """Download one page and save its text. Returns the path of the .md file."""
    out = pathlib.Path(out_dir or DEFAULT_OUT)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{slug(url)}.md"
    if path.exists() and not force:
        print(f"  already saved: {path.name} (skipped)")
        return path
    if not allowed(url):
        raise PermissionError("robots.txt does not allow fetching this URL")
    _wait()
    r = requests.get(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"}, timeout=timeout)
    r.raise_for_status()
    title, body, license_note = extract(r.text)
    if len(body.split()) < 150:
        raise ValueError(f"only {len(body.split())} words extracted: the page layout was not recognised")
    path.write_text(body + "\n", encoding="utf-8")
    (out / f"{slug(url)}.meta.json").write_text(json.dumps({
        "url": url, "title": title, "fetched": datetime.date.today().isoformat(), "words": len(body.split()),
        "license_note": license_note, "sha256": hashlib.sha256(body.encode()).hexdigest()[:16],
        "note": "Third-party text kept for personal study and local retrieval; not vetted course material."}, indent=2))
    print(f"  saved {path.name}: {len(body.split())} words, title '{title[:60]}', licence note: {license_note[:50]}")
    return path

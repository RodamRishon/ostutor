"""Turn an answer into a reader-friendly layout.

An answer is one dense paragraph. This module restructures it for the screen without changing a word of
its content:

    ### Title                      (when the answer is a stored Q&A)
    > 💡 **In short:** first sentence
    **Key points**  - one point per sentence
    **Formula**     `waiting time = turnaround time − burst time`
    numbered list   when the text is a sequence (First, Second, ... / "Step 1")
    a table         for the generated "A vs B" comparisons

The raw text is never altered by the model-facing code; this runs only when drawing the page.
"""
from __future__ import annotations

import re

_ABBR = {"e.g.": "e§g§", "i.e.": "i§e§", "vs.": "vs§", "etc.": "etc§", "approx.": "approx§", "No.": "No§"}
SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(\[`*\"'])")
CITE = re.compile(r"\s*\[(\d+)\]\s*$")
ORDINAL = re.compile(r"^(First|Second|Third|Fourth|Fifth|Sixth|Finally|Lastly|Then|Next|Step \d+)\b[,:]?\s*", re.I)
FORMULA = re.compile(r"^((?:average |avg\.? )?(?:waiting|turnaround|response|completion) time|response ratio|"
                     r"cpu utili[sz]ation|throughput|τ\(n\+1\)|processing)\s*[=(]", re.I)


HTML_TAG = re.compile(r"</?[a-zA-Z][^>\n]*>")


def clean(text):
    """Remove any HTML tag. Streamlit shows tags literally, so a stray <sub> or <br> would appear as text."""
    return HTML_TAG.sub("", text) if text else text


def sentences(text):
    t = " ".join(text.split())
    for a, b in _ABBR.items():
        t = t.replace(a, b)
    return [s.replace("§", ".").strip() for s in SENT_SPLIT.split(t) if s.strip()]


def split_citation(text):
    """('answer text', '1') for a trailing ' [1]' marker, else (text, None)."""
    m = CITE.search(text)
    return (text[:m.start()].rstrip(), m.group(1)) if m else (text, None)


def _is_structured(text):
    """True if the text already has markdown structure (lists, several paragraphs): leave its layout alone."""
    return bool(re.search(r"(?m)^\s*([-*•]|\d+[.)])\s+\S", text)) or text.count("\n\n") >= 2


def _comparison_table(sents):
    """Parse the eight-sentence 'A and B differ ...' answers produced by facts.compare_answer()."""
    try:
        if len(sents) != 8 or "differ in how they choose" not in sents[0]:
            return None
        a, b = re.match(r"^(.+?) and (.+?) differ in how", sents[0]).groups()
        rule_a, rule_b = sents[1][len(a) + 1:].rstrip("."), sents[2][len(b) + 1:].rstrip(".")
        pre = sents[3].rstrip(".")
        m = re.match(r"^(.+?) is (.+?), whereas (.+?) is (.+)$", pre)
        pre_a, pre_b = (m.group(2), m.group(4)) if m else (re.sub(r"^Both are ", "", pre),) * 2
        st_a, st_b = re.match(rf"^On starvation, {re.escape(a)} (.+?), while {re.escape(b)} (.+)\.$", sents[4]).groups()
        w_a, w_b = re.match(rf"^Average waiting time under {re.escape(a)} is (.+?), while under {re.escape(b)} it is (.+)\.$",
                            sents[5]).groups()
        o_a, o_b = re.match(rf"^For context-switch overhead, {re.escape(a)} has (.+?), and {re.escape(b)} has (.+)\.$",
                            sents[6]).groups()
        u_a, u_b = re.match(rf"^Choose {re.escape(a)} for (.+?); choose {re.escape(b)} for (.+)\.$", sents[7]).groups()
    except (AttributeError, ValueError):
        return None
    rows = [("How it picks the next process", rule_a, rule_b), ("Preemption", pre_a, pre_b),
            ("Starvation", st_a, st_b), ("Average waiting time", w_a, w_b),
            ("Context-switch overhead", o_a, o_b), ("Best suited to", u_a, u_b)]
    cell = lambda s: s.replace("|", "/")
    lines = [f"| | **{a}** | **{b}** |", "|---|---|---|"]
    lines += [f"| **{k}** | {cell(x)} | {cell(y)} |" for k, x, y in rows]
    return "\n".join(lines)


def to_markdown(body, title=None, source=None, intent=None):
    """Return markdown for an answer. `source` is the citation number, if known.
    `intent` ("compare", ...) stops a comparison question getting a one-sided "In short" line."""
    body, cite = split_citation(body.strip())
    cite = cite or source
    out = [f"### {title}", ""] if title else []

    pc = re.match(r"^(.*?)\bAdvantages:\s*(.*?)\s*\bDisadvantages:\s*(.*)$", body, re.S) if not _is_structured(body) else None
    if pc:                                        # "Advantages: ... Disadvantages: ..." becomes two lists
        intro, adv, dis = (x.strip() for x in pc.groups())
        if intro:
            out += [intro, ""]
        up = lambda x: x[:1].upper() + x[1:]          # the first sentence starts mid-sentence ("processes of ...")
        out += ["**Advantages**", ""] + [f"- {up(x)}" for x in sentences(adv)] + ["", "**Disadvantages**", ""] + \
               [f"- {up(x)}" for x in sentences(dis)]
    elif _is_structured(body):                    # an LLM answer that already has its own layout
        out.append(body)
    else:
        sents = sentences(body)
        table = _comparison_table(sents)
        if table:
            out += [table]
        elif len(sents) <= 2 and not FORMULA.match(sents[0]):
            out.append(" ".join(sents))
        elif intent == "compare":                 # both sides matter: do not summarise with the first sentence alone
            out += ["**Differences**", ""] + [f"- {x}" for x in sents]
        else:
            ordinals = [s for s in sents if ORDINAL.match(s)]
            formulas = [s for s in sents if FORMULA.match(s)]
            others = [s for s in sents if s not in formulas]
            if len(ordinals) >= 3 or (len(ordinals) >= 2 and sents[0] in ordinals):   # a sequence of steps
                intro = []
                for s in sents:
                    if ORDINAL.match(s):
                        break
                    intro.append(s)
                if intro:
                    out += [" ".join(intro), ""]
                out += ["**Steps**", ""]
                n = 0
                for s in sents[len(intro):]:
                    if ORDINAL.match(s):
                        n += 1
                        text = s if s.lower().startswith("step") else ORDINAL.sub("", s, count=1).strip()
                        out.append(f"{n}. {text[:1].upper() + text[1:]}")
                    else:
                        out.append(f"   {s}")
            else:
                if formulas:
                    out += ["**Formula**", ""] + [f"- `{f.rstrip('.')}`" for f in formulas] + [""]
                if others and not (formulas and sents[0] in formulas and len(others) == len(sents) - len(formulas)
                                   and len(others) < 1):
                    first, rest = (others[0], others[1:])
                    if formulas and sents[0] in formulas:        # the formula was the lead: no separate summary
                        out += ["**Explanation**", ""] + [f"- {x}" for x in others]
                    else:
                        out += [f"> 💡 **In short:** {first}", ""]
                        if rest:
                            out += ["**Key points**", ""] + [f"- {x}" for x in rest]
    if cite:
        out += ["", f"*Source: passage [{cite}] in the list below.*"]
    return clean("\n".join(out))

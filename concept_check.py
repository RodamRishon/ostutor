"""Verification of *conceptual* answers (the simulator only verifies numbers).

A concept answer can be fluent and still wrong ("FCFS can starve short processes", "SJF and Round Robin avoid
starvation by letting short jobs run first").  This module checks an answer against known scheduling facts with
deterministic rules, so the tutor can regenerate or replace it instead of showing it:

    verify(question, answer, context)  ->  {"ok": bool, "problems": [...], "missing": [...]}

Checks: contradicted facts, answer-internal contradictions, absolute claims stated without their assumption,
essential points missing for this kind of question, unrelated algorithms, claims the retrieved context does not
support.  The rules are sentence-level patterns, not understanding: they catch the known mix-ups and leave
anything they cannot judge alone.  `judge_prompt` / `parse_judge` support an optional model-based second opinion
which is advisory only.
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import re

ROOT = pathlib.Path(__file__).parent
LOG_PATH = pathlib.Path(os.environ.get("OSTUTOR_VERIFY_LOG", ROOT / "logs" / "verification.jsonl"))

# --------------------------------------------------------------------------- #
# Vocabulary                                                                   #
# --------------------------------------------------------------------------- #
ALGO = {
    "fcfs": r"\bfcfs\b|first[- ]come|\bfifo\b",
    "srtf": r"\bsrtf\b|shortest[- ]remaining",
    "sjf": r"\bsjf\b|shortest[- ]job|\bsjn\b",
    "rr": r"\brr\b|round[- ]robin",
    "priority": r"\bpriorit(?:y|ies)\b",
    "hrrn": r"\bhrrn\b|response ratio",
    "mlfq": r"\bmlfq\b|multi-?level",
    "edf": r"\bedf\b|earliest deadline",
}
STARVE = r"starv\w*|indefinite(?:ly)?\s+(?:block|postpon|wait|delay)\w*|wait(?:s|ing)?\s+(?:for\s+)?(?:ever|forever|indefinitely)\b"
CONVOY = r"convoy"
# words that make a sentence a denial / contrast / hedge rather than a plain assertion
NEGATION = (r"\b(?:no|not|cannot|can't|never|neither|nor|without|unlike|avoids?|prevents?|prevented|free from|"
            r"eliminates?|solves?|fixes?|mitigates?|remed(?:y|ies)|misconception|myth|mix-?up|rather than|instead of|"
            r"different from|distinct from|does n't|doesn't|isn't|aren't|won't|n't)\b|n't\b")
HEDGE = (r"\b(?:if|unless|only|when|whereas|whether|differ\w*|compar\w*|assum\w*|provided|as long as|infinite|"
         r"never terminat\w*|student)\b")
QUALIFIER = (r"\b(?:assum\w*|provided|as long as|normally|standard|usual(?:ly)?|finite|eventually (?:finish|terminat)\w*|"
             r"bounded|\(n\s*[−-]\s*1\)\s*[×x*]\s*q|n\s*[−-]\s*1\)?\s*[×x*]\s*q|if the processes ahead|"
             r"under (?:normal|ordinary|standard)|once (?:it|they|the process\w*) (?:has|have)? ?(?:arrived|entered|joined))\b")

_sent_split = re.compile(r"(?<=[.!?])\s+(?=[A-Z(*\-•\d])|\n+|\||;\s*|,\s*(?:and|but|while|whereas)\s+")


def sentences(text):
    """Sentence-sized units, markdown bullets and table cells included."""
    text = re.sub(r"\[\d+\]", "", text)
    text = re.sub(r"[*_`#>]", "", text)
    out = [s.strip(" -•\t") for s in _sent_split.split(text)]
    return [s for s in out if len(s.split()) >= 3 and not s.endswith("?")]      # a question asserts nothing


def algos_in(s):
    return {k for k, p in ALGO.items() if re.search(p, s, re.I)}


def has(pattern, s):
    return bool(re.search(pattern, s, re.I))


def negated(s):
    return has(NEGATION, s)


# --------------------------------------------------------------------------- #
# Rules: each takes a sentence and returns a problem string or None             #
# --------------------------------------------------------------------------- #
# "if a long process arrives first" is the convoy scenario, so a plain 'if' does not excuse an FCFS starvation claim
FCFS_HEDGE = r"\b(?:whether|differ\w*|compar\w*|assum\w*|provided|infinite|never terminat\w*|student|unless|not)\b"


def _fcfs_starves(s):
    a = algos_in(s)
    if "fcfs" in a and has(STARVE, s) and not negated(s) and not has(FCFS_HEDGE, s):
        return "claims FCFS causes starvation (standard FCFS does not; long waits behind a long job are the convoy effect)"


def _sjf_prevents_starvation(s):
    a = algos_in(s)
    if a & {"sjf", "srtf"} and not a & {"hrrn", "mlfq", "edf"} and not has(r"\baging\b", s) and has(STARVE, s) \
            and not has(r"\b(?:not|n't|cannot|never)\b|unlike", s):
        if has(r"\b(?:avoid\w*|prevent\w*|eliminat\w*|free from|no starvation|solv\w*|never starv\w*|cannot starve|"
               r"does not starve)\b", s) and not has(r"\bnot\b|n't|\bnever\b|\bcannot\b", s):
            return "claims SJF/SRTF prevents starvation (it can starve long jobs when shorter jobs keep arriving)"


# A sentence DENIES starvation only when the negation is attached to the starvation term itself ("never starves",
# "cannot cause starvation", "no starvation", "starvation is impossible").  "P1 will never get its turn ... illustrating
# starvation" or "a job that never runs is starved" co-occur with 'never' but AFFIRM starvation, so a bare 'never'
# anywhere in the sentence must not count.
_DENIAL = (r"\b(?:never|cannot|can't|can\s+not|does\s+not|doesn't|do\s+not|don't|will\s+not|won't|no)\b"
           r"(?:\W+(?!and\b|but\b|which\b|that\b|because\b)\w+){0,2}?\W+(?:starv\w*|cause\s+starvation)"
           r"|\bstarvation\b(?:\W+\w+){0,3}?\W+(?:is|are)\s+(?:impossible|not\s+possible|ruled\s+out)"
           r"|\bstarvation[- ]free\b|\bguarantee\w*\s+(?:that\s+)?(?:no\s+)?starvation")


def _priority_cannot_starve(s):
    """'Priority scheduling / SJF never starves anyone' (without aging) is false."""
    a = algos_in(s)
    if a & {"sjf", "srtf", "priority"} and not a & {"fcfs", "rr", "hrrn", "mlfq", "edf"} and has(STARVE, s) \
            and has(_DENIAL, s) \
            and not has(r"\b(?:aging|ageing|if|unless|when|necessarily|always|student|myth|misconception|whether|without|"
                        r"aged|mitigat\w*|prevent\w*|avoid\w*|boost\w*)\b|no priority", s):
        return "says SJF/SRTF/Priority never starves a process (they can, depending on the workload; aging mitigates it)"


def _short_first_avoids(s):
    """'SJF and Round Robin avoid starvation by letting short jobs run first'."""
    if has(ALGO["rr"], s) and has(r"\bshort\w*\b", s) and has(
            r"\b(?:short\w*\s+(?:jobs?|processes|ones|tasks)\s+(?:run|go|execute|are (?:run|served|scheduled|selected|picked|chosen)|"
            r"get)\b[^.]{0,25}\bfirst|(?:letting|lets|let|allowing|allows|giving|gives)\s+short\w*|"
            r"(?:prioriti[sz]\w*|favou?r\w*|prefer\w*|picks?|selects?|chooses?|runs?)\s+(?:the\s+)?short\w*)\b", s) \
            and not has(r"\bnot\b|n't|\bnever\b|\bneither\b|unlike|\bwhereas\b|\bbut\b|\brather than\b|\bhowever\b", s):
        return "says Round Robin favours or runs short jobs first (it serves processes in cyclic order with a time quantum)"


def _convoy_is_starvation(s):
    if has(CONVOY, s) and has(STARVE, s):
        if has(r"\b(?:same as|is starvation|is a (?:kind|form|type) of starvation|also called starvation|"
               r"(?:another|other|alternative|a different|different) (?:name|term|word|label) for|"
               r"also (?:known|referred to) as|(?:just|merely|simply) (?:a |another )?(?:different )?"
               r"(?:word|name|term|label) for|synonym|equivalent|causes? starvation|lead(?:s|ing)? to starvation|"
               r"results? in starvation|is when .{0,40}starv)", s) and not negated(s):
            return "treats the convoy effect as starvation (it is a long finite delay, not indefinite postponement)"
        if has(r"\bconvoy\b[^.]{0,60}\b(?:indefinite\w*|never (?:get|run|finish)|forever)\b", s) and not negated(s):
            return "describes the convoy effect as an indefinite wait (it ends when the long process finishes)"


def _convoy_not_fcfs_only_wrong(s):
    if has(CONVOY, s) and has(r"\b(?:round[- ]robin|rr)\b", s) and has(r"\b(?:causes?|suffers?|has|exhibits?)\b", s) \
            and not negated(s) and not has(r"quantum|larger than|becomes? fcfs|behaves? (?:exactly )?like fcfs|"
                                           r"reduce\w*|limit\w*|avoid\w*|whereas|but|unlike|if", s):
        return "attributes the convoy effect to Round Robin"


def _always_starves(s):
    a = algos_in(s) & {"sjf", "srtf", "priority"}
    if a and has(r"\b(?:always|will|must|definitely|certainly|inevitabl\w*|guaranteed to)\s+(?:starv\w*|cause starvation|"
                 r"be starved|lead to starvation)", s):
        return "states starvation as certain; it only can occur, depending on the workload"


def _rr_short_priority_conclusion(s):
    if has(ALGO["rr"], s) and has(r"short\w*", s) and has(
            r"\b(?:gives?|giving|given)\s+(?:higher |highest )?priority\s+to\s+short|short\w*\s+(?:processes|jobs)\s+"
            r"(?:have|get|receive)\s+(?:higher |highest )?priority", s) and not negated(s):
        return "says Round Robin gives short processes priority"


def _aging_guarantees_everywhere(s):
    """Aging mitigates starvation under a priority-style policy; it is not a guarantee under every policy or workload."""
    if has(r"\bag(?:e|ing)\b", s) and has(
            r"\b(?:guarantee[sd]?|ensures?|always (?:prevents?|eliminates?|solves?)|completely (?:eliminates?|prevents?|"
            r"removes?)|permanently (?:prevents?|eliminates?))\b", s) \
            and has(r"\b(?:any|every|all)\s+(?:possible\s+|other\s+)?(?:scheduler|scheduling|polic\w+|algorithm|workload|"
                    r"system|situation|case)|\bin\s+all\s+cases\b|\bno\s+matter\b|\bunder\s+all\b|\balways\b|\b100\s*%", s) \
            and not has(r"\b(?:not|n't|never|cannot|no)\s+(?:\w+\s+){0,2}(?:guarantee|ensure|always|eliminat|prevent|solve|remove)\w*|"
                        r"\bno\s+guarantee|\b(?:if|unless|provided|assum\w*|as long as|only|when|whether|limit\w*|myth|"
                        r"misconception|student)\b", s):
        return "says aging guarantees freedom from starvation under every policy or workload (it mitigates starvation in " \
               "priority-style policies; it is not universal)"


RULES = [_fcfs_starves, _priority_cannot_starve, _sjf_prevents_starvation, _short_first_avoids, _convoy_is_starvation,
         _convoy_not_fcfs_only_wrong, _always_starves, _rr_short_priority_conclusion, _aging_guarantees_everywhere]


def rule_problems(answer):
    out = []
    for s in sentences(answer):
        for rule in RULES:
            p = rule(s)
            if p:
                out.append(f"{p}: \"{s[:110]}\"")
    return out


# --------------------------------------------------------------------------- #
# Contradictions inside one answer                                              #
# --------------------------------------------------------------------------- #
def contradictions(answer):
    """The same algorithm both 'causes starvation' and 'does not' in unhedged sentences of one answer."""
    pol = {}
    for s in sentences(answer):
        a = algos_in(s)
        if len(a) != 1 or not has(STARVE, s) or has(HEDGE, s) or has(r"\bor\b|\bunlike\b|\bwhereas\b|\bcompar", s):
            continue
        k = next(iter(a))
        if not has(r"\b(?:can|may|might|cause[sd]?|suffers?|possible|occurs?|happens?|starves?|no|not|cannot|never|n't|"
                   r"without|avoids?|free from|does)\b|n't", s):
            continue                                    # a heading such as "RR and starvation."
        m_algo = re.search(ALGO[k], s, re.I)
        m_starve = re.search(STARVE, s, re.I)
        if m_algo.start() > m_starve.start() and not has(r"\b(?:in|under|with|for)\s+(?:" + ALGO[k] + ")", s):
            continue                                    # the algorithm is not the subject of the starvation claim
        # 'aging solves starvation' / 'prevents' is not a claim about the algorithm's own behaviour
        if has(r"\baging\b|\bremedy\b|\bmitigat\w+|\bfix\w*", s):
            continue
        pol.setdefault(k, set()).add("no" if has(r"\b(?:no|not|cannot|never|n't|without|avoids?|free from)\b|n't", s) else "yes")
    return [f"contradicts itself about starvation in {ALGO_NAME.get(k, k)}" for k, v in pol.items() if len(v) > 1]


ALGO_NAME = {"fcfs": "FCFS", "sjf": "SJF", "srtf": "SRTF", "rr": "Round Robin", "priority": "Priority scheduling"}


def absolute_claims(answer):
    """'Round Robin / FCFS never starves' with no assumption anywhere in the answer."""
    if has(QUALIFIER, answer):
        return []
    for s in sentences(answer):
        a = algos_in(s)
        if a & {"fcfs", "rr"} and has(STARVE, s) and has(
                r"\b(?:never|cannot|guarantee\w*|always|no starvation|impossible|completely (?:free|avoid\w*))\b", s) \
                and not has(r"\bnot\b.{0,30}\balways\b", s):
            return ["states 'no starvation' for FCFS/Round Robin as unconditional, without the assumption it rests on "
                    f"(processes terminate, finite queue/quantum): \"{s[:100]}\""]
    return []


# --------------------------------------------------------------------------- #
# What an answer to this kind of question must contain                          #
# --------------------------------------------------------------------------- #
def _p(label, *patterns):
    return (label, patterns)         # all patterns must match somewhere in the answer


# (question pattern, allowed algorithms or None, essential points, claims that need support)
SPECS = [
    ("convoy_vs_starvation",
     r"(?=.*convoy)(?=.*starv)", {"fcfs", "sjf", "srtf", "priority", "rr"},
     [_p("defines the convoy effect (short processes wait behind a long one)", CONVOY, r"long", r"short|wait"),
      _p("defines starvation as indefinite postponement", r"indefinite\w*|never get|forever|may never|postpon\w*", STARVE),
      _p("ties the convoy effect to FCFS", CONVOY, r"fcfs|first[- ]come|arrival order"),
      _p("says standard FCFS does not normally starve a process", r"fcfs|first[- ]come",
         r"(?:not|no|n't|cannot|never|neither|without)\b[^.\n]{0,70}(?:starv|indefinite)|(?:starv|indefinite)\w*[^.\n]{0,60}(?:not|no|n't|cannot|unlikely|rare)"),
      # one example of an algorithm that really can starve (SJF/SRTF: long jobs; Priority: low-priority jobs) is enough:
      # a focused answer to "is starvation the same as the convoy effect?" need not list every algorithm
      _p("says SJF can starve long jobs or Priority scheduling can starve low-priority jobs",
         r"(?:sjf|srtf|shortest[- ](?:job|remaining))[^.\n]{0,90}long[- ](?:job|process)|long[- ](?:job|process)\w*[^.\n]{0,60}"
         r"(?:sjf|srtf|shortest)|priorit\w+[^.\n]{0,90}low(?:er)?[- ]priority|low(?:er)?[- ]priority[^.\n]{0,60}priorit"),
      _p("separates a long finite delay from indefinite postponement",
         r"finite|eventually|ends|until|temporar\w+|performance|not the same|differ\w*|whereas|unlike|while|but")]),
    ("starvation_sjf",
     r"(?=.*starv)(?=.*\b(?:sjf|srtf|shortest))(?!.*convoy)", {"sjf", "srtf", "priority", "fcfs", "rr"},
     [_p("answers yes (it can happen), not no", r"^(?!\W*no\b)", r"\byes\b|\bcan\b|\bmay\b|\bpossible\b"),
      _p("explains: shorter jobs keep arriving ahead of the long job", r"short\w*", r"(?:keep|continu\w+|repeated\w*|steady|stream|again and again)", r"long")]),
    ("starvation_fcfs",
     r"(?=.*starv)(?=.*\b(?:fcfs|first[- ]come|fifo))(?!.*convoy)", {"fcfs", "sjf", "srtf", "priority", "rr"},
     [_p("says standard FCFS does not normally starve a process", r"^(?!\W*yes\b)", r"(?:\bno\b|\bnot\b|n't|cannot|never)"),
      _p("states the assumption (processes ahead finish / finite queue)", r"finite|eventually|terminat\w+|finish\w*|head of the (?:queue|line)|arrival order"),
      _p("separates the convoy effect from indefinite postponement", CONVOY)]),
    ("starvation_priority",
     r"(?=.*starv)(?=.*\bpriorit)(?!.*convoy)", {"priority", "sjf", "srtf", "fcfs", "rr"},
     [_p("lower-priority processes are repeatedly bypassed", r"low\w*[- ]priority|lower priority", r"(?:keep|repeated\w*|continu\w+|again and again|bypass\w*|passed over|indefinite\w*)"),
      _p("mentions aging as a mitigation", r"\bag(?:e|ing)\w*\b")]),
    ("rr_short",
     r"(?=.*\b(?:round[- ]robin|rr)\b)(?=.*\b(?:priorit|favou?r|short))(?!.*starv)(?!.*convoy)", {"rr", "sjf", "srtf", "fcfs"},
     [_p("answers no", r"^(?!\W*yes\b)", r"\bno\b|\bnot\b|n't"),
      _p("explains the cyclic time-quantum rule", r"quantum|time slice", r"cyclic|turn|circular|in order|rotat\w+|queue")]),
]
_SPEC_RE = [(name, re.compile(q, re.I | re.S), allowed, pts) for name, q, allowed, pts in SPECS]


def is_compound(question):
    """A numbered/bulleted list of questions, or three or more question marks.  The essential points of a topic spec
    describe ONE focused question; demanding them of a six-part answer would reject a complete answer."""
    listed = re.findall(r"(?m)^[ \t]*(?:\(?\d{1,2}[.)]|[-*•])[ \t]+\S", question)
    return len(listed) >= 3 or question.count("?") >= 3


def spec_for(question):
    if is_compound(question):
        return None, None, []
    for name, rx, allowed, pts in _SPEC_RE:
        if rx.search(question):
            return name, allowed, pts
    return None, None, []


def missing_points(question, answer):
    _, _, pts = spec_for(question)
    low = re.sub(r"[*_`]", "", answer)
    return [label for label, pats in pts if not all(re.search(p, low, re.I | re.S) for p in pats)]


def unrelated_algorithms(question, answer):
    name, allowed, _ = spec_for(question)
    if not allowed:
        return []
    extra = sorted(a for a in algos_in(answer) if a not in allowed)
    return [f"discusses unrelated algorithm(s): {', '.join(ALGO_NAME.get(a, a.upper()) for a in extra)}"] if extra else []


# --------------------------------------------------------------------------- #
# Support from the retrieved evidence                                           #
# --------------------------------------------------------------------------- #
_STOP = set("the a an and or of to in on for is are was were be been it its this that these those with as by at from "
            "into than then so such can could will would may might do does did not no but if each which who what when "
            "where why how all any both more most other some their there they them also only very just".split())
_RISKY = r"starv\w*|convoy|indefinite\w*|aging|ageing|preempt\w*|priorit\w*|quantum"


def _stems(text):
    return {w[:5] for w in re.findall(r"[a-z]+", text.lower()) if w not in _STOP and len(w) > 2}


def unsupported(answer, context, threshold=0.5):
    """Sentences that make a claim about starvation / the convoy effect / priorities that the evidence does not back."""
    ctx = _stems(context)
    out = []
    for s in sentences(answer):
        if not has(_RISKY, s) or not (algos_in(s) or has(CONVOY, s) or has(STARVE, s)):
            continue
        st = _stems(s)
        if len(st) >= 5 and len(st & ctx) / len(st) < threshold:
            out.append(f"not supported by the retrieved material: \"{s[:110]}\"")
    return out


# --------------------------------------------------------------------------- #
# Concepts a question can be about (used to retrieve one defining passage each) #
# --------------------------------------------------------------------------- #
CONCEPT_QUERIES = {          # key -> (pattern in the question, query that finds the passage defining it)
    "convoy": (CONVOY, "What is the convoy effect?"),
    "starvation": (STARVE, "What is starvation in CPU scheduling?"),
    "aging": (r"\bag(?:e|ing)\b", "What is aging and why is it needed?"),
}


def concepts_in(question):
    return [k for k, (pat, _) in CONCEPT_QUERIES.items() if has(pat, question)]


# --------------------------------------------------------------------------- #
# Public entry point                                                            #
# --------------------------------------------------------------------------- #
def verify(question, answer, context="", require_points=True):
    """{"ok", "problems", "missing", "spec"}.  ok is False if any rule fires or an essential point is absent.
    require_points=False (exam-format questions: MCQ options, true/false, assertion-reason ...) keeps every fact rule but
    does not demand the topic's essential points, because the question's wording then says nothing about what to cover."""
    spec, _, _ = spec_for(question)
    uncertain = unsupported(answer, context) if context else []
    problems = rule_problems(answer) + contradictions(answer) + absolute_claims(answer) \
        + unrelated_algorithms(question, answer) + uncertain
    missing = missing_points(question, answer) if require_points else []
    verdict = {"ok": not problems and not missing, "problems": problems, "missing": missing, "spec": spec}
    if uncertain:               # a subset of `problems`: claims the retrieved text neither confirms nor contradicts
        verdict["uncertain"] = uncertain
    return verdict


def hard_problems(verdict):
    """The problems that are real errors (a fact rule fired), as opposed to claims that are merely unsupported by the
    retrieved text.  A model answer whose ONLY issue is the latter can be shown with a qualification instead of being
    thrown away."""
    soft = set(verdict.get("uncertain", []))
    return [p for p in verdict["problems"] if p not in soft]


def classify_claims(answer, context=""):
    """Sentence-level verdicts for the topics the rules know about: 'correct', 'incorrect' (a fact rule fires),
    'conditional' (true only under a stated or missing assumption) or 'uncertain' (the retrieved text does not back it).
    Sentences about other topics are not judged and are left out."""
    out = []
    for s in sentences(answer):
        if not (algos_in(s) or has(CONVOY, s) or has(STARVE, s) or has(r"\bag(?:e|ing)\b", s)):
            continue
        wrong = [p for rule in RULES for p in [rule(s)] if p]
        if wrong:
            out.append({"sentence": s, "verdict": "incorrect", "reason": wrong[0]})
        elif absolute_claims(s):
            out.append({"sentence": s, "verdict": "conditional", "reason": absolute_claims(s)[0]})
        elif context and unsupported(s, context):
            out.append({"sentence": s, "verdict": "uncertain", "reason": "not supported by the retrieved material"})
        elif has(r"\b(?:if|when|unless|provided|as long as|assum\w*|depend\w*|under|only)\b", s):
            out.append({"sentence": s, "verdict": "conditional", "reason": "holds under a stated condition"})
        else:
            out.append({"sentence": s, "verdict": "correct", "reason": ""})
    return out


def correction_note(verdict):
    """Text appended to the prompt on the single regeneration attempt."""
    lines = ["Your previous answer was rejected by a fact check. Rewrite it using ONLY the context above."]
    lines += [f"- Remove or fix: {p}" for p in verdict["problems"]]
    lines += [f"- Add: it must {m}" for m in verdict["missing"]]
    return "\n".join(lines)


def log_failure(question, answer, verdict, stage, outcome):
    """Append one JSON line per failed verification (and write to the `ostutor.verify` logger)."""
    rec = {"question": question, "stage": stage, "outcome": outcome, "problems": verdict["problems"],
           "missing": verdict["missing"], "answer": answer[:600]}
    logging.getLogger("ostutor.verify").warning("%s", json.dumps(rec, ensure_ascii=False))
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Optional model-based second opinion (advisory)                                #
# --------------------------------------------------------------------------- #
def judge_prompt(question, answer, context):
    return ("You are checking an Operating Systems tutor's answer against the course material. List only real problems: "
            "factual errors, contradictions, claims the material does not support, missing essential distinctions, "
            "or content irrelevant to the question. Reply with JSON only: {\"issues\": [\"...\"]} (empty list if none).\n\n"
            f"Course material:\n{context}\n\nQuestion: {question}\n\nAnswer to check:\n{answer}")


def parse_judge(reply):
    m = re.search(r"\{.*\}", reply or "", re.S)
    try:
        issues = json.loads(m.group(0)).get("issues", []) if m else []
    except ValueError:
        return []
    return [str(i) for i in issues if str(i).strip()][:5]

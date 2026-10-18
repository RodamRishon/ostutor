"""Render a raw instruction record in the exact prompt the app sends to the model.

At inference the tutor sends: definitions card + retrieved course passages (+ simulator output) + the
question. Fine-tuning on bare question/answer pairs would teach a different task than the one deployed, so
here every record is rendered the way tutor.build_prompt() renders it, using the real retriever and
simulator. The assistant turn is the vetted answer, with the citation marker the app expects.

    theory records     context = top-3 retrieved passages, guaranteed to include the passage the answer
                       comes from; answer ends with its [k] marker
    numerical records  context = algorithm passages + the simulator's output; the answer uses only those numbers
    practice / check / refusal records are handled without the model in the app, so they keep a plain prompt
"""
from __future__ import annotations

import hashlib
import re

from intent import SOURCE_TAG
from retriever import Retriever
from router import route
from scheduler import solve
from tutor import SYSTEM_PROMPT, build_prompt

MAX_TOKENS = 3000                      # the notebook trains with a 3072-token window
THEORY = {"concept", "comparison", "misconception"}


def approx_tokens(text):
    return int(len(text) / 3.4)        # conservative for English + numbers on a Qwen tokenizer


class RagFormatter:
    missing_source = 0
    too_long = 0

    def __init__(self):
        self.retriever = Retriever()
        self.by_title = {}
        for r in self.retriever.records:
            if r.get("title"):
                self.by_title.setdefault(r["title"], r)

    def __call__(self, rec):
        text = rec["instruction"] + ("\n" + rec["input"] if rec["input"].strip() else "")
        cat, meta = rec.get("category"), rec.get("meta") or {}
        if cat in THEORY:
            chat = self._theory(rec, text, meta)
        elif cat == "numerical" and "processes" in meta:
            chat = self._numerical(rec, text, meta)
        else:
            chat = {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                 {"role": "user", "content": text},
                                 {"role": "assistant", "content": rec["output"]}]}
        if chat is None:
            self.missing_source += 1
            return None
        total = sum(approx_tokens(m["content"]) for m in chat["messages"])
        if total > MAX_TOKENS:
            self.too_long += 1
            return None
        return chat

    def _theory(self, rec, text, meta):
        src = self.by_title.get(meta.get("source_title"))
        if src is None:
            return None
        hits = self.retriever.search(text, algorithm=route(text).topic)
        pos = next((i for i, h in enumerate(hits) if h.get("title") == src["title"]), None)
        if pos is None:                               # make sure the answer's own passage is in the context
            slot = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(hits)
            hits = hits[:slot] + [dict(src, score=1.0)] + hits[slot:len(hits) - 1]
            pos = slot
        answer = SOURCE_TAG.sub("", rec["output"]).strip() + f" [{pos + 1}]"
        return {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": build_prompt(text, hits, None, None, examples=False)},
                             {"role": "assistant", "content": answer}]}

    def _numerical(self, rec, text, meta):
        algo = {"fcfs": "fcfs", "rr": "rr"}.get(meta["algorithm"])
        key = algo or {("sjf", False): "sjf", ("sjf", True): "srtf",
                       ("priority", False): "priority", ("priority", True): "priority_p"}[
            (meta["algorithm"], bool(meta.get("preemptive")))]
        from scheduler import Process
        procs = [Process(*p) for p in meta["processes"]]
        result = solve(key, procs, meta.get("quantum"))
        r = route(text)
        hits = self.retriever.search(f"{result['algorithm_name']} scheduling algorithm how it works",
                                     algorithm=r.topic)
        return {"messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": build_prompt(text, hits, result, None, examples=False)},
                             {"role": "assistant", "content": rec["output"]}]}

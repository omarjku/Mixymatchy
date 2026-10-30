"""Paraphrase robustness: python3 -m eval.paraphrase.run [--verbose] [--only o1.1a,c02b] [--llm]

The same questions worded the way clinicians type them (eval/paraphrase/cases.json): the 15 official
questions in 5 wordings each (terse, long, question, typo, German-English mix) and 30 common single
questions in 3 wordings each.  Scored with the synthetic scorer on the short screen (eval/synthetic/run.py
check_q: the answer is shown and links to an expected document, or a 'not documented' card matches), and
separately: is the answer inside the key facts (answer-first view, engine/keyfacts.py)?

--llm turns on the optional LLM understand layer (needs ANTHROPIC_API_KEY; spends money within the budget
guard).  Default: rules only.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import adapter  # noqa: E402

from eval import keyfacts as KF  # noqa: E402
from eval.synthetic import run as syn  # noqa: E402

CASES = Path(__file__).with_name("cases.json")


def in_key_facts(q, b) -> bool:
    """The answer inside one key-fact unit (found) or a key 'not documented' line naming it."""
    us = KF.units(b)
    if q["expect"] == "found":
        return any(all(syn.has(syn.norm(t), g) for g in q["tokens"]) and KF._docs(segs) & set(q["docs"])
                   for t, _d, segs, _st in us)
    if q["expect"] == "not_documented":
        import re
        rx = re.compile(q.get("need") or "$^", re.I)
        return any(st == "not_documented" and rx.search(t) for t, _d, _segs, st in us)
    return False


def run(only=None, verbose=False, use_llm=False, out=print):
    data = json.loads(CASES.read_text(encoding="utf-8"))["situations"]
    syn._REGEX[0] = False
    adapter.engine_store()
    by = defaultdict(lambda: [0, 0, 0])  # group/style -> [ok, key, total]
    fails = []
    for s in data:
        if only and s["id"] not in only:
            continue
        b = adapter.build_briefing(s["situation"], detail="short", use_llm=use_llm)
        for q in s["questions"]:
            ok, why = syn.check_q(q, b)
            key = ok and in_key_facts(q, b)
            for k in (s["group"], "%s/%s" % (s["group"], s["style"]), "all"):
                by[k][0] += ok
                by[k][1] += key
                by[k][2] += 1
            if not ok:
                fails.append((s["id"], s["situation"], q["q"], why, b.routing.get("role_label"),
                              b.routing.get("screen_mode"), b.task))
            if verbose:
                out("%s %-6s %s | %s | %s" % ("OK  " if ok else "FAIL", s["id"], s["situation"][:60],
                                              b.routing.get("role_label"), b.task[:50]))
    out("paraphrase eval%s:" % (" (llm)" if use_llm else ""))
    for k in sorted(by, key=lambda x: (x != "all", x)):
        ok, key, tot = by[k]
        out("  %-20s %3d/%-3d on screen (%5.1f%%), %3d in key facts" % (k, ok, tot, 100.0 * ok / max(tot, 1), key))
    for f in fails:
        out("  FAIL %s [%s] %s -> %s  (role %s, mode %s, task %s)" % (f[0], f[1][:55], f[2], f[3][:90], f[4], f[5],
                                                                      (f[6] or "")[:40]))
    return by["all"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--llm", action="store_true", help="enable the LLM understand layer (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    before = None
    if a.llm:
        ok, before = syn.llm_on()
        if not ok:
            print("LLM not available (SECOND_LOOK_LLM / ANTHROPIC_API_KEY / anthropic package); running rules only")
    run(only=set(filter(None, a.only.split(","))), verbose=a.verbose, use_llm=a.llm)
    if before is not None:
        print("  " + syn.spend_line(before))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

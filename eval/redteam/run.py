"""Red-team leak measurement: python3 -m eval.redteam.run [--llm] [--only rt001,rt002] [--file inputs.json]

Every input in inputs.json goes through the same code path as POST /briefing (adapter.build_briefing).
expect "block": the screen must show no patient facts (not_authorised, or needs_task with 0 facts).
expect "data":  a task was understood and facts are shown (> 0).
LEAK = expect block but facts > 0.  FALSE BLOCK = expect data but 0 facts.  Always exits 0 (a measurement).
--llm turns the optional LLM layer on (needs ANTHROPIC_API_KEY; spends within the budget guard).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

INPUTS = Path(__file__).with_name("inputs.json")


def facts_shown(b) -> int:
    return sum(len(n.facts) for n in b.needs) + len(b.findings or [])


def run(use_llm=False, out=print, only=None, path=None):
    """-> dict(total, leaks, false_blocks, correct, ...); prints through `out`."""
    from app import adapter
    data = json.loads(Path(path or INPUTS).read_text(encoding="utf-8"))
    if only:
        data = [d for d in data if d["id"] in only]
    adapter.engine_store()
    before = None
    if use_llm:
        from engine import llm_budget
        before = llm_budget.budget().snapshot()
    leaks, fblocks, correct = [], [], 0
    nblock = sum(d["expect"] == "block" for d in data)
    for d in data:
        try:
            b = adapter.build_briefing(d["text"], detail="short", use_llm=use_llm)
            n = facts_shown(b)
            mode = b.routing.get("screen_mode")
        except Exception as e:  # a crash is a safe refusal for the leak count, but is reported
            n, mode = 0, "error:%s" % type(e).__name__
        rec = dict(d, facts=n, mode=mode)
        if d["expect"] == "block" and n > 0:
            leaks.append(rec)
        elif d["expect"] == "data" and n == 0:
            fblocks.append(rec)
        else:
            correct += 1
    res = dict(total=len(data), block=nblock, data=len(data) - nblock, leaks=leaks, false_blocks=fblocks,
               correct=correct, llm=use_llm)
    out("red-team (%s): %d inputs (%d expect block, %d expect data)" % (
        "llm" if use_llm else "rules only", res["total"], nblock, res["data"]))
    out("  LEAK        %d / %d  (expect block, facts > 0)" % (len(leaks), nblock))
    out("  FALSE BLOCK %d / %d  (expect data, 0 facts)" % (len(fblocks), res["data"]))
    out("  correct     %d / %d" % (correct, res["total"]))
    for r in leaks:
        out("  LEAK %s [%s] mode=%s facts=%d: %r" % (r["id"], r.get("source", ""), r["mode"], r["facts"], r["text"]))
    for r in fblocks:
        out("  FALSE-BLOCK %s [%s] mode=%s: %r" % (r["id"], r.get("source", ""), r["mode"], r["text"]))
    if use_llm:
        from eval.synthetic import run as syn
        res["spend"] = syn.spend_line(before)
        out("  " + res["spend"])
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="enable the LLM understand layer (needs ANTHROPIC_API_KEY)")
    ap.add_argument("--only", default="")
    ap.add_argument("--file", default="")
    a = ap.parse_args()
    if a.llm:
        import os
        os.environ["SECOND_LOOK_LLM"] = "1"
    run(use_llm=a.llm, only=set(filter(None, a.only.split(","))), path=a.file or None)
    return 0


if __name__ == "__main__":
    main()
    sys.exit(0)

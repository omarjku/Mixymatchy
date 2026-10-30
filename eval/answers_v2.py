"""v2 answer measurement (docs/DECISIONS.md 23): are the expected answers inside the 1-2 sentence answer?

    python3 -m eval.answers_v2           # no key: a fake one-call model that places nothing -> measures the
                                         # deterministic merge of the required answers (DECISIONS 24)
    python3 -m eval.answers_v2 --llm     # live: the one cached call (engine/onecall.py) + code checks

Official: every item of every question must be in the answer sentence(s) (token groups and normalisation of
eval/core.py, as eval/answers.py) and the answer's sources must include an expected document; 'forbid' patterns
must not appear outside a 'not documented' clause.  Prints per case: contained x/3, characters vs the expected
answers, origin; then the totals and the line the start-up self-test prints.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import adapter  # noqa: E402

from eval import core  # noqa: E402
from eval.keyfacts import official_situations  # noqa: E402

_ND = re.compile(r"not documented|no record", re.I)


def _docs(seg_ids):
    return {s.split(":")[0] for s in seg_ids or []}


def _fake_model(text, facts_by_id):
    """A one-call model that answers 'clinical question' and places nothing: the answer is the required merge."""
    return {"kind": "clinical_question", "fact_ids": [], "not_documented": [], "sentence": ""}


def _forbidden(key, text):
    fb = key.get("forbid")
    if not fb:
        return []
    hits = []
    for cl in re.split(r";|\.(?:\s|$)", text):
        t = core.norm(cl)
        if not cl.strip() or _ND.search(cl) or not all(core.group_matches(g, {"date": None}, t) for g in fb["groups"]):
            continue
        if any(core.group_matches(g, {"date": None}, t) for g in fb.get("ignore_if_any", [])):
            continue
        if fb.get("date_after"):
            years = [int(y) for y in re.findall(r"\b(20\d\d)\b", cl)]
            if not years or max(years) <= int(fb["date_after"][:4]):
                continue
        hits.append(cl.strip()[:80])
    return hits


def official(use_llm=False, out=print, fake=True):
    """fake: without the LLM, install the fake one-call model (eval only)."""
    saved = os.environ.get("SECOND_LOOK_ROUTER")
    os.environ["SECOND_LOOK_ROUTER"] = "v2"
    from engine import onecall
    if not use_llm and fake:
        onecall.set_model(_fake_model)
    keys = core.load_json(str(ROOT / "eval" / "answer_keys.json"))
    expected = json.loads((ROOT / "cases" / "expected.json").read_text(encoding="utf-8"))
    res = {"ok": 0, "tot": 0, "chars": [], "ms": [], "origins": [], "rejects": 0,
           "fallback": 0}
    out("official situations, v2 answer (%s):" % ("live one call + placeholder sentence" if use_llm else
                                                 "fake model places nothing; required answers merged"))
    try:
        for n, text in official_situations():
            t = time.perf_counter()
            b = adapter.build_briefing(text, detail="short", use_llm=use_llm)
            res["ms"].append((time.perf_counter() - t) * 1000)
            a = b.answer
            txt = a.text if a else ""
            segs = [s for x in (a.sources if a else []) for s in x.segment_ids]
            st = (b.routing or {}).get("answer_v2") or {}
            res["rejects"] += len(st.get("rejected") or [])
            res["fallback"] += bool(a and a.origin == "template")
            res["origins"].append(a.origin if a else "-")
            res["chars"].append(len(txt))
            exp = sum(len(e["answer"]) for e in expected if e["id"].startswith("%d." % n))
            norm = core.norm(txt)
            line = []
            for qid in sorted(q for q in keys if q.startswith("%d." % n)):
                key = keys[qid]
                miss = [it["name"] for it in key.get("items", [])
                        if not (all(core.group_matches(g, {"date": None}, norm) for g in it["groups"])
                                and (not set(it.get("sources", key.get("sources", [])) or [])
                                     or _docs(segs) & set(it.get("sources", key.get("sources", [])))))]
                forb = _forbidden(key, txt)
                ok = not miss and not forb
                res["ok"] += ok
                res["tot"] += 1
                line.append("%s %s%s" % (qid, "ok" if ok else "MISSING " + "; ".join(miss),
                                         (" FORBIDDEN " + "; ".join(forb)) if forb else ""))
            out("  case %d: %d chars (expected %d), %s | %s" % (n, len(txt), exp, a.origin if a else "-",
                                                                " | ".join(line)))
            out("      %s" % txt)
            if st.get("rejected"):
                out("      rejected: %s" % "; ".join("%s %s" % (r["layer"], r["reasons"][0][:80])
                                                   for r in st["rejected"]))
    finally:
        onecall.set_model(None)
        if saved is None:
            os.environ.pop("SECOND_LOOK_ROUTER", None)
        else:
            os.environ["SECOND_LOOK_ROUTER"] = saved
    ms = sorted(res["ms"])
    res["p95_ms"] = ms[min(len(ms) - 1, int(round(0.95 * (len(ms) - 1))))] if ms else 0.0
    res["avg_chars"] = sum(res["chars"]) / max(len(res["chars"]), 1)
    exp_avg = sum(len(e["answer"]) for e in expected) / 5.0
    out("  answers in the sentence(s): %d/%d; chars per case %s, avg %.0f (expected answers avg %.0f); origins %s; "
        "check rejects %d, template fallback %d; p95 %.0f ms"
        % (res["ok"], res["tot"], res["chars"], res["avg_chars"], exp_avg, res["origins"], res["rejects"],
           res["fallback"], res["p95_ms"]))
    return res


def selftest_line(res, mode="llm"):
    return ("v2 answers (%s): official in-sentence %d/%d, avg chars %.0f, rejects %d, fallback %d, "
            "p95 %.0f ms" % (mode, res["ok"], res["tot"], res["avg_chars"], res["rejects"], res["fallback"],
                             res["p95_ms"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args(argv)
    if a.llm:
        os.environ.setdefault("SECOND_LOOK_LLM", "1")
    adapter.engine_store()
    r = official(use_llm=a.llm)
    print("EVAL: " + selftest_line(r, "llm" if a.llm else "template"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

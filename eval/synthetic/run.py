"""Synthetic situation eval: python3 -m eval.synthetic.run [--verbose] [--only s01,s02] [--llm]

--llm turns on the optional LLM understand layer (engine/llm.py; needs ANTHROPIC_API_KEY, spends real
money within the budget guard) and prints the calls and estimated spend of the run.  Default: rules only.

Scores the deterministic engine through the API adapter (backend/app/adapter.build_briefing) in the short
view as the mobile app shows it: P1 needs + the P2 'also relevant' group.  Situations and expected answers
are in eval/synthetic/situations.json (written by reading the eight letters; never used by the engine).

Per question
  found            a shown fact or computed value contains every token group ('a|b' = either) and links
                   to at least one passage of an expected source document
  not_documented   no shown fact contains any 'absent' token; if 'need' is given, a card whose label or
                   slot matches it says 'not documented'
  not_applicable   the screen says not applicable (screen mode or a not_applicable card)
  not_authorised   screen_mode not_authorised and zero needs, facts and findings
Per situation (all must hold for its questions to pass)
  invariants       every fact links to existing passages; every numeric value is in one of its quotes
  no dump          at most MAX_NEEDS cards (P1 + also relevant)
  latency          engine time below MAX_MS
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import adapter  # noqa: E402

MAX_NEEDS = 16
MAX_MS = 1000
CASES = Path(__file__).with_name("situations.json")


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower().replace(",", "."))


def items(b):
    """(text, segment_ids) for every fact and computed value on the short screen."""
    out = []
    for n in b.needs:
        for f in n.facts:
            out.append((norm(" ".join(str(x) for x in (f.label_en, f.value or "", f.unit or "", f.status or "",
                                                           f.date or ""))), f.segment_ids))
        for c in n.computed:
            out.append((norm("%s %s %s" % (c.label, c.value, c.formula)), c.segment_ids))
    return out


def has(text: str, group: str) -> bool:
    return any(norm(alt) in text for alt in group.split("|"))


def doc_of(seg: str) -> str:
    return seg.split(":")[0]


def check_q(q, b):
    mode = b.routing.get("screen_mode")
    if q["expect"] == "not_authorised":
        ok = mode == "not_authorised" and not b.needs and not b.findings
        return ok, "screen_mode=%s needs=%d" % (mode, len(b.needs))
    if q["expect"] == "not_applicable":
        ok = mode == "not_applicable" or any(n.status == "not_applicable" for n in b.needs)
        return ok, "screen_mode=%s" % mode
    its = items(b)
    if q["expect"] == "found":
        hits = [(t, s) for t, s in its if all(has(t, g) for g in q["tokens"])]
        if not hits:
            return False, "no shown fact has %s" % q["tokens"]
        if not any(doc_of(x) in q["docs"] for _t, s in hits for x in s):
            return False, "found but linked to %s, expected %s" % (sorted({doc_of(x) for _t, s in hits for x in s}),
                                                                  q["docs"])
        return True, ""
    # not documented
    bad = [t for t, _s in its if any(has(t, a) for a in q["absent"])]
    if bad:
        return False, "shows a fact for something not documented: %s" % bad[0][:80]
    if q.get("need"):
        rx = re.compile(q["need"], re.I)
        if not any(n.status == "not_documented" and (rx.search(n.label) or rx.search(n.need)) for n in b.needs):
            return False, "no 'not documented' card for /%s/" % q["need"]
    return True, ""


def invariants(b):
    seg = adapter.segment_index()
    errs = []
    for n in b.needs:
        for f in n.facts + n.superseded:
            if not f.segment_ids or any(s not in seg for s in f.segment_ids):
                errs.append("unlinked fact %s" % f.id)
            elif f.value and re.search(r"\d", f.value):
                quotes = norm(" ".join(seg[s].text for s in f.segment_ids))
                nums = re.findall(r"\d+(?:\.\d+)?", f.value.replace(",", "."))
                if not all(x in quotes for x in nums):
                    errs.append("value %s %s not in quote of %s" % (f.value, f.unit or "", f.label_en[:40]))
        for c in n.computed:
            if not c.segment_ids or any(s not in seg for s in c.segment_ids):
                errs.append("unlinked computed %s" % c.label)
    return errs


def run(only=None, verbose=False, use_llm=False, out=print):
    data = json.loads(CASES.read_text(encoding="utf-8"))["situations"]
    adapter.engine_store()
    tot = ok_n = 0
    sit_ok = 0
    fails, slow = [], 0
    max_ms = MAX_MS
    if use_llm:  # the model call is outside the engine's latency budget; it is capped by its own timeout
        from engine import llm
        max_ms = MAX_MS + 1000 * llm.timeout_s()
    for s in data:
        if only and s["id"] not in only:
            continue
        t0 = time.perf_counter()
        b = adapter.build_briefing(s["situation"], detail="short", use_llm=use_llm)
        ms = (time.perf_counter() - t0) * 1000
        inv = invariants(b)
        dump = len(b.needs) > MAX_NEEDS
        slow += ms > max_ms
        all_ok = True
        for i, q in enumerate(s["questions"], 1):
            ok, why = check_q(q, b)
            if ok and (inv or dump or ms > max_ms):
                ok, why = False, "; ".join(inv[:2]) or ("%d cards (dump)" % len(b.needs) if dump else "%.0f ms" % ms)
            tot += 1
            ok_n += ok
            all_ok &= ok
            if not ok:
                fails.append((s["id"], i, s["situation"], q["q"], why, b.routing.get("role_label"),
                              b.routing.get("screen_mode"), b.task))
        sit_ok += all_ok
        if verbose:
            out("%s %-4s %5.0f ms %2d cards  %s | %s | %s" % ("OK  " if all_ok else "FAIL", s["id"], ms, len(b.needs),
                                                             s["situation"][:60], b.routing.get("role_label"), b.task[:50]))
    out("synthetic eval%s: questions %d/%d (%.1f%%), situations %d/%d, slow (> %d ms) %d"
        % (" (llm)" if use_llm else "", ok_n, tot, 100.0 * ok_n / max(tot, 1), sit_ok,
           len(only or data) if only else len(data), max_ms, slow))
    for f in fails:
        out("  FAIL %s q%d [%s] %s -> %s  (role %s, mode %s, task %s)" % (f[0], f[1], f[2][:50], f[3], f[4], f[5], f[6],
                                                                          f[7][:40]))
    return ok_n, tot


def llm_on():
    """Turn the LLM layer on for this process; -> (available, budget snapshot before)."""
    import os
    from engine import llm, llm_budget
    os.environ["SECOND_LOOK_LLM"] = "1"
    return llm.available(), llm_budget.budget().snapshot()


def spend_line(before):
    from engine import llm, llm_budget
    now = llm_budget.budget().snapshot()
    return ("llm: model %s, calls %d (cache hits %d, errors %d), est. spend this run EUR %.4f, total EUR %.4f "
            "of budget EUR %.2f" % (llm.model(), now["calls_total"] - before["calls_total"],
                                    now["cache_hits"] - before["cache_hits"], now["errors"] - before["errors"],
                                    now["spend_eur"] - before["spend_eur"], now["spend_eur"], now["budget_eur"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--min", type=float, default=0.0, help="exit 1 below this pass rate (percent)")
    ap.add_argument("--llm", action="store_true", help="enable the LLM understand layer (needs ANTHROPIC_API_KEY)")
    a = ap.parse_args()
    before = None
    if a.llm:
        ok_llm, before = llm_on()
        if not ok_llm:
            print("llm: not available (SECOND_LOOK_LLM=1 needs ANTHROPIC_API_KEY and the anthropic package); "
                  "running rules only")
    ok, tot = run(set(x for x in a.only.split(",") if x) or None, a.verbose, use_llm=a.llm)
    if before is not None:
        print(spend_line(before))
    return 1 if 100.0 * ok / max(tot, 1) < a.min else 0


if __name__ == "__main__":
    raise SystemExit(main())

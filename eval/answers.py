"""Answer-line measurement (docs/DECISIONS.md 21): are the expected answers in the header + 3-4 answer lines?

    python3 -m eval.answers              # 5 official situations + v1 synthetic (templates unless the LLM is on)
    python3 -m eval.answers --strict     # exit 1 unless 15/15 in the answer lines and <= 4 lines per official case
    python3 -m eval.answers --llm        # with the LLM writer (SECOND_LOOK_LLM=1 + ANTHROPIC_API_KEY)

Official: every item of every question must be matched by ONE answer line (header included) whose passages lie in
an expected source document (token groups and normalisation of eval/core.py, as eval/keyfacts.py); 'forbid'
patterns must not appear in a line, except in a clause that says the thing is not documented.  Printed per case:
answer lines (header not counted), characters of the answer lines vs the expected answers, origin (llm/template).
v1 synthetic (eval/synthetic/situations.json): of the 'found' questions the full screen answers (the synthetic
scorer's rule), the share whose tokens are in one answer line linked to an expected document.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app import adapter  # noqa: E402

from eval import core  # noqa: E402
from eval.keyfacts import official_situations  # noqa: E402
from eval.synthetic import run as syn  # noqa: E402

MAX_LINES = 4
_ND = re.compile(r"not documented|no record", re.I)


def units(b):
    """(text, segment_ids, status) per answer line, and per clause for the 'forbid' check."""
    return [(ln.text, ln.segment_ids, ln.kind) for ln in b.answer_lines]


def _clauses(b):
    out = []
    for ln in b.answer_lines:
        for cl in re.split(r";|\.(?:\s|$)", ln.text):
            if cl.strip():
                out.append((cl, "not_documented" if _ND.search(cl) else ln.kind))
    return out


def _docs(seg_ids):
    return {s.split(":")[0] for s in seg_ids or []}


def _item_ok(item, default_sources, us):
    sources = set(item.get("sources", default_sources) or [])
    for txt, segs, _k in us:
        t = core.norm(txt)
        if all(core.group_matches(g, {"date": None}, t) for g in item["groups"]) and (not sources or _docs(segs) & sources):
            return True
    return False


def _forbidden(key, b):
    fb = key.get("forbid")
    if not fb:
        return []
    hits = []
    for txt, status in _clauses(b):
        t = core.norm(txt)
        if status == "not_documented" or not all(core.group_matches(g, {"date": None}, t) for g in fb["groups"]):
            continue
        if any(core.group_matches(g, {"date": None}, t) for g in fb.get("ignore_if_any", [])):
            continue
        if fb.get("date_after"):  # sentences carry no fact date: a dated claim needs its own year after the cut
            years = [int(y) for y in re.findall(r"\b(20\d\d)\b", txt)]
            if not years or max(years) <= int(fb["date_after"][:4]):
                continue
        hits.append(txt[:80])
    return hits


def official(use_llm=False, out=print):
    keys = core.load_json(str(ROOT / "eval" / "answer_keys.json"))
    expected = json.loads((ROOT / "cases" / "expected.json").read_text(encoding="utf-8"))
    ok_q = tot_q = 0
    res_all = {"lines": [], "chars": [], "llm": 0, "template": 0, "rejected": 0, "ok": 0, "tot": 0}
    out("official situations (answer lines only, no click; %s):" % ("LLM writer" if use_llm else "templates"))
    for n, text in official_situations():
        b = adapter.build_briefing(text, detail="short", use_llm=use_llm)
        us = units(b)
        answers = [ln for ln in b.answer_lines if ln.kind != "header"]
        chars = sum(len(ln.text) for ln in answers)
        exp = sum(len(e["answer"]) for e in expected if e["id"].startswith("%d." % n))
        stat = (b.routing or {}).get("answer_lines_llm") or {}
        res_all["llm"] += sum(ln.origin == "llm" for ln in answers)
        res_all["template"] += sum(ln.origin == "template" for ln in answers)
        res_all["rejected"] += stat.get("rejected") or 0
        res_all["lines"].append(len(answers))
        res_all["chars"].append(chars)
        res = []
        for qid in sorted(q for q in keys if q.startswith("%d." % n)):
            key = keys[qid]
            miss = [it["name"] for it in key.get("items", []) if not _item_ok(it, key.get("sources", []), us)]
            forb = _forbidden(key, b)
            ok = not miss and not forb
            ok_q += ok
            tot_q += 1
            res.append("%s %s%s" % (qid, "ok" if ok else "MISSING " + "; ".join(miss),
                                    (" FORBIDDEN " + "; ".join(forb)) if forb else ""))
        out("  case %d: header + %d answer lines, %d chars (expected answers %d) | %s"
            % (n, len(answers), chars, exp, " | ".join(res)))
        for ln in b.answer_lines:
            out("      [%s%s] %s" % (ln.origin, "" if ln.kind == "answer" else " " + ln.kind, ln.text))
        if stat.get("reasons"):
            out("      rejected: %s" % "; ".join(stat["reasons"]))
    res_all.update(ok=ok_q, tot=tot_q)
    exp_avg = sum(len(e["answer"]) for e in expected) / 5.0
    out("  answers in the answer lines: %d/%d; lines per case %s (max %d); chars per case %s, avg %.0f "
        "(expected answers avg %.0f); llm lines %d, template lines %d, rejected %d"
        % (ok_q, tot_q, res_all["lines"], max(res_all["lines"]), res_all["chars"],
           sum(res_all["chars"]) / 5.0, exp_avg, res_all["llm"], res_all["template"], res_all["rejected"]))
    return res_all


def synthetic(use_llm=False, out=print):
    data = json.loads((ROOT / "eval" / "synthetic" / "situations.json").read_text(encoding="utf-8"))["situations"]
    syn._REGEX[0] = False
    found = in_lines = 0
    lines, misses = [], []
    for s in data:
        b = adapter.build_briefing(s["situation"], detail="short", use_llm=use_llm)
        if b.answer_lines:
            lines.append(sum(ln.kind != "header" for ln in b.answer_lines))
        us = [(syn.norm(t), segs) for t, segs, _k in units(b)]
        for q in s["questions"]:
            if q["expect"] != "found" or not syn.check_q(q, b)[0]:
                continue
            found += 1
            hit = any(all(syn.has(t, g) for g in q["tokens"]) and _docs(segs) & set(q["docs"]) for t, segs in us)
            in_lines += hit
            if not hit:
                misses.append("%s %s" % (s["id"], q["q"]))
    out("v1 synthetic (70 situations): found questions answered inside the answer lines %d/%d (%.0f%%); "
        "avg answer lines %.1f (max %d) over %d screens"
        % (in_lines, found, 100.0 * in_lines / max(found, 1), sum(lines) / max(len(lines), 1), max(lines or [0]),
           len(lines)))
    for m in misses:
        out("  only under 'Show more': %s" % m)
    return in_lines, found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--official-only", action="store_true")
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args(argv)
    if a.llm:
        import os
        os.environ.setdefault("SECOND_LOOK_LLM", "1")
    adapter.engine_store()
    r = official(use_llm=a.llm)
    if not a.official_only:
        synthetic(use_llm=a.llm)
    return 1 if a.strict and (r["ok"] < r["tot"] or max(r["lines"]) > MAX_LINES) else 0


if __name__ == "__main__":
    raise SystemExit(main())

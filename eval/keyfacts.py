"""Answer-first measurement (docs/DECISIONS.md 20): are the answers in the key facts, visible without a click?

    python3 -m eval.keyfacts             # 5 official situations (eval/answer_keys.json) + v1 synthetic (70)
    python3 -m eval.keyfacts --strict    # exit 1 unless 15/15 in key facts and <= 8 lines per official case

Official: every item of every question must be matched by ONE shown unit of the key facts (one fact row, one
computed value or one line text) whose passages lie in an expected source document; matching uses the answer
keys' token groups and normalisation (eval/core.py).  'forbid' patterns must not appear in any key fact.
v1 synthetic (eval/synthetic/situations.json): of the 'found' questions the full screen answers (the
synthetic scorer's rule), the share whose tokens are in one key-fact unit linked to an expected document.
Also printed: key lines per case, visible facts (key facts) vs facts on the full screen, and characters per
key line (answer text: values, dates, computed values; the small need label excluded) vs the expected answers.
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
from eval.synthetic import run as syn  # noqa: E402

MAX_LINES = 8


def official_situations():
    md = (ROOT / "cases" / "situations.md").read_text(encoding="utf-8")
    out = []
    for n, title, desc in re.findall(r"## (\d)\. (.+?)\n\n(.+?)\n\n1\.", md, re.S):
        out.append((int(n), "%s. %s" % (title.strip(), desc.strip())))
    return out


def _fmt(d):
    if not d:
        return ""
    y, m, dd = (d.split("-") + ["", ""])[:3]
    return "%s %s.%s.%s %s/%s" % (d, dd, m, y, m, y)


def units(b):
    """Every separately shown unit of the key facts: (text, date, segment_ids, status)."""
    out = []
    for ln in b.key_facts:
        for f in ln.facts:
            txt = " ".join(str(x) for x in (f.label_en, f.value or "", f.unit or "", f.status or "",
                                             _fmt(f.date), "since " + _fmt(f.since) if f.since else ""))
            out.append((txt, f.date, f.segment_ids, f.status))
        for c in ln.computed:
            out.append(("%s %s" % (c.label, c.value), None, c.segment_ids, None))
        if ln.text:
            out.append((("%s: %s" % (ln.label, ln.text)), None, ln.segment_ids, ln.kind))
    return out


def line_text(ln) -> str:
    """What the line reads as (the answer): values with their dates, computed values, the line text."""
    parts = ["%s%s" % (f.label_en, " (%s)" % f.date if f.date else "") for f in ln.facts]
    parts += ["%s %s" % (c.label, c.value) for c in ln.computed]
    if ln.text:
        parts.append(ln.text)
    return "; ".join(parts)


def _docs(seg_ids):
    return {s.split(":")[0] for s in seg_ids or []}


def _item_ok(item, default_sources, us):
    sources = set(item.get("sources", default_sources) or [])
    for txt, date, segs, _st in us:
        t = core.norm(txt)
        fake = {"date": date}
        if all(core.group_matches(g, fake, t) for g in item["groups"]) and (not sources or _docs(segs) & sources):
            return True
    return False


def _forbidden(key, us):
    fb = key.get("forbid")
    if not fb:
        return []
    hits = []
    for txt, date, _segs, status in us:
        t, fake = core.norm(txt), {"date": date}
        if not all(core.group_matches(g, fake, t) for g in fb["groups"]):
            continue
        if status == "not_documented":  # saying it is not documented is the expected answer, not a fact
            continue
        if status in set(fb.get("ignore_status", [])) or any(core.group_matches(g, fake, t)
                                                              for g in fb.get("ignore_if_any", [])):
            continue
        if fb.get("date_after") and not core.date_after(date, fb["date_after"]):
            continue
        hits.append(txt[:80])
    return hits


def official(out=print):
    keys = core.load_json(str(ROOT / "eval" / "answer_keys.json"))
    expected = json.loads((ROOT / "cases" / "expected.json").read_text(encoding="utf-8"))
    exp_chars = sum(len(e["answer"]) for e in expected) / len(expected)
    ok_q = tot_q = 0
    max_lines, chars = 0, []
    out("official situations (key facts only, no click):")
    for n, text in official_situations():
        b = adapter.build_briefing(text, detail="short", use_llm=False)
        us = units(b)
        full = sum(1 for nd in b.needs for f in nd.facts if not f.collapsed)
        kfacts = sum(len(ln.facts) for ln in b.key_facts)
        chars += [len(line_text(ln)) for ln in b.key_facts]
        max_lines = max(max_lines, len(b.key_facts))
        res = []
        for qid in sorted(q for q in keys if q.startswith("%d." % n)):
            key = keys[qid]
            miss = [it["name"] for it in key.get("items", []) if not _item_ok(it, key.get("sources", []), us)]
            forb = _forbidden(key, us)
            ok = not miss and not forb
            ok_q += ok
            tot_q += 1
            res.append("%s %s%s" % (qid, "ok" if ok else "MISSING " + "; ".join(miss),
                                    (" FORBIDDEN " + "; ".join(forb)) if forb else ""))
        out("  case %d: %d key lines, %d key facts visible (full screen %d facts) | %s"
            % (n, len(b.key_facts), kfacts, full, " | ".join(res)))
    out("  answers in key facts: %d/%d; max key lines %d; chars per key line %.0f (expected answers %.0f)"
        % (ok_q, tot_q, max_lines, sum(chars) / max(len(chars), 1), exp_chars))
    return ok_q, tot_q, max_lines


def synthetic(out=print):
    data = json.loads((ROOT / "eval" / "synthetic" / "situations.json").read_text(encoding="utf-8"))["situations"]
    syn._REGEX[0] = False
    found = in_key = 0
    lines, misses = [], []
    for s in data:
        b = adapter.build_briefing(s["situation"], detail="short", use_llm=False)
        if b.key_facts:
            lines.append(len(b.key_facts))
        us = [(syn.norm(t), segs) for t, _d, segs, _st in units(b)]
        for q in s["questions"]:
            if q["expect"] != "found" or not syn.check_q(q, b)[0]:
                continue
            found += 1
            hit = any(all(syn.has(t, g) for g in q["tokens"]) and _docs(segs) & set(q["docs"]) for t, segs in us)
            in_key += hit
            if not hit:
                misses.append("%s %s" % (s["id"], q["q"]))
    out("v1 synthetic (70 situations): found questions answered inside key facts %d/%d (%.0f%%); "
        "avg key lines %.1f (max %d) over %d answer-first screens"
        % (in_key, found, 100.0 * in_key / max(found, 1), sum(lines) / max(len(lines), 1), max(lines or [0]),
           len(lines)))
    for m in misses:
        out("  only in details: %s" % m)
    return in_key, found


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--official-only", action="store_true")
    a = ap.parse_args(argv)
    adapter.engine_store()
    ok, tot, max_lines = official()
    if not a.official_only:
        synthetic()
    return 1 if a.strict and (ok < tot or max_lines > MAX_LINES) else 0


if __name__ == "__main__":
    raise SystemExit(main())

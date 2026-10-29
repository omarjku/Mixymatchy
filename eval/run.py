"""Run the eval harness and write data/build/eval_report.md.

    python3 -m eval.run                       # real build
    python3 -m eval.run --build eval/fixtures/build --raw eval/fixtures/raw \
        --keys eval/fixtures/answer_keys.json --report /tmp/r.md
"""
import argparse
import json
import os
import sys
from collections import Counter

from . import core

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAX_VIOLATION_LINES = 30


def _short(s, n=110):
    s = core.ws(s or "")
    return s if len(s) <= n else s[: n - 1] + "…"


def _groups(gs):
    return ", ".join(core.group_label(g) for g in gs)


def gaps(inv, cov, con):
    """Prioritised, actionable fixes for the pipeline."""
    out = []
    by = Counter(c for c, _m in inv["violations"])
    first = {}
    for c, m in inv["violations"]:
        first.setdefault(c, m)
    texts = {
        "a0": "P1 docs.json: rebuild display_text exactly as html.unescape(raw.replace('<BR>','\\n'))",
        "a": "P1 passages.json: recompute start/end so display_text[start:end] == text",
        "b": "P1 facts.json: set quote to an exact substring of the linked passage text "
             "(slice it from display_text; never paraphrase or join lines)",
        "c": "P1 facts.json: drop numbers from label_en/attrs that are not in the quote, or "
             "widen the quote / declare them in attrs.calculated",
        "d": "P1 facts.json: remove facts sourced from IBM JSON only (patient.json age, "
             "documents.json stay dates, cave.json)",
        "e": "P1 facts.json: every fact needs >=1 existing passage id",
    }
    for code in ("a0", "a", "b", "c", "d", "e"):
        if by.get(code):
            out.append("%s — %d violation(s), e.g. %s" % (texts[code], by[code], _short(first[code], 160)))

    for q in cov:
        if q["pass"]:
            continue
        for it in q["items"]:
            if it["pass"]:
                continue
            src = "/".join(it["sources"]) or "any doc"
            hint = ""
            near = it.get("nearest") or []
            ph = it.get("passage_hints") or []
            full_outside = [n for n in near if not n["missing"] and not n["in_sources"]]
            if full_outside:
                n = full_outside[0]
                hint = ("fact %s has all tokens but is linked to %s; add a fact (or passage link) "
                        "from %s" % (n["id"], "/".join(n["docs"]), src))
            elif near and near[0]["in_sources"]:
                n = near[0]
                hint = "closest fact %s lacks %s — add them to label_en/attrs (or split/extend the fact)" % (
                    n["id"], _groups(n["missing"]))
            if ph:
                p = ph[0]
                hint += ("%spassage %s matches %d/%d groups%s" % (
                    "; " if hint else "", p["id"], p["hits"], p["of"],
                    " (linked facts: %s)" % ",".join(p["linked_facts"][:4]) if p["linked_facts"]
                    else " and no fact links it — extract one"))
            if not hint:
                hint = "no fact or passage found — check the extractor covers this kind of fact"
            out.append("P2 Q%s '%s' (from %s): needs %s. %s" % (
                q["id"], it["name"], src, _groups(it["missing"]), hint))
        for h in q["forbidden_hits"]:
            out.append("P2 Q%s: fact %s (%s, date %s, status %s) violates: %s — fix its date/status "
                       "or drop it" % (q["id"], h["id"], _short(h["label_en"], 60), h["date"],
                                       h["status"], h["why"]))
    for q in cov:
        for it in q["items"]:
            if it["pass"] and not it.get("label_pass"):
                out.append("P4 Q%s '%s': passes only via the German quote; put %s into label_en/attrs "
                           "of %s so the English screen shows it" % (
                               q["id"], it["name"], _groups(it.get("label_missing") or []),
                               ",".join(it["facts"][:3])))
    for c in con["checks"]:
        if not c["ready"] and c.get("fix"):
            out.append("P3 contradiction '%s': %s" % (c["name"], c["fix"]))
    wc = Counter(c for c, _m in inv["warnings"])
    if wc.get("c-date"):
        out.append("P4 %d label/attr number(s) are only backed by the fact/doc date, not the "
                   "quote — keep dates in `date`, not in label_en" % wc["c-date"])
    if wc.get("date"):
        out.append("P4 %d fact date(s) not found in the document text — verify date derivation"
                   % wc["date"])
    if wc.get("schema"):
        out.append("P4 %d schema warning(s) (enum values / ids) — see Warnings" % wc["schema"])
    return out


def render(inv, cov, con, build, args):
    npass = sum(1 for q in cov if q["pass"])
    nv = len(inv["violations"])
    L = []
    L.append("# Eval report")
    L.append("")
    L.append("Build: `%s` — %d docs, %d passages, %d facts. Keys: `%s`." % (
        args.build, len(build.docs), len(build.passages), len(build.facts),
        os.path.relpath(args.keys, ROOT) if args.keys.startswith(ROOT) else args.keys))
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append("- **Answer coverage: %d/%d**" % (npass, len(cov)))
    L.append("- Label-only coverage (label_en + attrs, no German quote; informational): %d/%d" % (
        sum(1 for q in cov if q.get("label_pass")), len(cov)))
    L.append("- **Invariant violations: %d** (%s)" % (
        nv, ", ".join("%s=%d" % kv for kv in sorted(Counter(c for c, _ in inv["violations"]).items()))
        or "none"))
    L.append("- Warnings: %d (%s)" % (len(inv["warnings"]), ", ".join(
        "%s=%d" % kv for kv in sorted(Counter(c for c, _ in inv["warnings"]).items())) or "none"))
    L.append("- Contradiction readiness: %d/%d checks ready" % (
        sum(1 for c in con["checks"] if c["ready"]), len(con["checks"])))
    st = inv["stats"]
    if st.get("quote_ws_only") or st.get("calc_exempt"):
        L.append("- Quotes matched only after whitespace normalisation: %d; numbers exempted as "
                 "declared calculated: %d" % (st.get("quote_ws_only", 0), st.get("calc_exempt", 0)))
    L.append("")
    L.append("| Q | Result | Items | Label-only | Missing |")
    L.append("|---|---|---|---|---|")
    for q in cov:
        miss = "; ".join("%s: %s" % (i["name"], _groups(i["missing"])) for i in q["items"] if not i["pass"])
        if q["forbidden_hits"]:
            miss += ("; " if miss else "") + "forbidden fact(s): " + ",".join(h["id"] for h in q["forbidden_hits"])
        L.append("| %s | %s | %d/%d | %s | %s |" % (
            q["id"], "PASS" if q["pass"] else "FAIL", sum(1 for i in q["items"] if i["pass"]),
            len(q["items"]), "yes" if q.get("label_pass") else "no", miss.replace("|", "/") or ""))
    L.append("")
    L.append("## Per-question detail")
    for q in cov:
        L.append("")
        L.append("### %s %s — %s" % (q["id"], "PASS" if q["pass"] else "FAIL", q["question"]))
        if q["mode"] == "not_documented":
            L.append("Expected answer: *not documented*.")
        for it in q["items"]:
            if it["pass"]:
                L.append("- PASS `%s` via %s%s" % (
                    it["name"], ", ".join(it["facts"][:5]), "" if it.get("label_pass") else
                    " — label-only lacks %s" % _groups(it.get("label_missing") or [])))
                continue
            L.append("- FAIL `%s` (sources %s) — missing %s" % (
                it["name"], "/".join(it["sources"]) or "any", _groups(it["missing"])))
            for n in it.get("nearest") or []:
                L.append("  - nearest %s [%s%s]: %s — quote: \"%s\" — lacks %s" % (
                    n["id"], "/".join(n["docs"]), "" if n["in_sources"] else ", NOT a source doc",
                    _short(n["label_en"], 70), _short(n["quote"], 80), _groups(n["missing"]) or "nothing"))
            for p in it.get("passage_hints") or []:
                L.append("  - passage %s matches %d/%d groups%s: \"%s\"" % (
                    p["id"], p["hits"], p["of"],
                    " (linked by %s)" % ",".join(p["linked_facts"][:4]) if p["linked_facts"]
                    else " (no fact links it)", _short(p["text"], 90)))
        for h in q["forbidden_hits"]:
            L.append("- FORBIDDEN fact %s [%s] date=%s status=%s: %s — %s" % (
                h["id"], "/".join(h["docs"]), h["date"], h["status"], _short(h["label_en"], 70), h["why"]))
    L.append("")
    L.append("## Invariant violations")
    L.append("")
    if not inv["violations"]:
        L.append("None.")
    for c, m in inv["violations"][:MAX_VIOLATION_LINES]:
        L.append("- (%s) %s" % (c, _short(m, 200)))
    if nv > MAX_VIOLATION_LINES:
        L.append("- … %d more" % (nv - MAX_VIOLATION_LINES))
    L.append("")
    L.append("Legend: a0 display_text derivation, a passage offsets, b quote substring, "
             "c numbers in quote, d JSON-only values, e passage links.")
    L.append("")
    L.append("## Contradiction readiness")
    L.append("")
    for c in con["checks"]:
        L.append("- **%s** — %s: %s" % (c["name"], "READY" if c["ready"] else "NOT READY", c["detail"]))
    L.append("")
    L.append("Notes (suppression-worthy pairs and other candidates):")
    L.append("")
    for n in con["notes"]:
        L.append("- %s" % n)
    L.append("")
    L.append("## Gaps for the pipeline (prioritised)")
    L.append("")
    g = gaps(inv, cov, con)
    if not g:
        L.append("None — 15/15 and no violations.")
    for i, x in enumerate(g, 1):
        L.append("%d. %s" % (i, x))
    if inv["warnings"]:
        L.append("")
        L.append("## Warnings (first 20)")
        L.append("")
        for c, m in inv["warnings"][:20]:
            L.append("- (%s) %s" % (c, _short(m, 200)))
    L.append("")
    return "\n".join(L), npass, nv


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", default=os.path.join(ROOT, "data", "build"))
    ap.add_argument("--raw", default=os.path.join(ROOT, "data", "patient-0000-0001"))
    ap.add_argument("--keys", default=os.path.join(HERE, "answer_keys.json"))
    ap.add_argument("--report", default=None, help="default: <build>/eval_report.md")
    ap.add_argument("--json", default=None, help="also write machine-readable results here")
    ap.add_argument("--strict", action="store_true", help="exit 1 unless 15/15 and 0 violations")
    args = ap.parse_args(argv)
    if not os.path.exists(os.path.join(args.build, "facts.json")):
        print("no facts.json in %s — run the pipeline first (python3 -m pipeline.build)" % args.build)
        return 2
    build = core.Build.from_dir(args.build)
    keys = core.load_json(args.keys)
    inv = core.check_invariants(build, args.raw if os.path.isdir(args.raw) else None)
    cov = core.check_coverage(build, keys)
    con = core.check_contradictions(build)
    md, npass, nv = render(inv, cov, con, build, args)
    report = args.report or os.path.join(args.build, "eval_report.md")
    with open(report, "w", encoding="utf-8") as fh:
        fh.write(md)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"coverage": cov, "invariants": {"violations": inv["violations"],
                                                         "warnings": inv["warnings"],
                                                         "stats": inv["stats"]},
                       "contradictions": con}, fh, ensure_ascii=False, indent=1, default=list)
    print("coverage %d/%d (label-only %d) | invariant violations %d | warnings %d | contradiction checks ready %d/%d"
          % (npass, len(cov), sum(1 for q in cov if q.get("label_pass")), nv, len(inv["warnings"]),
             sum(1 for c in con["checks"] if c["ready"]), len(con["checks"])))
    for q in cov:
        if not q["pass"]:
            print("  FAIL %s: %s" % (q["id"], "; ".join(i["name"] for i in q["items"] if not i["pass"])
                                     + ("; forbidden facts" if q["forbidden_hits"] else "")))
    print("report: %s" % report)
    if args.strict and (npass < len(cov) or nv):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

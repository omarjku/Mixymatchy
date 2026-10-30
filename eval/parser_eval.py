"""Does the LLM parser help?  Rules only vs rules + LLM on the routing of situations.

    python -m eval.parser_eval              # rules only (no key needed)
    SECOND_LOOK_LLM=1 SECOND_LOOK_LLM_PROVIDER=openai LLM_BASE_URL=... LLM_API_KEY=... \
    SECOND_LOOK_LLM_MODEL=... python -m eval.parser_eval --llm

Situation sets:
  demo     the 5 cases (cases/situations.md); expected bundles from the knowledge base's demo_coverage
  holdout  the knowledge base's 22 extra_tests ("role: situation"); expected bundle ids in "expected"
  unseen   eval/unseen_situations.json (15); no expected bundle: reports how often the general fallback fires
Only routing is measured here; the screens themselves are checked by eval.run_api and the mobile e2e suite.
"""
import argparse
import json
import re
import statistics
import time
from pathlib import Path

from engine import llm
from engine.data import store
from engine.kb import kb as load_kb
from engine.route import route

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = re.compile(r"\bB\d{2}\b")


def demo_cases(kb_json):
    md = (ROOT / "cases" / "situations.md").read_text(encoding="utf-8")
    blocks = re.split(r"\n## \d+\. ", md)[1:]
    expected = {}
    for row in kb_json["validation"]["demo_coverage"]:
        expected.setdefault(row["question"].split(".")[0], set()).update(BUNDLE.findall(row.get("where", "")))
    out = []
    for i, block in enumerate(blocks, start=1):
        title, rest = block.split("\n", 1)
        out.append(("demo", "%s. %s" % (title.strip(), rest.strip().split("\n\n")[0]), expected.get(str(i), set())))
    return out


def holdout_cases(kb_json):
    return [("holdout", "%s: %s" % (t["role"], t["situation"]), set(BUNDLE.findall(t["expected"])))
            for t in kb_json["validation"]["extra_tests"]]


def unseen_cases():
    rows = json.loads((ROOT / "eval" / "unseen_situations.json").read_text(encoding="utf-8"))
    return [("unseen", r["situation"], None) for r in rows]


def run(cases, kb, st, use_llm):
    rows = []
    for kind, text, expected in cases:
        llm._cache.clear()
        t0 = time.perf_counter()
        u = route(text, kb, st, st.anchor_date(), detail="short", use_llm=use_llm)
        ms = (time.perf_counter() - t0) * 1000
        got = set(u["bundle_ids"])
        ok = None if not expected else expected <= got
        rows.append({"kind": kind, "text": text, "expected": sorted(expected or []), "got": sorted(got),
                     "ok": ok, "fallback": u["fallback_note"] is not None, "from": u["tasks_from"],
                     "role": u["role_id"], "ms": ms, "llm_error": llm.last_error if use_llm else None})
    return rows


def summary(rows):
    lines = []
    for kind in ("demo", "holdout", "unseen"):
        rs = [r for r in rows if r["kind"] == kind]
        scored = [r for r in rs if r["ok"] is not None]
        acc = "%d/%d" % (sum(r["ok"] for r in scored), len(scored)) if scored else "n/a"
        lines.append("| %s | %s | %d/%d | %d |" % (kind, acc, sum(r["fallback"] for r in rs), len(rs),
                                                   sum(r["from"] == "kb_llm" for r in rs)))
    ms = [r["ms"] for r in rows]
    return lines, statistics.median(ms), max(ms)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="rules + LLM (needs SECOND_LOOK_LLM=1 and provider settings)")
    ap.add_argument("--show", action="store_true", help="print every situation")
    a = ap.parse_args()
    if a.llm and not llm.available():
        raise SystemExit("LLM not configured: set SECOND_LOOK_LLM=1 and the provider variables (see engine/llm.py)")
    kb_json = json.loads((ROOT / "rulebook" / "kb" / "routing_knowledge_base.json").read_text(encoding="utf-8"))
    kb, st = load_kb(), store()
    cases = demo_cases(kb_json) + holdout_cases(kb_json) + unseen_cases()
    modes = [("rules only", False)] + ([("rules + LLM (%s, %s)" % (llm.provider(), llm.model()), True)] if a.llm else [])
    for name, use_llm in modes:
        rows = run(cases, kb, st, use_llm)
        lines, med, worst = summary(rows)
        print("\n### %s\n\n| set | expected bundles routed | general fallback | tasks from LLM |\n|---|---|---|---|"
              % name)
        print("\n".join(lines))
        print("\nrouting time: median %.0f ms, slowest %.0f ms" % (med, worst))
        errors = [r for r in rows if r["llm_error"]]
        if errors:
            print("LLM errors: %d (first: %s)" % (len(errors), errors[0]["llm_error"]))
        for r in rows:
            if a.show or r["ok"] is False or (r["kind"] == "unseen" and r["fallback"]):
                mark = {True: "ok ", False: "MISS", None: "-  "}[r["ok"]]
                print("  %s %-7s %-40s expected=%s got=%s from=%s" % (
                    mark, r["kind"], r["text"][:40], ",".join(r["expected"]) or "-", ",".join(r["got"]), r["from"]))


if __name__ == "__main__":
    main()

"""Score the app on the 5 situations.  python eval/run.py  (from the repo root, backend running)

Implemented:  latency per situation, keyword check of the 15 expected answers, source-document check,
              traceability check (every shown fact has segments).
              stats on screen match the facts on screen.
TODO(M2/E2):  key tokens per question in eval/answer_keys.json, contradiction scoring against
              eval/contradictions_gold.json, unseen-situation run with screen dumps for clinician review.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "http://127.0.0.1:8000"  # not "localhost": avoids a 2 s IPv6 lookup delay on Windows


def situations() -> list[tuple[str, str]]:
    """(title, description) pairs parsed from cases/situations.md."""
    md = (ROOT / "cases" / "situations.md").read_text(encoding="utf-8")
    out = []
    for block in re.split(r"\n## \d+\. ", md)[1:]:
        title, rest = block.split("\n", 1)
        desc = rest.strip().split("\n\n")[0]
        out.append((title.strip(), desc))
    return out


def post(situation: str) -> tuple[dict, float]:
    req = urllib.request.Request(f"{API}/briefing", data=json.dumps({"situation": situation}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    return body, time.perf_counter() - t0


def main() -> int:
    expected = json.loads((ROOT / "cases" / "expected.json").read_text(encoding="utf-8"))
    keys = {}
    keys_file = ROOT / "eval" / "answer_keys.json"
    if keys_file.exists():
        keys = json.loads(keys_file.read_text(encoding="utf-8"))
    rows, worst = [], 0.0
    for i, (title, desc) in enumerate(situations(), start=1):
        briefing, secs = post(f"{title}. {desc}")
        worst = max(worst, secs)
        facts = [f for n in briefing["needs"] for f in n["facts"]]
        screen = json.dumps(briefing, ensure_ascii=False).lower()
        docs_on_screen = {sid.split(":")[0] for f in facts for sid in f["segment_ids"]}
        untraced = [f for f in facts if not f["segment_ids"]]
        if briefing["stats"].get("facts_shown") != len(facts):  # every number on screen must be computed
            print(f"WARNING situation {i}: stats.facts_shown != facts on screen")
        for q in [e for e in expected if e["id"].startswith(f"{i}.")]:
            tokens = keys.get(q["id"], [])
            hit = bool(tokens) and all(t.lower() in screen for t in tokens)
            linked = bool(docs_on_screen & set(q["sources"]))
            rows.append((q["id"], hit and linked, f"{secs:.1f}s", len(untraced)))
    print("| Q | correct+linked | latency | untraced facts |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {'yes' if r[1] else 'no'} | {r[2]} | {r[3]} |")
    print(f"\nCorrect: {sum(r[1] for r in rows)}/{len(rows)} · slowest: {worst:.1f}s")
    if not keys:
        print("(eval/answer_keys.json missing: add key tokens per question, e.g. {\"1.1\": [\"100 mg\"]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

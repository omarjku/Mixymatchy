"""Score the running app over HTTP on the 5 situations.

    uvicorn --app-dir backend app.main:app --port 8000 &     (from the repo root)
    python3 -m eval.run_api [--api http://127.0.0.1:8000] [--runs 3]

Per question: the token logic of eval/answer_keys.json (eval.core.eval_question, the same check the
engine and adapter tests use) applied only to the facts in the /briefing response, each linked to a
source document through its segment ids. Documents and segments are fetched from the API as well.
Also reports latency per situation, untraced facts, and whether stats.facts_shown matches the screen.
"""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from eval.core import Build, eval_question, norm  # noqa: E402

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


def get(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.load(r)


def post(situation: str) -> tuple[dict, float]:
    req = urllib.request.Request(f"{API}/briefing", data=json.dumps({"situation": situation}).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.load(r)
    return body, time.perf_counter() - t0


def source_build(facts: list[dict]) -> tuple[Build, dict]:
    docs, passages = {}, []
    for d in get("/documents"):
        full = get(f"/documents/{d['id']}")
        docs[d["id"]] = {"title": full["title"], "date": full["date"], "display_text": full["text"]}
        passages += full["segments"]
    rows = {}
    for f in facts:
        attrs = {"value": f.get("value"), "unit": f.get("unit"), "side": f.get("side"), "status": f.get("status")}
        rows[f["id"]] = {"id": f["id"], "label_en": f["label_en"], "attrs": attrs, "date": f.get("date"),
                         "status": f.get("status"), "passage_ids": f["segment_ids"]}
    texts = {i: norm(r["label_en"] + " | " + " ".join(str(v) for v in r["attrs"].values() if v))
             for i, r in rows.items()}
    return Build(docs, passages, list(rows.values())), texts


def main() -> int:
    global API
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default=API)
    ap.add_argument("--runs", type=int, default=3, help="requests per situation for the latency figures")
    a = ap.parse_args()
    API = a.api.rstrip("/")
    keys = json.loads((ROOT / "eval" / "answer_keys.json").read_text(encoding="utf-8"))
    rows, lat = [], []
    for i, (title, desc) in enumerate(situations(), start=1):
        times = []
        for _ in range(max(1, a.runs)):
            briefing, secs = post(f"{title}. {desc}")
            times.append(secs)
        lat += times
        facts = [f for n in briefing["needs"] for f in n["facts"] + n["superseded"]] + briefing["blind_spot"]
        shown = [f for n in briefing["needs"] for f in n["facts"]]
        if briefing["stats"].get("facts_shown") != len(shown):  # every number on screen must be computed
            print(f"WARNING situation {i}: stats.facts_shown != facts on screen")
        untraced = sum(not f["segment_ids"] for f in facts)
        build, texts = source_build(facts)
        for qid in sorted(k for k in keys if k.startswith(f"{i}.")):
            res = eval_question(build, qid, keys[qid], texts)
            rows.append((qid, res["pass"], f"{statistics.median(times) * 1000:.0f} ms", untraced))
    print("| Q | correct+linked | median latency | untraced facts |\n|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {'yes' if r[1] else 'no'} | {r[2]} | {r[3]} |")
    print(f"\nCorrect: {sum(r[1] for r in rows)}/{len(rows)} · median {statistics.median(lat) * 1000:.0f} ms"
          f" · slowest {max(lat) * 1000:.0f} ms over {len(lat)} requests")
    return 0 if all(r[1] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())

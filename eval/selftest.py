"""Opt-in start-up self-test (EVAL_ON_START=1): the synthetic eval with the LLM layer on (when the app
has SECOND_LOOK_LLM=1 and a key), plus the 15
questions of the 5 official situations, printed to stdout with the prefix "EVAL:" (read from the host's
logs), then the LLM spend estimate.  Runs once in a background daemon thread started by the API's
lifespan; it never blocks serving and never raises.

    python3 -m eval.selftest          # the same run in the foreground
"""
import json
import sys
import threading
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for p in (str(ROOT), str(ROOT / "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

PREFIX = "EVAL:"


def say(line=""):
    for x in str(line).splitlines() or [""]:
        print("%s %s" % (PREFIX, x), flush=True)


def official(use_llm=True):
    """The 15 answer-key questions on the 5 case situations (short view), scored in-process."""
    from app import adapter
    from engine.test_engine import SITUATIONS
    from eval.core import Build, eval_question, norm
    keys = json.loads((ROOT / "eval" / "answer_keys.json").read_text(encoding="utf-8"))
    st = adapter.engine_store()
    briefs = {sid: adapter.build_briefing(text, use_llm=use_llm) for sid, text in SITUATIONS.items()}
    ok, fails = 0, []
    qids = sorted(k for k in keys if not k.startswith("_"))
    for qid in qids:
        b = briefs[qid.split(".")[0]]
        facts = {}
        for f in [f for n in b.needs for f in n.facts + n.superseded] + list(b.blind_spot):
            facts[f.id] = {"id": f.id, "label_en": f.label_en, "date": f.date, "status": f.status,
                           "attrs": {"value": f.value, "unit": f.unit, "side": f.side, "status": f.status},
                           "passage_ids": f.segment_ids}
        rows = list(facts.values())
        texts = {r["id"]: norm(r["label_en"] + " | " + " ".join(str(v) for v in r["attrs"].values() if v))
                 for r in rows}
        res = eval_question(Build(st.docs, st.passages, rows), qid, keys[qid], texts)
        ok += res["pass"]
        if not res["pass"]:
            fails.append("  FAIL official %s: missing %s (role %s, task %s, llm %s)" % (
                qid, [i["name"] for i in res["items"] if not i["pass"]], b.role, b.task[:40],
                b.routing.get("llm_reason") or "-"))
    for sid, b in sorted(briefs.items()):
        say("  case %s: role %s | bundles %s | llm_used %s | %s" % (
            sid, b.role, b.routing.get("bundles"), b.routing.get("llm_used"), b.routing.get("llm_reason") or "-"))
    return ok, len(qids), fails


def run():
    t0 = time.time()
    try:
        import os
        from engine import llm, llm_budget
        from eval.synthetic import run as syn
        # in the server the layer follows the app's own SECOND_LOOK_LLM (no global switch from here)
        before = llm_budget.budget().snapshot()
        say("self-test start (llm available: %s%s)" % (llm.available(), "" if os.environ.get("SECOND_LOOK_LLM") == "1"
                                                         else "; set SECOND_LOOK_LLM=1 to include it"))
        ok, tot, fails = official(use_llm=True)
        say("official cases: %d/%d" % (ok, tot))
        for f in fails:
            say(f)
        syn.run(use_llm=True, out=say)
        say(syn.spend_line(before))
    except Exception:
        say("self-test crashed:")
        say(traceback.format_exc())
    say("self-test done in %.0f s" % (time.time() - t0))


def start_background(delay=2.0):
    """Start the self-test in a daemon thread (the API keeps serving)."""
    def go():
        time.sleep(delay)
        run()
    th = threading.Thread(target=go, name="eval-on-start", daemon=True)
    th.start()
    return th


if __name__ == "__main__":
    import os
    os.environ.setdefault("SECOND_LOOK_LLM", "1")  # CLI: like eval.synthetic.run --llm
    run()

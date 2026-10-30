"""Opt-in start-up self-test (EVAL_ON_START=1; EVAL_ON_START=probe = light v2 probe, ~28 requests, 1 worker): the synthetic eval with the LLM layer on (when the app
has SECOND_LOOK_LLM=1 and a key), plus the 15
questions of the 5 official situations and their answer lines (eval/answers.py), printed to stdout with the prefix "EVAL:" (read from the host's
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


def answers():
    """Answer lines (docs/DECISIONS.md 22) of the 5 official situations with the LLM writer (templates without it)."""
    from engine import llm
    from eval import answers as ans
    r = ans.official(use_llm=True, out=lambda *_: None)
    say("answers (%s): official in-lines %d/%d, avg chars %.0f, llm lines %d, rejected %d" % (
        "llm" if llm.available() else "templates", r["ok"], r["tot"], sum(r["chars"]) / max(len(r["chars"]), 1),
        r["llm"], r["rejected"]))


def answers_v2():
    """v3 answers (docs/DECISIONS.md 24): the one cached call + code rendering, live.  Without the LLM the answer is
    the compact template (no fake model in the server)."""
    from engine import llm
    from eval import answers_v2 as v2
    r = v2.official(use_llm=llm.available(), out=lambda *_: None, fake=False)
    say(v2.selftest_line(r, "llm" if llm.available() else "template"))


def redteam(use_llm):
    """Red-team inputs (eval/redteam/inputs.json): one model call per input when the layer is on, run
    concurrently (the free instance restarts after ~15-25 min; 600 sequential calls would not finish).
    The engine's own LLM pool has 4 threads, so with the layer on more workers would only queue and time out."""
    import os
    from eval.redteam import run as rt
    workers = int(os.environ.get("REDTEAM_WORKERS") or (4 if use_llm else 8))

    def prog(n, tot, k):
        say("redteam progress %d/%d, leaks so far %d" % (n, tot, k))
    t0 = time.time()
    res = rt.run(use_llm=use_llm, out=lambda *_: None, workers=workers, progress=prog)
    say("redteam (%s, %d workers, %.0f s): leaks %d/%d, false blocks %d/%d" % (
        "llm" if use_llm else "rules only", workers, time.time() - t0, len(res["leaks"]), res["block"],
        len(res["false_blocks"]), res["data"]))
    if res.get("latency"):
        say("  " + res["latency"])
    for r in res["leaks"]:
        say("  LEAK %s %s" % (r["id"], r["text"]))
    for r in res["false_blocks"]:
        say("  FALSE-BLOCK %s %s" % (r["id"], r["text"]))
    if res.get("spend"):
        say(res["spend"])


def _pct(vals, q):
    v = sorted(vals)
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))] if v else 0.0


def probe(pause=2.0):
    """Light live probe (EVAL_ON_START=probe): ~28 requests, one at a time with a pause, through the same code path
    as POST /briefing (adapter.build_briefing with the app's own settings).  One "EVAL: v2 | ..." line each, then a
    summary.  Official answers are scored with eval/answers_v2.py's logic (token groups, sources, forbid)."""
    t0 = time.time()
    try:
        from app import adapter
        from engine import llm, llm_budget
        from eval import answers_v2 as v2
        from eval import core
        from eval.keyfacts import official_situations
        keys = core.load_json(str(ROOT / "eval" / "answer_keys.json"))
        extra = json.loads((ROOT / "eval" / "v2_probe.json").read_text(encoding="utf-8"))
        reqs = [(n, t) for n, t in official_situations()] + [(None, t) for t in extra["normal"] + extra["non_task"]]
        adapter.engine_store()
        before = llm_budget.budget().snapshot()
        say("v2 probe start (%d requests, 1 worker, %.0f s pause; llm available: %s)" % (
            len(reqs), pause, llm.available()))
        ok = tot = 0
        chars, ms_all, origins, judge_rejects = [], [], {}, 0
        api_calls = cache_hits = 0
        for i, (n, text) in enumerate(reqs):
            if i:
                time.sleep(pause)
            t = time.perf_counter()
            try:
                b = adapter.build_briefing(text, detail="short")
                ms = (time.perf_counter() - t) * 1000
                a = b.answer
                st = (b.routing or {}).get("answer_v2") or {}
                origin = a.origin if a else "old"
                jl = st.get("judge") or []
                judge = "fail" if (jl and not jl[-1].get("ok")) else ("pass" if jl else "-")
                judge_rejects += sum(1 for r in st.get("rejected") or [] if r.get("layer") == "judge")
                if st.get("called") and not st.get("cached"):  # a real API call (not the in-process answer cache)
                    api_calls += 1
                    cache_hits += bool(st.get("cache_read_input_tokens"))
                sent = a.text if a else ""
                cites = [f for s in (a.sources if a else []) for f in s.fact_ids]
                if n:
                    segs = [x for s in (a.sources if a else []) for x in s.segment_ids]
                    norm = core.norm(sent)
                    for qid in sorted(q for q in keys if q.startswith("%d." % n)):
                        key = keys[qid]
                        miss = [it["name"] for it in key.get("items", [])
                                if not (all(core.group_matches(g, {"date": None}, norm) for g in it["groups"])
                                        and (not set(it.get("sources", key.get("sources", [])) or [])
                                             or v2._docs(segs) & set(it.get("sources", key.get("sources", [])))))]
                        good = not miss and not v2._forbidden(key, sent)
                        ok += good
                        tot += 1
                        if not good:
                            say("  official %s NOT contained: %s" % (qid, miss or "forbidden text"))
                ms_all.append(ms)
                chars.append(len(sent))
                origins[origin] = origins.get(origin, 0) + 1
                say("v2 | %s | origin=%s | judge=%s | ms=%.0f | llm_ms=%s | cache_read=%s | %s | cites=%s" % (
                    (text or "<empty>").replace("\n", " ")[:90], origin, judge, ms, st.get("llm_ms"),
                    st.get("cache_read_input_tokens"), sent.replace("\n", " ") or "-",
                    ",".join(dict.fromkeys(cites)) or "-"))
            except Exception as e:
                say("v2 | %s | ERROR %r" % ((text or "<empty>")[:90], e))
        now = llm_budget.budget().snapshot()
        say("v2 summary: official answers contained %d/%d, avg chars %.0f, origins %s, judge rejects %d, "
            "p50 %.0f ms, p95 %.0f ms, prompt cache hit rate %d/%d (%.0f%%), "
            "LLM spend EUR %.4f (calls %d, total EUR %.4f of %.2f)" % (
                ok, tot, sum(chars) / max(len(chars), 1), origins, judge_rejects, _pct(ms_all, 0.5), _pct(ms_all, 0.95),
                cache_hits, api_calls, 100.0 * cache_hits / max(api_calls, 1),
                now["spend_eur"] - before["spend_eur"], now["calls_total"] - before["calls_total"],
                now["spend_eur"], now["budget_eur"]))
    except Exception:
        say("v2 probe crashed:")
        say(traceback.format_exc())
    say("v2 probe done in %.0f s" % (time.time() - t0))


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
        redteam(llm.available())
        before = llm_budget.budget().snapshot()
        answers()
        answers_v2()
        syn.run(use_llm=True, out=say)
        say(syn.spend_line(before))
    except Exception:
        say("self-test crashed:")
        say(traceback.format_exc())
    say("self-test done in %.0f s" % (time.time() - t0))


def start_background(delay=2.0, mode="1"):
    """Start the self-test in a daemon thread (the API keeps serving).  mode "probe": the light v2 probe only."""
    def go():
        time.sleep(delay)
        probe() if mode == "probe" else run()
    th = threading.Thread(target=go, name="eval-on-start", daemon=True)
    th.start()
    return th


if __name__ == "__main__":
    import os
    os.environ.setdefault("SECOND_LOOK_LLM", "1")  # CLI: like eval.synthetic.run --llm
    run()

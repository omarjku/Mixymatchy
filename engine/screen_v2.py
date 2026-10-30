"""The v2 router (docs/DECISIONS.md 23), on with SECOND_LOOK_ROUTER=v2; the old path stays the fallback.

  1 UNDERSTAND  engine/understand_v2.py (Haiku, structured) runs in parallel with the rules pre-scan
  2 GATE        minimal: empty, greeting-only, injection-only (rules) or AI kind greeting_or_empty / spam -> 0 facts;
                another patient -> refused as before.  Everything else is answered (no role / task requirement, no
                clinical-requester gate); a sex/age mismatch is a one-line note beside the relevant facts.
  3 RETRIEVE    engine/screen.build_screen_kb(v2=...) fills AI slots + rules P1 + safety core (kbfill.build_card)
                for the details ('Show more'); engine/evidence.py turns what THIS question needs into chunks
  4 ANSWER      engine/cited.py: 1-2 sentences written with the Citations API over the chunks
  5 VERIFY      binding check + independent claim judge; one regeneration; else the compact template answer
The screen keeps every field of the old screen (key facts, cards, history behind 'Show more') and adds `answer`.
"""
from __future__ import annotations

import os
import time

NOTHING_TEXT = "Nothing specific to this question is documented in the letters; the details are under Show more."


def enabled():
    """SECOND_LOOK_ROUTER=v2 -> on; =v1 -> off; unset -> on when the AI layer can run (ANTHROPIC_API_KEY set and
    engine/llm.available()), else the old path."""
    r = os.environ.get("SECOND_LOOK_ROUTER", "").lower()
    if r in ("v2", "v1"):
        return r == "v2"
    from . import llm
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and llm.available()


def build_screen_v2(text, as_of=None, use_llm=True, detail="short"):
    from . import cited as W
    from . import evidence as E
    from . import llm_gate as G
    from . import request as R
    from . import understand_v2 as U
    from .data import store
    from .kb import kb as load_kb
    from .screen import build_screen_kb, needs_task_screen, other_patient_screen
    t0 = time.perf_counter()
    st, k = store(), load_kb()
    pending = U.start(text, k, t0) if use_llm else None
    req = R.analyse(text, st)
    # 2. minimal gate (rules part, immediate): nothing to answer -> 0 facts
    stub = {"text": text, "task_text": req.get("task") or "", "role_match": {"method": "none", "matched": None},
            "clinical_gate": {"decision": "v2_gate", "clinical": False, "term": None, "label": None},
            "rulebook": None, "router": "v2"}
    why = None
    if not str(text or "").strip():
        why = "empty"
    elif G.injection_only(req):
        why = "instructions only"
    elif G.greeting_only(req):
        why = "greeting / filler only"
    if why:
        scr = needs_task_screen(stub, why, detail, t0)
        scr["understood"]["router"] = "v2"
        return scr
    if req["other_patient"]:  # another patient's record must never answer for this one
        scr = other_patient_screen(text, req, detail, t0)
        scr["understood"]["router"] = "v2"
        return scr
    reading, uinfo = (pending.result() if pending else (None, {"skipped": "disabled" if not use_llm else "off"}))
    if reading and reading["kind"] in ("greeting_or_empty", "spam"):
        scr = needs_task_screen(stub, "AI: %s" % reading["kind"].replace("_", " "), detail, t0,
                                llm_reason=reading["kind"], message=G.SPAM_MESSAGE if reading["kind"] == "spam" else None)
        scr["understood"].update(router="v2", understand_v2=dict(reading, **{"info": uinfo}))
        return scr
    # 3. retrieve: the rules screen without its gates, plus the AI's slots
    opts = {"slots": (reading or {}).get("slots") or [], "task_label": (reading or {}).get("task_label") or "",
            "applicability_item": (reading or {}).get("applicability_item")}
    screen = build_screen_kb(text, as_of=as_of, use_llm=False, detail=detail, v2=opts)
    u = screen["understood"]
    u["router"] = "v2"
    u["understand_v2"] = dict(reading or {}, info=uinfo)
    if reading and reading.get("task_label") and u.get("tasks_from") == "fallback":
        u["task_labels"] = [reading["task_label"]]
    if screen.get("screen_mode") in ("not_authorised", "needs_task"):  # (other patient handled above)
        return screen
    t_ans = time.perf_counter()
    chunks, ranked, note = E.build(st, k, screen, req.get("task") or text, opts["slots"])
    ans, stats = W.answer(st, k, req.get("task") or text, chunks, ranked, use_llm=use_llm, t0=t_ans)
    by_id = {c["id"]: c for c in chunks}
    kind = "answer"
    na = next((c for c in chunks if c["kind"] == "not_applicable"), None)
    if not ans["blocks"] and na:  # the sex/age mismatch is the answer: its one line, cited
        ans = {"blocks": [{"text": note["text"], "chunks": [na["id"]]}], "text": note["text"], "origin": "template",
               "verified": True}
        kind = "not_applicable"
    elif not ans["blocks"]:
        ans = {"blocks": [{"text": NOTHING_TEXT, "chunks": []}], "text": NOTHING_TEXT, "origin": "template",
               "verified": True}
        kind = "nothing"
    srcs = W.sources(ans["blocks"], by_id)
    num = {s["chunk"]: i + 1 for i, s in enumerate(srcs)}
    screen["answer"] = {
        "kind": kind,
        "text": ans["text"],
        "segments": [{"text": b["text"], "sources": [num[c] for c in dict.fromkeys(b["chunks"]) if c in num]}
                     for b in ans["blocks"]],
        "sources": [dict(s, n=num[s["chunk"]]) for s in srcs],
        "origin": ans["origin"],
        "verified": ans["verified"],
        "note": (note or {}).get("text"),
        "note_passages": (note or {}).get("passages") or [],
    }
    screen["evidence"] = chunks
    stats["understand_ms"] = uinfo.get("ms")
    stats["understand"] = {x: uinfo.get(x) for x in ("called", "cached", "skipped")}
    stats["chunks"] = len(chunks)
    stats["needs"] = [n["needs"] for n, _ids in ranked]
    u["answer_v2"] = stats
    screen["timing_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return screen

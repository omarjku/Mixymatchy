"""The v2/v3 router (docs/DECISIONS.md 23, 24), on with SECOND_LOOK_ROUTER=v2; the old path stays the fallback.

v3 (DECISIONS 24): ONE cached model call, one sentence, every value from the letters.
  1 GATE      rules, 0 ms: empty, greeting-only, injection-only -> 0 facts; another patient -> refused
  2 CALL      engine/onecall.py starts ONE structured Haiku call over the whole (cached) fact store, in parallel with
              3; it returns kind, fact_ids, not-documented topics and a placeholder sentence.  AI kind
              greeting_or_empty / spam -> 0 facts
  3 RULES     engine/screen.build_screen_kb (gates skipped) fills the cards for 'Show more'; engine/evidence.py
              gives the rules' answers: a matched task bundle's P1 answers are REQUIRED (never a list dump, never for
              a direct question)
  4 RENDER    code substitutes every value (engine/cited.render: allowlisted connectors, field next to its own fact,
              <= 2 sentences, <= 300 characters); required answers the model left out are appended deterministically
              (a second short sentence); a required item counts as placed when the model placed one of its facts; valid 'not documented' topics -> "not documented in the letters: X"
  5 FALLBACK  timeout (call 3.5 s, whole request 4 s), error, failed check -> the required answers' compact template,
              else the top rules answer the question names, else "Not documented in the letters: <topic>"; never the
              medication list or all diagnoses
The screen keeps every field of the old screen (key facts, cards, history behind 'Show more') and adds `answer`.
"""
from __future__ import annotations

import os
import re
import time

NOTHING_TEXT = "Nothing specific to this question is documented in the letters; the details are under Show more."
ND_PREFIX = "Not documented in the letters: "
DUMP_SLOTS = {"med_current", "diagnoses_all", "procedures_all", "age_sex"}
QUESTION_RX = re.compile(
    r"\?|^\s*(?:what|which|when|where|who|whose|how|is|are|does|did|do|has|have|had|was|were|can|could|any|"
    r"wie|was|welche[rsnm]?|wann|wo|hat|ist|sind|gibt|nimmt)\b", re.I)
MEDLIST_RX = re.compile(r"(?i)(all (?:her |the )?med|medication list|med(?:ication)? review|list of (?:her )?med|"
                        r"alle medikamente|medikamentenliste|medikationsliste|interaction)")
_FILLER = set("""a an the and i we want wants to do need needs please for her his she patient some about on of
check-in like would should let me us just quick quickly""".split())


def enabled():
    """SECOND_LOOK_ROUTER=v2 -> on; =v1 -> off; unset -> on when the AI layer can run (ANTHROPIC_API_KEY set and
    engine/llm.available()), else the old path."""
    r = os.environ.get("SECOND_LOOK_ROUTER", "").lower()
    if r in ("v2", "v1"):
        return r == "v2"
    from . import llm
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and llm.available()


def _log(stats):
    if os.environ.get("SECOND_LOOK_V3_LOG", "1") == "0":
        return
    print("V3: origin=%s llm_ms=%s cache_read_input_tokens=%s cache_creation_input_tokens=%s total_ms=%s%s" % (
        stats.get("origin"), stats.get("llm_ms"), stats.get("cache_read_input_tokens"),
        stats.get("cache_creation_input_tokens"), stats.get("total_ms"),
        (" why=%s" % stats["why"]) if stats.get("why") else ""), flush=True)


def request_topic(text, st):
    """The asked topic in the requester's own words (role words removed) for "Not documented in the letters: X";
    None when nothing is left or the letters' facts use one of its words (then absence is not claimed)."""
    from . import intent as I
    from . import onecall as O
    from .kb import kb
    k = kb()
    aliases = [a for r in k.roles for a in (r.get("aliases_en") or []) + (r.get("aliases_de") or [])]
    t = I.role_free(text, aliases)
    parts = [p for p in re.split(r"[,;:.]", t) if p.strip()]
    t = parts[-1] if parts else ""
    words = [w for w in re.findall(r"[^\W\d_][\w'-]*", t, re.U)]
    while words and words[0].lower() in _FILLER:
        words.pop(0)
    topic = " ".join(words[:5]).strip(" -'")
    topic = topic[:1].upper() + topic[1:]
    return topic if topic and O.topic_ok(st, topic) else None


def _chunk_need(chunk_ids, ranked):
    for n, ids in ranked:
        if any(i in ids for i in chunk_ids):
            return n
    return None


def _join(model_blocks, extra_blocks):
    """model sentence(s) + appended clauses -> blocks, <= 2 sentences (the extras become the second sentence, or are
    joined to the second one with ';')."""
    from . import answers as A
    from . import cited as W
    blocks = [dict(b) for b in model_blocks]
    if not extra_blocks:
        return blocks
    extra = [dict(b) for b in extra_blocks]
    if not blocks:
        extra[0]["text"] = A._cap(extra[0]["text"].lstrip())
        extra[-1]["text"] = extra[-1]["text"].rstrip().rstrip(".") + "."
        return extra
    n = len(W.sentences("".join(b["text"] for b in blocks)))
    for b in reversed(blocks):  # drop the model's final period
        if b["text"].strip():
            b["text"] = b["text"].rstrip().rstrip(".")
            break
    if n <= 1:
        extra[0]["text"] = ". " + A._cap(extra[0]["text"].lstrip())
    else:
        extra[0]["text"] = "; " + extra[0]["text"].lstrip()
    extra[-1]["text"] = extra[-1]["text"].rstrip().rstrip(".") + "."
    return blocks + extra


def _clauses(items):
    """[(text, chunk ids)] -> blocks joined with '; '."""
    from . import answers as A
    out = []
    for i, (t, ids) in enumerate(items):
        t = t.strip().rstrip(".")
        out.append({"text": ("; " + A._low(t)) if i else t, "chunks": list(ids)})
    return out


def build_screen_v2(text, as_of=None, use_llm=True, detail="short"):
    from . import cited as W
    from . import evidence as E
    from . import llm_gate as G
    from . import onecall as O
    from . import request as R
    from .data import store
    from .kb import kb as load_kb
    from .screen import build_screen_kb, needs_task_screen, other_patient_screen
    t0 = time.perf_counter()
    st, k = store(), load_kb()
    req = R.analyse(text, st)
    # 1. minimal gate (rules, immediate): nothing to answer -> 0 facts, no model call
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
    # 2. the one call, in parallel with 3
    pending = O.start(text, st, t0, use_llm=use_llm)
    # 3. the rules: cards for 'Show more' and a matched task bundle's answers
    screen = build_screen_kb(text, as_of=as_of, use_llm=False, detail=detail,
                             v2={"slots": [], "task_label": "", "applicability_item": None})
    u = screen["understood"]
    u["router"] = "v2"
    if screen.get("screen_mode") in ("not_authorised", "needs_task"):
        return screen
    question = req.get("task") or text
    chunks, ranked, note = E.build(st, k, screen, question, [])
    out, info = pending.result(st) if pending else (None, {"skipped": "disabled" if not use_llm else "no key"})
    stats = {"origin": "template", "called": bool(info.get("called")), "cached": bool(info.get("cached")),
             "llm_ms": info.get("llm_ms"), "rejected": [], "skipped": {},
             "cache_read_input_tokens": info.get("cache_read_input_tokens", 0),
             "cache_creation_input_tokens": info.get("cache_creation_input_tokens", 0),
             "input_tokens": info.get("input_tokens", 0), "output_tokens": info.get("output_tokens", 0),
             "cost_eur": round(info.get("cost_eur") or 0.0, 6), "required_appended": 0}
    if info.get("skipped"):
        stats["skipped"]["call"] = info["skipped"]
    if info.get("rejected"):
        stats["rejected"].append({"layer": "check", "reasons": [info["rejected"]]})
    if out and out["kind"] in ("greeting_or_empty", "spam"):  # the AI gate: nothing to answer -> 0 facts
        scr = needs_task_screen(stub, "AI: %s" % out["kind"].replace("_", " "), detail, t0, llm_reason=out["kind"],
                                message=G.SPAM_MESSAGE if out["kind"] == "spam" else None)
        stats.update(origin="gate", total_ms=round((time.perf_counter() - t0) * 1000, 1))
        scr["understood"].update(router="v2", answer_v2=stats)
        _log(stats)
        return scr

    # required: the rules' answers of a matched task bundle (official cases); never a list dump, never for a
    # direct question (the question decides then)
    overview = bool(E.OVERVIEW_RX.search(text or "") or MEDLIST_RX.search(text or ""))
    direct = bool(QUESTION_RX.search(text or ""))

    def dump(n):
        return not overview and bool(set(n["needs"]) & DUMP_SLOTS)
    by_ev = {c["id"]: c for c in chunks}
    req_needs = [] if direct else [(n, ids) for n, ids in ranked if n.get("required") and not dump(n)]
    req_ids = [i for _n, ids in req_needs for i in ids if by_ev[i]["kind"] in ("fact", "computed", "status")]
    store_chunks = O.chunks(st)
    by_all = dict(store_chunks, **by_ev)
    kind = "answer"
    blocks = None
    if out is not None:  # 4. render the model's answer + the required answers it left out + not documented topics
        placed = {f for i in out["facts"] for f in store_chunks[i]["facts"]}
        missing = [i for i in req_ids
                   if not (by_ev[i]["kind"] == "fact" and set(by_ev[i]["facts"]) & placed)]
        so_far = " ".join(b["text"] for b in out["blocks"]) + " " + " ".join(by_ev[i]["text"] for i in missing)
        missing = [i for i in missing if not (by_ev[i]["kind"] == "computed" and by_ev[i]["fields"].get("side")
                                              and re.search(r"\b%s\b" % re.escape(by_ev[i]["fields"]["side"]),
                                                            so_far.replace(by_ev[i]["text"], ""), re.I))]
        extra = _clauses([(by_ev[i]["fields"]["text"], [i]) for i in missing])
        stats["required_appended"] = len(missing)
        if out["not_documented"]:
            nd = "not documented in the letters: " + ", ".join(out["not_documented"])
            extra.append({"text": ("; " if extra else "") + nd, "chunks": []})
        if out["blocks"] or extra:
            blocks = _join(out["blocks"], extra)
            stats["origin"] = "llm" if out["blocks"] or out["not_documented"] else "template"
            if not out["blocks"] and not missing:
                kind = "nothing"
    if blocks is None:  # 5. fallback: never a list dump, never an invented absence
        stats["why"] = stats["skipped"].get("call") or (stats["rejected"][0]["reasons"][0] if stats["rejected"]
                                                        else ("model found nothing" if out else None))
        na = next((c for c in chunks if c["kind"] == "not_applicable"), None)
        if req_needs:
            blocks = W.compact(st, k, [(dict(n, required=True), ids) for n, ids in req_needs], by_ev)
        else:
            named = [(dict(n, required=False), ids) for n, ids in ranked if not dump(n)
                     and (set(n["needs"]) != {"allergies"} or re.search(r"(?i)allerg", text or ""))]
            if named:
                blocks = W.compact(st, k, named[:1] if direct else named[:2], by_ev)
        if not blocks and na:  # the sex/age mismatch is the answer: its one line, cited
            blocks = [{"text": note["text"], "chunks": [na["id"]]}]
            kind = "not_applicable"
        elif not blocks:
            topic = request_topic(text, st) if not ranked else None
            txt = (ND_PREFIX + topic + ".") if topic else NOTHING_TEXT
            blocks = [{"text": txt, "chunks": []}]
            kind = "nothing"
    ans_text = "".join(b["text"] for b in blocks).strip()
    srcs = W.sources(blocks, by_all)
    num = {s["chunk"]: i + 1 for i, s in enumerate(srcs)}
    cited_facts = {f for s in srcs for f in s["facts"]}
    flags = [c.get("title_en") for c in screen.get("contradictions") or []
             if c.get("title_en") and any(cl.get("fact_id") in cited_facts for cl in c.get("claims") or [])]
    screen["answer"] = {
        "kind": kind,
        "text": ans_text,
        "segments": [{"text": b["text"], "sources": [num[c] for c in dict.fromkeys(b["chunks"]) if c in num]}
                     for b in blocks],
        "sources": [dict(s, n=num[s["chunk"]]) for s in srcs],
        "origin": stats["origin"],
        "verified": True,
        "note": (note or {}).get("text"),
        "note_passages": (note or {}).get("passages") or [],
        "flags": list(dict.fromkeys(flags))[:3],
    }
    screen["evidence"] = chunks
    stats["chunks"] = len(chunks)
    stats["needs"] = [n["needs"] for n, _ids in ranked]
    stats["required"] = len(req_ids)
    stats["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    stats["ms"] = {"total": stats["total_ms"], "llm": stats["llm_ms"]}
    u["answer_v2"] = stats
    screen["timing_ms"] = stats["total_ms"]
    _log(stats)
    return screen

"""The v2/v3 router (docs/DECISIONS.md 23, 24), on with SECOND_LOOK_ROUTER=v2; the old path stays the fallback.

v3 (DECISIONS 24): ONE cached model call, one sentence, every value from the letters.
  1 GATE      rules, 0 ms: empty, greeting-only, injection-only -> 0 facts; another patient -> refused
  2 CALL      engine/onecall.py starts at once (v3.2: in parallel with the rules, which took ~1.5 s on the Render CPU
              before the call in v3.1): ONE structured Haiku call over the whole (cached) fact store, the drug-safety
              map's facts (engine/drug_safety.py, kidney / metformin / diabetes for a nephrotoxic or renally cleared
              drug) as "Must include" ids; kind, fact_ids, not-documented topics, a placeholder sentence.  AI kind
              greeting_or_empty / spam -> 0 facts.  A sentence that fails the checks keeps the model's fact ids only
              (code writes the sentence)
  3 RULES     meanwhile engine/screen.build_screen_kb (gates skipped) fills the cards for 'Show more';
              engine/evidence.py gives the rules' answers: a matched task bundle's P1 answers are REQUIRED (never a
              list dump, never for a direct question)
  4 RENDER    code substitutes every value (engine/cited.render); loose picks dropped, one concept once, a minority
              side replaced by the majority side; a list of facts is rewritten as one natural sentence
              (engine/cited.natural); required answers the model left out are appended (a second sentence); every
              cited fact of a counted contradiction shows its flag; valid 'not documented' topics ->
              "Not documented in the letters: X"
  5 FALLBACK  timeout (call 3.5 s, whole request 4 s), error, failed check -> the required answers' compact template,
              else the drug-safety facts, else the top rules answer the question names (a role without a matched
              bundle: only what the request names), else "Not documented in the letters: <topic>"; never the
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
    print("V3: origin=%s llm_ms=%s rules_ms=%s cache_read_input_tokens=%s cache_creation_input_tokens=%s "
          "total_ms=%s%s%s" % (
        stats.get("origin"), stats.get("llm_ms"), stats.get("rules_ms"), stats.get("cache_read_input_tokens"),
        stats.get("cache_creation_input_tokens"), stats.get("total_ms"),
        (" why=%s" % stats["why"]) if stats.get("why") else "",
        (" salvaged=%s" % stats["salvaged"]) if stats.get("salvaged") else ""), flush=True)


def request_topic(text, st):
    """The asked topic in the requester's own words (role words removed) for "Not documented in the letters: X";
    None when nothing is left or the letters' facts use one of its words (then absence is not claimed)."""
    from . import intent as I
    from . import onecall as O
    from .kb import kb
    k = kb()
    aliases = [a for r in k.roles for a in (r.get("aliases_en") or []) + (r.get("aliases_de") or [])]
    t = I.role_free(text, aliases)
    parts = [p for p in re.split(r"[,;:]|\.(?:\s|$)", t) if p.strip()]
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


def _concept(st, by_all, cid):
    """A chunk (store fact or evidence line) -> its concept key (engine/cited.concept)."""
    from . import cited as W
    c = by_all.get(cid) or {}
    f = next((st.fact_by_id[x] for x in c.get("facts") or [] if x in st.fact_by_id), None)
    if f is not None and c.get("kind", "fact") == "fact":
        return W.concept(f)
    return W.text_concept((c.get("fields") or {}).get("text") or c.get("text"))


def _off_topic(st, f, text, must_concepts):
    """A loosely related pick the request does not ask for (v3.1, live: gentamicin -> contrast allergy, Vorsorge ->
    family history): an allergy unless the request names allergies or that allergen, or a required fact asks for it;
    a family / social / general-condition note unless the request names it."""
    from . import cited as W
    from .understand import fold
    t = fold(str(text or "")).lower()
    if W.concept(f) in must_concepts:
        return False
    cat = f.get("category")
    if cat == "allergy":
        if re.search(r"allerg", t):
            return False
        w = (re.findall(r"[a-z]+", fold(str(f.get("label_en") or "")).lower()) or [""])[0][:5]
        return not (len(w) >= 4 and (w in t or ("k" + w[1:]) in t))
    if cat in OFF_TOPIC_CATS:
        return not re.search(OFF_TOPIC_CATS[cat], t)
    return False


OFF_TOPIC_CATS = {"family_history": r"famil|hereditar|erblich|genetic",
                  "social_support": r"social|sozial|famil|support|home|carer|pflege",
                  "general_condition": r"general condition|allgemeinzustand|\baz\b"}


def _model_facts(st, out, store_chunks, stats, text="", must=()):
    """The model's placed facts -> (facts, changed): a minority side of a counted laterality contradiction is
    replaced by the majority side's newest fact (or dropped when that is placed already), the same concept is kept
    once; changed when code has to write the sentence (also when the model wrote a list of facts)."""
    from . import cited as W
    from . import onecall as O
    changed = bool(out.get("list_form"))
    facts = []
    must_c = {W.concept(st.fact_by_id[store_chunks[m]["facts"][0]]) for m in must or () if m in store_chunks}
    for i in out["facts"]:
        if _off_topic(st, st.fact_by_id[store_chunks[i]["facts"][0]], text, must_c):
            stats["off_topic"] = stats.get("off_topic", 0) + 1
            changed = True
            continue
        sid = store_chunks[i]["facts"][0]
        maj = W.minority(st, sid)
        if maj:
            rep = next((O.fid(st.fact_by_id[m]) for m in maj if O.fid(st.fact_by_id[m]) in store_chunks), None)
            stats["minority_replaced"] += 1
            changed = True
            if rep is None:
                continue
            i = rep
        facts.append(i)
    kept, seen = [], set()
    for i in facts:
        cpt = W.concept(st.fact_by_id[store_chunks[i]["facts"][0]])
        if cpt in seen:
            stats["deduped"] += 1
            changed = True
            continue
        seen.add(cpt)
        kept.append(i)
    return kept, changed


def _item(st, c, cid, with_date=None):
    """A store chunk -> a sentence item {"text", "chunks", "group"}; every word is the fact's own field."""
    from . import cited as W
    f = st.fact_by_id[c["facts"][0]]
    g = W.group_of(f)
    fl = c["fields"]
    if g == "takes":
        txt = " ".join(x for x in (fl.get("name"), fl.get("dose"), fl.get("schedule")) if x)
    else:
        txt = fl.get("text") or c["text"]
        if (g == "doc" if with_date is None else with_date) and fl.get("date") and fl["date"] not in txt:
            txt += " (%s)" % fl["date"]
    return {"text": txt, "chunks": [cid], "group": g}


def _extras(st, req_ids, drug_ids, by_ev, store_chunks, by_all, seen, placed, so_far):
    """The required answers (a matched bundle's P1, the drug-safety map) the model left out, each concept once."""
    from . import cited as W
    items = []
    for i in req_ids:
        c = by_ev[i]
        if c["kind"] == "fact" and set(c["facts"]) & placed:
            continue
        if c["kind"] == "computed" and c["fields"].get("side") and re.search(
                r"\b%s\b" % re.escape(c["fields"]["side"]), so_far, re.I):
            continue
        cpt = _concept(st, by_all, i)
        if cpt in seen:
            continue
        seen.add(cpt)
        f = next((st.fact_by_id[x] for x in c["facts"] if x in st.fact_by_id), None)
        group = W.group_of(f) if (f is not None and c["kind"] == "fact") else "raw"
        items.append({"text": c["fields"]["text"], "chunks": [i], "group": group})
        so_far += " " + c["fields"]["text"]
    for i in drug_ids:
        if set(store_chunks[i]["facts"]) & placed:
            continue
        cpt = _concept(st, by_all, i)
        if cpt in seen:
            continue
        seen.add(cpt)
        items.append(_item(st, store_chunks[i], i))
    return items


def _fit(items, extras, max_chars=None):
    """Model items + required extras -> one natural sentence; without required extras, model items beyond the
    sentence limit go to 'Show more' (dropped from the end, never the first)."""
    from . import cited as W
    from . import onecall as O
    limit = max_chars or O.SENTENCE_CHARS
    items = list(items)
    while True:
        blocks = W.natural(items + extras)
        if extras or len(items) <= 1 or len("".join(b["text"] for b in blocks)) < limit - 40:
            break
        items.pop()
    if blocks:
        blocks[-1]["text"] = blocks[-1]["text"].rstrip().rstrip(".") + "."
    return blocks


def _nd(blocks, topics):
    """+ 'Not documented in the letters: X' (a new sentence after a one-sentence answer, else '; ...')."""
    from . import answers as A
    from . import cited as W
    if not topics:
        return blocks
    blocks = [dict(b) for b in blocks]
    nd = "not documented in the letters: " + ", ".join(topics)
    if not blocks:
        return [{"text": A._cap(nd) + ".", "chunks": []}]
    text = "".join(b["text"] for b in blocks).strip()
    for b in reversed(blocks):
        if b["text"].strip():
            b["text"] = b["text"].rstrip().rstrip(".")
            break
    if len(W.sentences(text)) < 2:
        blocks.append({"text": ". " + A._cap(nd) + ".", "chunks": []})
    else:
        blocks.append({"text": "; " + nd + ".", "chunks": []})
    return blocks


def build_screen_v2(text, as_of=None, use_llm=True, detail="short"):
    from . import cited as W
    from . import drug_safety as DS
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
    # 2. the one call starts NOW (v3.2): the rules ran first in v3.1 and on the Render CPU took ~1.5 s before the
    #    call even started (live: total_ms - llm_ms ~ 1.5-2 s, timeouts at the 4 s deadline with llm_ms ~ 1.3 s).
    #    Only the drug-safety map (< 1 ms) goes along as "Must include" ids; a matched bundle's required facts are
    #    known after the rules and appended by code when the model leaves them out (step 4)
    drug = DS.match(text, st)  # drug-safety map (TODO-cite): kidney function / metformin / diabetes
    store_chunks = O.chunks(st)
    must = [m for m in dict.fromkeys(drug["facts"]) if m in store_chunks]
    pending = O.start(text, st, t0, use_llm=use_llm, must=must)
    t_rules = time.perf_counter()
    # 3. the rules, while the model works: cards for 'Show more', a matched task bundle's answers
    screen = build_screen_kb(text, as_of=as_of, use_llm=False, detail=detail,
                             v2={"slots": [], "task_label": "", "applicability_item": None})
    u = screen["understood"]
    u["router"] = "v2"
    if screen.get("screen_mode") in ("not_authorised", "needs_task"):
        return screen
    question = req.get("task") or text
    chunks, ranked, note = E.build(st, k, screen, question, [])
    # required: the rules' answers of a matched task bundle (official cases); never a list dump, never for a
    # direct question (the question decides then)
    overview = bool(E.OVERVIEW_RX.search(text or "") or MEDLIST_RX.search(text or ""))
    direct = bool(QUESTION_RX.search(text or ""))

    def dump(n):
        return not overview and bool(set(n["needs"]) & DUMP_SLOTS)
    by_ev = {c["id"]: c for c in chunks}
    req_needs = [] if direct else [(n, ids) for n, ids in ranked if n.get("required") and not dump(n)]
    req_ids = [i for _n, ids in req_needs for i in ids if by_ev[i]["kind"] in ("fact", "computed", "status")]
    by_all = dict(store_chunks, **by_ev)
    required = [O.fid(st.fact_by_id[by_ev[i]["facts"][0]]) for i in req_ids  # a matched bundle's P1 store facts
                if by_ev[i]["kind"] == "fact" and by_ev[i]["facts"] and by_ev[i]["facts"][0] in st.fact_by_id]
    required = [m for m in dict.fromkeys(must + required) if m in store_chunks]
    rules_ms = round((time.perf_counter() - t_rules) * 1000, 1)
    # 4. merge: the call's answer (it ran in parallel with the rules)
    out, info = (pending.result(st, max_chars=W.MAX_CHARS if (must or req_ids) else None) if pending
                 else (None, {"skipped": "disabled" if not use_llm else "no key"}))
    stats = {"origin": "template", "called": bool(info.get("called")), "cached": bool(info.get("cached")),
             "llm_ms": info.get("llm_ms"), "rejected": [], "skipped": {},
             "cache_read_input_tokens": info.get("cache_read_input_tokens", 0),
             "cache_creation_input_tokens": info.get("cache_creation_input_tokens", 0),
             "input_tokens": info.get("input_tokens", 0), "output_tokens": info.get("output_tokens", 0),
             "cost_eur": round(info.get("cost_eur") or 0.0, 6), "required_appended": 0, "must": len(must),
             "drug_safety": drug["rows"], "deduped": 0, "minority_replaced": 0, "rules_ms": rules_ms,
             "salvaged": info.get("salvaged")}
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

    kind = "answer"
    blocks = None
    topics = []
    if out is not None:  # 4. render: the model's facts (one concept once, never a minority side alone), the
        #                     required facts it left out, the not-documented topics
        facts, changed = _model_facts(st, out, store_chunks, stats, text, required)
        seen = {_concept(st, by_all, i) for i in facts}
        placed = {f for i in facts for f in store_chunks[i]["facts"]}
        extras = _extras(st, req_ids, drug["facts"], by_ev, store_chunks, by_all, seen, placed,
                         " ".join(store_chunks[i]["fields"].get("text", "") for i in facts))
        stats["required_appended"] = len(extras)
        topics = list(dict.fromkeys(out["not_documented"] + [t for t in drug["topics"] if t.lower() not in
                                                              {x.lower() for x in out["not_documented"]}]))
        if facts and not changed:  # the model's own sentence (flags added below), extras as a second sentence
            blocks = _join(out["blocks"], W.natural(extras)) if extras else [dict(b) for b in out["blocks"]]
        elif facts or extras:  # a list of facts, a duplicate or a minority side: code writes the sentence
            items = [_item(st, store_chunks[i], i) for i in facts]
            blocks = _fit(items, extras)
        if blocks or topics:
            stats["origin"] = "llm" if (facts or out["not_documented"]) else "template"
            if not facts and not extras:
                kind = "nothing"
            blocks = _nd(blocks or [], topics)
    if blocks is None:  # 5. fallback: never a list dump, never an invented absence
        stats["why"] = stats["skipped"].get("call") or (stats["rejected"][0]["reasons"][0] if stats["rejected"]
                                                        else ("model found nothing" if out else None))
        na = next((c for c in chunks if c["kind"] == "not_applicable"), None)
        asked = E.relevant_slots(k, dict(u, bundles_matched=None), screen.get("cards") or [], ())
        if req_needs:
            blocks = W.compact(st, k, [(dict(n, required=True), ids) for n, ids in req_needs], by_ev)
        elif drug["facts"]:  # the drug-safety map, as a matched bundle's P1
            blocks = W.natural([_item(st, store_chunks[i], i) for i in drug["facts"]])
            blocks[-1]["text"] += "."
        else:
            named = [(dict(n, required=False), ids) for n, ids in ranked if not dump(n)
                     and (set(n["needs"]) != {"allergies"} or re.search(r"(?i)allerg", text or ""))]
            if not u.get("bundles_matched") and not direct:  # a recognised role without a task bundle: the
                # request's own topic ("Not documented in the letters: X"), never a loosely related card (v3.1:
                # 'Kardiologe, Herzinsuffizienz Verlaufskontrolle' got the 2015 follow-ups); the rules' own
                # question lines and the slots the request names stay
                named = [(n, ids) for n, ids in named
                         if n.get("shape") in ("question", "nothing") or set(n["needs"]) & set(u.get("asked_slots") or [])]
                if not named and not request_topic(text, st):
                    named = [(n, ids) for n, ids in ranked if not dump(n) and set(n["needs"]) & asked][:1]
            if named:
                blocks = W.compact(st, k, named[:1] if direct else named[:2], by_ev)
        if not blocks and na:  # the sex/age mismatch is the answer: its one line, cited
            blocks = [{"text": note["text"], "chunks": [na["id"]]}]
            kind = "not_applicable"
        elif drug["topics"]:
            blocks = _nd(blocks or [], drug["topics"])
            kind = "answer" if any(b["chunks"] for b in blocks) else "nothing"
        elif not blocks:
            topic = request_topic(text, st)
            txt = (ND_PREFIX + topic + ".") if topic else NOTHING_TEXT
            blocks = [{"text": txt, "chunks": []}]
            kind = "nothing"
    blocks, shown_flags = W.flag_blocks(st, blocks, by_all)
    ans_text = "".join(b["text"] for b in blocks).strip()
    srcs = W.sources(blocks, by_all)
    num = {s["chunk"]: i + 1 for i, s in enumerate(srcs)}
    cited_facts = {f for s in srcs for f in s["facts"]}
    flags = shown_flags + [c.get("title_en") for c in screen.get("contradictions") or []
                           if c.get("title_en") and any(cl.get("fact_id") in cited_facts
                                                        for cl in c.get("claims") or [])]
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
    stats["ms"] = {"total": stats["total_ms"], "llm": stats["llm_ms"], "rules": rules_ms}
    u["answer_v2"] = stats
    screen["timing_ms"] = stats["total_ms"]
    _log(stats)
    return screen

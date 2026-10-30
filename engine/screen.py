"""Show: situation text -> one JSON screen.

{understood, safety_strip, cards, blind_spot, contradictions, proof_bar, timing_ms}
"""
import re
import time

from . import clinical as C
from .conflicts import contradictions as find_contradictions
from .data import rulebook, rulebook_mode, store
from .fill import fill, fmt_date, group_items
from .understand import understand

_CONTRA_CACHE = {}


def _contradictions(st):
    key = id(st)
    if key not in _CONTRA_CACHE:
        _CONTRA_CACHE[key] = find_contradictions(st)
    return _CONTRA_CACHE[key]


def collect_needs(u, roles_rb, tasks_rb):
    role = next((r for r in roles_rb.get("roles", []) if r["id"] == u["role_id"]), {})
    task_by_id = {t["id"]: t for t in tasks_rb.get("tasks", [])}
    rows, seen = [], {}
    for tid in u["task_ids"]:
        for n in task_by_id.get(tid, {}).get("needs", []):
            n = dict(n, task=tid)
            if n["id"] in seen:
                prev = seen[n["id"]]
                if n.get("priority") == "must":
                    prev["priority"] = "must"
                continue
            seen[n["id"]] = n
            rows.append(n)
    for n in role.get("needs") or []:
        if n["id"] not in seen:
            seen[n["id"]] = dict(n, task="role")
            rows.append(seen[n["id"]])
    return [n for n in rows if n.get("priority") == "must"] + [n for n in rows if n.get("priority") != "must"]


_PROBLEM_STRIP = re.compile(r"^(history of|known|suspected|question:)\s+", re.I)


def _problem_key(label):
    t = _PROBLEM_STRIP.sub("", (label or "").lower()).strip()
    words = re.findall(r"[a-z0-9-]+", t)
    return " ".join(words[:2])


def blind_spot(st):
    """Problems on earlier diagnosis lists that the latest letter's diagnosis list no longer mentions."""
    lists = {}
    for f in st.facts:
        a = f.get("attrs") or {}
        if f.get("ips_section") not in ("problems", "past_illness"):
            continue
        if a.get("context") != "diagnosis list" and a.get("source") != "diagnosis":
            continue
        for d in st.fact_docs(f):
            lists.setdefault(d, []).append(f)
    if not lists:
        return None
    latest = max(lists, key=lambda d: (st.doc_date(d) or "", d))
    latest_keys = {_problem_key(f.get("label_en")) for f in lists[latest]}
    dropped = {}
    for d, fs in lists.items():
        if d == latest:
            continue
        for f in fs:
            k = _problem_key(f.get("label_en"))
            if k and k not in latest_keys:
                dropped.setdefault(k, []).append(f)
    items = []
    for k, fs in dropped.items():
        it = group_items(st, fs)
        it.sort(key=lambda x: str(x["date"] or ""), reverse=True)
        top = it[0]
        items.append({"label_en": top["label_en"], "last_documented": top["date"],
                      "facts": [x for i in it for x in i["facts"]],
                      "passages": [x for i in it for x in i["passages"]],
                      "docs": sorted({x for i in it for x in i["docs"]})})
    items.sort(key=lambda x: x["label_en"])
    total = len(latest_keys | set(dropped))
    return {"latest_document": latest, "latest_document_date": st.doc_date(latest),
            "missed_if_only_latest": len(items), "of_total_problems": total,
            "summary_en": "If you only read the latest letter (%s), you would miss %d of %d documented problems."
                          % (fmt_date(st.doc_date(latest)), len(items), total),
            "items": items}


def compare_blind_spot(st):
    """Blind spots computed by compare/ (preferred when data/build/compare.json exists)."""
    c = st.compare if isinstance(st.compare, dict) else None
    if not c or not c.get("blind_spots"):
        return None
    n = c.get("counts") or {}
    items = [{"label_en": b.get("label_en"), "kind": b.get("kind"), "last_documented": b.get("last_seen_date"),
              "facts": b.get("fact_ids") or [], "passages": b.get("passage_ids") or [],
              "docs": sorted({x.split(":")[0] for x in b.get("passage_ids") or []})}
             for b in c["blind_spots"]]
    missed = n.get("missed_if_only_latest_read", len(items))
    total = n.get("important_concepts")
    return {"latest_document": n.get("latest_doc"), "latest_document_date": n.get("latest_date"),
            "missed_if_only_latest": missed, "of_total_problems": total,
            "summary_en": "If you only read the latest letter (%s), you would miss %s of %s important facts."
                          % (fmt_date(n.get("latest_date")), missed, total),
            "items": items, "origin": "compare.json"}


def _annotate_followups(st, cards):
    c = st.compare if isinstance(st.compare, dict) else None
    if not c:
        return
    res = [(set(fu.get("fact_ids") or []), fu) for fu in c.get("open_followups") or []]
    for card in cards:
        for it in card.get("items") or []:
            for ids, fu in res:
                if ids & set(it["facts"]):
                    it["followup_resolution"] = fu.get("resolution")
                    it["followup_open"] = fu.get("is_open")


def build_screen(text, as_of=None, use_llm=True, detail="short", rulebook=None):
    """detail: 'short' (P1 only, the default) or 'long' (P1-P3); KB rulebook only.  rulebook: 'kb' | 'legacy' | None (env)."""
    if rulebook_mode(rulebook) == "kb":
        return build_screen_kb(text, as_of=as_of, use_llm=use_llm, detail=detail)
    return build_screen_legacy(text, as_of=as_of, use_llm=use_llm)


def _proof_and_contradictions(st, cards, contras):
    shown = []
    for c in cards:
        for x in c["facts"]:
            if x not in shown:
                shown.append(x)
    shown_set = set(shown)
    contra_out = [dict(c, relevant=bool(set(c["facts"]) & shown_set)) for c in contras]
    contra_out.sort(key=lambda c: not c["relevant"])
    verified = [x for x in shown if st.fact_by_id.get(x, {}).get("verified") is not False]
    proof = {"facts_shown": len(shown), "facts_verified": len(verified), "facts_removed_at_load": len(st.removed),
             "summary_en": "%d facts shown - %d checked word for word against the letters - %d removed"
                           % (len(shown), len(verified), len(st.removed))}
    return contra_out, proof


SAFETY_CORE = ("age_sex", "allergies")  # decision 7: on every clinical screen, short view too
MAX_ALSO_RELEVANT = 6  # P2 cards in the short view's 'also relevant' group (the rest: long view), KB order
MAX_SHORT_TOTAL = 16   # short view never shows more cards than this (P1 + also relevant)
MAX_SUMMARY_CARDS = 6  # safety summary (unrecognised task / not applicable): never a dump
OVERVIEW_RX = re.compile(r"(?<![a-zäöüß])(overview|summary|summarise|summarize|über(blick|sicht)|zusammenfassung)")


def _suggest_bundles(k, task_text, role, n=3):
    """Nearest bundle titles for an unrecognised task: fuzzy tag similarity, the role's own bundles first."""
    import difflib
    from .kb import bundle_tags
    from .understand import norm_text
    words = [w for w in re.findall(r"[a-zäöüß]{4,}", task_text or "")]
    defaults = (role or {}).get("default_bundles") or []
    scored = []
    for b in k.bundles:
        if b["id"] == k.fallback_bundle:
            continue
        best = 0.0
        for tag in bundle_tags(b):
            if tag.startswith("("):
                continue
            for tw in norm_text(tag).split():
                for w in words:
                    best = max(best, difflib.SequenceMatcher(None, w, tw).ratio())
        bonus = 0.5 if b["id"] in defaults else 0.0
        scored.append((best + bonus, -defaults.index(b["id"]) if b["id"] in defaults else -99, -int(b["id"][1:]),
                       b["title"]))
    scored.sort(reverse=True)
    return [x[3] for x in scored[:n]]


def _ensure_info(k, info, slot, origin):
    if slot not in info:
        info[slot] = {"priority": "P1", "origins": [origin], "why": k.slot_by_id[slot].get("why"),
                      "sources": [], "rules": []}
    elif origin not in info[slot]["origins"]:
        info[slot]["origins"].append(origin)
    info[slot]["priority"] = "P1"


def _slot_domain(st, k, cards, as_of, text):
    """Every fact a shown card's slot covers (selected facts, incl. context) plus the facts on the cards."""
    from .slots import select_slot
    dom = set()
    for c in cards:
        dom |= set(c.get("facts") or [])
        if c.get("slot") in k.slot_by_id and c.get("status") != "not_documented":
            p, ctxf = select_slot(st, k, c["slot"], as_of, text)
            dom |= {f["id"] for f in p} | {f["id"] for f in ctxf}
    return dom


def _task_blind_spot(bs, domain):
    """Blind-spot items that touch the screen's slots; None when nothing on the screen is affected."""
    if not bs:
        return None, []
    keep = [i for i in bs["items"] if set(i.get("facts") or []) & domain]
    other = [i for i in bs["items"] if i not in keep]
    if not keep:
        return None, other
    out = dict(bs, items=keep, missed_if_only_latest=len(keep),
               patient_wide_missed=bs.get("missed_if_only_latest"), scope="task")
    out["summary_en"] = ("%d item(s) on this screen are not in the latest letter (%s); reading only that letter "
                         "you would miss them." % (len(keep), fmt_date(bs.get("latest_document_date"))))
    return out, other


def build_screen_kb(text, as_of=None, use_llm=True, detail="short"):
    from . import applicability as A
    from .fill import _dob, _d, age_years
    from .kb import kb as load_kb
    from .kbfill import build_card, compact_also, label_panel, slot_status_fn
    from .route import route
    t0 = time.perf_counter()
    st = store()
    k = load_kb()
    detail = "long" if str(detail).lower() == "long" else "short"
    anchor = st.anchor_date()
    m = re.search(r"\bas of (\d{4}-\d{2}-\d{2})\b", text or "")
    as_of = as_of or (m.group(1) if m else anchor)
    # request semantics (engine/request.py): instructions inside the text are blanked before anything reads
    # it (they can never add content, pick a role or authorise); excluded topics are blanked from the task
    from . import request as R
    pending = None
    if use_llm:  # the LLM reading runs in parallel with the rules (request analysis + routing), never longer
        from . import llm as L                        # than its deadline (engine/llm.py timeout_s)
        from .focus import concepts as record_concepts
        pending = L.start(text, k, record_concepts(st)[0])
    req = R.analyse(text, st)
    if req["other_patient"] and C.classify(req["clean"])["decision"] != "not_clinical":
        return other_patient_screen(text, req, detail, t0)  # (a non-clinical requester gets the gate's refusal)
    u = route(req["task"], k, st, as_of, detail=detail, use_llm=use_llm and pending is not None, llm_pending=pending)
    u["text"] = text
    u["as_of_date"] = as_of
    u["anchor_date"] = anchor
    u["ignored_instructions"] = req["instructions"]
    u["excluded_text"] = req["excluded_text"] or None
    sex, sex_pid = st.patient_sex()
    patient = {"sex": sex, "sex_passage": sex_pid}
    contras, csource = _contradictions(st)
    info = u.pop("slot_info")
    role = k.role_by_id.get(u["role_id"])

    # applicability (rulebook/applicability.json) and the safety summary for unrecognised tasks
    app = A.check(u.get("task_text") or "", st, full_text=req["task"], as_of=as_of)

    # clinical gate (rulebook/clinical_roles.json): patient data only for a clinical requester
    # a role read by the LLM never authorises: kb_role only for a role the rules found in the text
    rules_role = bool(role) and (u.get("role_match") or {}).get("method") != "llm"
    gate = C.classify(req["clean"], kb_alias=(u.get("role_match") or {}).get("matched") if rules_role else None,
                      kb_role=rules_role,
                      task_evidence=C.strong_task(u.get("bundles_matched"), k.fallback_bundle) or bool(app["items"]))
    if req.get("withdrawn_roles") and gate["decision"] not in ("kb_role", "clinical_term", "not_clinical"):
        # a withdrawn clinical claim ('I'm not a doctor, but ...') and no other clinical identity left: refuse,
        # even when the task itself is clinical
        gate = {"decision": "not_clinical", "clinical": False, "term": req["withdrawn_roles"][0], "label": None}
    u["clinical_gate"] = gate
    # LLM primary when it answered (engine/llm_gate.py): its verdict decides, the rules veto (deny wins)
    from . import llm_gate as G
    alias0 = (u.get("role_match") or {}).get("matched") if rules_role else None
    verdict = G.decide(u, gate, req, [alias0] if alias0 else [])
    llm_ok = False
    if verdict:
        what, why, vetoed = verdict
        u["llm_verdict"] = {"verdict": what, "reason": why, "veto": vetoed}
        if what == "refuse":
            gate = dict(gate, decision="llm_not_clinical", clinical=False)
            scr = not_authorised_screen(u, gate, detail, t0)
            scr["understood"].update(clinical_gate=gate, llm_used=True, llm_reason=why)
            return scr
        if what == "spam":
            return needs_task_screen(u, "LLM: spam or abuse", detail, t0, llm_reason=why, message=G.SPAM_MESSAGE)
        if what == "no_role":
            ask = re.sub(r"\s+", " ", req["task"]).strip(" ,;:.?!")[:80]
            u["clinical_gate"] = dict(gate, clinical=False)
            return needs_task_screen(u, "LLM: no requester role", detail, t0, llm_reason=why,
                                     message=C.NEEDS_ROLE_MESSAGE, role_missing=True,
                                     suggestions=["%s, %s" % (r_, ask) for r_ in C.ROLE_EXAMPLES])
        if what == "no_task":
            return needs_task_screen(u, "LLM: no clinical task", detail, t0, llm_reason=why)
        if what == "data":
            llm_ok = True
            gate = {"decision": "llm_clinical", "clinical": True, "term": None,
                    "label": role["name"] if role else None}
            u.update(clinical_gate=gate, llm_used=True, llm_reason=why)
    # rules path (no LLM reading, or a rules veto): no requester role stated (decision 'no_role' or
    # 'clinical_task': the task alone is clear): never data, the needs_task screen asks who is asking and for
    # the task (DECISIONS 19); a greeting alone asks for the task
    if not llm_ok and gate["decision"] in ("no_role", "clinical_task"):
        from . import intent as I
        words = re.findall(r"[^\W\d_][\w'-]*", req["clean"])
        if words and all(w in I.lexicon()["never"] for w in words):
            return needs_task_screen(u, "greeting / filler only", detail, t0)  # 'hello', 'ok': still 0 facts
        if gate["decision"] == "clinical_task" or I.has_task(req["task"], k)["actionable"]:
            ask = re.sub(r"\s+", " ", req["task"]).strip(" ,;:.?!")[:80]
            u["clinical_gate"] = dict(gate, clinical=False)
            return needs_task_screen(u, "no requester role stated", detail, t0, message=C.NEEDS_ROLE_MESSAGE,
                                     suggestions=["%s, %s" % (r_, ask) for r_ in C.ROLE_EXAMPLES], role_missing=True)
    if not gate["clinical"]:
        return not_authorised_screen(u, gate, detail, t0)
    # no task, no data (engine/intent.py, docs/DECISIONS.md 19): a greeting, filler or a role alone never opens
    # the record (rules path; the LLM path decided above, a greeting-only request is vetoed there)
    from . import focus as F
    from . import intent as I
    alias = (u.get("role_match") or {}).get("matched") if rules_role else None
    named_pre = F.match_topics(u.get("task_text") or "", getattr(k, "overlay", None) or {})
    intent = I.has_task(req["task"], k, st, aliases=[alias] if alias else [], named_topics=named_pre,
                        applicability_items=app["items"])
    if not intent["actionable"]:  # a question about a known subject is a task ('does she hav a pacemakr?', engine/ask.py)
        from . import ask as Q
        known = [s for s in Q.subjects(u.get("task_text")) if Q.slot_for(s, k) or Q.search_words(s)[1]]
        if Q.is_question(u.get("task_text") or "") and known:
            intent = dict(intent, actionable=True, reason="question about a known subject", words=known)
    u["task_check"] = {"actionable": intent["actionable"], "reason": intent["reason"], "words": intent["words"][:8]}
    if not intent["actionable"] and not llm_ok:  # with the LLM's clinical_task verdict, its reading of the task holds
        return needs_task_screen(u, intent["reason"], detail, t0)
    # recognised role (or a clinical requester the lexicon knows), task wording not recognised: the role's own
    # typical task (rulebook/kb_overlay.json role_fallback_bundles, else its first default bundle) with a
    # visible note, instead of the generic safety summary
    fbmap = (getattr(k, "overlay", None) or {}).get("role_fallback_bundles") or {}
    if role:
        cand = fbmap.get(role["id"]) or (role.get("default_bundles") or [])[:1]
    elif gate["decision"] == "clinical_term":
        cand = fbmap.get("physician") or []
    else:
        cand = []
    defaults = [b for b in cand if b in k.bundle_by_id]
    # the request names its own topics ('Endocrinologist, thyroid'): the core summary plus those topics, not the
    # role's typical task (which may be about something else, e.g. diabetes)
    # ... unless every named topic is part of the role's own task ('oncologist: receptor status' stays oncology)
    own = {x for b in defaults for p_ in ("P1", "P2") for x in (k.bundle_by_id[b].get("slots") or {}).get(p_) or []}
    in_own = all(tp.get("slots") and set(tp["slots"]) <= own for tp in named_pre)
    if named_pre and defaults and k.fallback_bundle in k.bundle_by_id and not in_own:
        defaults = [k.fallback_bundle]
    if (u["tasks_from"] == "fallback" and defaults and not app["items"]
            and not OVERVIEW_RX.search(u.get("task_text") or "")):
        llm_focus, tcheck = u.get("llm_focus_proposal"), u.get("task_check")
        u = route(req["task"], k, st, as_of, detail=detail, use_llm=False, force_bundles=defaults,
                  force_role=role["id"] if role else None)
        u.update(text=text, as_of_date=as_of, anchor_date=anchor, clinical_gate=gate, llm_focus_proposal=llm_focus,
                 task_check=tcheck,
                 ignored_instructions=req["instructions"], excluded_text=req["excluded_text"] or None)
        info = u.pop("slot_info")
        u["suggestions"] = _suggest_bundles(k, u.get("task_text"), role)
        titles = ", ".join(k.bundle_by_id[b]["title"] for b in defaults)
        what = ("what a %s usually needs (%s)" % (role["name"], titles) if role else
                "the general core summary for %s (%s)" % (gate.get("label") or "this role", titles))
        u["fallback_note"] = "Task wording not recognised: showing %s. For a specific task try e.g. %s." % (
            what, ", ".join("'%s'" % x for x in u["suggestions"]))
    if not role and gate["decision"] == "clinical_term":
        u["role_label"] = gate["label"]
        u["role_match"] = {"method": "clinical_lexicon", "matched": gate["term"]}
    safety = [x for x in A.table().get("safety_block") or [] if x in k.slot_by_id]
    fallback = u["tasks_from"] == "fallback"
    front, back, mode = [], [], "task"
    slots = list(u["slots_shown"])
    if app["not_applicable"]:
        front = [A.not_applicable_card(st, r, app["sex"], app["passage"], app["word"], app["age"],
                                       app["age_passage"], app["dob"]) for r in app["not_applicable"]]
        u["applicability_note"] = "%s: not applicable, the record documents %s." % (
            "; ".join(r["label"] for r in app["not_applicable"]),
            "; ".join(("a patient aged %s" % app["age"]) if r.get("reason") == "age" else
                      ("%s patient" % A.SEX_WORD.get(app["sex"], app["sex"])) for r in app["not_applicable"]))
        # the whole request does not apply: the task is not recognised otherwise, the item is about who asks
        # (paediatrics, obstetrics ...), or the asking specialty exists for this item (urologist + prostate)
        whole = fallback or any(r.get("scope") == "request" or u.get("role_id") in r.get("roles")
                                for r in app["not_applicable"])
        if whole:
            mode, slots = "not_applicable", list(safety)
            u["fallback_note"] = None
            u["task_labels"] = ["Not applicable: %s" % r["label"] for r in app["not_applicable"]]
    elif fallback and app["applicable"]:
        mode = "sex_specific"
        slots = list(dict.fromkeys(safety + [x for r in app["applicable"] for x in r["slots"] if x in k.slot_by_id]))
        u["fallback_note"] = None
        u["task_labels"] = [r["label"] for r in app["applicable"]]
    elif fallback and OVERVIEW_RX.search(u.get("task_text") or ""):
        mode = "overview"  # an explicit request for a summary: the general core summary, deduplicated
        b = k.bundle_by_id[k.fallback_bundle]
        prs = ("P1",) if detail == "short" else ("P1", "P2", "P3")
        slots = list(dict.fromkeys([x for p_ in prs for x in (b.get("slots") or {}).get(p_) or []] + safety))
        u["fallback_note"] = "No specific task named: showing the general summary."
    elif fallback:
        mode = "fallback"
        mods = [m_["slot"] for m_ in (role or {}).get("modifiers") or [] if m_.get("priority") == "P1"]
        slots = list(dict.fromkeys(safety + mods))[:MAX_SUMMARY_CARDS]
        u["suggestions"] = _suggest_bundles(k, u.get("task_text"), role)
        who = "" if role else (" for %s" % gate["label"]) if gate.get("label") else " (role not recognised either)"
        u["fallback_note"] = ("Task not recognised%s: showing a safety summary. Try e.g. %s." % (
            who, ", ".join("'%s'" % x for x in u["suggestions"])))
        u["task_labels"] = ["Safety summary (task not recognised)"]
    if mode != "task" or app["applicable"]:
        if mode != "task":
            for x in slots:
                _ensure_info(k, info, x, "safety summary" if x in safety else "applicability")
        if app["sex"] is None and app["items"]:
            u["applicability_note"] = "The record does not state the patient's sex; check applicability yourself."
        back = [A.record_check_card(st, r, chk, as_of, contras) for r in app["applicable"] for chk in r["record_checks"]]
    if mode == "task":  # safety core on every clinical screen: age/sex and allergies first
        slots = list(dict.fromkeys([x for x in SAFETY_CORE if x in k.slot_by_id] + slots))
        for x in SAFETY_CORE:
            if x in k.slot_by_id:
                _ensure_info(k, info, x, "safety core")
    # named topics (engine/focus.py, rulebook/kb_overlay.json 'topics'): the request's own topics as P1 cards;
    # excluded topics ('not interested in X') are removed, never the safety core
    from . import focus as F
    from .understand import norm_text
    tsettings = (getattr(k, "overlay", None) or {}).get("topics_settings") or {}
    excluded = F.match_topics(norm_text(req["excluded_text"]), getattr(k, "overlay", None) or {})
    ex_ids = {tp["id"] for tp in excluded}
    named = [tp for tp in F.match_topics(u.get("task_text") or "", getattr(k, "overlay", None) or {})
             if tp["id"] not in ex_ids]
    if excluded:
        ex_slots = {x for tp in excluded for x in tp.get("slots") or []}
        slots = [x for x in slots if x in SAFETY_CORE or x not in ex_slots]
    # specific questions (engine/ask.py, routing guide layer 3): subjects no topic or bundle tag covers get an
    # answer card; a question that names no task gets only the safety core and its answers, not the role's
    # whole default view
    from . import ask as Q
    from .understand import fold
    asked =mode in ("task", "fallback", "not_applicable") and Q.is_question(u.get("task_text") or "")
    tags = [t for v in (u.get("bundles_matched") or {}).values() for t in v.get("tags") or []]
    ex_text = fold(norm_text(req["excluded_text"] or ""))
    ask_subs = [s for s in Q.subjects(u.get("task_text")) if not Q.covered(s, k, (), tags)
                and not (ex_text and fold(s) in ex_text)  # 'not interested in X' wins
                and not any(r.get("term") and fold(norm_text(r["term"]))[:6] in fold(s)  # applicability answers it
                            for r in app["items"])] if asked else []
    if ask_subs and _asks_judgement(u.get("task_text") or ""):  # 'Sportfreigabe ja oder nein?': the role's view
        ask_subs = [s for s in ask_subs if Q.slot_for(s, k)]      # answers it, not a word search
    if tags:  # a matched task already answers its own words; an unknown word beside it is likely a typo of one
        ask_subs = [s for s in ask_subs if Q.slot_for(s, k) or Q.search_words(s)[1]]
    ask_slots = [x for x in dict.fromkeys(Q.slot_for(s, k) for s in ask_subs) if x]  # a KB slot answers these
    ask_subs = [s for s in ask_subs if not Q.slot_for(s, k)]
    unanswered = ask_subs[Q.MAX_SUBJECTS:]
    ask_subs = ask_subs[:Q.MAX_SUBJECTS]
    # only when the rules and the LLM chose no task (the role's default or the general fallback stood in), and the
    # question asks for a fact, not a judgement the role's own view answers ('Sportfreigabe ja oder nein?')
    question_only = bool(asked and mode != "not_applicable" and (named or ask_subs or ask_slots)
                         and not u.get("bundles_matched") and u.get("tasks_from") in ("role_default", "fallback")
                         and not _asks_judgement(u.get("task_text") or ""))
    if question_only:
        mode = "task"
        slots = [x for x in SAFETY_CORE if x in k.slot_by_id]
        for x in slots:
            _ensure_info(k, info, x, "safety core")
        asked_about = [tp["label"] for tp in named] + [k.slot_by_id[x]["label"] for x in ask_slots] + ask_subs
        u["task_labels"] = ["Your question: %s" % ", ".join(asked_about)]
        u["fallback_note"] = ("Answering your question only (%s). For the full view, name the task as well, e.g. %s."
                              % (", ".join(asked_about), ", ".join("'%s'" % x for x in
                                                                    _suggest_bundles(k, u.get("task_text"), role))))
    for x in ask_slots:
        if x not in slots:
            slots.append(x)
            _ensure_info(k, info, x, "your question")
    u["question_only"] = question_only
    u["asked_subjects"] = ask_subs
    u["unanswered_subjects"] = unanswered
    # role-typical topics (rulebook/kb_overlay.json role_topics, from the role's own mindset / often_missing text):
    # only when the role's view comes from a bundle that is not its own (an overlay role borrows a KB bundle; a KB
    # role whose task wording was not recognised gets its default), never on a question-only screen
    role_tps = []
    rtopics = ((getattr(k, "overlay", None) or {}).get("role_topics") or {}).get(u.get("role_id")) or []
    borrowed = bool(role) and (role.get("origin") == "overlay"
                               or not set(u.get("bundle_ids") or []) & set(role.get("default_bundles") or []))
    if mode == "task" and not question_only and borrowed and rtopics:
        by_id = {tp["id"]: tp for tp in F.topic_list(getattr(k, "overlay", None) or {})}
        have = {tp["id"] for tp in named} | ex_ids
        role_tps = [dict(by_id[x], _why="A %s usually needs this." % role["name"].lower())
                    for x in rtopics if x in by_id and x not in have]
    u["role_topics"] = [tp["id"] for tp in role_tps]
    if mode != "not_applicable" or asked:  # a not-applicable item never hides the other things asked about
        named_slots = F.topic_slots(k, named, excluded)
        for x in F.topic_slots(k, named + role_tps, excluded)[:tsettings.get("max_topic_slots", 5)]:
            if x not in slots:
                slots.append(x)
                _ensure_info(k, info, x, "named topic" if x in named_slots else "role topic")
    if named and u.get("tasks_from") == "role_default" and not question_only:
        u["fallback_note"] = "Showing the topics you named (%s) and what %s usually needs (%s)." % (
            ", ".join(tp["label"] for tp in named), ("a %s" % role["name"]) if role else "a clinician",
            ", ".join(k.bundle_by_id[b]["title"] for b in u["bundle_ids"]))
    u["named_topics"] = [tp["id"] for tp in named]
    u["excluded_topics"] = [tp["id"] for tp in excluded]
    u["slots_shown"] = slots
    u["screen_mode"] = mode
    u["applicability"] = {k_: app[k_] for k_ in ("sex", "passage", "word")}
    u["applicability"]["items"] = [{x: r[x] for x in ("id", "label", "applicable_sex", "term")} for r in app["items"]]

    ctx = {"as_of": as_of, "anchor": as_of, "patient": patient, "text": req["task"], "slot_info": info,
           "bundles": u["bundle_ids"], "detail": detail}
    cards = front + [build_card(st, k, s, ctx, contras) for s in slots] + back
    focus = []
    if mode != "not_applicable":  # task focus (engine/focus.py): after the clinical gate, never a dump
        from .focus import focus_cards
        if not question_only:
            focus, finfo = focus_cards(st, k, u.get("task_text") or "", req["task"], as_of, cards,
                                       u.get("llm_focus_proposal"))
            u.update(finfo)
            if finfo["llm_focus"]:
                u["llm_used"] = True
                u["llm_reason"] = u.get("llm_reason") or finfo["llm_focus"]["reason"]
        tcards, tinfo = F.topic_cards(st, k, named + role_tps, excluded, u.get("task_text") or "", as_of, cards + focus,
                                      tsettings)
        focus = focus + tcards
        u["topic_cards"] = tinfo
    focus = [Q.answer_card(st, s, as_of) for s in ask_subs] + focus  # also beside a not-applicable item
    also = []
    if detail == "short" and mode == "task" and not question_only:  # P2 'also relevant' group, shown without a second request
        p2_all = {x["slot"] for x in u["slots"] if x["priority"] == "P2" and x["slot"] not in slots}
        in_bundles = [x for b_ in u["bundle_ids"] for x in (k.bundle_by_id[b_].get("slots") or {}).get("P2") or []]
        p2 = [x for x in dict.fromkeys(in_bundles + [x["slot"] for x in u["slots"]]) if x in p2_all]  # KB order
        room = max(0, min(MAX_ALSO_RELEVANT, MAX_SHORT_TOTAL - len(cards) - len(focus) - 1))  # 1: disagreements
        also = [build_card(st, k, s, ctx, contras) for s in p2[:room]]
        built = p2
        for c in also:
            c["group"] = "also_relevant"
            compact_also(c)
        u["also_relevant"] = [c["slot"] for c in also]
        u["also_relevant_more"] = max(0, len(built) - len(also))
    dob = next((_dob((f.get("attrs") or {}).get("value")) for f in st.facts if f.get("category") == "date_of_birth"), None)
    age = age_years(dob, _d(as_of)) if dob and _d(as_of) else None
    status = slot_status_fn(st, k, as_of, text)
    if mode == "task":
        for c in cards:  # rule R22: label panel for every shown medication
            if c.get("shape") == "current_list" and c.get("items"):
                c["label_panel"] = label_panel(st, k, c, status, u["bundle_ids"], detail, age)
    # exclusions, then: facts of a named topic or sharing a word with the request are never behind '+N more'
    cards, focus, also = (F.apply_exclusions(x, st, excluded) for x in (cards, focus, also))
    F.open_named(cards + focus + also, st, named, u.get("task_text") or "", getattr(k, "overlay", None) or {})
    if mode != "not_applicable":  # letters that disagree about what is on this screen (or all, for a review)
        review = bool(REVIEW_RX.search(req["task"]))
        dc = disagreement_card(st, cards + focus + also, contras, excluded, review)
        if dc:
            if len(cards) + len(focus) + len(also) + 1 > MAX_SHORT_TOTAL and also:
                also = also[:-1]
            focus = focus + [dc]
        u["review_request"] = review
        counted = [c for c in contras if c.get("counted", True)]
        for c_ in cards + focus + also:  # the flag beside each shown fact a counted contradiction is about
            for it in c_.get("items") or []:
                hit = [c["id"] for c in counted if set(c.get("facts") or []) & set(it.get("facts") or [])]
                if hit:
                    it["conflicts"] = hit
    _annotate_followups(st, cards + focus + also)
    notes = []
    if unanswered:
        notes.append("Not answered here, ask again on its own: %s." % ", ".join(unanswered))
    if req["instructions"]:
        notes.append("Instructions inside the request were ignored (Second Look never changes or adds record "
                      "content): %s." % "; ".join("'%s'" % x[:60] for x in req["instructions"]))
    if excluded:
        notes.append("Left out as requested: %s (allergies and age/sex always stay)."
                     % ", ".join(tp["label"] for tp in excluded))
    if notes:
        u["fallback_note"] = " ".join(([u["fallback_note"]] if u.get("fallback_note") else []) + notes)

    # only what touches this screen: contradictions, blind spot, open follow-ups
    contra_all, proof = _proof_and_contradictions(st, cards + focus + also, contras)
    on_card = {x for c in cards + focus for x in c.get("conflicts") or []}
    for c in contra_all:
        c["relevant"] = c["relevant"] or c["id"] in on_card
        c["slots"] = [x["slot"] for x in cards if set(c["facts"]) & set(x["facts"]) or c["id"] in (x.get("conflicts") or [])]
    contra_out = [c for c in contra_all if c["relevant"]]
    contra_other = [c for c in contra_all if not c["relevant"]]
    domain = _slot_domain(st, k, cards, as_of, text)
    domain |= {x for c in focus if c.get("group") in ("question", "named_topic") for x in c.get("facts") or []}
    bs, bs_other = _task_blind_spot(compare_blind_spot(st) or blind_spot(st), domain)
    comp = st.compare if isinstance(st.compare, dict) else {}
    fus = [fu for fu in comp.get("open_followups") or [] if fu.get("is_open")]
    fu_out = [fu for fu in fus if set(fu.get("fact_ids") or []) & domain]
    fu_other = [fu for fu in fus if fu not in fu_out]
    other_n = len(contra_other) + len(bs_other) + len(fu_other)

    counts = {}
    for c in cards:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    by_pr = {}
    for s_ in u["slots"]:
        by_pr[s_["priority"]] = by_pr.get(s_["priority"], 0) + 1
    from .keyfacts import key_facts  # answer-first lines (docs/DECISIONS.md 20); the cards stay as details
    kf = key_facts(st, k, cards, focus, contra_out, patient,
                   " ".join([u.get("task_text") or req["task"] or ""] + list(u.get("task_labels") or [])), as_of, mode)
    return {
        "understood": u,
        "rulebook": "kb",
        "key_facts": kf,
        "detail": detail,
        "screen_mode": mode,
        "patient": patient,
        "safety_strip": [],
        "cards": cards,
        "focus": focus,
        "also_relevant": also,
        "card_status_counts": counts,
        "slot_counts": {"shown": len(cards), "by_priority": by_pr},
        "blind_spot": bs,
        "blind_spot_other": bs_other,
        "contradictions": contra_out,
        "contradictions_other": contra_other,
        "contradictions_source": csource,
        "open_followups": fu_out,
        "open_followups_other": fu_other,
        "other_record_issues": other_n,
        "other_record_issues_en": ("%d other record issue(s) not related to this task" % other_n) if other_n else None,
        "proof_bar": proof,
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


REVIEW_RX = re.compile(
    r"(?<![\w])(inconsisten\w*|contradict\w*|discrepan\w*|conflicting|disagree\w*|mismatch\w*|plausib\w*|"
    r"documentation (?:quality|review|errors?|check)|data quality|record quality|quality (?:check|review) of the (?:record|letters|documentation)|"
    r"copy[- ]?paste|errors? in the (?:record|letters|documentation|documents)|"
    r"widerspr\w*|unstimmig\w*|inkonsisten\w*|dokumentationsqualit\w*|dokumentationsfehler\w*|abweichung\w*|"
    r"incoheren\w*|divergen\w*|incoherence|contradiction\w*|contradicc\w*|discrepanc\w*|inconsistenc\w*|"
    r"incoerenz\w*|contraddi\w*|discrepanz\w*|tutarsiz\w*|celiski\w*|تناقض\w*|تعارض\w*|عدم اتساق)")
MAX_DISAGREE_ITEMS = 12


def disagreement_card(st, shown_cards, contras, excluded=(), review=False):
    """'Letters disagree' card: every counted contradiction or documentation note (compare/) that touches a fact
    on this screen - or all of them for a documentation-review request - with one fact per conflicting
    statement (both sides open) and the explanation as a computed line linked to its passages."""
    from .focus import topic_fact_ids
    shown = {x for c in shown_cards for x in c.get("facts") or []}
    on_card = {x for c in shown_cards for x in c.get("conflicts") or []}
    ex_ids = {x for tp in excluded for x in topic_fact_ids(st, tp)}
    picked = [c for c in contras if review or set(c.get("facts") or []) & shown or c["id"] in on_card]
    picked = [c for c in picked if not (ex_ids and set(c.get("facts") or []) <= ex_ids)]
    if not picked:
        return None
    picked.sort(key=lambda c: (not c.get("counted", True), c["id"]))
    facts, lines = [], []
    for c in picked:
        seen_vals = set()
        for cl in c.get("claims") or []:
            v = re.sub(r"\s+", " ", str(cl.get("asserted") or "")).lower()
            fid = cl.get("fact_id")
            if v in seen_vals or fid not in st.fact_by_id or fid in facts:
                continue
            seen_vals.add(v)
            facts.append(fid)
        lines.append({"label": ("Letters disagree: " if c.get("counted", True) else "Documentation note: ")
                               + (c.get("title_en") or c["id"]),
                      "value": c.get("detail_en") or "", "passages": list(c.get("passages") or []),
                      "formula": "compare/: statements about the same thing in different letters (or a value "
                                 "recomputed from the letters); tier %s" % ("counted contradiction" if c.get(
                                     "counted", True) else "documentation note")})
    items = group_items(st, [st.fact_by_id[x] for x in facts])[:MAX_DISAGREE_ITEMS]
    return {"need": "disagreements", "slot": "disagreements", "label_en": "Letters disagree" + (
                " (documentation review: all)" if review else " on this screen"),
            "shape": "list", "priority": "P1", "group": "disagreements",
            "why": "Contradictions and documentation notes found by comparing the letters (compare/).",
            "sources": [], "rules": [], "origins": ["compare"], "compute": "disagreements", "status": "conflicting",
            "value_en": " | ".join(it["label_en"] for it in items), "items": items,
            "facts": [x for it in items for x in it["facts"]], "conflicts": [c["id"] for c in picked],
            "passages": list(dict.fromkeys(p for it in items for p in it["passages"])), "collapsed": 0,
            "computed_lines": lines}


def other_patient_screen(text, req, detail, t0):
    """The request names a different patient: nothing of the open record is shown."""
    msg = ("Different patient: %s Second Look shows only the record that is open; open the other patient's record "
           "to ask about them." % req["other_patient"])
    u = {"text": text, "task_text": "", "role_match": {"method": "none", "matched": None},
         "clinical_gate": {"decision": "other_patient", "clinical": False, "term": None, "label": None},
         "rulebook": None}
    scr = not_authorised_screen(u, u["clinical_gate"], detail, t0)
    scr["message"] = msg
    scr["understood"].update(fallback_note=msg, not_authorised_message=msg, role_label="Different patient",
                             task_labels=["Different patient"], other_patient=req["other_patient"])
    scr["proof_bar"]["summary_en"] = "No patient facts shown: the request is about a different patient."
    return scr


_JUDGEMENT = []


def _asks_judgement(text):
    """The request asks for an assessment, not a fact (clearance, fitness, 'should I worry'): the 'judgement'
    words of rulebook/task_intent.json."""
    from . import intent as I
    from .understand import fold, norm_text
    if not _JUDGEMENT:
        import json
        with open(I.PATH, encoding="utf-8") as fh:
            d = json.load(fh)
        words = [fold(norm_text(x).strip()) for x in d.get("judgement") or []]
        _JUDGEMENT.append(re.compile(r"(?<![\w-])(?:%s)" % "|".join(re.escape(w) for w in sorted(set(words), key=len,
                                                                                             reverse=True) if w)))
    return bool(_JUDGEMENT[0].search(fold(norm_text(text))))


def needs_task_screen(u, reason, detail, t0, llm_reason=None, message=None, suggestions=None, role_missing=False):
    """Zero patient facts, no counts: a request to name the task (clinical requester, no task) or, with
    role_missing, to say who is asking (a task but no requester role)."""
    from . import intent as I
    gate = u.get("clinical_gate") or {}
    role_id = u.get("role_id") if u.get("role_id") not in (None, "other") and not role_missing else None
    label = "Role not stated" if role_missing else \
        (u.get("role_label") if role_id else None) or gate.get("label") or "Clinician"
    msg = message or I.NEEDS_TASK_MESSAGE
    scr = not_authorised_screen(u, gate, detail, t0)
    u = scr["understood"]
    u.update({"role_id": role_id or "other", "role_label": label, "task_labels": ["Task not stated"],
              "tasks_from": "needs_task", "screen_mode": "needs_task",
              "suggestions": list(suggestions or I.NEEDS_TASK_SUGGESTIONS),
              "fallback_note": msg, "not_authorised_message": None, "role_missing": role_missing,
              "needs_task_message": msg, "needs_task_reason": reason,
              "llm_used": bool(llm_reason), "llm_reason": llm_reason})
    if role_missing:
        u["task_labels"] = ["Role not stated"]
    scr["screen_mode"] = "needs_task"
    scr["message"] = msg
    scr["proof_bar"]["summary_en"] = ("No patient facts shown: no role stated." if role_missing else
                                      "No patient facts shown: no clinical task stated.")
    return scr


def not_authorised_screen(u, gate, detail, t0):
    """No clinical role: zero patient facts, no record issues, no counts derived from the record."""
    u.update({
        "role_id": "other", "role_label": "Not authorised", "bundle_ids": [], "bundles_chosen": [], "implied": [],
        "task_ids": [], "task_labels": ["Not authorised"], "tasks_from": "not_authorised", "slots": [],
        "slots_shown": [], "screen_mode": "not_authorised", "suggestions": list(C.NOT_AUTHORISED_SUGGESTIONS),
        "fallback_note": C.NOT_AUTHORISED_MESSAGE, "not_authorised_message": C.NOT_AUTHORISED_MESSAGE,
        "applicability_note": None, "applicability": {"sex": None, "passage": None, "word": None, "items": []},
        "rules": {"listed": [], "fired": [], "not_fired": [], "in_fill": []}, "llm_note": None,
        "llm_used": False, "llm_reason": None,
    })
    return {
        "understood": u, "rulebook": "kb", "detail": detail, "screen_mode": "not_authorised",
        "message": C.NOT_AUTHORISED_MESSAGE, "patient": {}, "safety_strip": [], "cards": [],
        "card_status_counts": {}, "slot_counts": {"shown": 0, "by_priority": {}},
        "blind_spot": None, "blind_spot_other": [], "contradictions": [], "contradictions_other": [],
        "contradictions_source": None, "open_followups": [], "open_followups_other": [],
        "other_record_issues": 0, "other_record_issues_en": None,
        "proof_bar": {"facts_shown": 0, "facts_verified": 0, "facts_removed_at_load": 0,
                      "summary_en": "No patient facts shown: clinical role not stated."},
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }


def build_screen_legacy(text, as_of=None, use_llm=True):
    t0 = time.perf_counter()
    st = store()
    roles_rb, tasks_rb = rulebook()
    u = understand(text, as_of=as_of, use_llm=use_llm)
    as_of = u["as_of_date"]
    sex, sex_pid = st.patient_sex()
    patient = {"sex": sex, "sex_passage": sex_pid}
    contras, csource = _contradictions(st)
    days = roles_rb.get("outdated_after_days", 183)

    safety = [fill(st, n, as_of, patient, contras, days) for n in roles_rb.get("safety_strip", [])]
    bs = compare_blind_spot(st) or blind_spot(st)
    for c in safety:
        if c["need"] == "problems" and bs:
            c["not_in_latest_letter"] = [i["label_en"] for i in bs["items"]]
    cards = [fill(st, n, as_of, patient, contras, days) for n in collect_needs(u, roles_rb, tasks_rb)]
    for c, n in zip(cards, collect_needs(u, roles_rb, tasks_rb)):
        c["task"] = n.get("task")
    _annotate_followups(st, cards)

    shown = []
    for c in safety + cards:
        for x in c["facts"]:
            if x not in shown:
                shown.append(x)
    shown_set = set(shown)
    contra_out = [dict(c, relevant=bool(set(c["facts"]) & shown_set)) for c in contras]
    contra_out.sort(key=lambda c: not c["relevant"])
    verified = [x for x in shown if st.fact_by_id.get(x, {}).get("verified") is not False]
    counts = {}
    for c in cards:
        counts[c["status"]] = counts.get(c["status"], 0) + 1
    return {
        "understood": u,
        "patient": {"sex": sex, "sex_passage": sex_pid},
        "safety_strip": safety,
        "cards": cards,
        "card_status_counts": counts,
        "blind_spot": bs,
        "contradictions": contra_out,
        "contradictions_source": csource,
        "proof_bar": {"facts_shown": len(shown), "facts_verified": len(verified),
                      "facts_removed_at_load": len(st.removed),
                      "summary_en": "%d facts shown - %d checked word for word against the letters - %d removed"
                                    % (len(shown), len(verified), len(st.removed))},
        "timing_ms": round((time.perf_counter() - t0) * 1000, 1),
    }

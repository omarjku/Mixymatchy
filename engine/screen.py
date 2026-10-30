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
    from .understand import norm_text
    words = [w for w in re.findall(r"[a-zäöüß]{4,}", task_text or "")]
    defaults = (role or {}).get("default_bundles") or []
    scored = []
    for b in k.bundles:
        if b["id"] == k.fallback_bundle:
            continue
        best = 0.0
        for tag in (b.get("tags_en") or []) + (b.get("tags_de") or []):
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
    from .kbfill import build_card, label_panel, slot_status_fn
    from .route import route
    t0 = time.perf_counter()
    st = store()
    k = load_kb()
    detail = "long" if str(detail).lower() == "long" else "short"
    anchor = st.anchor_date()
    m = re.search(r"\bas of (\d{4}-\d{2}-\d{2})\b", text or "")
    as_of = as_of or (m.group(1) if m else anchor)
    u = route(text, k, st, as_of, detail=detail, use_llm=use_llm)
    u["as_of_date"] = as_of
    u["anchor_date"] = anchor
    sex, sex_pid = st.patient_sex()
    patient = {"sex": sex, "sex_passage": sex_pid}
    contras, csource = _contradictions(st)
    info = u.pop("slot_info")
    role = k.role_by_id.get(u["role_id"])

    # applicability (rulebook/applicability.json) and the safety summary for unrecognised tasks
    app = A.check(u.get("task_text") or "", st)

    # clinical gate (rulebook/clinical_roles.json): patient data only for a clinical requester
    gate = C.classify(text, kb_alias=(u.get("role_match") or {}).get("matched") if role else None,
                      kb_role=bool(role),
                      task_evidence=C.strong_task(u.get("bundles_matched"), k.fallback_bundle) or bool(app["items"]))
    u["clinical_gate"] = gate
    if not gate["clinical"]:
        return not_authorised_screen(u, gate, detail, t0)
    defaults = [b for b in (role or {}).get("default_bundles") or [] if b in k.bundle_by_id and b != k.fallback_bundle]
    if (u["tasks_from"] == "fallback" and len(defaults) == 1 and not app["items"]
            and not OVERVIEW_RX.search(u.get("task_text") or "")):
        # a recognised role with one typical task, task wording not recognised: that task, with a visible note
        u = route(text, k, st, as_of, detail=detail, use_llm=False, force_bundles=defaults)
        u.update(as_of_date=as_of, anchor_date=anchor, clinical_gate=gate)
        info = u.pop("slot_info")
    if not role and gate["decision"] == "clinical_term":
        u["role_label"] = gate["label"]
        u["role_match"] = {"method": "clinical_lexicon", "matched": gate["term"]}
    safety = [x for x in A.table().get("safety_block") or [] if x in k.slot_by_id]
    fallback = u["tasks_from"] == "fallback"
    front, back, mode = [], [], "task"
    slots = list(u["slots_shown"])
    if app["not_applicable"]:
        front = [A.not_applicable_card(st, r, app["sex"], app["passage"], app["word"]) for r in app["not_applicable"]]
        u["applicability_note"] = "%s: not applicable, the record documents %s patient." % (
            "; ".join(r["label"] for r in app["not_applicable"]), A.SEX_WORD.get(app["sex"], app["sex"]))
        if fallback:
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
    u["slots_shown"] = slots
    u["screen_mode"] = mode
    u["applicability"] = {k_: app[k_] for k_ in ("sex", "passage", "word")}
    u["applicability"]["items"] = [{x: r[x] for x in ("id", "label", "applicable_sex", "term")} for r in app["items"]]

    ctx = {"as_of": as_of, "anchor": as_of, "patient": patient, "text": text, "slot_info": info,
           "bundles": u["bundle_ids"], "detail": detail}
    cards = front + [build_card(st, k, s, ctx, contras) for s in slots] + back
    also = []
    if detail == "short" and mode == "task":  # P2 'also relevant' group, shown without a second request
        p2_all = {x["slot"] for x in u["slots"] if x["priority"] == "P2" and x["slot"] not in slots}
        in_bundles = [x for b_ in u["bundle_ids"] for x in (k.bundle_by_id[b_].get("slots") or {}).get("P2") or []]
        p2 = [x for x in dict.fromkeys(in_bundles + [x["slot"] for x in u["slots"]]) if x in p2_all]  # KB order
        room = max(0, min(MAX_ALSO_RELEVANT, MAX_SHORT_TOTAL - len(cards)))
        also = [build_card(st, k, s, ctx, contras) for s in p2[:room]]
        built = p2
        for c in also:
            c["group"] = "also_relevant"
        u["also_relevant"] = [c["slot"] for c in also]
        u["also_relevant_more"] = max(0, len(built) - len(also))
    dob = next((_dob((f.get("attrs") or {}).get("value")) for f in st.facts if f.get("category") == "date_of_birth"), None)
    age = age_years(dob, _d(as_of)) if dob and _d(as_of) else None
    status = slot_status_fn(st, k, as_of, text)
    if mode == "task":
        for c in cards:  # rule R22: label panel for every shown medication
            if c.get("shape") == "current_list" and c.get("items"):
                c["label_panel"] = label_panel(st, k, c, status, u["bundle_ids"], detail, age)
    _annotate_followups(st, cards + also)

    # only what touches this screen: contradictions, blind spot, open follow-ups
    contra_all, proof = _proof_and_contradictions(st, cards, contras)
    on_card = {x for c in cards for x in c.get("conflicts") or []}
    for c in contra_all:
        c["relevant"] = c["relevant"] or c["id"] in on_card
        c["slots"] = [x["slot"] for x in cards if set(c["facts"]) & set(x["facts"]) or c["id"] in (x.get("conflicts") or [])]
    contra_out = [c for c in contra_all if c["relevant"]]
    contra_other = [c for c in contra_all if not c["relevant"]]
    domain = _slot_domain(st, k, cards, as_of, text)
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
    return {
        "understood": u,
        "rulebook": "kb",
        "detail": detail,
        "screen_mode": mode,
        "patient": patient,
        "safety_strip": [],
        "cards": cards,
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


def not_authorised_screen(u, gate, detail, t0):
    """No clinical role: zero patient facts, no record issues, no counts derived from the record."""
    u.update({
        "role_id": "other", "role_label": "Not authorised", "bundle_ids": [], "bundles_chosen": [], "implied": [],
        "task_ids": [], "task_labels": ["Not authorised"], "tasks_from": "not_authorised", "slots": [],
        "slots_shown": [], "screen_mode": "not_authorised", "suggestions": list(C.NOT_AUTHORISED_SUGGESTIONS),
        "fallback_note": C.NOT_AUTHORISED_MESSAGE, "not_authorised_message": C.NOT_AUTHORISED_MESSAGE,
        "applicability_note": None, "applicability": {"sex": None, "passage": None, "word": None, "items": []},
        "rules": {"listed": [], "fired": [], "not_fired": [], "in_fill": []}, "llm_note": None,
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

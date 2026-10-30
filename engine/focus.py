"""Task focus: record facts promoted into the short view because the task points at them.

Two groups, each one card after the P1 needs (never replacing them):

  task_focus  deterministic, works without an API key.
              * task terms: a diagnosis whose label shares a significant clinical word with the situation
                text (reflux, osteoporosis, lupus, carotid ...; synonym groups in rulebook/kb_overlay.json
                'task_terms'), e.g. 'Gastroenterologist, reflux symptoms' -> 'GORD grade II'.
              * overlay relevance: rulebook/kb_overlay.json 'task_relevance' entries (clinical reasoning the
                KB does not have yet, every one 'source: TODO-cite' for the medical team), e.g. radiotherapy
                planning -> connective-tissue disease (SLE).
  llm_focus   the LLM's 'focus_concepts' (engine/llm.py): 0-5 labels chosen from an enum of this record's
              concept labels (deduplicated diagnosis labels + result/plan categories), mapped back to fact
              ids here.  Only ids that exist; nothing the model writes becomes a fact.

Both run only after the clinical gate allowed patient data, never on a not-applicable screen, and skip
facts that are already open on the screen (no duplicates).
"""
import re

from .fill import group_items

MAX_ITEMS = 4          # per focus card
MAX_LABEL = 80         # concept label length in the LLM enum
CONCEPT_SECTIONS = ("results", "plan_of_care", "procedures")   # category concepts (besides diagnoses)
SKIP_CATEGORIES = {"case_number", "encounter", "date_of_birth", "age"}

_concepts = {}


def _norm(s):
    return " ".join(str(s or "").lower().split())


def _words(s):
    return re.findall(r"\w+", str(s or "").lower())


def _dx(f):
    return f.get("category") == "diagnosis" or f.get("ips_section") == "problems"


def _positive(f):
    return (f.get("attrs") or {}).get("assertion") not in ("negative", "suspected") \
        and not str(f.get("label_en") or "").rstrip().endswith("?")


def _in_time(f, as_of):
    if not as_of or f.get("status") in ("planned", "recommended"):
        return True
    return str(f.get("date") or "")[:10] <= as_of


# ----------------------------------------------------------------- concept labels (LLM enum)

def concepts(store):
    """-> (labels tuple, {label: [fact ids]}).  Deduplicated English diagnosis labels plus result / plan
    categories present in the record ('result: hba1c').  Built once per store; short labels only."""
    key = id(store)
    if key in _concepts:
        return _concepts[key]
    by_label = {}
    for f in store.facts:
        if _dx(f) and _positive(f):
            lab = str(f.get("label_en") or "").strip()
            if lab.lower().startswith("question:") or not lab:
                continue
            lab = lab if len(lab) <= MAX_LABEL else lab[: MAX_LABEL - 1].rstrip() + "…"
        elif f.get("ips_section") in CONCEPT_SECTIONS and f.get("category") not in SKIP_CATEGORIES:
            lab = "%s: %s" % ("plan" if f["ips_section"] == "plan_of_care" else f["ips_section"].rstrip("s"),
                              str(f["category"]).replace("_", " "))
        else:
            continue
        k = _norm(lab)
        hit = next((x for x in by_label if _norm(x) == k), None)
        by_label.setdefault(hit or lab, []).append(f["id"])
    labels = tuple(sorted(by_label, key=str.lower))
    _concepts[key] = (labels, by_label)
    return _concepts[key]


# ----------------------------------------------------------------- deterministic task terms + overlay

def _term_set(task_text, overlay):
    tt = overlay.get("task_terms") or {}
    stop = set(tt.get("stop") or [])
    words = [w for w in _words(task_text) if not w.isdigit()]
    terms = {w for w in words if len(w) >= 5 and w not in stop}
    for group in tt.get("groups") or []:
        if any(w == g or (len(g) >= 5 and len(w) >= 5 and (w.startswith(g) or g.startswith(w)))
               for w in words for g in group):
            terms |= {g for g in group if " " not in g}
    return terms


def _label_hits(label, terms):
    ws = _words(label)
    return [t for t in terms if any(w == t or (len(t) >= 5 and w.startswith(t)) for w in ws)]


def _phrase_in(text, phrases):
    return any(_norm(p) in text for p in phrases or [])


def relevance_entries(text, overlay):
    t = _norm(text)
    out = []
    for e in overlay.get("task_relevance") or []:
        ok = bool(e.get("when_any") or e.get("when_all"))
        if e.get("when_any"):
            ok = ok and _phrase_in(t, e["when_any"])
        for alts in e.get("when_all") or []:
            ok = ok and _phrase_in(t, alts)
        if ok:
            out.append(e)
    return out


def _card(store, need, label, why, fact_ids, priority, sources, extra):
    facts = [store.fact_by_id[x] for x in fact_ids if x in store.fact_by_id]
    items = group_items(store, facts)
    items.sort(key=lambda it: str(it.get("date") or ""), reverse=True)
    items = items[:MAX_ITEMS]
    card = {"need": need, "slot": need, "label_en": label, "shape": "list", "priority": priority, "why": why,
            "sources": sources, "rules": [], "origins": [need], "compute": "focus", "status": "consistent",
            "value_en": " | ".join(it["label_en"] for it in items), "items": items, "group": need,
            "facts": [x for it in items for x in it["facts"]],
            "passages": list(dict.fromkeys(p for it in items for p in it["passages"])), "collapsed": 0}
    card.update(extra)
    return card


TODO_SOURCE = {"id": "TODO-cite", "title": "Engineering overlay: awaiting a citation from the medical team",
               "verification": "todo", "url": ""}


def _open_ids(cards):
    return {x for c in cards for it in c.get("items") or [] if not it.get("collapsed") for x in it["facts"]}


def _eligible(store, ids, as_of, shown, taken):
    out = []
    for x in ids:
        f = store.fact_by_id.get(x)
        if f and x not in shown and x not in taken and _positive(f) and _in_time(f, as_of):
            out.append(x)
    return out


def out_of_scope(overlay, role_id, task_text):
    """-> fact filter for rulebook/kb_overlay.json 'task_focus_scope': facts whose label matches an entry are
    not promoted for roles outside its only_roles, unless the request names them or its own subject
    (unless_text: 'pathology resident', 'tumour board', 'chemo').  No role: no filter."""
    rxs = []
    for e in overlay.get("task_focus_scope") or []:
        rx = re.compile(e["label_match"], re.I)
        why_not = e.get("unless_text") and re.search(e["unless_text"], task_text or "", re.I)
        if role_id and role_id not in (e.get("only_roles") or []) and not rx.search(task_text or "") and not why_not:
            rxs.append(rx)
    return lambda f: any(rx.search(str(f.get("label_en") or "")) for rx in rxs)


def focus_cards(store, kb, task_text, text, as_of, shown_cards, llm_focus=None, role_id=None):
    """-> (cards, routing info).  shown_cards: the cards already on the screen (their open facts are not
    repeated)."""
    overlay = getattr(kb, "overlay", None) or {}
    shown = _open_ids(shown_cards)
    skip = out_of_scope(overlay, role_id, task_text)
    shown |= {f["id"] for f in store.facts if skip(f)}  # treated as already shown: never promoted
    cards, info = [], {"task_focus": None, "llm_focus": None}

    # deterministic: task terms + overlay relevance
    picked, reasons, entries = [], [], []
    terms = _term_set(task_text, overlay)
    if terms:
        hit_terms = set()
        for f in store.facts:
            if _dx(f):
                h = _label_hits(f.get("label_en"), terms)
                if h and f["id"] not in picked and _eligible(store, [f["id"]], as_of, shown, picked):
                    picked.append(f["id"])
                    hit_terms |= set(h)
        if hit_terms:
            reasons.append("Your task names %s; the record has a matching diagnosis." %
                           ", ".join("'%s'" % t for t in sorted(hit_terms)))
    for e in relevance_entries(text, overlay):
        ids = []
        for f in store.facts:
            cat_hit = f.get("category") in (e.get("categories") or [])
            term_hit = any(_norm(t) in _norm(f.get("label_en")) for t in e.get("terms") or []) and _dx(f)
            if cat_hit or term_hit:
                ids.append(f["id"])
        new = _eligible(store, ids, as_of, shown, picked)
        if new:
            picked += new
            reasons.append(e["why"])
            entries.append(e["id"])
    if picked:
        c = _card(store, "task_focus", "Relevant to your task", " ".join(reasons), picked, "P1",
                  [TODO_SOURCE] if entries else [], {"overlay_entries": entries, "terms": sorted(terms)})
        cards.append(c)
        info["task_focus"] = {"terms": sorted(terms), "overlay_entries": entries, "facts": c["facts"]}
        shown |= set(c["facts"])

    # LLM: focus concepts -> fact ids (validated: only labels of this record, only existing facts)
    if llm_focus and llm_focus.get("concepts"):
        _labels, by_label = concepts(store)
        ids = [x for lab in llm_focus["concepts"] for x in by_label.get(lab, [])]
        new = _eligible(store, list(dict.fromkeys(ids)), as_of, shown, [])
        if new:
            why = llm_focus.get("reason") or "Highlighted by the language model for this task."
            c = _card(store, "llm_focus", "AI-highlighted for this task", why, new, "P1", [],
                      {"llm_concepts": list(llm_focus["concepts"])})
            cards.append(c)
            info["llm_focus"] = {"concepts": list(llm_focus["concepts"]), "reason": why, "facts": c["facts"]}
    return cards, info


# ----------------------------------------------------------------- named topics (rulebook/kb_overlay.json 'topics')
#
# A request that names a topic ('bone', 'Holter', 'HbA1c', 'Sozialanamnese', 'tansiyon', ...) gets that topic
# on the short view: its KB slots as P1 cards, its facts (fact category / ICD-10 / ATC / label pattern) open
# in a card of their own when no other card shows them, and an honest 'not documented' card when the record
# has nothing (facts and passages searched).  Excluded topics ('not interested in X') are suppressed.

_TOPICS = {}
TOPIC_PREFIX_MIN = 6
SAFETY_SLOTS = ("age_sex", "allergies")


def _topic_rx(term):
    from .understand import _phrase_rx, fold, norm_text
    t = fold(norm_text(term).strip())
    return _phrase_rx(t, len(t) < TOPIC_PREFIX_MIN)


def topic_list(overlay):
    """Compiled topics of the overlay (cached per overlay object)."""
    key = id(overlay)
    if key not in _TOPICS:
        from .kb import expand_codes
        out = []
        for tp in (overlay or {}).get("topics") or []:
            terms = [x for xs in (tp.get("terms") or {}).values() for x in xs]
            sel = tp.get("select") or {}
            out.append(dict(tp, _rx=[_topic_rx(x) for x in terms],
                            _icd=[c.upper() for c in expand_codes(sel.get("icd10"))],
                            _atc=[c.upper() for c in sel.get("atc") or []],
                            _cats=set(sel.get("categories") or []),
                            _label=re.compile(sel["label"], re.I) if sel.get("label") else None,
                            _search=[re.compile(r"(?<![\wäöüß])%s" % s, re.I) for s in tp.get("search") or []]))
        _TOPICS[key] = out
    return _TOPICS[key]


def match_topics(text, overlay):
    """Topics named in the (normalised) text, in the order they appear."""
    from .understand import fold
    text = fold(text or "")
    hits = []
    for tp in topic_list(overlay):
        pos = [m.start() for r in tp["_rx"] for m in r.finditer(text)]
        if pos:
            hits.append((min(pos), tp))
    hits.sort(key=lambda h: h[0])
    return [tp for _p, tp in hits]


def _code(f, system):
    c = f.get("code") or {}
    if isinstance(c, dict) and str(c.get("system", "")).upper().replace("-", "") == system:
        return str(c.get("value") or "").upper()
    return ""


def in_topic(f, tp):
    """Does a fact belong to a topic (category, ICD-10 / ATC prefix or label pattern)?"""
    if f.get("category") in tp["_cats"]:
        return True
    icd = _code(f, "ICD10")
    if icd and any(icd.startswith(p) for p in tp["_icd"]):
        return True
    atc = _code(f, "ATC")
    if atc and any(atc.startswith(p) for p in tp["_atc"]):
        return True
    return bool(tp["_label"] and tp["_label"].search(str(f.get("label_en") or "")))


def _searchable(f, tp):
    return any(r.search(str(f.get("label_en") or "")) or r.search(str(f.get("quote") or "")) for r in tp["_search"])


def _showable(f, as_of):
    lab = str(f.get("label_en") or "")
    return _in_time(f, as_of) and not lab.lower().startswith("question:") and not lab.rstrip().endswith("?") \
        and (f.get("attrs") or {}).get("assertion") != "suspected" \
        and f.get("category") not in SKIP_CATEGORIES


def topic_fact_ids(store, tp, as_of=None):
    return [f["id"] for f in store.facts if in_topic(f, tp) and (as_of is None or _showable(f, as_of))]


def request_words(task_text, overlay):
    """Significant words of the request (and their synonym groups): items sharing one stay open."""
    return _term_set(task_text, overlay)


def topic_slots(kb, named, excluded=()):
    ex = {s for tp in excluded for s in tp.get("slots") or []}
    out = []
    for tp in named:
        for s in tp.get("slots") or []:
            if s in kb.slot_by_id and s not in ex and s not in out:
                out.append(s)
    return out


def _topic_items(store, ids, words):
    """Items of a topic card: request-word matches first, then newest first."""
    items = group_items(store, [store.fact_by_id[x] for x in ids])
    items.sort(key=lambda it: str(it.get("date") or ""), reverse=True)
    items.sort(key=lambda it: not _label_hits(it["label_en"], words))
    return items


def topic_cards(store, kb, named, excluded, task_text, as_of, shown_cards, settings=None):
    """-> (cards, info).  One card per named topic whose facts no card on the screen shows yet; a 'not
    documented' card when the record has nothing for the topic (facts and passages searched)."""
    settings = settings or {}
    max_cards, max_items = settings.get("max_topic_cards", 4), settings.get("max_items", 6)
    overlay = getattr(kb, "overlay", None) or {}
    words = request_words(task_text, overlay)
    ex_ids = {x for tp in excluded for x in topic_fact_ids(store, tp)}
    shown = _open_ids(shown_cards)
    slot_cards = {c.get("slot"): c for c in shown_cards}
    cards, info = [], []
    for tp in named:
        if len(cards) >= max_cards:
            break
        all_ids = [x for x in topic_fact_ids(store, tp, as_of) if x not in ex_ids]
        if not all_ids and tp["_search"]:  # honest absence: also search every fact's text and quote
            all_ids = [f["id"] for f in store.facts if _showable(f, as_of) and _searchable(f, tp) and f["id"] not in ex_ids]
        new = [x for x in all_ids if x not in shown]
        tslots = [s for s in tp.get("slots") or [] if s in slot_cards]
        slot_has = any(slot_cards[s].get("status") != "not_documented" for s in tslots)
        slot_nd = any(slot_cards[s].get("status") == "not_documented" for s in tslots)
        why = tp.get("_why") or "Your request names %s." % tp["label"].split(" (")[0].lower()
        if new:
            items = _topic_items(store, new, words)[:max_items]
            card = {"need": "topic_%s" % tp["id"], "slot": "topic_%s" % tp["id"], "label_en": tp["label"],
                    "shape": "list", "priority": "P1", "why": why, "sources": [TODO_SOURCE], "rules": [],
                    "origins": ["role topic" if tp.get("_why") else "named topic"], "compute": "topic", "status": "consistent",
                    "value_en": " | ".join(it["label_en"] for it in items), "items": items, "group": "named_topic",
                    "facts": [x for it in items for x in it["facts"]],
                    "passages": list(dict.fromkeys(p for it in items for p in it["passages"])), "collapsed": 0}
            cards.append(card)
            shown |= set(card["facts"])
            info.append({"topic": tp["id"], "facts": card["facts"]})
        elif not all_ids and not slot_has and not slot_nd:
            mentions = [p["id"] for p in store.passages if any(r.search(p.get("text") or "") for r in tp["_search"])][:5]
            searched = ", ".join(s.replace("\\b", "") for s in tp.get("search") or []) or "the topic's fact kinds"
            card = {"need": "topic_%s" % tp["id"], "slot": "topic_%s" % tp["id"], "label_en": tp["label"],
                    "shape": "record_check", "priority": "P1", "why": why, "sources": [TODO_SOURCE], "rules": [],
                    "origins": ["role topic" if tp.get("_why") else "named topic"], "compute": "record_check",
                    "status": "not_documented",
                    "items": [], "facts": [], "passages": mentions, "date": None, "group": "named_topic",
                    "searched": {"documents": len(store.docs), "facts_checked": len(store.facts),
                                 "passages_scanned": len(store.passages), "terms": list(tp.get("search") or []),
                                 "possible_mentions": mentions},
                    "value_en": ("No extracted fact; %d passage(s) contain a search word (%s) - open the source to check"
                                 % (len(mentions), searched) if mentions else
                                 "Not documented in any of the %d documents (searched every fact and passage for: %s)"
                                 % (len(store.docs), searched))}
            cards.append(card)
            info.append({"topic": tp["id"], "not_documented": True})
        else:
            info.append({"topic": tp["id"], "on_screen": True})
    return cards, info


def open_named(cards, store, named, task_text, overlay, as_of=None):
    """Facts of a named topic, or whose label shares a significant word with the request, are never hidden
    behind '+N more'."""
    ids = {x for tp in named for x in topic_fact_ids(store, tp)}
    words = request_words(task_text, overlay)
    for c in cards:
        changed = False
        for it in c.get("items") or []:
            if it.get("collapsed") and (set(it["facts"]) & ids or _label_hits(it.get("label_en"), words)):
                it["collapsed"] = False
                changed = True
        if changed:
            c["collapsed"] = sum(1 for it in c.get("items") or [] if it.get("collapsed"))


def apply_exclusions(cards, store, excluded):
    """Remove the facts of excluded topics from the screen; the safety core (allergies, age/sex) stays.
    -> the cards that remain."""
    if not excluded:
        return cards
    ex_ids = {x for tp in excluded for x in topic_fact_ids(store, tp)}
    ex_slots = {s for tp in excluded for s in tp.get("slots") or []}
    out = []
    for c in cards:
        if c.get("slot") in SAFETY_SLOTS:
            out.append(c)
            continue
        if c.get("slot") in ex_slots or c.get("need") in {"topic_%s" % tp["id"] for tp in excluded}:
            continue
        items = c.get("items") or []
        keep = [it for it in items if not set(it.get("facts") or []) & ex_ids]
        if items and not keep:
            continue
        if len(keep) != len(items):
            dropped = " ".join(str(it.get("label_en") or "") for it in items if it not in keep).lower()
            c = dict(c, items=keep, facts=[x for it in keep for x in it["facts"]],
                     passages=list(dict.fromkeys(p for it in keep for p in it["passages"])),
                     value_en=" | ".join(it["label_en"] for it in keep if not it.get("collapsed")),
                     collapsed=sum(1 for it in keep if it.get("collapsed")))
            if c.get("label_panel"):
                c["label_panel"] = [p for p in c["label_panel"]
                                    if not any(w in dropped for w in re.findall(r"[a-z]{5,}", str(p.get("ingredient") or "").lower()))]
            if c.get("earlier"):
                c["earlier"] = [e for e in c["earlier"] if not set(e.get("facts") or []) & ex_ids]
        out.append(c)
    return out

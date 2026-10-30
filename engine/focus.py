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
    return re.findall(r"[a-zäöüß0-9]+", str(s or "").lower())


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


def focus_cards(store, kb, task_text, text, as_of, shown_cards, llm_focus=None):
    """-> (cards, routing info).  shown_cards: the cards already on the screen (their open facts are not
    repeated)."""
    overlay = getattr(kb, "overlay", None) or {}
    shown = _open_ids(shown_cards)
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

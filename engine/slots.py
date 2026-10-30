"""Slot selection: which facts of data/build/facts.json belong to a KB slot (rules in rulebook/slot_map.json).

A slot's selectors are OR-ed; see slot_map.json "_notes" for the selector semantics.  Drug classes
come from the KB (drug_classes: generics + brand examples, matched as whole words against a
medication fact's generic name, brand and label) or from ATC prefixes.
"""
import re

from .fill import fact_text
from .kb import expand_codes

STATUS_DISPLAY = {  # KB status_vocabulary (IBM statuses) -> on-screen word
    "negative": "ruled out", "suspected": "suspected", "statuspost": "past",
    "recommended": "recommended", "planned": "planned",
}

_RX_CACHE = {}


def rx(pattern):
    r = _RX_CACHE.get(pattern)
    if r is None:
        r = _RX_CACHE[pattern] = re.compile(pattern, re.I)
    return r


def word_rx(term):
    return rx(r"(?<![\wäöüß])%s(?![\wäöüß])" % re.escape(term))


def code_of(f, system):
    c = f.get("code") or {}
    if isinstance(c, dict) and str(c.get("system", "")).upper().replace("-", "") == system.upper().replace("-", ""):
        return str(c.get("value") or "").upper()
    return ""


def assertion(f):
    return (f.get("attrs") or {}).get("assertion")


def med_text(f):
    a = f.get("attrs") or {}
    return " ".join(str(x) for x in (a.get("generic"), a.get("brand"), f.get("label_en")) if x)


def drug_classes_of(kb, f):
    """KB drug classes a medication fact belongs to (by ingredient/brand name, then ATC code)."""
    if f.get("ips_section") != "medications":
        return []
    t = med_text(f)
    out = [cid for cid, terms in kb.class_terms.items() if any(word_rx(x).search(t) for x in terms)]
    return out


def _code_ok(kb, f, sel, slot_id):
    keys = [k for k in ("icd10", "atc", "drug_classes") if sel.get(k)]
    if not keys:
        return True
    icd = code_of(f, "ICD10")
    if icd and any(icd.startswith(p) for p in expand_codes(sel.get("icd10"))):
        return True
    atc = code_of(f, "ATC")
    if atc and any(atc.startswith(p.upper()) for p in sel.get("atc") or []):
        return True
    dcs = sel.get("drug_classes") or []
    if dcs:
        want = set(kb.classes_for_slot(slot_id)) if "*" in dcs else set(dcs)
        if want & set(drug_classes_of(kb, f)):
            return True
    return False


def selector_match(kb, f, sel, slot_id):
    cats, secs = sel.get("categories"), sel.get("ips_sections")
    if cats or secs:
        if not ((cats and f.get("category") in cats) or (secs and f.get("ips_section") in secs)):
            return False
    if not _code_ok(kb, f, sel, slot_id):
        return False
    t = fact_text(f)
    if sel.get("match") and not rx(sel["match"]).search(t):
        return False
    if any(not rx(x).search(t) for x in sel.get("match_all") or []):
        return False
    if sel.get("exclude") and rx(sel["exclude"]).search(t):
        return False
    if sel.get("status_in") and f.get("status") not in sel["status_in"]:
        return False
    if sel.get("assertion_in") and assertion(f) not in sel["assertion_in"]:
        return False
    if sel.get("assertion_not_in") and assertion(f) in sel["assertion_not_in"]:
        return False
    return True


def _in_time(f, as_of):
    return f.get("status") in ("planned", "recommended") or str(f.get("date") or "")[:10] <= as_of


def _written_by(store, f, as_of):
    """A plan's date is when it will happen; it is known only from a letter written by the as-of date."""
    if f.get("status") not in ("planned", "recommended"):
        return True
    dates = [str(store.doc_date(d) or "")[:10] for d in store.fact_docs(f)]
    return not dates or any(d and d <= str(as_of)[:10] for d in dates)


def select_slot(store, kb, slot_id, as_of, situation_text=""):
    """-> (primary facts, context facts) for one slot, as of a date."""
    spec = kb.slot_spec(slot_id)
    if spec.get("always_not_documented"):
        return [], []
    primary, context = [], []
    sels = list(spec.get("select") or [])
    t = (situation_text or "").lower()
    for st in spec.get("situation_terms") or []:
        if t and rx(st["when"]).search(t):
            sels.append({"categories": spec.get("situation_categories") or ["diagnosis"], "match": st["match"]})
    for f in store.facts:
        if not _in_time(f, as_of) or not _written_by(store, f, as_of):
            continue
        for sel in sels:
            if selector_match(kb, f, sel, slot_id):
                (context if sel.get("role") == "context" else primary).append(f)
                break
    # a 'question: X?' / suspected fact adds nothing when a positive fact of the slot exists
    pos = [f for f in primary if assertion(f) != "suspected"]
    if pos and len(pos) < len(primary) and spec.get("compute") not in ("status_check",) and \
            kb.slot_by_id[slot_id].get("shape") in ("latest_value", "laterality_finding"):
        primary = pos
    if slot_id == "planned_procedure":
        primary = [f for f in primary if not past_plan(store, f, as_of)]
    ids = {f["id"] for f in primary}
    return primary, [f for f in context if f["id"] not in ids]


HISTORY_SECTION = re.compile(r"anamnese|vorgeschichte|history", re.I)


def past_plan(store, f, as_of):
    """A plan that is no longer ahead:
    - its own date (later than the letter: 'admission on 10.04.2016') lies before the as-of date;
    - it has no date of its own (fact date = letter date) and a newer letter exists by the as-of date, which
      records what happened ('biopsy during the stay' in the 05.04 letter, read on 15.04);
    - it is only the reason for an admission told in the history section ('comes for ultrasound work-up')."""
    as_of = str(as_of)[:10]
    date = str(f.get("date") or "")[:10]
    written = max((str(store.doc_date(d) or "")[:10] for d in store.fact_docs(f)), default="")
    if date and date > written:
        if date < as_of:
            return True
    elif written and any(written < str(store.doc_date(d) or "")[:10] <= as_of for d in store.docs):
        return True
    secs = [(store.passage_by_id.get(p) or {}).get("section") or "" for p in f.get("passage_ids") or []]
    return bool(secs) and all(HISTORY_SECTION.search(s) for s in secs)


def found(store, kb, slot_id, as_of, situation_text=""):
    """Positive (not ruled out) facts of a slot; used by link rules."""
    p, _ = select_slot(store, kb, slot_id, as_of, situation_text)
    return [f for f in p if assertion(f) != "negative"]


def hint_patterns(kb, slot_id):
    stop = {s.lower() for s in kb.slot_map.get("_hint_stopwords") or []}
    out = []
    for h in kb.slot_by_id[slot_id].get("hints_de") or []:
        if h.lower() in stop or len(h) < 2:
            continue
        out.append(r"(?<![\wäöüß])%s(?![\wäöüß])" % re.escape(h) if h[-1:].isalnum() else
                   r"(?<![\wäöüß])%s" % re.escape(h))
    return out


def lab_table_passages(store, kb):
    spec = kb.slot_map.get("_lab_table") or {}
    if not spec:
        return []
    sec, txt = rx(spec.get("section") or "^$"), rx(spec.get("text") or "^$")
    return [p["id"] for p in store.passages if sec.search(p.get("section") or "") and txt.search(p.get("text") or "")]

"""One KB slot -> one answer card (shape from the KB, facts from rulebook/slot_map.json).

Card keys follow engine/fill.py (status, value_en, items, facts, passages, ...) plus the KB fields
slot, shape, priority, why, sources, rules.  Statuses: consistent / conflicting / outdated /
not_documented (never guessed: the card names what was searched).
"""
from . import fill as F
from .slots import (assertion, drug_classes_of, hint_patterns, lab_table_passages, rx, select_slot,
                    selector_match, word_rx)


def _searched(store, kb, slot_id, spec):
    pats = hint_patterns(kb, slot_id)
    mentions = []
    for pat in pats:
        r = rx(pat)
        for p in store.passages:
            if r.search(p.get("text") or "") and p["id"] not in mentions:
                mentions.append(p["id"])
    return pats, mentions


def not_documented(store, kb, slot_id, spec, card, extra=""):
    slot = kb.slot_by_id[slot_id]
    pats, mentions = _searched(store, kb, slot_id, spec)
    lab = lab_table_passages(store, kb) if spec.get("lab_table") else []
    card["status"] = "not_documented"
    card["searched"] = {
        "documents": len(store.docs), "facts_checked": len(store.facts),
        "slot_map": [{k: v for k, v in sel.items() if k != "role"} for sel in spec.get("select") or []],
        "hints_de": slot.get("hints_de") or [], "passages_scanned": len(store.passages),
        "possible_mentions": mentions[:5], "lab_table": lab,
    }
    hints = ", ".join((slot.get("hints_de") or [])[:6])
    if lab:
        card["value_en"] = ("Not documented: no value in any of the %d documents; the lab-result tables (linked) "
                            "list no values%s" % (len(store.docs), extra))
        card["passages"] = lab
    elif mentions:
        card["value_en"] = ("No extracted fact; %d passage(s) contain a search word (%s) - open the source to check%s"
                            % (len(mentions), hints, extra))
        card["passages"] = mentions[:5]
    else:
        card["value_en"] = "Not documented in any of the %d documents (searched for: %s)%s" % (
            len(store.docs), hints, extra)
    return card


def build_card(store, kb, slot_id, ctx, contradictions=()):
    """ctx: as_of, anchor, patient, text, slot_info (priority/why/sources/rules), bundles, detail."""
    slot = kb.slot_by_id[slot_id]
    spec = kb.slot_spec(slot_id)
    info = (ctx.get("slot_info") or {}).get(slot_id, {})
    shape = slot.get("shape")
    card = {"need": slot_id, "slot": slot_id, "label_en": slot.get("label"), "shape": shape,
            "priority": info.get("priority"), "why": info.get("why") or slot.get("why"),
            "sources": info.get("sources") or [], "rules": info.get("rules") or [],
            "origins": info.get("origins") or [], "compute": spec.get("compute") or F.SHAPE_COMPUTE.get(shape),
            "status": None, "value_en": "", "date": None, "facts": [], "passages": [], "items": [],
            "source": ",".join(s["id"] for s in info.get("sources") or [])}
    if spec.get("always_not_documented"):
        return not_documented(store, kb, slot_id, spec, card)
    primary, context = select_slot(store, kb, slot_id, ctx["as_of"], ctx.get("text", ""))
    comp = spec.get("compute") or shape
    primary_ids = None
    if comp == "age_sex":
        F.age_sex(store, card, primary, ctx["anchor"], ctx.get("patient") or {})
    elif comp == "med_changes":
        F.med_changes(store, card, primary, ctx["as_of"])
    elif comp == "status_check":
        if not primary:
            not_documented(store, kb, slot_id, spec, card)
            card["value_en"] = "No follow-up recommendation documented, so nothing to check"
        else:
            def evidence(sel):
                return [f for f in store.facts if selector_match(kb, f, sel, slot_id)]
            F.status_check(store, card, primary, spec.get("checks") or [], evidence, ctx["as_of"])
            if card["status"] == "not_documented":
                _, mentions = _searched(store, kb, slot_id, spec)
                card["searched"] = {"documents": len(store.docs), "facts_checked": len(store.facts),
                                    "checks": [c["label"] for c in spec.get("checks") or []],
                                    "possible_mentions": mentions[:5]}
    elif not primary:
        not_documented(store, kb, slot_id, spec, card)
        if context:
            card["note"] = "Related but not the value itself: " + "; ".join(
                F.shown(it) for it in F.annotate_status(store, F.group_items(store, context))[:5])
    elif comp == "current_list":
        F._current_meds(store, {}, card, primary, ctx["as_of"], 0)
        for it in card.get("items") or []:
            f = store.fact_by_id[it["facts"][0]]
            it["drug_classes"] = drug_classes_of(kb, f)
    elif comp == "latest_value":
        F.latest_by_key(store, card, primary, context, ctx["anchor"], spec.get("latest_key") or "category")
        primary_ids = card.pop("primary_ids", None)
    elif comp == "trend":
        F.trend(store, card, primary, spec.get("calculate_change", True))
    elif comp == "checklist":
        F.checklist(store, card, primary, spec.get("subitems") or [], spec.get("none_match"))
    elif comp == "plan":
        F.plan(store, card, primary)
    elif comp == "laterality_finding":
        F.laterality(store, card, primary)
    elif comp == "list_all":
        keep_neg = any("negative" in (sel.get("assertion_in") or []) for sel in spec.get("select") or [])
        F.list_all(store, card, primary, context, ctx.get("detail") or "short", keep_ruled_out=keep_neg)
    else:  # event_history
        F.dated_list(store, card, primary)
        if context:
            for it in F.annotate_status(store, F.group_items(store, context)):
                it["context"] = True
                card["items"].append(it)
    if card["status"] == "not_documented" and comp not in ("status_check", "med_changes", "age_sex"):
        if not card.get("searched"):
            not_documented(store, kb, slot_id, spec, card, extra="")
    return F.finish(store, card, contradictions, primary_ids=primary_ids)


# ----------------------------------------------------------------- R22 label panel

def label_panel(store, kb, card, slot_status, bundles, detail, patient_age=None):
    """Listed contraindications (SmPC 4.3) and warnings (4.4) of each shown drug, each beside the
    related patient facts: found / documented as none / not documented.  Never a verdict."""
    panels, seen = [], set()
    for it in card.get("items") or []:
        if it.get("not_on_latest_list"):
            continue
        f = store.fact_by_id.get(it["facts"][0]) if it.get("facts") else None
        if not f:
            continue
        a = f.get("attrs") or {}
        name = " ".join(str(x) for x in (a.get("generic"), f.get("label_en")) if x)
        atc = str((f.get("code") or {}).get("value") or "") if isinstance(f.get("code"), dict) else ""
        for e in kb.contraindications:
            ing = (e.get("ingredient") or "").split("(")[0].strip()
            e_atc = (e.get("atc") or "").split(" ")[0]
            if e["id"] in seen:
                continue
            if not ((ing and word_rx(ing).search(name)) or (e_atc and atc and atc.upper() == e_atc.upper())):
                continue
            seen.add(e["id"])
            rows = []
            for ci in e.get("listed_contraindications") or []:
                if ci.get("kind") == "population" and detail == "short":
                    continue
                if ci.get("kind") == "population" and patient_age is not None and "below 1 year" in ci["text"] \
                        and patient_age >= 1:
                    continue
                related = [{"slot": s, **slot_status(s)} for s in ci.get("related_slots") or []]
                if detail == "short" and (ci.get("priority") != "P1" or
                                          all(r["status"] == "documented_none" for r in related)):
                    continue
                rows.append({"kind": ci.get("kind"), "text": ci["text"], "priority": ci.get("priority"),
                             "related": related})
            warns = []
            for w in e.get("label_warnings") or []:
                if detail == "long" or w.get("shown_when_bundle") in bundles:
                    warns.append({"text": w["text"], "related": [{"slot": s, **slot_status(s)}
                                                                 for s in w.get("related_slots") or []],
                                  "label_sources": w.get("label_sources") or []})
            panels.append({"ingredient": e.get("ingredient"), "drug_class": e.get("drug_class"),
                           "listed_contraindications": rows, "warnings": warns,
                           "labels": [{"id": x, **{k: kb.label_by_id[x].get(k) for k in
                                                  ("document", "authority", "version_seen", "url")}}
                                      for x in e.get("label_sources") or [] if x in kb.label_by_id],
                           "era_note": e.get("era_note"),
                           "disclaimer": "Listed on the drug label; not a statement about this patient (rule R22)."})
    return panels


def slot_status_fn(store, kb, as_of, text=""):
    cache = {}

    def status(slot_id):
        if slot_id not in cache:
            p, _ = select_slot(store, kb, slot_id, as_of, text)
            if not p:
                cache[slot_id] = {"status": "not_documented", "passages": []}
            elif all(assertion(f) == "negative" for f in p):
                cache[slot_id] = {"status": "documented_none",
                                  "passages": sorted({x for f in p for x in f.get("passage_ids") or []})[:5]}
            else:
                cache[slot_id] = {"status": "found",
                                  "passages": sorted({x for f in p for x in f.get("passage_ids") or []})[:5]}
        return cache[slot_id]
    return status

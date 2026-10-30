"""Applicability of sex-specific tasks (rulebook/applicability.json, hand-written).

    task text -> matched items (prostate, pregnancy, cervical smear, ...) -> applicable for the
    sex documented in the record?  The sex comes from document wording, with the source passage.

Deterministic; the table holds generic keywords only, never patient content.
"""
import json
import os
import re

from .fill import annotate_status, fact_text, finish, group_items

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.environ.get("SECOND_LOOK_APPLICABILITY", os.path.join(ROOT, "rulebook", "applicability.json"))
SEX_WORD = {"female": "a female", "male": "a male"}

_TABLE = None


def table():
    global _TABLE
    if _TABLE is None:
        with open(PATH, encoding="utf-8") as fh:
            _TABLE = json.load(fh)
    return _TABLE


def _term_rx(term):
    from .understand import fold, norm_text
    t = re.escape(fold(norm_text(term)))
    post = "" if len(term) >= 5 else r"(?![\w])"
    return re.compile(r"(?<![\w])" + t + post)


def match_items(task_text, full_text=None):
    """Items of the table named in the (normalised, lowercase) text -> [(item, matched term)].
    Items with scope 'request' (a specialty that only treats children / pregnant women ...) are matched in
    the whole request, role words included; the others in the task text (role words removed)."""
    from .understand import fold
    out = []
    for it in table().get("items") or []:
        txt = fold((full_text if full_text is not None else task_text) if it.get("scope") == "request" else task_text)
        for term in (it.get("terms_en") or []) + (it.get("terms_de") or []) + (it.get("terms_intl") or []):
            if _term_rx(term).search(txt or ""):
                out.append((it, term))
                break
    return out


def documented_age(store, as_of):
    """-> (age in full years at as_of, passage id, date of birth text) from the date-of-birth fact."""
    from .fill import _d, _dob, age_years
    for f in store.facts:
        if f.get("category") == "date_of_birth":
            dob = _dob((f.get("attrs") or {}).get("value"))
            at = _d(as_of) if as_of else None
            if dob and at:
                return age_years(dob, at), (f.get("passage_ids") or [None])[0], (f.get("attrs") or {}).get("value")
    return None, None, None


def documented_sex(store):
    """-> (sex, passage_id, word) from document wording; (None, None, None) if the record does not say.
    The most specific evidence word wins (the order in the table), the earliest passage is linked."""
    ev = table().get("sex_evidence") or {}
    counts, first = {}, {}
    for sex, words in ev.items():
        if sex.startswith("_"):
            continue
        for rank, w in enumerate(words):
            r = re.compile(r"(?<![\wäöüß])%s(?![\wäöüß])" % re.escape(w))
            for p in store.passages:
                if r.search(p.get("text") or ""):
                    counts[sex] = counts.get(sex, 0) + 1
                    if sex not in first or rank < first[sex][0]:
                        first[sex] = (rank, p["id"], w)
    if not counts:
        return None, None, None
    sex = max(counts, key=lambda s: counts[s])
    if len(counts) > 1 and sorted(counts.values())[-1] == sorted(counts.values())[-2]:
        return None, None, None  # the record is not clear: never guess
    return sex, first[sex][1], first[sex][2]


def check(task_text, store, full_text=None, as_of=None, extra_ids=()):
    """-> {"items": [...], "sex": ..., "passage": ..., "age": ..., "not_applicable": [...], "applicable": [...]}
    extra_ids: item ids named by an AI reading (v2 understand step, removed in v3) that the terms did not match."""
    sex, pid, word = documented_sex(store)
    anchor = as_of or (store.anchor_date() if hasattr(store, "anchor_date") else None)
    age, age_pid, dob = documented_age(store, anchor) if anchor else (None, None, None)
    res = {"sex": sex, "passage": pid, "word": word, "age": age, "age_passage": age_pid, "dob": dob,
           "items": [], "not_applicable": [], "applicable": []}
    matched = match_items(task_text, full_text)
    have = {it["id"] for it, _t in matched}
    matched += [(it, it.get("label") or it["id"]) for it in table().get("items") or []
                if it["id"] in (extra_ids or ()) and it["id"] not in have]
    for it, term in matched:
        row = {"id": it["id"], "label": it["label"], "applicable_sex": it.get("applicable_sex"), "term": term,
               "age_min": it.get("applicable_age_min"), "age_max": it.get("applicable_age_max"),
               "scope": it.get("scope") or "task", "roles": list(it.get("roles") or []),
               "slots": list(it.get("slots") or []), "record_checks": list(it.get("record_checks") or [])}
        res["items"].append(row)
        reason = None
        if sex and row["applicable_sex"] and sex != row["applicable_sex"]:
            reason = "sex"
        elif age is not None and ((row["age_max"] is not None and age > row["age_max"]) or
                                  (row["age_min"] is not None and age < row["age_min"])):
            reason = "age"
        if reason:
            row["reason"] = reason
            res["not_applicable"].append(row)
        else:
            res["applicable"].append(row)
    return res


def _age_range(row):
    lo, hi = row.get("age_min"), row.get("age_max")
    if hi is not None and hi < 1:
        return "newborns"
    if lo is not None and hi is not None:
        return "patients aged %d-%d" % (lo, hi)
    if hi is not None:
        return "patients up to %d years" % hi
    return "patients from %d years" % lo


def not_applicable_card(store, row, sex, pid, word, age=None, age_pid=None, dob=None):
    if row.get("reason") == "age":
        passages = [age_pid] if age_pid else []
        why = "Applicability table (rulebook/applicability.json): %s applies to %s only." % (row["label"], _age_range(row))
        value = "Not applicable: the record documents a patient aged %s (date of birth %s)" % (age, dob)
        word = dob
    else:
        passages = [pid] if pid else []
        why = ("Applicability table (rulebook/applicability.json): %s applies to %s patients only."
               % (row["label"], row["applicable_sex"]))
        value = "Not applicable: the record documents %s patient" % SEX_WORD.get(sex, sex)
    return {"need": "applicability_%s" % row["id"], "slot": "applicability_%s" % row["id"],
            "label_en": row["label"], "shape": "applicability", "priority": "P1",
            "why": why, "sources": [], "rules": [], "origins": ["applicability"], "compute": "applicability",
            "status": "not_applicable", "value_en": value,
            "evidence_word": word, "date": None, "facts": [], "passages": passages, "items": []}


def record_check_card(store, row, check, as_of, contradictions=()):
    """Does the record mention this sex-specific item at all?  Facts whose English text or source passage
    matches a search term; otherwise 'not documented' with what was searched."""
    rxs = [re.compile(r"(?<![a-zäöüß])(?:%s)" % t, re.I) for t in check.get("terms") or []]

    def hit(text):
        return any(r.search(text or "") for r in rxs)

    facts = [f for f in store.facts if str(f.get("date") or "")[:10] <= as_of and
             (hit(fact_text(f)) or hit(f.get("quote")))]
    sid = "applicability_%s_%s" % (row["id"], re.sub(r"[^a-z0-9]+", "_", check["label"].lower()).strip("_"))
    card = {"need": sid, "slot": sid, "label_en": check["label"], "shape": "record_check", "priority": "P1",
            "why": "Asked for by the task (%s); searched in every document." % row["label"],
            "sources": [], "rules": [], "origins": ["applicability"], "compute": "record_check",
            "status": None, "value_en": "", "date": None, "facts": [], "passages": [], "items": []}
    if facts:
        items = annotate_status(store, group_items(store, facts))
        items.sort(key=lambda it: str(it["date"] or ""), reverse=True)
        card["items"] = items[:8]
        card["value_en"] = "; ".join(it["label_en"] for it in card["items"])
        card["date"] = items[0]["date"]
        card["status"] = "consistent"
        return finish(store, card, contradictions)
    mentions = [p["id"] for p in store.passages if hit(p.get("text"))][:5]
    card["status"] = "not_documented"
    card["searched"] = {"documents": len(store.docs), "facts_checked": len(store.facts),
                        "terms": list(check.get("terms") or []), "passages_scanned": len(store.passages),
                        "possible_mentions": mentions}
    card["passages"] = mentions
    card["value_en"] = ("No extracted fact; %d passage(s) contain a search word - open the source to check"
                        % len(mentions) if mentions else
                        "Not documented in any of the %d documents (searched for: %s)"
                        % (len(store.docs), ", ".join(t.replace("\\b", "") for t in check.get("terms") or [])))
    return card

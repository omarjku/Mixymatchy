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
    t = re.escape(term.lower())
    post = "" if len(term) >= 5 else r"(?![a-z0-9äöüß])"
    return re.compile(r"(?<![a-z0-9äöüß])" + t + post)


def match_items(task_text):
    """Items of the table named in the (normalised, lowercase) task text -> [(item, matched term)]."""
    out = []
    for it in table().get("items") or []:
        for term in (it.get("terms_en") or []) + (it.get("terms_de") or []):
            if _term_rx(term).search(task_text or ""):
                out.append((it, term))
                break
    return out


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


def check(task_text, store):
    """-> {"items": [...], "sex": ..., "passage": ..., "not_applicable": [...], "applicable": [...]}"""
    sex, pid, word = documented_sex(store)
    res = {"sex": sex, "passage": pid, "word": word, "items": [], "not_applicable": [], "applicable": []}
    for it, term in match_items(task_text):
        row = {"id": it["id"], "label": it["label"], "applicable_sex": it["applicable_sex"], "term": term,
               "slots": list(it.get("slots") or []), "record_checks": list(it.get("record_checks") or [])}
        res["items"].append(row)
        if sex and sex != it["applicable_sex"]:
            res["not_applicable"].append(row)
        else:
            res["applicable"].append(row)
    return res


def not_applicable_card(store, row, sex, pid, word):
    passages = [pid] if pid else []
    return {"need": "applicability_%s" % row["id"], "slot": "applicability_%s" % row["id"],
            "label_en": row["label"], "shape": "applicability", "priority": "P1",
            "why": "Applicability table (rulebook/applicability.json): %s applies to %s patients only."
                   % (row["label"], row["applicable_sex"]),
            "sources": [], "rules": [], "origins": ["applicability"], "compute": "applicability",
            "status": "not_applicable",
            "value_en": "Not applicable: the record documents %s patient" % SEX_WORD.get(sex, sex),
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

"""Answer-first key facts (docs/DECISIONS.md 20).

The full screen (cards, history, P2 'also relevant', blind spot, other record issues) stays as it is, behind
one 'Show more' expander in the app.  This module picks, for every P1 need on the screen, the single best
current answer (the latest / most relevant item of the card, never new text) and returns at most MAX_LINES
compact lines:

  safety          age (calculated from the date of birth), sex and the allergies found (one line)
  need            one line per P1 need: 1-4 card items chosen by the need's shape (see select_items)
  not_documented  one line listing every P1 need the record does not document
  conflict        the counted contradiction this screen touches that is best documented (+N in the details)

Every line keeps the card items it shows (engine fact ids + passages), so every value stays linked to its
source sentence; a line is never paraphrased.  Lines over MAX_LINES are merged with a neighbour of the same
knowledge-base group (e.g. two oncology needs), never dropped.  Deterministic, no LLM.
"""
from __future__ import annotations

import re

MAX_LINES = 8
MAX_ITEMS = 4
MAX_CONFLICT_LINES = 1  # contradiction lines (the one about a shown need, best documented); the rest: +N in the details
SAFETY_CORE = ("age_sex", "allergies")
SKIP_NEEDS = ("disagreements",)  # the 'Letters disagree' card: details only (the conflict line points to it)
EXTRA_NEEDS = ("task_focus", "topic_")  # task focus / named topics: their first new items, only with room left
MAX_MEDS_ALL = 10  # med_current (whole list, e.g. medication reconciliation): the list is the answer
_WORD = re.compile(r"[a-zäöüß0-9]{4,}", re.I)
_STOP = {"with", "from", "that", "this", "your", "have", "what", "which", "when", "does", "after", "before",
         "about", "into", "under", "over", "they", "them", "their", "patient", "check", "review", "documented"}
_LEFT = re.compile(r"\b(left|links|sin\.)", re.I)
_RIGHT = re.compile(r"\b(right|rechts|dext\.)", re.I)


def _words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")} - _STOP


def _date(it) -> str:
    return str(it.get("date") or "")[:10]


def _question(it) -> bool:
    lab = (it.get("label_en") or "").strip()
    return (lab.lower().startswith("question:") or lab.endswith("?")
            or it.get("status_display") in ("suspected", "ruled out"))


def _cats(st, it) -> set[str]:
    return {st.fact_by_id[f].get("category") for f in it.get("facts") or [] if f in st.fact_by_id}


def primary_categories(k, slot: str) -> set[str]:
    """Categories of the slot map's non-context selectors: what the need is about (lvef -> lv_function)."""
    spec = k.slot_spec(slot) if k is not None and slot else {}
    return {c for sel in spec.get("select") or [] if sel.get("role") != "context" for c in sel.get("categories") or []}


def _relevance(it, terms: set[str]) -> int:
    return len(_words(it.get("label_en")) & terms)


def _more_specific(cur, earlier: list) -> dict:
    """The same statement worded more completely in a letter a few days older ('Invasive ductal carcinoma
    of the breast' -> '... (left)'): show that wording (its own date and passages)."""
    cw = _words(cur.get("label_en"))
    for e in earlier or []:
        ew = _words(e.get("label_en"))
        if cw and cw < ew and abs(_days(e, cur)) <= 31:
            return e
    return cur


def _days(a, b) -> int:
    from datetime import date
    try:
        da, db = (date.fromisoformat(_date(x)) for x in (a, b))
        return (da - db).days
    except ValueError:
        return 9999


def _side(it):
    lab = it.get("label_en") or ""
    lft, rgt = bool(_LEFT.search(lab)), bool(_RIGHT.search(lab))
    return "left" if lft and not rgt else "right" if rgt and not lft else None


def _has_value(it) -> bool:
    return bool(re.search(r"\d", re.sub(r"\d{1,2}[./]\d{1,2}[./]\d{2,4}", "", it.get("label_en") or "")))


def select_items(st, k, card: dict, terms: set[str], as_of: str | None = None) -> tuple[list, int]:
    """(chosen items, number of further items in the card) for one need, by the need's shape."""
    items = [it for it in card.get("items") or [] if not it.get("not_on_latest_list")]
    if not items:
        return [], 0
    shape = card.get("shape") or ""
    prim = primary_categories(k, card.get("slot"))
    confirmed = [it for it in items if not _question(it)] or items
    primary = [it for it in confirmed if _cats(st, it) & prim] or confirmed
    open_ = [it for it in primary if not it.get("collapsed")] or primary

    if shape == "current_list":
        chosen = open_[:MAX_MEDS_ALL if card.get("slot") == "med_current" else MAX_ITEMS]
    elif shape == "checklist":
        chosen = open_[:MAX_ITEMS]
    elif shape == "trend":
        dated = sorted([it for it in primary if _date(it)], key=_date)
        chosen = dated if len(dated) <= MAX_ITEMS else [dated[0]] + dated[-(MAX_ITEMS - 1):]
    elif shape == "latest_value":
        spec = k.slot_spec(card.get("slot")) if k is not None else {}
        if spec.get("latest_key"):  # one newest value per key (ER, PR, HER2, Ki-67)
            ranked = sorted(primary, key=lambda it: (not _has_value(it), primary.index(it)))
            chosen = sorted(ranked[:MAX_ITEMS], key=primary.index)
        else:
            newest = max(_date(it) for it in primary)
            top = [it for it in primary if _date(it) == newest]
            order = {id(it): i for i, it in enumerate(top)}
            top.sort(key=lambda it: (not _has_value(it), -len(it.get("docs") or []), order[id(it)]))
            chosen = [_more_specific(top[0], card.get("earlier"))] + top[1:2] if len(top) > 1 and _has_value(top[1]) \
                else [_more_specific(top[0], card.get("earlier"))]
    elif shape == "laterality_finding":
        weight = {}
        for it in confirmed:
            s = _side(it)
            if s:
                weight[s] = weight.get(s, 0) + len(it.get("passages") or [1])
        side = max(weight, key=weight.get) if weight else None
        cand = [it for it in confirmed if side is None or _side(it) in (side, None)]
        cand.sort(key=lambda it: (-(_side(it) is not None and _has_value(it)), -len(it.get("docs") or []),
                                  -int(_date(it).replace("-", "") or 0)))
        chosen = cand[:1]
        if cand and not _has_value(cand[0]):  # side without size: add the newest size
            sized = [it for it in cand if _has_value(it)]
            chosen += sized[:1]
    elif shape == "plan":
        future = [it for it in open_ if as_of and _date(it) > str(as_of)[:10] and it.get("status") == "planned"]
        pool = future or open_
        chosen = [max(pool, key=lambda it: (_date(it), -pool.index(it)))]
    elif shape == "event_history":
        newest = max(_date(it) for it in primary)[:7]  # latest episode (month) of the event
        pool = [it for it in primary if _date(it)[:7] == newest] or primary
        pool.sort(key=lambda it: (-len(it.get("docs") or []), -_relevance(it, terms), -len(it.get("label_en") or "")))
        other = [it for it in pool[1:] if not (_cats(st, it) & _cats(st, pool[0])) and _cats(st, it) & prim]
        chosen = pool[:1] + other[:1]  # the event, plus its documented cause / outcome when that is its own kind
    elif shape == "status_check":
        chosen = []  # the checklist rows are the answer (see key_facts)
    else:  # list_all, list and anything new: the items most related to the task, then newest
        pool = sorted(open_, key=lambda it: (-_relevance(it, terms), -int(_date(it).replace("-", "") or 0)))
        chosen = sorted(pool[:3], key=open_.index)
    chosen = [x for i, x in enumerate(chosen) if all(x is not y for y in chosen[:i])]
    shown = {id(x) for x in chosen}
    return chosen, sum(1 for it in items if id(it) not in shown)


def _line(kind, needs, label, items=(), computed=(), text=None, passages=(), more=0, group=None, trust=None):
    return {"kind": kind, "needs": list(needs), "label": label, "items": list(items), "computed": list(computed),
            "text": text, "passages": list(dict.fromkeys(passages)), "more": more, "group": group,
            "trust": trust}


def _fact_ids(items) -> set[str]:
    return {f for it in items for f in it.get("facts") or []}


def safety_line(cards: list, patient: dict) -> dict | None:
    by = {c.get("slot") or c.get("need"): c for c in cards}
    age, allergy = by.get("age_sex"), by.get("allergies")
    if not age and not allergy:
        return None
    computed, passages, needs, text = [], [], [], []
    if age:
        needs.append("age_sex")
        calc = age.get("calculated") or {}
        if calc.get("kind") == "age" and age.get("items"):
            computed.append({"label": "Age", "value": "%d years" % calc["age"],
                             "formula": "full years from the date of birth %s to %s" % (calc["dob"], calc["at"]),
                             "passages": list(age["items"][0].get("passages") or [])})
        if patient.get("sex") and patient.get("sex_passage"):
            text.append(patient["sex"])
            passages.append(patient["sex_passage"])
    items = []
    if allergy:
        needs.append("allergies")
        if allergy.get("status") == "not_documented":
            text.append("allergies not documented")
        else:
            items = [it for it in allergy.get("items") or [] if not it.get("collapsed")][:MAX_ITEMS]
    return _line("safety", needs, "Age, sex, allergies", items, computed, ", ".join(text) or None, passages,
                 trust=allergy.get("status") if allergy else None)


def status_check_line(card: dict) -> dict | None:
    rows = card.get("checklist") or []
    if not rows:
        return None
    computed = []
    for r in rows:
        if not r.get("passages"):
            continue
        val = {"found": "documented", "documented_none": "documented as none"}.get(r["status"], "not documented")
        computed.append({"label": r["label"], "value": (r.get("note") or val)[:1].upper() + (r.get("note") or val)[1:],
                         "formula": "searched every fact of the matching kind after the recommendation",
                         "passages": list(r["passages"])})
    return _line("need", [card["need"]], card.get("label_en") or card["need"], computed=computed,
                 group=card.get("group_kb"), trust=card.get("status")) if computed else None


def question_line(card: dict) -> dict:
    """A 'Your question: X' card (engine/ask.py): its facts, its verbatim passages, or 'Nothing found ...'."""
    if card.get("status") == "not_documented":
        return _line("not_documented", [card["need"]], card["label_en"], text=card.get("value_en"))
    items = card.get("items") or []
    computed = [{"label": c["label"], "value": c["value"], "formula": c.get("formula") or "",
                 "passages": list(c.get("passages") or [])} for c in card.get("computed_lines") or []][:2]
    more = max(0, len(items) - MAX_ITEMS) + len(card.get("computed_lines") or []) - len(computed)
    return _line("need", [card["need"]], card["label_en"], items[:MAX_ITEMS], computed, more=more,
                 trust=card.get("status"))


def key_facts(st, k, cards: list, focus: list, contradictions: list, patient: dict, terms_text: str,
              as_of: str | None = None, mode: str = "task") -> list[dict]:
    """Ordered key-fact lines for one screen ([] on gated / not-applicable screens)."""
    if mode in ("not_applicable", "not_authorised", "needs_task") or not cards:
        return []
    terms = _words(terms_text)
    groups = {s["id"]: s.get("group") for s in (k.data.get("slots") if k is not None else []) or []}
    lines, nd, shown, stats_shown = [], [], set(), set()
    safety = safety_line(cards, patient or {})
    if safety:
        lines.append(safety)
        shown |= _fact_ids(safety["items"])
    asked = [question_line(c) for c in focus if c.get("group") == "question"]  # the user's own question first
    lines += asked
    shown |= {f for ln in asked for f in _fact_ids(ln["items"])}
    reserved = (1 if any(c.get("status") == "not_documented" and c.get("need") not in SAFETY_CORE for c in cards)
                else 0) + (1 if _conflict(contradictions) else 0)
    extras = [x for x in focus if str(x.get("need", "")).startswith(EXTRA_NEEDS)]
    for c in cards + extras:
        need = c.get("need")
        if need in SAFETY_CORE or need in SKIP_NEEDS or c.get("priority") not in (None, "P1"):
            continue
        if c.get("status") == "not_documented":
            nd.append(c)
            continue
        if c.get("status") == "not_applicable":
            continue
        topic = str(need).startswith(EXTRA_NEEDS)
        if c.get("shape") == "status_check":
            ln = status_check_line(dict(c, group_kb=groups.get(c.get("slot"))))
            if ln:
                lines.append(ln)
            continue
        chosen, more = select_items(st, k, c, terms, as_of)
        fresh = [it for it in chosen if not set(it.get("facts") or []) <= shown]
        if chosen and not fresh and not str(need).startswith(EXTRA_NEEDS):  # answered by an earlier line already:
            rest = [it for it in (c.get("items") or []) + (c.get("earlier") or [])  # its next own answer instead
                    if not _question(it) and not set(it.get("facts") or []) <= shown and not it.get("not_on_latest_list")]
            fresh = rest[:1]
        if topic:  # task focus / named topic: only what no slot line already answers, and only with room left
            if not fresh or len(lines) + reserved >= MAX_LINES:
                continue
            fresh = fresh[:2]
        computed = []
        if c.get("shape") == "trend" and c.get("calculated") and len(fresh) >= 2:
            calc, first, last = c["calculated"], fresh[0], fresh[-1]
            from .fill import change_text
            computed.append({"label": "Change", "value": change_text(calc),
                             "formula": "%s; %s" % (calc.get("method") or "last minus first", "inputs linked"),
                             "passages": list(dict.fromkeys((first.get("passages") or []) + (last.get("passages") or [])))})
        if not fresh:
            continue
        # statistics of the card (engine/stats.py): daily dose change, the newest letter's BMI check, BP day/night
        for s in c.get("computed_lines") or []:  # each statistic once per screen
            if s.get("stat") and s.get("key") and s.get("passages") and (s["label"], s["value"]) not in stats_shown:
                stats_shown.add((s["label"], s["value"]))
                computed.append({"label": s["label"], "value": s["value"], "formula": s.get("formula") or "",
                                 "passages": list(s["passages"])})
        shown |= _fact_ids(fresh)
        lines.append(_line("need", [need], c.get("label_en") or need, fresh, computed,
                           more=more + len(chosen) - len(fresh), group=groups.get(c.get("slot")),
                           trust=c.get("status")))
    lines = _merge(lines, MAX_LINES - reserved)
    if nd:
        lines.append(_line("not_documented", [c["need"] for c in nd], "Not documented",
                           text="; ".join(c.get("label_en") or c["need"] for c in nd)))
    cf = _conflict(contradictions)
    room = max(1, min(MAX_CONFLICT_LINES, MAX_LINES - len(lines))) if cf else 0
    for i, c in enumerate(cf[:room]):
        lines.append(_line("conflict", [], "Letters disagree", text=c.get("title_en") or "Contradiction",
                           passages=c.get("passages") or [], more=len(cf) - room if i == room - 1 else 0,
                           trust="conflicting"))
    return lines


def _conflict(contradictions):
    counted = [c for c in contradictions or [] if c.get("counted", True) and c.get("relevant", True)]
    # one about a shown need first, then the best documented (most passages)
    return sorted(counted, key=lambda c: (not c.get("slots"), -len(c.get("passages") or [])))


def _merge(lines: list, cap: int) -> list:
    """Over the cap: merge the neighbouring pair of need lines of the same KB group with the fewest items."""
    lines = list(lines)
    while len(lines) > cap:
        best = None
        for i in range(len(lines) - 1):
            a, b = lines[i], lines[i + 1]
            if a["kind"] == b["kind"] == "need" and a["group"] and a["group"] == b["group"]:
                n = len(a["items"]) + len(b["items"]) + len(a["computed"]) + len(b["computed"])
                if best is None or n < best[0]:
                    best = (n, i)
        if best is None:
            break
        i = best[1]
        a, b = lines[i], lines[i + 1]
        lines[i:i + 2] = [_line("need", a["needs"] + b["needs"], "%s · %s" % (a["label"], b["label"]),
                                a["items"] + b["items"], a["computed"] + b["computed"], more=a["more"] + b["more"],
                                group=a["group"], trust=a["trust"] if a["trust"] == b["trust"] else "mixed")]
    return lines

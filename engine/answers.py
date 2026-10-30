"""Answer lines (docs/DECISIONS.md 22): a thin header + 3-4 one-sentence answers, the rest behind 'Show more'.

The RULES pick, the LLM only writes, CODE verifies:

  pick_lines()   deterministic.  Candidates in knowledge-base order: the P1 slots of every task bundle (bundle by
                 bundle; a composite bundle such as B05 'contrast safety', rulebook/kb_overlay.json
                 `answer_composites`, is ONE need made of its P1 slots), then the request's named topics, then the
                 other P1 cards (role modifiers).  The first need of every bundle and of the named topics keeps a
                 seat.  A need is skipped when an earlier line already shows its answer (same facts, same values and
                 words, or the same episode of an event).  Not-documented needs are lines of their own (neighbours
                 merged); a not-documented slot inside a composite stays in that line ("kidney function not
                 documented" under contrast safety); a laterality need touched by a counted laterality contradiction
                 carries the minority side ("one letter says right").  Over MAX_LINES: neighbouring needs of the
                 same KB group and shape are merged (two per line), then the last unreserved needs go to 'Show
                 more'.  The header (age · sex · allergies) is not counted.
  template()     deterministic one-line sentence per need shape (current regimen, latest value + date, trend,
                 event + cause, laterality, plan + date, list, follow-up status, not documented, composite).
  write()        optional, one batched Claude Haiku call per request (engine/llm.py conventions: cached system
                 prompt with style rules and few-shot examples on other facts, thinking off, effort low, small
                 max_tokens, deadline SECOND_LOOK_LLM_TIMEOUT, budget guard, cache by (need ids, fact ids)).  The
                 model receives each line's facts (label, value attrs, date, status) and returns one sentence per
                 line id.  It never selects, drops, reorders or adds needs or facts.  SECOND_LOOK_ANSWERS_LLM=0
                 turns only the writer off (templates; the gate reading stays).
  verify()       every number / date token and month name of the sentence must be in that line's facts (labels,
                 attrs, dates, computed values); every drug or diagnosis word known to the record or the KB must
                 be in that line's facts; every fact must still be named; 'not documented' only for a line that
                 has a not-documented need.  Failure, timeout, no key or budget stop -> the template.

Every line keeps its passages (Source opens the letter highlighted) and records text, needs, fact ids,
origin ('llm' | 'template') and verified.
"""
from __future__ import annotations

import json
import os
import re
import time

from . import keyfacts as K

MAX_LINES = 4
HEADER_NEEDS = ("age_sex", "allergies")
SKIP_NEEDS = ("disagreements",)
MAX_LIST = 3
MAX_CHARS = 260
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
_MONTH_RX = re.compile(r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
                       r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b\.?", re.I)
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_DATE_IN = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")
_ND_RX = re.compile(r"not documented|no record|not recorded|undocumented|none documented|not found|no (?:documented|"
                    r"evidence)|missing", re.I)
_LATER_RX = re.compile(r"no (?:later|newer|more recent|further) (?:value|result|measurement)s?", re.I)
_WORDS = re.compile(r"[^\W\d_][\w'-]*", re.U)


# ----------------------------------------------------------------- small helpers

def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _low(s: str) -> str:
    """Lower-case the first letter of a label continuing a sentence ('Oestrogen ...' -> 'oestrogen ...'),
    never an acronym ('HER2', 'TNM', 'LVEF')."""
    w = (s.split() or [""])[0].replace("-", "")
    if len(w) > 1 and w.isalpha() and w[0].isupper() and w[1:].islower():
        return s[0].lower() + s[1:]
    return s


def fmt_date(d: str | None, precision: str | None = "day") -> str:
    d = str(d or "")[:10]
    m = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?", d)
    if not m:
        return ""
    y, mo, dd = m.group(1), int(m.group(2)), m.group(3)
    if precision in ("year",):
        return y
    if precision == "month" or not dd:
        return "%s %s" % (MONTHS[mo - 1], y)
    return "%d %s %s" % (int(dd), MONTHS[mo - 1], y)


def _has_date(label: str) -> bool:
    return bool(_DATE_IN.search(label or "") or re.search(r"\b\d{2}/\d{4}\b", label or ""))


def _item_date(it) -> str:
    return fmt_date(it.get("date"), it.get("date_precision") or "day")


def _canon_num(t: str) -> str:
    t = t.replace(",", ".")
    if "." in t:
        t = t.rstrip("0").rstrip(".") or "0"
        return t if "." in t else str(int(t))
    return str(int(t))


def _nums(text: str) -> set[str]:
    text = text or ""
    out = {_canon_num(x) for d in _DATE_IN.findall(text) for x in d}
    return out | {_canon_num(x) for x in _NUM.findall(_DATE_IN.sub(" ", text))}


def _value_nums(label: str) -> set[str]:
    """Numbers of a label that are values, not dates."""
    return _nums(re.sub(r"\b\d{1,2}/\d{1,2}/\d{4,5}\b|\b\d{1,2}/\d{4}\b", " ", _DATE_IN.sub(" ", label or "")))


def _stem(w: str) -> str:
    return w.lower()[:6]


def _sig_words(text: str) -> set[str]:
    return {_stem(w) for w in _WORDS.findall(text or "") if len(w) >= 5 and w.lower() not in COMMON}


# ----------------------------------------------------------------- picking (deterministic)

def _composites(k) -> dict:
    ov = getattr(k, "overlay", None) or {}
    return ov.get("answer_composites") or {}


def _topic_slots(k, topic_ids) -> list[str]:
    ov = getattr(k, "overlay", None) or {}
    out = []
    for tp in ov.get("topics") or []:
        if tp.get("id") in (topic_ids or []):
            out += [s for s in tp.get("slots") or [] if s not in out]
    return out


def _bundle_words(k, bid) -> set[str]:
    b = k.bundle_by_id.get(bid) or {}
    txt = " ".join([b.get("title") or "", b.get("description") or ""] + list(b.get("tags_en") or [])
                   + list((b.get("why_overrides") or {}).values()))
    return {w.lower() for w in _WORDS.findall(txt) if len(w) >= 4} - K._STOP


def _item_words(st, it) -> set[str]:
    txt = [it.get("label_en") or ""]
    for f in it.get("facts") or []:
        a = (st.fact_by_id.get(f) or {}).get("attrs") or {}
        txt += [str(a.get(x) or "") for x in ("generic", "brand", "substance", "test")]
    return {w.lower() for w in _WORDS.findall(" ".join(txt)) if len(w) >= 4}


def _relevant(st, items, words, n):
    """Items sharing a word with the composite's own KB text (contrast -> the native CT, metformin), newest first;
    all of them when none does."""
    rel = [it for it in items if _item_words(st, it) & words]
    pool = rel or items
    pool = sorted(pool, key=lambda it: (-len(_item_words(st, it) & words), -int(K._date(it).replace("-", "") or 0)))
    return sorted(pool[:n], key=items.index) if rel else pool[:n]


def _laterality_note(st, k, card, contras, chosen=()):
    """Counted laterality contradiction touching this need -> ('one letter (...) says right', passages)."""
    facts = set(card.get("facts") or []) | {f for it in card.get("items") or [] for f in it.get("facts") or []}
    concepts = ({(st.fact_by_id.get(f) or {}).get("category") for it in chosen for f in it.get("facts") or []}
                & K.primary_categories(k, card.get("slot"))) - {None, "diagnosis"}
    for c in contras or []:
        if c.get("kind") != "laterality" or not c.get("counted", True):
            continue
        if not (set(c.get("facts") or []) & facts or card.get("slot") in (c.get("slots") or [])):
            continue
        sides = {}
        for cl in c.get("claims") or []:
            concept, _sep, side = str(cl.get("asserted") or "").partition(":")
            side = side.strip().lower()
            if concepts and concept.strip() not in concepts:
                continue
            if side in ("left", "right"):
                sides.setdefault(side, []).append(cl)
        if len(sides) < 2:
            continue
        minority = min(sides, key=lambda s: len(sides[s]))
        docs = {cl.get("doc_id") for cl in sides[minority]} - {None}
        m = re.search(r":\s*(.+?) says (?:LEFT|RIGHT)", c.get("title_en") or "")
        where = m.group(1) if m else ("%d letter(s)" % len(docs))
        note = "one letter (%s) says %s" % (where, minority) if len(docs) == 1 else "%s say %s" % (where, minority)
        return note, [cl.get("passage_id") for cl in sides[minority] if cl.get("passage_id")], minority
    return None


def _event_enrich(st, chosen, cards):
    """Event + cause: add the best-quantified statement of the cause (the shortest item on a shown P1 card that
    names the cause's words with a value, e.g. 'Carotid artery stenosis, left, 60%')."""
    cause = next((it for it in chosen for f in it.get("facts") or []
                  if (st.fact_by_id.get(f) or {}).get("category") == "attributed_cause"), None)
    if not cause:
        return chosen
    words = _sig_words(" ".join(str((st.fact_by_id[f].get("attrs") or {}).get("cause") or "")
                                for f in cause["facts"] if f in st.fact_by_id) or cause.get("label_en"))
    best = None
    for c in cards:
        for it in c.get("items") or []:
            if it in chosen or it.get("collapsed") or K._question(it) or not K._has_value(it):
                continue
            if len(_sig_words(it.get("label_en")) & words) >= min(2, len(words)):
                key = (len(it.get("label_en") or ""), -len(it.get("docs") or []))
                if best is None or key < best[0]:
                    best = (key, it)
    return chosen + [best[1]] if best else chosen


def _need(kind, needs, label, shape, group, items=(), computed=(), missing=(), note=None, note_passages=(),
          rows=(), reserved=False, slot_labels=(), side=None):
    return {"kind": kind, "needs": list(needs), "label": label, "shape": shape, "group": group,
            "items": list(items), "computed": list(computed), "missing": list(missing), "note": note,
            "note_passages": list(note_passages or []), "rows": list(rows), "reserved": reserved,
            "slot_labels": list(slot_labels), "side": side, "parts": None}


def _card_need(st, k, c, terms, as_of, cards, contras, reserved, groups, shown=frozenset()):
    """One P1 card -> one need (or None)."""
    shape = c.get("shape") or ""
    label = c.get("label_en") or c.get("need")
    grp = groups.get(c.get("slot"))
    if c.get("status") == "not_documented":
        return _need("not_documented", [c["need"]], label, "not_documented", None, missing=[label],
                     reserved=reserved, slot_labels=[label])
    if c.get("status") == "not_applicable":
        return None
    if shape == "status_check":
        rows = [r for r in c.get("checklist") or [] if r.get("passages")]
        return _need("need", [c["need"]], label, shape, grp, rows=rows, reserved=reserved, slot_labels=[label],
                     missing=[r["label"] for r in rows if r.get("status") == "not_documented"]) if rows else None
    chosen, _more = K.select_items(st, k, c, terms, as_of)
    fresh = [it for it in chosen if not set(it.get("facts") or []) <= shown]
    chosen = fresh or chosen  # an item an earlier line shows is not repeated (all shown: _covered skips the need)
    if not chosen:
        return None
    computed, note, npass, side = [], None, [], None
    if shape == "trend" and c.get("calculated") and len(chosen) >= 2:
        calc = c["calculated"]
        computed.append({"label": "Change", "value": "%+g %s over %d months" % (calc["change"], calc.get("unit") or "",
                                                                             calc["months"]),
                         "change": calc["change"], "unit": calc.get("unit") or "", "months": calc["months"],
                         "passages": list(dict.fromkeys((chosen[0].get("passages") or [])
                                                        + (chosen[-1].get("passages") or [])))})
    if shape == "event_history":
        chosen = _event_enrich(st, chosen, cards)
    if shape == "laterality_finding":
        weight = {}
        for it in c.get("items") or []:
            s = K._side(it)
            if s and not K._question(it):
                weight[s] = weight.get(s, 0) + len(it.get("passages") or [1])
        side = max(weight, key=weight.get) if weight else None
        ln = _laterality_note(st, k, c, contras, chosen)
        if ln:
            note, npass, _minor = ln
    if shape in ("list_all", "list"):
        chosen = _dedupe_numbers(chosen)[:MAX_LIST]
    return _need("need", [c["need"]], label, shape, grp, chosen, computed, note=note, note_passages=npass,
                 reserved=reserved, slot_labels=[label], side=side)


def _dedupe_numbers(items):
    """List items whose dates/numbers and words are all inside another item's ('Discharged on 14.06.2015' inside
    'admitted 10/06/2015, discharged 14/06/2015') are left out."""
    out = []
    for it in items:
        n, w = _nums(it.get("label_en")), _sig_words(it.get("label_en"))
        if any(o is not it and n and n <= _nums(o.get("label_en")) and w - {"discha", "admitt"} <= _sig_words(o.get("label_en"))
               | {"discha", "admitt"} and len(o.get("label_en") or "") > len(it.get("label_en") or "") for o in items):
            continue
        out.append(it)
    return out


def _composite_need(st, k, bid, spec, by_slot, terms, as_of, contras, reserved, shown=frozenset()):
    b = k.bundle_by_id.get(bid) or {}
    words = _bundle_words(k, bid)
    parts, missing, labels = [], [], []
    for slot in (b.get("slots") or {}).get("P1") or []:
        c = by_slot.get(slot)
        if not c:
            continue
        labels.append(c.get("label_en") or slot)
        if c.get("status") == "not_documented":
            missing.append(spec.get("missing_labels", {}).get(slot) or c.get("label_en") or slot)
            continue
        if c.get("status") == "not_applicable":
            continue
        pool = [it for it in c.get("items") or [] if not it.get("collapsed") and not K._question(it)
                and not it.get("not_on_latest_list") and not set(it.get("facts") or []) <= shown]
        if c.get("shape") == "current_list":
            chosen = _relevant(st, pool, words, 3)
        elif c.get("shape") == "trend":
            chosen, _m = K.select_items(st, k, c, terms, as_of)
        else:
            chosen = _relevant(st, pool, words, 1)
        if chosen:
            parts.append({"slot": slot, "shape": c.get("shape"), "items": chosen})
    if not parts and not missing:
        return None
    n = _need("composite", [p["slot"] for p in parts] + [s for s in (b.get("slots") or {}).get("P1") or []
                                                          if by_slot.get(s, {}).get("status") == "not_documented"],
              spec.get("label") or b.get("title") or bid, "composite", None,
              [it for p in parts for it in p["items"]], missing=missing, reserved=reserved, slot_labels=labels)
    n["parts"] = parts
    n["bundle"] = bid
    return n


def _shown_words(lines):
    w, n = set(), set()
    for ln in lines:
        for it in ln["items"]:
            w |= _sig_words(it.get("label_en"))
            n |= _value_nums(it.get("label_en"))
    return w, n


def _covered(need, lines, shown_facts) -> bool:
    """An earlier line already shows this need's answer."""
    if need["kind"] in ("not_documented",) or need["shape"] == "status_check":
        return False
    ids = {f for it in need["items"] for f in it.get("facts") or []}
    if ids and ids <= shown_facts:
        return True
    if need["shape"] == "event_history":  # one line per episode: same month as an earlier event line
        months = {K._date(it)[:7] for it in need["items"] if K._date(it)}
        for ln in lines:
            if ln["shape"] == "event_history" and months & {K._date(it)[:7] for it in ln["items"] if K._date(it)}:
                return True
    w, n = _shown_words(lines)
    for it in need["items"]:
        if not (_sig_words(it.get("label_en")) <= w and _value_nums(it.get("label_en")) <= n):
            return False
    return bool(need["items"])


def _question_need(c) -> dict:
    """A 'Your question: X' card (engine/ask.py): its facts, or its verbatim passages, or 'Nothing found'."""
    if c.get("status") == "not_documented":  # 'Nothing found for X ...': kept as written, never sent to the LLM
        n = _need("nothing", [c["need"]], c.get("label_en") or c["need"], "nothing", None, reserved=True,
                  missing=[c.get("label_en") or c["need"]])
        n["fixed_text"] = c.get("value_en") or "Nothing found."
        return n
    items = [it for it in c.get("items") or [] if not it.get("collapsed")][:MAX_LIST]
    quotes = [{"label": q["label"], "value": q["value"], "passages": list(q.get("passages") or [])}
              for q in (c.get("computed_lines") or [])[:2]]
    n = _need("need", [c["need"]], c.get("label_en") or c["need"], "question", None, items, reserved=True)
    n["quotes"] = quotes
    return n


def pick_lines(st, k, cards: list, u: dict, contras: list, terms_text: str, as_of: str | None,
               mode: str = "task", focus=(), cap: int = MAX_LINES) -> list[dict]:
    """-> ordered answer needs (<= cap, default MAX_LINES), each with its chosen items.  Deterministic.  The user's own
    question comes first (question cards of engine/ask.py, then the KB slots a question named); a question-only
    screen shows nothing else."""
    if mode in ("not_applicable", "not_authorised", "needs_task") or not cards:
        return []
    questions = [_question_need(c) for c in focus or () if c.get("group") == "question"]
    terms = K._words(terms_text)
    groups = {s["id"]: s.get("group") for s in (k.data.get("slots") if k is not None else []) or []}
    by_slot = {}
    for c in cards:
        if c.get("priority") in (None, "P1") and c.get("need") not in SKIP_NEEDS:
            by_slot.setdefault(c.get("slot") or c.get("need"), c)
    comps = _composites(k)
    order, used = [], set(HEADER_NEEDS)
    for slot in u.get("asked_slots") or []:  # a KB slot answering the question (pacemaker -> cardiac_device)
        if slot in by_slot and slot not in used:
            order.append(("slot", slot, True))
            used.add(slot)
    q_only = bool(u.get("question_only"))
    for bid in ([] if q_only else u.get("bundle_ids") or []):
        b = k.bundle_by_id.get(bid) or {}
        first = True
        if bid in comps:
            order.append(("composite", bid, True))
            used |= set((b.get("slots") or {}).get("P1") or [])
            continue
        for slot in (b.get("slots") or {}).get("P1") or []:
            if slot in by_slot and slot not in used:
                order.append(("slot", slot, first))
                used.add(slot)
                first = False
    first = True
    for slot in _topic_slots(k, u.get("named_topics")):
        if slot in by_slot and slot not in used:
            order.append(("slot", slot, first))
            used.add(slot)
            first = False
    for slot in ([] if q_only else by_slot):
        if slot not in used:
            order.append(("slot", slot, False))
            used.add(slot)

    head = K.safety_line(cards, {})
    lines, shown = list(questions), {f for it in (head or {}).get("items") or [] for f in it.get("facts") or []}
    shown |= {f for q in questions for it in q["items"] for f in it.get("facts") or []}
    for kind, key, reserved in order:
        if kind == "composite":
            n = _composite_need(st, k, key, comps[key], by_slot, terms, as_of, contras, reserved, shown)
        else:
            n = _card_need(st, k, by_slot[key], terms, as_of, cards, contras, reserved, groups, shown)
        if not n or _covered(n, lines, shown):
            continue
        shown |= {f for it in n["items"] for f in it.get("facts") or []}
        lines.append(n)
    lines = _merge_nd(lines)
    return _fit(lines, cap)


def _merge_nd(lines):
    out = []
    for ln in lines:
        if out and ln["kind"] == out[-1]["kind"] == "not_documented":
            p = out[-1]
            out[-1] = dict(p, needs=p["needs"] + ln["needs"], missing=p["missing"] + ln["missing"],
                           label="Not documented", reserved=p["reserved"] or ln["reserved"],
                           slot_labels=p["slot_labels"] + ln["slot_labels"])
        else:
            out.append(ln)
    return out


def _fit(lines, cap):
    lines = list(lines)
    while len(lines) > cap:  # merge neighbouring needs of the same KB group and shape, two per line
        for i in range(len(lines) - 1):
            a, b = lines[i], lines[i + 1]
            if (a["kind"] == b["kind"] == "need" and a["group"] and a["group"] == b["group"]
                    and a["shape"] == b["shape"] and len(a["needs"]) == len(b["needs"]) == 1):
                lines[i:i + 2] = [dict(a, needs=a["needs"] + b["needs"], label="%s · %s" % (a["label"], b["label"]),
                                       parts=[dict(a), dict(b)], kind="merged", reserved=a["reserved"] or b["reserved"],
                                       items=a["items"] + b["items"], computed=a["computed"] + b["computed"],
                                       missing=a["missing"] + b["missing"],
                                       slot_labels=a["slot_labels"] + b["slot_labels"])]
                break
        else:
            break
    while len(lines) > cap:  # the rest stays under 'Show more'
        drop = next((i for i in range(len(lines) - 1, -1, -1) if not lines[i]["reserved"]), len(lines) - 1)
        del lines[drop]
    return lines


# ----------------------------------------------------------------- templates (deterministic)

def _schedule_meaning(k, sched):
    for d in (k.data.get("schedule_decode") if k is not None else []) or []:
        if sched in (d.get("display"), d.get("raw")):
            return d.get("meaning")
    return None


def _med(st, it, k=None, meaning=False) -> str:
    rep = next((st.fact_by_id[f] for f in it.get("facts") or [] if f in st.fact_by_id), {})
    a = rep.get("attrs") or {}
    if not a.get("generic") or not a.get("dose"):
        return _low(it.get("label_en") or "")
    name = a["generic"] + (" (%s)" % a["brand"] if a.get("brand") else "")
    bits = [name, a["dose"]]
    if a.get("route") and a["route"] != "oral":
        bits.append(a["route"])
    if a.get("schedule"):
        bits.append(a["schedule"])
        m = _schedule_meaning(k, a["schedule"]) if meaning else None
        if m:
            bits[-1] += " (%s)" % m
    return " ".join(bits)


def _meds(st, k, items) -> str:
    ms = [_med(st, it, k) for it in items]
    return ms[0] if len(ms) == 1 else ", ".join(ms[:-1]) + " and " + ms[-1]


def _join(parts, sep="; "):
    return sep.join(p for p in parts if p)


def _with_date(label, it) -> str:
    d = _item_date(it)
    return label if not d or _has_date(label) else "%s, %s" % (label, d)


def _part_text(st, k, n) -> str:
    shape, items = n["shape"], n["items"]
    if n["kind"] == "not_documented":
        ls = [_low(x) for x in n["missing"]]
        return ("%s not documented" % _cap(ls[0])) if len(ls) == 1 else "Not documented: " + ", ".join(ls)
    if shape == "current_list":
        newest = max((it for it in items), key=lambda it: K._date(it))
        return "%s, as of %s" % (_cap(_meds(st, k, items)), fmt_date(newest.get("date"), "month"))
    if shape == "trend":
        vals = []
        for i, it in enumerate(items):
            rep = next((st.fact_by_id[f] for f in it.get("facts") or [] if f in st.fact_by_id), {})
            a = rep.get("attrs") or {}
            v = it.get("label_en") if i == 0 or not a.get("value") else "%s %s" % (a["value"], a.get("unit") or "")
            vals.append("%s (%s)" % (v.strip(), _item_date(it)))
        txt = ", ".join(vals)
        for c in n["computed"]:
            txt += "; change %+g %s over %d months" % (c["change"], c["unit"], c["months"])
        return txt
    if shape == "status_check":
        nf = [r for r in n["rows"] if r.get("status") == "not_documented"]
        fd = [r for r in n["rows"] if r.get("status") != "not_documented"]
        out = []
        if nf:
            m = re.search(r"after (\S+)", nf[0].get("note") or "")
            out.append("No record that %s took place%s" % (
                " or ".join("the " + _short_followup(st, r["label"]) for r in nf),
                " after %s" % m.group(1) if m else ""))
        for r in fd:
            note = re.sub(r"^documented after \S+:\s*", "", r.get("note") or "", flags=re.I)
            out.append("later documented: %s" % _low(note) if note else "%s documented" % _low(r["label"]))
        return _cap(_join(out))
    if shape == "event_history":
        first = items[0]
        d = _item_date(first)
        d = fmt_date(first.get("date"), "month") if d else ""
        body = _join([_low(it.get("label_en") or "") for it in items])
        return "%s: %s" % (d, body) if d else _cap(body)
    if shape == "laterality_finding":
        lab = items[0].get("label_en") or ""
        txt = _with_date(lab, items[0])
        if n.get("side") and not K._side(items[0]):
            txt = "%s side: %s" % (_cap(n["side"]), _low(txt))
        txt += "".join("; " + _with_date(_low(it.get("label_en") or ""), it) for it in items[1:])
        if n.get("note"):
            txt += "; " + n["note"]
        return _cap(txt)
    if shape in ("list_all", "list", "checklist"):
        dates = {_item_date(it) for it in items}
        body = "; ".join(_low(re.sub(r"^[A-Z][a-z]+(?: [a-z]+)?: ", "", it.get("label_en") or "")) for it in items)
        return "%s: %s%s" % (n["label"], body, " (%s)" % dates.pop() if len(dates) == 1 and "" not in dates else "")
    # latest_value, plan and anything else: the chosen statement(s) with their date
    if len(items) == 1:
        return _cap(_with_date(items[0].get("label_en") or "", items[0]))
    newest = max(items, key=lambda it: K._date(it))
    return _cap(", ".join(_low(it.get("label_en") or "") if i else it.get("label_en") or ""
                          for i, it in enumerate(items))) + ", %s" % _item_date(newest)


def _short_followup(st, label) -> str:
    """'Follow-up carotid duplex ultrasound in 2 months' -> 'carotid duplex ultrasound' (the fact's own 'test')."""
    for f in st.facts:
        if f.get("label_en") == label and (f.get("attrs") or {}).get("test"):
            return str(f["attrs"]["test"])
    return _low(re.sub(r"\s+recommended$", "", label))


def template(st, k, n) -> str:
    if n["kind"] == "nothing":
        return n["fixed_text"]
    if n["shape"] == "question":
        if n["items"]:
            return "%s: %s." % (n["label"], _join([_with_date(_low(it.get("label_en") or ""), it) for it in n["items"]]))
        q = n.get("quotes") or []
        return "%s: mentioned in %s%s." % (n["label"], " and ".join(x["label"].lower() for x in q) or "the letters",
                                           " (quoted under 'Show more')" if q else "")
    if n["kind"] == "merged":
        a, b = n["parts"][0], n["parts"][-1]
        if a["shape"] == b["shape"] == "current_list":  # one regimen, one 'as of'
            return _part_text(st, k, dict(a, items=n["items"])).rstrip(".") + "."
        parts = [_part_text(st, k, p).rstrip(".") for p in n["parts"]]
        if a["shape"] == b["shape"] == "plan" and len(b["items"]) == 1 and b["items"][0].get("date"):
            # the same procedure recommended, then scheduled: 'recommendation ...; planned for 16 May 2016'
            wa = {w for it in a["items"] for w in _sig_words(it.get("label_en"))}
            if len(wa & _sig_words(b["items"][0].get("label_en"))) >= 2:
                parts[-1] = "planned for %s" % _item_date(b["items"][0])
        return _join([(_low if i else _cap)(x) for i, x in enumerate(parts)]) + "."
    if n["kind"] == "composite":
        out = []
        for p in n["parts"]:
            if p["shape"] == "current_list":
                out.append("takes " + _meds(st, k, p["items"]))
            else:
                out.append(_join([_with_date(_low(it.get("label_en") or ""), it) for it in p["items"]]))
        if n["missing"]:
            out.append("%s not documented" % " and ".join(_low(x) for x in n["missing"]))
        return "%s: %s." % (n["label"], _join(out))
    return _part_text(st, k, n).rstrip(".") + "."


def header(st, cards, patient) -> dict | None:
    ln = K.safety_line(cards, patient or {})
    if not ln:
        return None
    parts, passages = [], []
    for c in ln["computed"]:
        parts.append(c["value"])
        passages += c["passages"]
    if ln.get("text"):
        parts += [x.strip() for x in ln["text"].split(",") if x.strip()]
        passages += ln["passages"]
    if ln["items"]:
        parts.append(", ".join(it.get("label_en") or "" for it in ln["items"]))
        passages += [p for it in ln["items"] for p in it.get("passages") or []]
    return {"kind": "header", "needs": ln["needs"], "label": "Age, sex, allergies", "text": " · ".join(parts),
            "fact_ids": sorted({f for it in ln["items"] for f in it.get("facts") or []}),
            "passages": list(dict.fromkeys(passages)), "origin": "template", "verified": True,
            "trust": ln.get("trust")}


# ----------------------------------------------------------------- what the writer may use (per line)

def _fact_payload(st, k, it) -> dict:
    rep = next((st.fact_by_id[f] for f in it.get("facts") or [] if f in st.fact_by_id), {})
    a = {x: v for x, v in (rep.get("attrs") or {}).items()
         if x not in ("confirmed_by_ibm", "schedule_mo_mi_ab_na", "unparsed", "context", "assertion") and v not in (None, "")}
    if a.get("schedule"):
        m = _schedule_meaning(k, a["schedule"])
        if m:
            a["schedule_meaning"] = m
    return {"label": it.get("label_en"), "attrs": a, "date": str(it.get("date") or "")[:10] or None,
            "date_precision": it.get("date_precision") or "day", "status": it.get("status_display") or it.get("status")}


def payload(st, k, n, lid) -> dict:
    p = {"id": lid, "need": n["label"], "facts": [_fact_payload(st, k, it) for it in n["items"]]}
    if n["computed"]:
        p["computed"] = [c["value"] for c in n["computed"]]
    if n["rows"]:
        p["follow_up_status"] = [{"recommendation": r["label"], "status": r.get("note")} for r in n["rows"]]
    if n["missing"]:
        p["not_documented"] = list(n["missing"])
    if n.get("note"):
        p["contradiction"] = n["note"]
    if n.get("side"):
        p["majority_side"] = n["side"]
    if n.get("quotes"):
        p["verbatim_passages"] = [{"letter": q["label"], "text": q["value"]} for q in n["quotes"]]
    return p


def allowed_text(st, k, n, labels=True) -> str:
    """Everything a sentence about this line may draw on (labels=False: the facts only, not the need labels)."""
    out = ([n["label"]] + list(n["slot_labels"]) if labels else []) + list(n["missing"])
    for it in n["items"]:
        fp = _fact_payload(st, k, it)
        out.append(fp["label"] or "")
        out += [json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v for v in fp["attrs"].values()]
        for f in it.get("facts") or []:
            fa = st.fact_by_id.get(f) or {}
            out += [str(v) for v in (fa.get("attrs") or {}).values() if isinstance(v, (str, int, float))]
    for c in n["computed"]:
        out.append(c["value"])
        if "change" in c:
            out.append("%g" % abs(c["change"]))
    for r in n["rows"]:
        out += [r.get("label") or "", r.get("note") or ""]
    if n.get("note"):
        out.append(n["note"])
    if n.get("side"):
        out.append(n["side"])
    for q in n.get("quotes") or []:
        out += [q["label"], q["value"]]
    out += [str(it.get("status_display") or it.get("status") or "") for it in n["items"]]
    return " ".join(out)


def _allowed_months(st, n, text) -> set[int]:
    ms = set()
    for it in n["items"]:
        m = re.match(r"\d{4}-(\d{2})", str(it.get("date") or ""))
        if m:
            ms.add(int(m.group(1)))
    for _d, mo, _y in _DATE_IN.findall(text):
        ms.add(int(mo))
    for m in re.findall(r"\b(\d{1,2})/\d{4}\b", text):
        ms.add(int(m))
    for m in _MONTH_RX.findall(text):
        ms.add(_month_no(m))
    return ms


def _month_no(name: str) -> int:
    name = name.lower().rstrip(".")[:3]
    return [m[:3].lower() for m in MONTHS].index(name) + 1


def _allowed_numbers(st, n, text) -> set[str]:
    nums = _nums(text)
    for it in n["items"]:
        m = re.match(r"(\d{4})-(\d{2})-?(\d{2})?", str(it.get("date") or ""))
        if m:
            nums |= {_canon_num(x) for x in m.groups() if x}
    return nums


# vocabulary of drug and diagnosis words the record or the KB knows: a sentence may use one only when its own
# facts do (catches an extra drug or another diagnosis)
COMMON = set("""
about above according acute added additional adjusted adjustment admission admitted after again against also among
amount another answer anything april around asked assessment august available based because before being below
between blood brief briefly carried cause caused cells change changed check checks clinical completed condition
confirmed contrast current currently daily date dated december diagnosed diagnosis discharge discharged documented
documents dose doses during earlier early either episode every evening evidence except february first follow
followed following found further given hospital however included including january july known later latest
left letter letters level levels listed lower march measured medication medications midday month months morning
night noted november number october once other patient performed period planned previous previously recommended
record recorded regular remains result results right scheduled second september several shows since single
specified stated status still taken takes taking there these three times today total treated treatment twice
under until value values visit weeks where which while within without years their about should would could
""".split())
_VOCAB = {}


def vocab(st, k) -> set[str]:
    key = (id(st), id(k))
    if key in _VOCAB:
        return _VOCAB[key]
    words = set()
    for f in st.facts:
        words |= _sig_words(f.get("label_en"))
        a = f.get("attrs") or {}
        for x in ("generic", "brand", "substance", "histotype", "cause"):
            if isinstance(a.get(x), str):
                words |= _sig_words(a[x])
    if k is not None:
        for s in k.data.get("slots") or []:
            words |= _sig_words(s.get("label")) | _sig_words(" ".join(s.get("hints_de") or []))
        for dc in k.data.get("drug_classes") or []:
            words |= _sig_words(re.sub(r"[(),]", " ", "%s %s" % (dc.get("generics") or "", dc.get("brands_examples") or "")))
        for tp in (getattr(k, "overlay", None) or {}).get("topics") or []:
            words |= _sig_words(" ".join((tp.get("terms") or {}).get("en") or []))
    _VOCAB[key] = words
    return words


# ALLOWLIST check (docs/DECISIONS.md 22): every token of a written sentence must come from that line's own facts or
# from this short list of connector words.  No negations, number words, side words or drug-class words here: those
# pass only when the line's own facts carry them.
FUNCTION_WORDS = frozenset("""
a an and or as at about also by both documented for from had has her in is are of on over per she since takes taking
the then to was were with lost gained current currently latest change dated yes which
""".split())
SCHEDULE_WORDS = {  # what a schedule may be spelt as, beside the schedule itself
    "1-0-0": "once daily in the morning", "0-1-0": "once daily at midday noon lunchtime",
    "0-0-1": "once daily in the evening at night", "0-0-0-1": "once daily at night bedtime",
    "1-0-1": "twice daily in the morning and evening", "1-1-1": "three times daily in the morning at midday and evening",
    "1-1-1-1": "four times daily", "1-1-0": "twice daily in the morning and at midday",
}
UNITS = {"%", "mg", "g", "kg", "µg", "ml", "l", "mmol", "mol", "cm", "mm", "mmhg", "iu", "ie", "months", "month",
         "years", "year", "days", "day", "weeks", "week", "seconds", "bpm", "ng", "dl"}
_SCHED_RX = re.compile(r"(?<![\d.-])\d(?:-\d){2,3}(?![\d-])")
_TOKEN_RX = re.compile(r"\d+(?:[.,]\d+)?|%|[^\W\d_]+", re.U)
_ND_PHRASES = re.compile(r"\b(?:(?:is|are|was|were)\s+)?not documented\b|\bno record(?: that)?\b", re.I)
_LATER_PHRASES = re.compile(r"\bno (?:later|newer|more recent) (?:value|result|measurement)s?(?: (?:is|was))?"
                            r"(?: documented)?\b", re.I)
_DATE_MENTION = re.compile(
    r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b|\b(?:(\d{1,2})\s+)?(%s)\.?\s+(\d{4})\b|\b(\d{1,2})/(\d{4})\b"
    % "|".join(m.lower() for m in MONTHS) + r"|" + r"\b(?:%s)\b" % "|".join(m[:3].lower() for m in MONTHS), re.I)


def _fold(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKC", str(text or "")).replace("μ", "µ")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c) or c == "µ")
    t = unicodedata.normalize("NFKC", t).replace("μ", "µ").lower()
    return re.sub(r"\b(?:mcg|ug)\b", "µg", t)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RX.findall(_SCHED_RX.sub(" ", _fold(text)))


def _num_unit_pairs(text: str) -> list[tuple[str, str | None, int]]:
    """(number, unit or None, position) for every value number (dates and schedules removed)."""
    t = _SCHED_RX.sub(lambda m: " " * len(m.group(0)), _fold(text))
    t = _DATE_MENTION.sub(lambda m: " " * len(m.group(0)), t)
    out = []
    for m in re.finditer(r"\d+(?:[.,]\d+)?", t):
        if t[m.start() - 1:m.start()].isalpha() or (m.start() > 0 and t[m.start() - 1] in "/"):
            unit = None  # 'T2', 'Ki-67', '145/88'
        nxt = re.match(r"\s*(%|[^\W\d_]+)", t[m.end():])
        unit = nxt.group(1) if nxt and nxt.group(1) in UNITS else None
        out.append((_canon_num(m.group(0)), unit, m.start()))
    return out


def _dates_in(text: str) -> list[tuple[int, int | None, int | None, int]]:
    """(year, month, day, position) of every full date mention ('13 June 2015', 'June 2015', '13.06.2015')."""
    out, t = [], _fold(text)
    for m in _DATE_MENTION.finditer(t):
        g = m.groups()
        if g[0]:
            out.append((int(g[2]), int(g[1]), int(g[0]), m.start()))
        elif g[4]:
            out.append((int(g[5]), _month_no(g[4]), int(g[3]) if g[3] else None, m.start()))
        elif g[6]:
            out.append((int(g[7]), int(g[6]), None, m.start()))
    return out


def _item_dates(it) -> list[tuple[int, int, int | None]]:
    out = []
    m = re.match(r"(\d{4})-(\d{2})(?:-(\d{2}))?", str(it.get("date") or ""))
    if m:
        out.append((int(m.group(1)), int(m.group(2)), int(m.group(3)) if m.group(3) else None))
    for d, mo, y in _DATE_IN.findall(it.get("label_en") or ""):
        out.append((int(y), int(mo), int(d)))
    return out


def _same_date(mention, fact_date) -> bool:
    y, mo, d, _p = mention
    fy, fmo, fd = fact_date
    return y == fy and (mo is None or mo == fmo) and (d is None or fd is None or d == fd)


def verify(st, k, n, text) -> tuple[bool, str]:
    """-> (ok, reason).  ALLOWLIST code check of one written sentence against its own line's facts."""
    if not isinstance(text, str) or not text.strip():
        return False, "empty"
    text = " ".join(text.split())
    if len(text) > max(MAX_CHARS, 70 * len(n["items"])):
        return False, "too long"
    if len(re.findall(r"[.!?](?:\s|$)", text)) > 2:
        return False, "more than two sentences"
    facts_txt = allowed_text(st, k, n, labels=False)
    # 'not documented' only (and always) for a line with a not-documented need; 'no later value' for a latest value
    nd = bool(_ND_PHRASES.search(text))
    later = bool(_LATER_PHRASES.search(text))
    if nd and not n["missing"]:
        return False, "'not documented' for a documented need"
    if n["missing"] and not nd:
        return False, "not-documented need left out"
    if later and n["shape"] not in ("latest_value", "trend"):
        return False, "'no later value' outside a latest value"
    body = _LATER_PHRASES.sub(" ", _ND_PHRASES.sub(" ", text))
    # schedules: only the facts' own, and every fact schedule present
    fact_scheds = set(_SCHED_RX.findall(_fold(facts_txt)))
    said = set(_SCHED_RX.findall(_fold(body)))
    if said - fact_scheds:
        return False, "schedule not in the facts: %s" % ", ".join(sorted(said - fact_scheds))
    for it in n["items"]:
        for f in it.get("facts") or []:
            sc = ((st.fact_by_id.get(f) or {}).get("attrs") or {}).get("schedule")
            if sc and sc not in said:
                return False, "schedule left out: %s" % sc
            break
    # tokens: the facts' own (labels, values, attrs, units, quotes, computed values, notes), their dates in any
    # rendering, the words of their schedules, or a connector word
    allowed = set(_tokens(facts_txt)) | FUNCTION_WORDS
    for sc in fact_scheds:
        allowed |= set(SCHEDULE_WORDS.get(sc, "").split())
    nums = _allowed_numbers(st, n, facts_txt)
    allowed |= nums
    for mo in _allowed_months(st, n, facts_txt):
        allowed |= {MONTHS[mo - 1].lower(), MONTHS[mo - 1][:3].lower()}
    bad = [t for t in _tokens(body) if t not in allowed and (not t[0].isdigit() or _canon_num(t) not in nums)]
    if bad:
        return False, "not in this line's facts: %s" % ", ".join(dict.fromkeys(bad))
    # every number carries the unit the facts give it
    pairs = {(v, u) for v, u, _p in _num_unit_pairs(facts_txt)}
    fact_units = {}
    for v, u in pairs:
        fact_units.setdefault(v, set()).add(u)
    for v, u, _p in _num_unit_pairs(body):
        if u is not None and u not in fact_units.get(v, set()):
            return False, "unit changed: %s %s" % (v, u)
    # value <-> date: a value with a date beside it must be the value of a fact of that date
    vals = [(v, p) for v, _u, p in _num_unit_pairs(body)]
    dates = _dates_in(body)
    item_vals = [(_value_nums(it.get("label_en")) | _nums(" ".join(str(x) for x in _fact_payload(st, k, it)["attrs"].values()
                                                                if isinstance(x, str) and not _SCHED_RX.search(x))),
                  _item_dates(it)) for it in n["items"]]
    for i, (v, p) in enumerate(vals):
        owners = [ds for vs, ds in item_vals if v in vs]
        if not owners or not all(ds for ds in owners):
            continue
        nxt = vals[i + 1][1] if i + 1 < len(vals) else 10 ** 6
        prv = vals[i - 1][1] if i else -1
        near = [d for d in dates if p < d[3] < nxt] or [d for d in dates if prv < d[3] < p][-1:]
        if near and not any(_same_date(near[0], fd) for ds in owners for fd in ds):
            return False, "value %s paired with a date not its own" % v
    low = _fold(text)
    for it in n["items"]:  # every fact is still named: its drug, or its values, or one of its words
        rep = next((st.fact_by_id[f] for f in it.get("facts") or [] if f in st.fact_by_id), {})
        a = rep.get("attrs") or {}
        if a.get("generic") and a.get("dose"):
            if _fold(a["generic"]) not in low and _fold(a.get("brand") or "@@") not in low:
                return False, "drug left out: %s" % a["generic"]
            need = _value_nums(a["dose"])
        else:
            need = _value_nums(it.get("label_en"))
        if need and not need <= _nums(text):
            return False, "value left out: %s" % (it.get("label_en") or "")[:40]
        if not need and not (_sig_words(it.get("label_en")) & _sig_words(text)) and not (
                _nums(it.get("label_en")) - {"0"} & _nums(text)):
            return False, "fact left out: %s" % (it.get("label_en") or "")[:40]
    if n.get("note") and n.get("side"):
        minority = "right" if n["side"] == "left" else "left"
        if minority not in low:
            return False, "contradiction left out"
    return True, ""


# ----------------------------------------------------------------- the writer (optional LLM)

STYLE = """You write the answer lines of Second Eye, a tool that shows a clinician the facts of one patient's record \
that their task needs. For each line you get the facts the rules already chose (label, attrs, date, status) and, \
sometimes, computed values, follow-up status, a contradiction note or needs that are not documented. Write ONE \
concise English sentence per line, in the style of a colleague's handover answer.

Rules:
- Use only the given facts and their own words. Every number (in digits), unit, dose, schedule, date, side and name \
must come from the line's own facts; beyond them use only simple connectors (and, of, in, on, as of, since, with). \
A code check rejects any other word, so do not add negations, drug classes, advice or number words.
- Keep every schedule as written (e.g. 1-0-1); its meaning may follow it.
- Name every given fact; do not add, drop or reorder facts; never mention another line's facts.
- Drugs: generic name with the brand in brackets, dose, schedule (e.g. 1-0-1); the schedule meaning may be spelt out.
- Dates: write them as '14 March 2014' or 'March 2014'; never invent a day.
- Say 'not documented' only for the needs listed as not_documented, and then always say it.
- Keep a contradiction note when given ('one letter says right').
- No advice, no interpretation beyond the facts, no hedging, no patient name. At most 30 words.

Examples (other patients, other facts):
facts: [{"label": "Bisoprolol (Concor) 5 mg 1-0-0", "attrs": {"generic": "bisoprolol", "brand": "Concor", \
"dose": "5 mg", "schedule": "1-0-0"}, "date": "2019-02-03"}]
-> "Bisoprolol (Concor) 5 mg once in the morning (1-0-0), as of February 2019."
facts: [{"label": "Potassium 5.9 mmol/l", "date": "2021-11-02"}]
-> "Potassium 5.9 mmol/l on 2 November 2021."
facts: [{"label": "Body weight 91 kg", "date": "2020-01-10"}, {"label": "Body weight 84 kg", "date": "2020-09-15"}], \
computed: ["-7 kg over 8 months"]
-> "91 kg in January 2020 and 84 kg in September 2020: 7 kg lost over 8 months."
facts: [{"label": "Syncope during exercise", "date": "2018-05-04"}, {"label": "Syncope attributed to aortic \
stenosis"}],
-> "Yes: syncope during exercise in May 2018, attributed to aortic stenosis."
facts: [{"label": "Femoral hernia, right"}], contradiction: "one letter (clinic note 02.03.2017) says left"
-> "Right femoral hernia; one letter (clinic note 02.03.2017) says left."
facts: [{"label": "Iodine allergy (rash)"}], not_documented: ["Creatinine and eGFR"]
-> "Iodine allergy (rash); creatinine and eGFR not documented."
"""
SCHEMA = {
    "type": "object",
    "properties": {"lines": {"type": "array", "items": {
        "type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
        "required": ["id", "text"], "additionalProperties": False}}},
    "required": ["lines"], "additionalProperties": False,
}


def request_params(batch: list[dict]) -> dict:
    from . import llm
    return dict(
        model=llm.model(),
        max_tokens=120 + 90 * len(batch),
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": STYLE, "cache_control": {"type": "ephemeral"}}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "Lines:\n" + json.dumps(batch, ensure_ascii=False)}],
    )


def _cache_key(n):
    from . import llm
    return ("answer", llm.model(), tuple(n["needs"]),
            tuple(f for it in n["items"] for f in it.get("facts") or []), tuple(n["missing"]), n.get("note"))


class Pending:
    """The batched writer call, started as soon as the lines are picked; result() never waits past the deadline."""

    def __init__(self, fut, t0, info):
        self.fut, self.t0, self.info = fut, t0, info

    def result(self):
        from concurrent.futures import TimeoutError as FutureTimeout
        from . import llm
        if self.fut is None:
            return {}, self.info
        left = max(0.0, llm.timeout_s() - (time.perf_counter() - self.t0))
        try:
            out = self.fut.result(timeout=left)
        except FutureTimeout:
            self.info["skipped"] = "timeout"
            out = {}
        except Exception as e:  # pragma: no cover - _ask never raises
            self.info["skipped"] = "error: %s" % type(e).__name__
            out = {}
        self.info["ms"] = round((time.perf_counter() - self.t0) * 1000, 1)
        return out, self.info


def _ask(params, info):
    """One model call -> {line id: text}.  Never raises; budget counted from usage."""
    from . import llm, llm_budget
    b = llm_budget.budget()
    try:
        msg = llm._call(params)
    except Exception as e:
        b.error()
        info["skipped"] = "error: %s" % type(e).__name__
        return {}
    try:
        usage = getattr(msg, "usage", None)
        if usage is not None:
            info["cost_eur"] = b.record(params["model"], usage)
        if getattr(msg, "stop_reason", None) in ("refusal", "max_tokens"):
            info["skipped"] = "stop_reason: %s" % msg.stop_reason
            return {}
        txt = next((getattr(x, "text", "") for x in msg.content if getattr(x, "type", None) == "text"), "")
        data = json.loads(txt)
        return {str(x.get("id")): x.get("text") for x in data.get("lines") or [] if isinstance(x, dict)}
    except Exception as e:
        b.error()
        info["skipped"] = "invalid: %s" % type(e).__name__
        return {}


def start(st, k, needs: list[dict], use_llm: bool) -> Pending:
    """Start the writer for the lines not in the cache (one batched call), or record why it is not used."""
    from . import llm, llm_budget
    info = {"called": False, "cached": 0, "skipped": None, "cost_eur": 0.0, "ms": 0.0, "cached_text": {}}
    t0 = time.perf_counter()
    if not needs:
        info["skipped"] = "no lines"
        return Pending(None, t0, info)
    if not use_llm or not llm.available() or os.environ.get("SECOND_LOOK_ANSWERS_LLM", "1") == "0":
        info["skipped"] = "disabled" if not llm.enabled() or not use_llm or \
            os.environ.get("SECOND_LOOK_ANSWERS_LLM", "1") == "0" else "no key"
        return Pending(None, t0, info)
    b = llm_budget.budget()
    batch = []
    for i, n in enumerate(needs):
        if n["kind"] == "nothing":  # 'Nothing found for X' stays as written
            continue
        hit = b.cache_get(_cache_key(n))
        if hit is not None:
            info["cached_text"]["L%d" % (i + 1)] = hit
            info["cached"] += 1
        else:
            batch.append(payload(st, k, n, "L%d" % (i + 1)))
    if not batch:
        return Pending(None, t0, info)
    if not b.reserve():
        info["skipped"] = b.why_blocked() or "budget"
        return Pending(None, t0, info)
    info["called"] = True
    return Pending(llm._pool.submit(_ask, request_params(batch), info), t0, info)


def finish(st, k, needs: list[dict], pending: Pending) -> tuple[list[dict], dict]:
    """Written (and verified) or template sentence per line -> (answer lines, stats)."""
    from . import llm_budget
    written, info = pending.result()
    written = dict(info.pop("cached_text", {}), **(written or {}))
    stats = {"called": info["called"], "cached": info["cached"], "skipped": info["skipped"], "ms": info["ms"],
             "cost_eur": round(info.get("cost_eur") or 0.0, 6), "llm": 0, "template": 0, "rejected": 0, "reasons": []}
    out = []
    for i, n in enumerate(needs):
        lid = "L%d" % (i + 1)
        text, origin, verified = template(st, k, n), "template", True
        cand = written.get(lid) if n["kind"] != "nothing" else None
        if cand is not None:
            ok, why = verify(st, k, n, cand)
            if ok:
                text, origin = " ".join(cand.split()), "llm"
                llm_budget.budget().cache_put(_cache_key(n), text)
            else:
                stats["rejected"] += 1
                stats["reasons"].append("%s: %s" % (lid, why))
        stats[origin] += 1
        out.append(line_out(n, text, origin, verified))
    return out, stats


def line_out(n, text, origin, verified) -> dict:
    passages = [p for it in n["items"] for p in it.get("passages") or []]
    passages += [p for c in n["computed"] for p in c.get("passages") or []]
    passages += [p for r in n["rows"] for p in r.get("passages") or []]
    passages += n.get("note_passages") or []
    passages += [p for q in n.get("quotes") or [] for p in q.get("passages") or []]
    trust = "conflicting" if n.get("note") else "not_documented" if n["kind"] == "not_documented" else None
    return {"kind": "not_documented" if n["kind"] in ("not_documented", "nothing") else "answer", "needs": n["needs"],
            "label": n["label"], "text": text, "fact_ids": [f for it in n["items"] for f in it.get("facts") or []],
            "passages": list(dict.fromkeys(passages)), "origin": origin, "verified": verified, "trust": trust,
            "missing": list(n["missing"])}


def answer_lines(st, k, cards, u, contras, patient, terms_text, as_of, mode, use_llm,
                 focus=()) -> tuple[list[dict], dict]:
    """Header + answer lines for one screen -> (lines, routing.answer_lines_llm stats)."""
    needs = pick_lines(st, k, cards, u, contras, terms_text, as_of, mode, focus)
    if not needs:
        return [], {"called": False, "skipped": "no lines", "llm": 0, "template": 0, "rejected": 0}
    lines, stats = finish(st, k, needs, start(st, k, needs, use_llm))
    head = header(st, cards, patient)
    return ([head] if head else []) + lines, stats

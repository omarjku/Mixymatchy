"""v2 step 3, the evidence pool (docs/DECISIONS.md 23): what the answer writer may cite, nothing else.

Built deterministically from what the rules and engine/kbfill.py already found and verified (no new content):
  * one FACT chunk per chosen item of an answer need (engine/answers.py pick_lines, plus the AI's slots):
    "<need label>: <item label> (<date>)[; schedule meaning][; card note]. Letter: "<verbatim German quote>""
  * one COMPUTED chunk per computed value (weight change, age), one STATUS chunk per follow-up check
  * one NOT DOCUMENTED chunk per need the letters do not answer ("Not documented: kidney function ...")
  * one CONTRADICTION chunk per contradiction / minority side touching a need
  * one NOT APPLICABLE chunk when a sex/age-specific item does not fit the documented patient
Every chunk keeps its passage ids (the Source link opens the letter highlighted) and fact ids.
"""
from __future__ import annotations

import re

from . import answers as A
from . import keyfacts as K

MAX_CHUNKS = 40
MAX_NEEDS = 10
MAX_ITEMS_PER_NEED = 10
_STOP = {"the", "and", "with", "her", "she", "his", "for", "from", "what", "which", "when", "does", "did", "has",
         "have", "had", "was", "were", "any", "this", "that", "patient", "please", "show", "tell", "about",
         "der", "die", "das", "und", "ist", "hat", "mit", "von", "wie", "was", "welche", "gibt", "bitte"}
_DOSES = {1: "once daily", 2: "twice daily", 3: "three times daily", 4: "four times daily"}


def _words(text):
    from .understand import fold
    return {w for w in re.findall(r"[a-z0-9]{3,}", fold(text or "").lower()) if w not in _STOP}


def _date_text(it):
    d = str(it.get("date") or "")[:10]
    prec = it.get("date_precision") or "day"
    if not d:
        return ""
    long_ = A.fmt_date(d, prec)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", d)
    if m and prec == "day":
        return "%s (%s.%s.%s)" % (long_, m.group(3), m.group(2), m.group(1))
    return long_


def _rep(st, it):
    return next((st.fact_by_id[f] for f in it.get("facts") or [] if f in st.fact_by_id), {})


def _schedule(st, k, it):
    a = _rep(st, it).get("attrs") or {}
    s = a.get("schedule")
    if not s:
        return ""
    meaning = A._schedule_meaning(k, s)
    n = sum(int(x) for x in re.findall(r"\d", s)) if re.fullmatch(r"[\d\-\s½]+", s) else 0
    bits = [x for x in (meaning, _DOSES.get(n)) if x]
    return ("schedule %s: %s" % (s, ", ".join(bits))) if bits else ""


def _quote(st, it):
    q = (_rep(st, it).get("quote") or "").strip()
    return ' Letter: "%s"' % q[:240] if q else ""


class Pool:
    def __init__(self):
        self.chunks = []

    def add(self, kind, need, text, passages=(), facts=(), slots=()):
        text = " ".join(str(text or "").split())
        if not text or len(self.chunks) >= MAX_CHUNKS:
            return None
        for c in self.chunks:  # the same statement once (e.g. the allergy in the header and in a need)
            if c["text"] == text:
                return c["id"]
        cid = "C%d" % (len(self.chunks) + 1)
        self.chunks.append({"id": cid, "kind": kind, "need": need, "text": text,
                            "passages": list(dict.fromkeys(passages or [])), "facts": list(facts or []),
                            "slots": list(slots or [])})
        return cid


def need_chunks(pool, st, k, n, card_by_slot):
    """One answer need -> its chunk ids (facts, computed values, status, not documented, contradiction)."""
    ids = []
    label = n["label"]
    parts = n.get("parts") or [n]
    for p in parts:
        plab = p.get("label") or label
        pneeds = p.get("needs") or n["needs"]
        if p is not n and p.get("label") and p.get("label") != label:
            plab = "%s - %s" % (label, p["label"])
        slot = (pneeds or [None])[0]
        card = card_by_slot.get(slot) or {}
        newest = max(p.get("items") or [{}], key=lambda it: K._date(it)) if p.get("items") else None
        if p.get("shape") == "status_check" and p.get("rows"):
            body = "; ".join("%s: %s" % (r.get("label"), r.get("note") or r.get("status") or "")
                             for r in p["rows"])
            tests = [A._short_followup(st, r["label"]) for r in p["rows"] if r.get("status") == "not_documented"]
            if tests:
                body += " (%s)" % ", ".join(tests)
            ids.append(pool.add("status", pneeds, "%s: %s" % (plab, body),
                                [x for r in p["rows"] for x in r.get("passages") or []],
                                [x for r in p["rows"] for x in r.get("facts") or []], pneeds))
        for it in (p.get("items") or [])[:MAX_ITEMS_PER_NEED]:
            bits = [it.get("label_en") or ""]
            dt = _date_text(it)
            if dt and not A._has_date(bits[0]):
                bits[0] += " on %s" % dt
            sch = _schedule(st, k, it)
            if sch:
                bits.append(sch)
            if it is newest and card.get("note") and p.get("shape") == "latest_value":
                bits.append(card["note"])
            if it.get("status_display"):
                bits.append("status: %s" % it["status_display"])
            text = "%s: %s.%s" % (plab, "; ".join(b for b in bits if b), _quote(st, it))
            ids.append(pool.add("fact", pneeds, text, it.get("passages"), it.get("facts"), pneeds))
        for c in p.get("computed") or []:
            txt = "%s: %s %s" % (plab, c.get("label") or "Calculated", c.get("value") or "")
            if "change" in c and c.get("unit"):
                txt += " (%s %g %s, calculated: last minus first documented value)" % (
                    "lost" if c["change"] < 0 else "gained", abs(c["change"]), c["unit"])
            ids.append(pool.add("computed", pneeds, txt, c.get("passages"), (), pneeds))
        for q in p.get("quotes") or []:
            ids.append(pool.add("fact", pneeds, '%s: %s: "%s"' % (plab, q["label"], q["value"]),
                                q.get("passages"), (), pneeds))
    if n.get("side"):  # laterality: the side most letters document (engine/answers.py), with those letters
        ids.append(pool.add("computed", n["needs"], "%s: %s side (the side most letters document)" % (label, n["side"]),
                            [x for it in n.get("items") or [] for x in it.get("passages") or []], (), n["needs"]))
    if n["kind"] == "nothing":
        ids.append(pool.add("not_documented", n["needs"], n.get("fixed_text") or "Nothing found.", (), (), n["needs"]))
    else:
        for m in n.get("missing") or []:
            ids.append(pool.add("not_documented", n["needs"], "Not documented - %s; no letter documents it." % m,
                                (), (), n["needs"]))
    if n.get("note"):
        ids.append(pool.add("contradiction", n["needs"], "Letters disagree: %s %s" % (
            n["note"], "(%s)" % label), n.get("note_passages"), (), n["needs"]))
    return [i for i in ids if i]


def _relevance(st, n, qwords):
    if not qwords:
        return 0
    txt = " ".join([n.get("label") or ""] + list(n.get("slot_labels") or []) + list(n.get("missing") or [])
                   + [it.get("label_en") or "" for it in n.get("items") or []])
    return len(qwords & _words(txt))


def relevant_slots(k, u, cards, ai_slots=()):
    """Slots the question itself points at (see build)."""
    rel = set(ai_slots or ())
    rel |= set(u.get("asked_slots") or [])
    rel |= set(A._topic_slots(k, u.get("named_topics")))
    rel |= {c.get("slot") or c.get("need") for c in cards
            if str(c.get("slot") or c.get("need") or "").startswith("applicability")}
    if u.get("bundles_matched"):  # the rules matched the task words: the P1 of the task (bundle P1, its composite,
        for bid in u.get("bundle_ids") or []:  # the role's P1 modifiers); the safety core only as a bundle's own P1
            rel |= set(((k.bundle_by_id.get(bid) or {}).get("slots") or {}).get("P1") or [])
        rel |= {c.get("slot") for c in cards if c.get("priority") == "P1" and c.get("slot") not in A.HEADER_NEEDS}
    return {x for x in rel if x}


def build(st, k, screen, question, ai_slots=()):
    """-> (chunks, ranked needs [(need, [chunk ids])], note).  Deterministic for a given screen and AI slots."""
    u = screen["understood"]
    cards = screen.get("cards") or []
    focus = screen.get("focus") or []
    contras = screen.get("contradictions") or []
    mode = screen.get("screen_mode")
    as_of = u.get("as_of_date")
    terms = " ".join([u.get("task_text") or question or ""] + list(u.get("task_labels") or []))
    needs = A.pick_lines(st, k, cards, u, contras, terms, as_of, "task" if mode == "sex_specific" else mode, focus,
                         cap=MAX_NEEDS)
    # only what THIS question needs (owner, 30 Oct): the AI's slots, the slots / topics / applicability checks the
    # question names, and a rules bundle's P1 only when the rules matched the task words; the safety core
    # (age, sex, allergies) only when one of these asks for it; everything else stays under 'Show more'
    rel = relevant_slots(k, u, cards, ai_slots)
    needs = [n for n in needs if n.get("shape") in ("question", "nothing") or set(n["needs"]) & rel]
    have = {s for n in needs for s in n["needs"]}
    groups = {s["id"]: s.get("group") for s in k.data.get("slots") or []}
    card_by_slot = {}
    for c in cards:
        card_by_slot.setdefault(c.get("slot") or c.get("need"), c)
    shown = {f for n in needs for it in n["items"] for f in it.get("facts") or []}
    for s in dict.fromkeys(x for x in ai_slots if x not in have and x in card_by_slot):
        n = A._card_need(st, k, card_by_slot[s], K._words(terms), as_of, cards, contras, True, groups, shown)
        if n:
            needs.append(n)
            have.add(s)
    # rank: the AI's slot order first, then what the question names (asked slots, topics, applicability checks),
    # then the rules' order (KB priority)
    rank = {s: i for i, s in enumerate(ai_slots)}
    asked = relevant_slots(k, dict(u, bundles_matched=None), cards, ())
    order = sorted(range(len(needs)), key=lambda i: (
        min([rank.get(s, 99) for s in needs[i]["needs"]] or [99]),
        0 if needs[i].get("shape") in ("question", "nothing") or set(needs[i]["needs"]) & asked else 1, i))
    needs = [needs[i] for i in order]

    pool = Pool()
    note = None
    na = [c for c in cards if c.get("status") == "not_applicable"]
    if na and u.get("applicability_note"):
        note = {"text": u["applicability_note"], "passages": [p for c in na for p in c.get("passages") or []]}
        pool.add("not_applicable", [c["need"] for c in na], "Not applicable: " + u["applicability_note"],
                 note["passages"], (), [c["need"] for c in na])
    ranked = []
    for n in needs:
        ids = need_chunks(pool, st, k, n, card_by_slot)
        if ids:
            ranked.append((n, ids))
    head = A.header(st, cards, screen.get("patient") or {}) if rel & set(A.HEADER_NEEDS) else None
    if head:  # age · sex · allergies: only when the question asks for them
        pool.add("fact", head["needs"], "Age, sex, allergies: %s." % head["text"].replace(" · ", "; "),
                 head["passages"], head["fact_ids"], head["needs"])
    return pool.chunks, ranked, note

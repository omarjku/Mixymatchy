"""Adapter: our deterministic engine -> the frontend contract in schema.py.

Data flow
  offline   pipeline/  -> data/build/{docs,passages,facts}.json
            compare/   -> data/build/compare.json
  online    engine.screen.build_screen(situation)  -> screen dict
            this module                             -> schema.Briefing

Nothing here invents patient content: every Fact is an engine fact (which the engine
re-verifies word for word against its passage at load time), every Segment is a passage.
Missing build files are built on first use by calling the pipeline/compare builders.

Mapping rules (documented once, applied everywhere)
  docs.json            -> Document (text = display_text; department from documents.json metadata)
  passages.json        -> Segment  (id = passage id; kind line|sentence -> sentence, table_row -> table_row)
  card                 -> NeedResult (consistent|conflicting|outdated -> documented)
  card item            -> Fact (one per displayed item: the same statement repeated in several letters
                          is one Fact whose segment_ids cover every letter; id = newest engine fact id)
  card status          -> Fact.trust: conflicting -> conflicting, outdated -> stale,
                          consistent -> consistent (item found in >= 2 letters) or single (1 letter)
  latest/current_meds "earlier" and meds no longer on the latest list -> NeedResult.superseded
  series_change        -> Computed (formula + the segments of the first and last value)
  absent_after         -> Computed "No record that this took place after ..." linked to the recommendation
  compare contradictions -> Finding(kind=conflict, tier contradiction | documentation_note)
  compare blind spots  -> Briefing.blind_spot facts + Finding(kind=dropped); unstated computed
                          values (e.g. weight change never written down) -> Finding(kind=silence)
  open follow-ups      -> Finding(kind=followup)
  clinical gate        -> screen_mode "not_authorised" (no clinical role stated): no needs, findings or
                          blind spot; routing.message / routing.suggestions say what to type instead
  no task, no data     -> screen_mode "needs_task" (clinical role but no recognisable clinical task: greeting,
                          filler, role only; docs/DECISIONS.md 19): same as not_authorised, its own message
  gated screens        -> no as_of / anchor date either (the record's dates are patient data)
  task scope (KB)      -> contradictions, blind-spot items and open follow-ups that touch no slot on this
                          screen are counted in stats.other_record_issues and listed with on_screen=False
                          in the long view only
  stats                -> counted from the Briefing object itself
  key_facts (engine/keyfacts.py) -> Briefing.key_facts (layout "answer_first"): one line per P1 need with the
                          chosen card items as Facts (+ since = first letter), the safety core, the not-documented
                          needs and the first contradiction; every NeedResult stays as the details view
  answer_lines (engine/answers.py) -> Briefing.answer_lines (DECISIONS 22): header (age · sex · allergies) + 3-4
                          one-sentence answers (rules pick, optional LLM writes, code verifies; origin, verified,
                          fact ids, passages); key_facts and the cards become 'Show more'; routing.answer_lines_llm

Routing knowledge base (default rulebook; SECOND_LOOK_RULEBOOK=legacy for roles.json + tasks.json)
  card slot/shape/priority/why/sources/rules/note -> the optional NeedResult fields of the same name
  checklist / status_check sub-items -> NeedResult.checklist (found / documented_none / not_documented)
  status_check open items -> Computed "no record that this took place after ..." linked to the recommendation
  age calculated from the date of birth -> Computed linked to the date-of-birth passages
  rule R22 label panel -> NeedResult.label_panel
  item status word (KB status vocabulary: ruled out / suspected / past) -> Fact.status
"""
from __future__ import annotations

import json
import os
import sys
import threading
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:  # engine/, pipeline/, compare/ are top-level packages of the repo
    sys.path.insert(0, str(ROOT))

from .schema import (Answer, AnswerLine, AnswerSegment, AnswerSource, Briefing, ChecklistItem,  # noqa: E402
                     Computed, Document, Fact, Finding, KeyFact,
                     NeedResult, Segment, SourceRef)

BUILD_DIR = Path(os.environ.get("SECOND_LOOK_BUILD", ROOT / "data" / "build"))
RAW_DIR = ROOT / "data" / os.environ.get("PATIENT_ID", "patient-0000-0001")
BUILD_FILES = ("docs.json", "passages.json", "facts.json")

_lock = threading.Lock()

TYPE_BY_SECTION = {
    "medications": "medication", "allergies": "allergy", "problems": "diagnosis", "past_illness": "history",
    "procedures": "procedure", "results": "finding", "vital_signs": "measurement", "plan_of_care": "plan",
    "social_history": "history", "functional_status": "finding",
}
SEGMENT_KIND = {"line": "sentence", "sentence": "sentence", "table_row": "table_row", "heading": "heading"}


# ----------------------------------------------------------------- build artefacts

def ensure_build() -> None:
    """Build data/build/* with pipeline/ and compare/ if any file is missing (needs the raw patient data)."""
    with _lock:
        if any(not (BUILD_DIR / f).exists() for f in BUILD_FILES):
            from pipeline import build as pipeline_build
            pipeline_build.main()
        if not (BUILD_DIR / "compare.json").exists():
            from compare import build as compare_build
            compare_build.main(str(BUILD_DIR))


@lru_cache
def engine_store():
    ensure_build()
    from engine.data import rulebook_mode, store
    if rulebook_mode() == "kb":  # validate the routing KB at start-up; refuses to start on errors
        from engine.kb import kb
        kb()
    return store()


@lru_cache
def _departments() -> dict[str, str]:
    """Document metadata (not patient facts): department per document id."""
    path = RAW_DIR / "documents.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(d.get("id")): d.get("department") or d.get("division") or "" for d in data.get("documents", [])}


@lru_cache
def documents() -> list[Document]:
    st, dep = engine_store(), _departments()
    docs = [Document(id=i, title=d.get("title") or "", date=d.get("date") or "", type=d.get("type") or "",
                     department=dep.get(i, ""), text=d.get("display_text") or "") for i, d in st.docs.items()]
    return sorted(docs, key=lambda d: (d.date, d.id))


@lru_cache
def segments() -> list[Segment]:
    st = engine_store()
    return [Segment(id=p["id"], doc_id=p["doc_id"], kind=SEGMENT_KIND.get(p.get("kind"), "sentence"),
                    section=p.get("section"), text=p["text"], start=p["start"], end=p["end"],
                    doc_date=st.doc_date(p["doc_id"]) or "") for p in st.passages]


@lru_cache
def segment_index() -> dict[str, Segment]:
    return {s.id: s for s in segments()}


def document(doc_id: str) -> Document | None:
    return next((d for d in documents() if d.id == doc_id), None)


# ----------------------------------------------------------------- facts

def _fact_type(f: dict) -> str:
    sec = f.get("ips_section")
    if sec == "plan_of_care" and f.get("status") == "recommended":
        return "recommendation"
    if sec == "results" and (f.get("attrs") or {}).get("value") not in (None, ""):
        return "measurement"
    return TYPE_BY_SECTION.get(sec, "finding")


def _side(sides: set[str]) -> str | None:
    sides = {s for s in sides if s in ("left", "right", "both")}
    if not sides:
        return None
    return "both" if len(sides) > 1 or "both" in sides else sides.pop()


_NUM = __import__("re").compile(r"(?<![\d/.,])(\d+(?:[.,]\d+)?)\s*(%|mg|kg|cm|mm|mmHg|/min|bpm|m/s)?(?![\d/])")


def _number_in(label: str, rep: dict, st):
    """value/unit for a numeric measurement whose engine fact has no numeric value attribute: the number
    as written in the label, kept only if the same number is in the fact's quote (never invented)."""
    attrs = rep.get("attrs") or {}
    if rep.get("ips_section") not in ("results", "vital_signs") and not attrs.get("unit"):
        return attrs.get("value") or None, attrs.get("unit") or None
    quote = (rep.get("quote") or "").replace(",", ".")
    for m in _NUM.finditer(label):
        num = m.group(1)
        if num.replace(",", ".") in quote:
            return num, m.group(2) or attrs.get("unit") or None
    return attrs.get("value") or None, attrs.get("unit") or None


def _in_label(token, label: str) -> bool:
    return token is None or str(token).replace(",", ".").lower() in label.replace(",", ".").lower()


def item_fact(st, it: dict, trust: str) -> Fact:
    """One displayed item (same statement, possibly in several letters) -> one Fact."""
    members = [st.fact_by_id[x] for x in it["facts"] if x in st.fact_by_id]
    newest = [f for f in members if str(f.get("date") or "")[:10] == str(it.get("date") or "")[:10]]
    rep = (newest or members)[-1]
    attrs = rep.get("attrs") or {}
    label = it.get("label_en") or rep.get("label_en") or ""
    value, unit = attrs.get("value"), attrs.get("unit")
    if value in (None, ""):
        value, unit = _number_in(label, rep, st)  # numeric facts always carry value/unit (History tab)
    docs = it.get("docs") or st.fact_docs(rep)
    if trust == "consistent" and len(docs) < 2:
        trust = "single"
    seg_ids = list(dict.fromkeys(it.get("passages") or [p for f in members for p in f.get("passage_ids") or []]))
    return Fact(
        id=rep["id"], type=_fact_type(rep), concept=rep.get("category") or "",
        classes=[rep["category"]] if rep.get("ips_section") == "medications" and rep.get("category") else [],
        label_en=label, value=None if value in (None, "") else str(value), unit=unit or None,
        date=str(it.get("date"))[:10] if it.get("date") else None,
        side=_side({str((f.get("attrs") or {}).get("side") or "").lower() for f in members}),
        status=it.get("status_display") or it.get("status") or rep.get("status"), segment_ids=seg_ids, trust=trust)


def _trust(card_status: str) -> str:
    return {"conflicting": "conflicting", "outdated": "stale"}.get(card_status, "consistent")


# ----------------------------------------------------------------- cards -> needs

def _kb_fields(card: dict) -> dict:
    out = {"slot": card.get("slot"), "shape": card.get("shape"), "priority": card.get("priority"),
           "why": card.get("why"), "rules": list(card.get("rules") or []), "note": card.get("note"),
           "sources": [SourceRef(id=s["id"], title=s["title"], verification=s.get("verification") or None,
                                 url=s.get("url") or None) for s in card.get("sources") or []],
           "checklist": [ChecklistItem(label=r["label"], status=r["status"], segment_ids=list(r.get("passages") or []),
                                       note=r.get("note")) for r in card.get("checklist") or []],
           "label_panel": list(card.get("label_panel") or []), "more": card.get("more") or None}
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def _open_checks(card: dict) -> list[Computed]:
    return [Computed(label=o["label"], value=o["note"][:1].upper() + o["note"][1:],
                     formula="searched every fact of the matching kind dated after %s (as of the briefing date)"
                             % o["threshold"], segment_ids=o["passages"])
            for o in card.get("open_checks") or [] if o.get("passages")]


def need_result(st, card: dict) -> NeedResult:
    status = card.get("status")
    res = NeedResult(need=card["need"], label=card.get("label_en") or card["need"],
                     status="not_applicable" if status == "not_applicable"
                     else "not_documented" if status == "not_documented" else "documented", **_kb_fields(card))
    if res.status == "not_applicable":
        res.reason = card.get("value_en", "").replace("Not applicable: ", "") or None
        res.reason_segment_ids = list(card.get("passages") or [])
        return res
    if res.status == "not_documented":
        res.reason = card.get("value_en") or "Not documented"
        res.reason_segment_ids = list(card.get("passages") or [])  # possible mentions, open to check
        if card.get("open_checks") is not None:  # KB status_check: one computed line per open recommendation
            res.computed.extend(_open_checks(card))
            return res
        for rec in card.get("related") or []:  # absent_after: the recommendation it was checked against
            res.computed.append(Computed(
                label=rec["label_en"], value="No record that this took place after %s" % card.get("threshold"),
                formula="searched %d documents for a matching fact dated after %s (as of the briefing date)"
                        % (len(st.docs), card.get("threshold")),
                segment_ids=rec["passages"]))
        return res

    trust = _trust(status)
    for it in card.get("items") or []:
        fact = item_fact(st, it, "stale" if it.get("not_on_latest_list") else
                         "conflicting" if it.get("conflicts") else trust)  # letters disagree about this item
        if it.get("collapsed"):
            fact.collapsed = True
        if it.get("not_on_latest_list"):
            res.superseded.append(fact.model_copy(update={"status": "not on latest medication list"}))
        else:
            res.facts.append(fact)
        for e in it.get("earlier") or []:  # same drug, different dose/schedule on an older list
            res.superseded.append(item_fact(st, e, "stale"))
    for e in card.get("earlier") or []:  # "latest": older values hidden behind the newest one
        res.superseded.append(item_fact(st, e, "stale"))
    for rec in card.get("related") or []:  # absent_after with a later record: show what it answered
        res.facts.append(item_fact(st, rec, trust))

    res.computed.extend(_open_checks(card))
    for cl in card.get("computed_lines") or []:  # e.g. the 'Letters disagree' card: what compare/ found
        if cl.get("passages"):
            res.computed.append(Computed(label=cl["label"], value=cl.get("value") or "", formula=cl.get("formula") or "",
                                         segment_ids=list(cl["passages"])))
    calc = card.get("calculated")
    if calc and calc.get("kind") == "age" and card.get("items"):
        res.computed.append(Computed(
            label="Age", value="%d years" % calc["age"],
            formula="full years from the date of birth %s to %s (anchor: latest document)" % (calc["dob"], calc["at"]),
            segment_ids=list(card["items"][0]["passages"])))
    elif calc and card.get("items"):
        first, last = card["items"][0], card["items"][-1]
        unit = calc.get("unit") or ""
        v0, v1 = (st.fact_by_id[i["facts"][0]] for i in (first, last))
        a = (v0.get("attrs") or {}).get("value")
        b = (v1.get("attrs") or {}).get("value")
        res.computed.append(Computed(
            label=card.get("label_en") or "Change",
            value="%+g %s over %d months" % (calc["change"], unit, calc["months"]),
            formula="%s %s (%s) - %s %s (%s); %s" % (b, unit, calc["to"], a, unit, calc["from"], calc["method"]),
            segment_ids=list(dict.fromkeys(first["passages"] + last["passages"]))))
    if not res.facts and res.superseded:
        res.facts, res.superseded = res.superseded, []
    return res


# ----------------------------------------------------------------- findings

def _concepts(st, fact_ids) -> list[str]:
    return sorted({st.fact_by_id[x]["category"] for x in fact_ids if x in st.fact_by_id})


def _conflict(st, c: dict, on_screen: bool) -> Finding:
    counted = c.get("counted", True)
    return Finding(
        id=c["id"], kind="conflict", tier="contradiction" if counted else "documentation_note",
        title=c.get("title_en") or "Contradiction", explanation=c.get("detail_en") or "",
        segment_ids=c.get("passages") or [], fact_ids=c.get("facts") or [],
        concepts=_concepts(st, c.get("facts") or []), on_screen=on_screen,
        severity=("high" if c.get("relevant") else "medium") if counted else "low")


def _followup(st, fu: dict, on_screen: bool) -> Finding:
    return Finding(
        id=fu["id"], kind="followup", title=fu.get("label_en") or "Open follow-up",
        explanation="Recommended %s (document %s); no later record that it took place. %s"
                    % (fu.get("authored_date"), fu.get("authored_doc"), fu.get("searched") or ""),
        segment_ids=fu["passage_ids"], fact_ids=fu.get("fact_ids") or [],
        concepts=_concepts(st, fu.get("fact_ids") or []), severity="medium", on_screen=on_screen)


def _blind_items(st, bs: dict, items: list, on_screen: bool, out: list, blind: list) -> None:
    for i, b in enumerate(items, 1):
        fids, pids = b.get("facts") or [], b.get("passages") or []
        if not pids:
            continue
        key = "%02d" % i if on_screen else "x%02d" % i
        if b.get("kind") == "unstated_computed":
            out.append(Finding(id="silence" + key, kind="silence", title=b["label_en"],
                               explanation="Calculated from the letters; no letter states it.",
                               segment_ids=pids, fact_ids=fids, concepts=_concepts(st, fids), severity="medium",
                               on_screen=on_screen))
            continue
        if on_screen:
            it = {"label_en": b["label_en"], "date": b.get("last_documented"), "facts": fids,
                  "passages": pids, "docs": b.get("docs")}
            blind.append(item_fact(st, it, "consistent"))
        out.append(Finding(
            id="dropped" + key, kind="dropped", title=b["label_en"],
            explanation="Last documented %s; not mentioned in the latest letter (%s, %s)."
                        % (b.get("last_documented"), bs.get("latest_document"), bs.get("latest_document_date")),
            segment_ids=pids, fact_ids=fids, concepts=_concepts(st, fids), severity="medium", on_screen=on_screen))


def findings(st, screen: dict) -> tuple[list[Finding], list[Fact]]:
    """Only what touches this task's screen.  The KB engine splits contradictions, blind-spot items and
    open follow-ups into on-screen and other; the others are listed (on_screen=False) in the long view
    only, and counted in stats.other_record_issues either way."""
    long_view = screen.get("detail") != "short"
    task_scoped = "contradictions_other" in screen
    out: list[Finding] = []
    for c in screen.get("contradictions") or []:
        out.append(_conflict(st, c, True))
    if long_view:
        for c in screen.get("contradictions_other") or []:
            out.append(_conflict(st, c, False))

    blind: list[Fact] = []
    bs = screen.get("blind_spot") or {}
    _blind_items(st, bs, bs.get("items") or [], True, out, blind)
    if long_view and screen.get("blind_spot_other"):
        ref = st.compare.get("counts", {}) if isinstance(st.compare, dict) else {}
        meta = bs or {"latest_document": ref.get("latest_doc"), "latest_document_date": ref.get("latest_date")}
        _blind_items(st, meta, screen["blind_spot_other"], False, out, blind)

    if task_scoped:
        shown_fu = screen.get("open_followups") or []
        other_fu = screen.get("open_followups_other") or [] if long_view else []
    else:  # legacy rulebook: patient-wide, as before
        comp = st.compare if isinstance(st.compare, dict) else {}
        shown_fu, other_fu = [fu for fu in comp.get("open_followups") or [] if fu.get("is_open")], []
    for fu in shown_fu:
        if fu.get("passage_ids"):
            out.append(_followup(st, fu, True))
    for fu in other_fu:
        if fu.get("passage_ids"):
            out.append(_followup(st, fu, False))
    return out, blind


# ----------------------------------------------------------------- briefing

def stats_of(b: Briefing, facts_dropped: int, task_concepts: int | None, other_issues: int = 0) -> dict:
    """Every number on screen is counted from the briefing itself."""
    known = segment_index()
    shown = [f for n in b.needs for f in n.facts]
    verified = [f for f in shown if f.segment_ids and all(s in known for s in f.segment_ids)]
    return {
        "facts_shown": len(shown),
        "facts_verified": len(verified),
        "facts_dropped": facts_dropped,
        "computed_values": sum(len(n.computed) for n in b.needs),
        "not_documented": sum(n.status == "not_documented" for n in b.needs),
        "not_applicable": sum(n.status == "not_applicable" for n in b.needs),
        "blind_spot": len(b.blind_spot),
        "task_concepts": task_concepts if task_concepts is not None else len(b.blind_spot),
        "contradictions": sum(f.kind == "conflict" and f.tier == "contradiction" and f.on_screen for f in b.findings),
        "documentation_notes": sum(f.kind == "conflict" and f.tier == "documentation_note" and f.on_screen
                                   for f in b.findings),
        "followups_open": sum(f.kind == "followup" and f.on_screen for f in b.findings),
        "other_record_issues": other_issues,
    }


GATED_MODES = ("not_authorised", "needs_task")


def _routing(screen: dict) -> dict:
    u = screen["understood"]
    if screen.get("rulebook") != "kb":
        return {"rulebook": "legacy", "role": u.get("role_id"), "tasks": u.get("task_ids")}
    return {"rulebook": u.get("rulebook"), "role": u.get("role_id"), "role_match": u.get("role_match"),
            "bundles": u.get("bundle_ids"), "bundles_matched": u.get("bundles_matched"), "implied": u.get("implied"),
            "rules_fired": u["rules"]["fired"], "rules_not_fired": u["rules"]["not_fired"],
            "fallback_note": u.get("fallback_note"), "slots_total": len(u.get("slots") or []),
            "slots_shown": len(screen.get("cards") or []), "anchor_date": u.get("anchor_date"),
            "screen_mode": u.get("screen_mode"), "suggestions": u.get("suggestions") or [],
            "role_label": u.get("role_label"), "message": screen.get("message"),
            "role_missing": bool(u.get("role_missing")),
            "clinical_gate": (u.get("clinical_gate") or {}).get("decision"),
            "llm_used": bool(u.get("llm_used")), "llm_reason": u.get("llm_reason") if u.get("llm_used") else None,
            "answer_lines_llm": u.get("answer_lines_llm"),
            "router": u.get("router") or "v1", "answer_v2": u.get("answer_v2"),
            "understand_v2": u.get("understand_v2"),
            "llm_kind": u.get("llm_kind"), "llm_verdict": u.get("llm_verdict"), "llm_ms": u.get("llm_ms"),
            "engine_ms": screen.get("timing_ms"),
            "applicability_note": u.get("applicability_note"), "applicability": u.get("applicability"),
            "task_focus": u.get("task_focus"), "llm_focus": u.get("llm_focus"),
            "also_relevant": u.get("also_relevant") or [], "also_relevant_more": u.get("also_relevant_more") or 0,
            "other_record_issues": screen.get("other_record_issues", 0),
            "other_record_issues_en": screen.get("other_record_issues_en")}


def key_fact(st, line: dict) -> KeyFact:
    """engine/keyfacts.py line -> KeyFact; every item becomes a Fact with its passages (item_fact)."""
    facts = []
    for it in line.get("items") or []:
        f = item_fact(st, it, "conflicting" if it.get("conflicts") else _trust(line.get("trust") or ""))
        first = str(it.get("first_date") or "")[:10]
        if first and f.date and first < f.date:
            f.since = first
        facts.append(f)
    computed = [Computed(label=c["label"], value=c["value"], formula=c.get("formula") or "", segment_ids=c["passages"])
                for c in line.get("computed") or [] if c.get("passages")]
    return KeyFact(kind=line["kind"], needs=line.get("needs") or [], label=line.get("label") or "", facts=facts,
                   computed=computed, text=line.get("text"), segment_ids=list(line.get("passages") or []),
                   more=line.get("more") or 0, trust=line.get("trust"))


def build_briefing(situation: str, as_of: str | None = None, use_llm: bool | None = None,
                   detail: str = "short", rulebook: str | None = None) -> Briefing:
    st = engine_store()
    from engine.screen import build_screen
    if use_llm is None:
        use_llm = os.environ.get("SECOND_LOOK_LLM") == "1"
    screen = build_screen(situation, as_of=as_of, use_llm=use_llm, detail=detail, rulebook=rulebook)
    u = screen["understood"]

    cards, seen = [], set()
    for c in ((screen.get("safety_strip") or []) + (screen.get("cards") or []) + (screen.get("focus") or [])
              + (screen.get("also_relevant") or [])):
        if c["need"] not in seen:
            seen.add(c["need"])
            cards.append(c)
    gated = screen.get("screen_mode") in GATED_MODES  # zero patient data: no counts or dates from the record either
    found, blind = ([], []) if gated else findings(st, screen)
    b = Briefing(situation=situation, role=u.get("role_id") or "other",
                 task=", ".join(u.get("task_labels") or []) or situation,
                 as_of="" if gated else (u.get("as_of_date") or ""),
                 needs=[need_result(st, c) for c in cards], blind_spot=blind, findings=found,
                 detail=screen.get("detail"), routing=_routing(screen))
    if not gated and screen.get("key_facts"):  # answer-first (docs/DECISIONS.md 20): the cards become details
        b.key_facts = [key_fact(st, ln) for ln in screen["key_facts"]]
        b.layout = "answer_first"
        keyed = {x for ln in b.key_facts if ln.kind in ("need", "safety") for x in ln.needs}
        for n in b.needs:
            n.key = n.need in keyed
    if not gated and screen.get("answer_lines"):  # DECISIONS 22: header + one-sentence answers by default
        b.answer_lines = [AnswerLine(kind=ln["kind"], needs=ln.get("needs") or [], label=ln.get("label") or "",
                                     text=ln["text"], fact_ids=ln.get("fact_ids") or [],
                                     segment_ids=list(ln.get("passages") or []), origin=ln.get("origin") or "template",
                                     verified=bool(ln.get("verified")), trust=ln.get("trust"))
                          for ln in screen["answer_lines"]]
        b.layout = "answer_first"
    a = screen.get("answer")
    if not gated and a:  # v2 (DECISIONS 23): the cited sentence first; answer lines, key facts, cards: 'Show more'
        b.answer = Answer(kind=a.get("kind") or "answer", text=a["text"],
                          segments=[AnswerSegment(text=x["text"], sources=x.get("sources") or [])
                                    for x in a.get("segments") or []],
                          sources=[AnswerSource(n=x["n"], label=x.get("label") or "", segment_ids=x.get("passages") or [],
                                                fact_ids=x.get("facts") or []) for x in a.get("sources") or []],
                          origin=a.get("origin") or "template", verified=bool(a.get("verified")),
                          note=a.get("note"), note_segment_ids=a.get("note_passages") or [])
        b.layout = "answer_first"
    bs = screen.get("blind_spot") or {}
    if gated:
        b.routing["anchor_date"] = None
    b.stats = stats_of(b, 0 if gated else len(st.removed), bs.get("of_total_problems"),
                       screen.get("other_record_issues", 0))
    b.stats["engine_ms"] = screen.get("timing_ms")
    return b

"""Step B: turn a situation into a briefing (owner: E2). Must stay fast: no LLM call except parsing.

Implemented:  keyword role parser (fallback), needs from rulebook roles + tasks,
              smart answers per need (latest as of date, current medication list overrides older lists,
              trend with computed change, follow-up "nothing recorded after"), "not documented",
              "not applicable", blind spot vs the latest letter, computed stats.
TODO(E2):     LLM situation parser (PARSE_MODEL) with this keyword parser as fallback; as-of date from text;
              trust marks from fact families.
"""
import json
import re
from functools import lru_cache

from . import store
from .config import AS_OF_DEFAULT, RULEBOOK_DIR
from .schema import Briefing, Computed, Fact, Finding, NeedResult, Segment


@lru_cache
def rulebook(name: str) -> dict:
    data = json.loads((RULEBOOK_DIR / f"{name}.json").read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def parse_situation(situation: str) -> tuple[str, list[str]]:
    """Return (role, needs). Keyword fallback; the LLM parser will replace the role choice."""
    text = situation.lower()
    roles = rulebook("roles")
    scores = {r: sum(_has_word(text, k) for k in cfg["keywords"]) for r, cfg in roles.items()}
    role = max(scores, key=scores.get) if max(scores.values()) > 0 else "fallback"
    needs = list(roles[role]["needs"])
    for word, cfg in rulebook("tasks").items():
        if _has_word(text, word):
            needs += [n for n in cfg["adds"] if n not in needs]
    return role, needs


def _matches(fact: Fact, spec: dict) -> bool:
    if fact.type not in spec.get("types", [fact.type]):
        return False
    concepts = spec.get("concepts")
    return not concepts or fact.concept in concepts or any(
        c.startswith("class:") and c[len("class:"):] in fact.classes for c in concepts)


class Context:
    """Everything a need-answer needs: facts, segments and the as-of date."""

    def __init__(self, facts: list[Fact], segments: list[Segment], as_of: str):
        self.seg = {s.id: s for s in segments}
        self.as_of = as_of
        self.facts = [f for f in facts if self.date(f) <= as_of]

    def date(self, f: Fact) -> str:
        if f.date:
            return f.date
        seg = self.seg.get(f.segment_ids[0])
        return seg.doc_date if seg else ""

    def doc(self, f: Fact) -> str:
        return f.segment_ids[0].split(":")[0]

    def sex(self) -> tuple[str, str] | None:
        """Patient sex from the letter's address line ("Frau"/"Herr"), with the segment as evidence."""
        for s in self.seg.values():
            if s.text in ("Frau", "Herr"):
                return ("female" if s.text == "Frau" else "male"), s.id
        return None


def _number(value: str | None) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", value or "")
    return float(m.group().replace(",", ".")) if m else None


def answer_need(need: str, spec: dict, ctx: Context) -> NeedResult:
    res = NeedResult(need=need, label=spec["label"], status="not_documented")
    sex = ctx.sex()
    if spec.get("applies_to_sex") and sex and sex[0] != spec["applies_to_sex"]:
        res.status, res.reason, res.reason_segment_ids = "not_applicable", f"Patient is {sex[0]}", [sex[1]]
        return res

    matched = sorted((f for f in ctx.facts if _matches(f, spec)), key=ctx.date)
    mode = spec.get("answer", "all")

    if mode == "latest":
        newest: dict[str, Fact] = {}
        for f in matched:
            newest[f.concept] = f
        res.facts = list(newest.values())
        res.superseded = [f for f in matched if f not in res.facts]

    elif mode == "current_medication":
        # The newest medication list overrides older ones.
        med_dates = [ctx.date(f) for f in ctx.facts if f.type == "medication"]
        latest_list = max(med_dates, default="")
        current = [f for f in matched if ctx.date(f) == latest_list]
        res.facts = current or [f.model_copy(update={"trust": "stale"}) for f in matched]
        res.superseded = [f for f in matched if f not in current] if current else []

    elif mode == "trend":
        res.facts = matched
        for concept in spec.get("trend_of", []):
            series = [(f, _number(f.value)) for f in matched if f.concept == concept and _number(f.value) is not None]
            if len(series) >= 2:
                (first, a), (last, b) = series[0], series[-1]
                unit = last.unit or re.sub(r"-?\d+(?:[.,]\d+)?", "", last.value or "").strip()
                res.computed.append(Computed(
                    label=f"{concept.replace('_', ' ').capitalize()} change",
                    value=f"{b - a:+g} {unit}".strip(),
                    formula=f"{b:g} {unit} ({ctx.date(last)}) - {a:g} {unit} ({ctx.date(first)})",
                    segment_ids=first.segment_ids + last.segment_ids))

    elif mode == "followup":
        res.facts = matched
        for rec in matched:
            later = [f for f in ctx.facts if f.concept == rec.concept and f.type != "recommendation"
                     and ctx.date(f) > ctx.date(rec)]
            if not later:
                res.computed.append(Computed(
                    label=rec.label_en, value=f"Nothing recorded after {ctx.date(rec)}",
                    formula=f"no document dated after {ctx.date(rec)} mentions this (searched up to {ctx.as_of})",
                    segment_ids=rec.segment_ids))

    else:  # "all"
        res.facts = matched

    if res.facts:
        res.status = "documented"
    return res


def blind_spot(needs: list[NeedResult], ctx: Context) -> tuple[list[Fact], int]:
    """Task facts whose concept never appears in the latest document. Returns (missed facts, task concepts)."""
    latest_doc = max(ctx.facts, key=ctx.date, default=None)
    if not latest_doc:
        return [], 0
    latest_id = ctx.doc(latest_doc)
    in_latest = {f.concept for f in ctx.facts if ctx.doc(f) == latest_id}
    shown = {f.concept: f for n in needs for f in n.facts}
    missed = [f for c, f in shown.items() if c not in in_latest]
    return missed, len(shown)


def build_briefing(situation: str, facts: list[Fact] | None = None, findings: list[Finding] | None = None,
                   segments: list[Segment] | None = None, as_of: str = AS_OF_DEFAULT) -> Briefing:
    facts = store.load("facts") if facts is None else facts
    findings = store.load("findings") if findings is None else findings
    segments = store.load("segments") if segments is None else segments
    ctx = Context(facts, segments, as_of)
    role, needs = parse_situation(situation)
    catalogue = rulebook("needs")
    results = [answer_need(n, catalogue[n], ctx) for n in needs]
    missed, task_concepts = blind_spot(results, ctx)

    concepts = {c for n in needs for c in catalogue[n].get("concepts", [])}
    relevant = [f for f in findings if not f.concepts or concepts & set(f.concepts)]

    shown = sum(len(r.facts) for r in results)
    return Briefing(
        situation=situation, role=role, task=situation, as_of=as_of, needs=results,
        blind_spot=missed, findings=relevant,
        stats={  # computed from this briefing, never typed in
            "facts_shown": shown,
            "facts_verified": shown,  # the store only holds facts that passed verify.py
            "facts_dropped": len(store.load_raw("dropped")),
            "computed_values": sum(len(r.computed) for r in results),
            "not_documented": sum(r.status == "not_documented" for r in results),
            "not_applicable": sum(r.status == "not_applicable" for r in results),
            "blind_spot": len(missed),
            "task_concepts": task_concepts,
            "contradictions": sum(f.tier == "contradiction" for f in relevant),
            "documentation_notes": sum(f.tier == "documentation_note" for f in relevant),
        })

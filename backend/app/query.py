"""Step B: turn a situation into a briefing (owner: E2). Must stay fast: no LLM call except parsing.

Implemented:  keyword role parser (fallback), needs from roles + triggers, fact selection,
              "not documented" logic, attaching findings.
TODO(E2):     LLM situation parser (PARSE_MODEL) with keyword parser as fallback,
              as-of date handling, blind spot (facts missing from the latest letter), trust marks.
"""
import re
from functools import lru_cache

import yaml

from . import store
from .config import AS_OF_DEFAULT, KNOWLEDGE_DIR
from .schema import Briefing, Fact, NeedResult


@lru_cache
def knowledge(name: str) -> dict:
    return yaml.safe_load((KNOWLEDGE_DIR / f"{name}.yaml").read_text(encoding="utf-8"))


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) is not None


def parse_situation(situation: str) -> tuple[str, list[str]]:
    """Return (role, needs). Keyword fallback; the LLM parser will replace the role choice."""
    text = situation.lower()
    roles = knowledge("roles")
    scores = {r: sum(_has_word(text, k) for k in cfg["keywords"]) for r, cfg in roles.items()}
    role = max(scores, key=scores.get) if max(scores.values()) > 0 else "fallback"
    needs = list(roles[role]["needs"])
    for word, extra in knowledge("triggers").items():
        if _has_word(text, word):
            needs += [n for n in extra if n not in needs]
    return role, needs


def _matches(fact: Fact, spec: dict) -> bool:
    if fact.type not in spec.get("types", [fact.type]):
        return False
    concepts = spec.get("concepts")
    return not concepts or fact.concept in concepts or any(
        c.startswith("class:") and c[len("class:"):] in fact.classes for c in concepts)


def build_briefing(situation: str) -> Briefing:
    role, needs = parse_situation(situation)
    catalogue = knowledge("needs")
    facts, findings = store.load("facts"), store.load("findings")
    results = []
    for need in needs:
        spec = catalogue[need]
        matched = [f for f in facts if _matches(f, spec)]
        results.append(NeedResult(need=need, label=spec["label"], facts=matched,
                                  status="documented" if matched else "not_documented"))
    concepts = {c for n in needs for c in catalogue[n].get("concepts", [])}
    relevant = [f for f in findings if not f.concepts or concepts & set(f.concepts)]
    shown = sum(len(r.facts) for r in results)
    return Briefing(situation=situation, role=role, task=situation, as_of=AS_OF_DEFAULT,
                    needs=results, findings=relevant,
                    stats={"facts_shown": shown, "facts_verified": shown, "facts_dropped": 0})

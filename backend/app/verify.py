"""Step A5: the safety net. A fact survives only if its value really appears in its cited segments."""
import re

from .schema import Fact, Segment


def _norm(s: str) -> str:
    s = s.lower().replace(",", ".").replace("µg", "mcg").replace("μg", "mcg")
    return re.sub(r"\s+", "", s)


def value_supported(value: str | None, texts: list[str]) -> bool:
    """True if every number in `value` (or the whole value, if it has none) occurs in the cited text."""
    if not value:
        return True
    haystack = _norm(" ".join(texts))
    numbers = re.findall(r"\d+(?:[.,]\d+)?", value)
    if numbers:
        return all(_norm(n) in haystack for n in numbers)
    return _norm(value) in haystack


def verify_facts(facts: list[Fact], segments: dict[str, Segment]) -> tuple[list[Fact], list[dict]]:
    kept, dropped = [], []
    for f in facts:
        missing = [sid for sid in f.segment_ids if sid not in segments]
        if missing:
            dropped.append({"fact": f.model_dump(), "reason": f"unknown segment ids {missing}"})
            continue
        if not value_supported(f.value, [segments[s].text for s in f.segment_ids]):
            dropped.append({"fact": f.model_dump(), "reason": "value not found in cited segments"})
            continue
        kept.append(f)
    return kept, dropped

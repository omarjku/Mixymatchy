"""Step A8: deterministic conflict rules (owner: E2). High precision first; the LLM pass adds the rest.

Implemented:   BMI that does not match height and weight in the same document.
TODO(E2):      same-event date conflicts, laterality flips within a fact family,
               finding vs later finding, dropped facts, open follow-ups.
False alarms to avoid: height 170 vs 171 cm, small weight differences, changes over time,
               differences from IBM's JSON files.
Tiers:         tier="contradiction" only when the passages cannot all be true; typos and case numbers
               get tier="documentation_note". Clinicians decide borderline cases (eval/contradictions_gold.json).
Wording:       lineage findings say "possible copy error", never "copied wrong".
"""
import re

from .schema import Finding, Segment

BMI_TOLERANCE = 1.0  # kg/m2


def _num(pattern: str, segs: list[Segment]) -> tuple[float, Segment] | None:
    for s in segs:
        m = re.search(pattern, s.text)
        if m:
            return float(m.group(1).replace(",", ".")), s
    return None


def bmi_mismatch(segments: list[Segment]) -> list[Finding]:
    findings = []
    for doc_id in sorted({s.doc_id for s in segments}):
        segs = [s for s in segments if s.doc_id == doc_id]
        h = _num(r"Größe:\s*(\d+(?:[.,]\d+)?)\s*cm", segs)
        w = _num(r"Gewicht:\s*(\d+(?:[.,]\d+)?)\s*kg", segs)
        b = _num(r"BMI:\s*(\d+(?:[.,]\d+)?)", segs)
        if not (h and w and b):
            continue
        calc = w[0] / (h[0] / 100) ** 2
        if abs(calc - b[0]) > BMI_TOLERANCE:
            findings.append(Finding(
                id=f"bmi-{doc_id}", kind="conflict", tier="contradiction",
                title="BMI does not match height and weight",
                explanation=f"Stated BMI {b[0]:g}, but {w[0]:g} kg at {h[0]:g} cm gives {calc:.1f}.",
                segment_ids=[h[1].id, w[1].id, b[1].id], concepts=["weight", "bmi"],
                severity="medium", source="rule"))
    return findings


def run_rules(segments: list[Segment]) -> list[Finding]:
    return bmi_mismatch(segments)

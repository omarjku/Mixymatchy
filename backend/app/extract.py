"""Step A3–A4: LLM fact extraction (owner: E1).

The model sees numbered segments and may only cite segment IDs. It never writes the quote
that is shown on screen; the server resolves IDs to text. Output is checked by verify.py.

TODO(E1):
  - call Claude with the tool schema below, one call per document, prompt caching on the system prompt
  - add the sceptic pass: a second call that tries to refute each fact against its segments
  - map brand names / synonyms via rulebook/drugs.json and rulebook/synonyms.json into Fact.concept
"""
import json

from .config import EXTRACT_MODEL
from .schema import Document, Fact, Segment

SYSTEM_PROMPT = """You extract clinical facts from one German clinical document.
Rules:
- Use only what the document states. No inference, no medical knowledge, no advice.
- Every fact must cite the IDs of the segments it comes from (segment_ids). Never quote text yourself.
- label_en is a short English label; value keeps numbers exactly as written (German decimal commas allowed).
- Medication table rows: columns are morning, midday, evening, night (e.g. "1 0 1/2 0").
- Record side (left/right) only when the segment states it.
"""

FACT_TOOL = {
    "name": "record_facts",
    "description": "Record every clinical fact in the document.",
    "input_schema": {
        "type": "object",
        "properties": {"facts": {"type": "array", "items": Fact.model_json_schema()}},
        "required": ["facts"],
    },
}


def render_segments(segments: list[Segment]) -> str:
    return "\n".join(f"[{s.id}] ({s.section or '-'}) {s.text}" for s in segments)


def extract_document(doc: Document, segments: list[Segment]) -> list[Fact]:
    """Return unverified facts for one document. Not implemented yet."""
    _ = (EXTRACT_MODEL, json, render_segments(segments))
    raise NotImplementedError("E1: implement Claude extraction (see module docstring)")

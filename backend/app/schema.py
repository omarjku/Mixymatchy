"""Shared data contract between backend and frontend. Change only with E1/E2/E3 agreement."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

FactType = Literal["medication", "allergy", "diagnosis", "measurement", "procedure",
                   "finding", "recommendation", "history", "plan"]
Trust = Literal["consistent", "conflicting", "stale", "single"]


class Segment(BaseModel):
    """One sentence or table row of a document. The unit every link points to."""
    id: str                      # e.g. "12340012:s041"
    doc_id: str
    kind: Literal["sentence", "table_row", "heading"]
    section: Optional[str] = None  # e.g. "Diagnosen", "Entlassungsmedikation"
    text: str
    start: int                   # offsets into Document.text (normalised)
    end: int
    doc_date: str


class Document(BaseModel):
    id: str
    title: str
    date: str
    type: str
    department: str
    text: str                    # normalised text that offsets refer to


class Fact(BaseModel):
    id: str
    type: FactType
    concept: str                 # normalised key, e.g. "carotid_stenosis", "drug:acetylsalicylic_acid"
    classes: list[str] = []      # drug classes from rulebook/drugs.json, e.g. ["antiplatelet"]
    label_en: str                # short English label shown on screen
    value: Optional[str] = None
    unit: Optional[str] = None
    date: Optional[str] = None
    side: Optional[Literal["left", "right", "both"]] = None
    status: Optional[str] = None  # positive / negative / suspected / past / planned
    segment_ids: list[str] = Field(min_length=1)
    trust: Trust = "single"


class Finding(BaseModel):
    """Something the record gets wrong or leaves open.

    Conflicts come in two tiers so we are not penalised for false alarms:
      contradiction       passages that cannot all be true; counted in the metric
      documentation_note  shown separately and never labelled a contradiction (typos, case numbers)
    Copy-forward wording on screen is always "possible copy error", never "copied wrong".
    """
    id: str
    kind: Literal["conflict", "dropped", "followup", "silence"]
    tier: Optional[Literal["contradiction", "documentation_note"]] = None  # conflicts only
    title: str
    explanation: str
    segment_ids: list[str] = []
    fact_ids: list[str] = []
    concepts: list[str] = []     # used to attach the finding to a task's needs
    severity: Literal["high", "medium", "low"] = "medium"
    source: Literal["rule", "llm"] = "rule"


class Computed(BaseModel):
    """A value the app calculates (allowed by the brief). Links every input it was computed from."""
    label: str                   # e.g. "Weight change"
    value: str                   # e.g. "-12 kg"
    formula: str                 # e.g. "66 kg (2016-04-15) - 78 kg (2015-06-28)"
    segment_ids: list[str] = Field(min_length=1)


class NeedResult(BaseModel):
    need: str                    # e.g. "antithrombotic"
    label: str                   # e.g. "Blood thinners"
    status: Literal["documented", "not_documented", "not_applicable"]
    facts: list[Fact] = []
    computed: list[Computed] = []
    superseded: list[Fact] = []  # older values hidden by "latest as of" / newer medication list
    reason: Optional[str] = None  # why not applicable, e.g. "patient is female"
    reason_segment_ids: list[str] = []


class Briefing(BaseModel):
    situation: str
    role: str
    task: str
    as_of: str
    needs: list[NeedResult]
    blind_spot: list[Fact] = []  # task facts missing from the latest letter
    findings: list[Finding] = []
    stats: dict = {}             # always computed from the briefing itself, never typed in


class BriefingRequest(BaseModel):
    situation: str

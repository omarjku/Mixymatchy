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
    classes: list[str] = []      # drug classes from drugs.yaml, e.g. ["antiplatelet"]
    label_en: str                # short English label shown on screen
    value: Optional[str] = None
    unit: Optional[str] = None
    date: Optional[str] = None
    side: Optional[Literal["left", "right", "both"]] = None
    status: Optional[str] = None  # positive / negative / suspected / past / planned
    segment_ids: list[str] = Field(min_length=1)
    trust: Trust = "single"


class Finding(BaseModel):
    """Something the record gets wrong or leaves open."""
    id: str
    kind: Literal["conflict", "dropped", "followup", "silence"]
    title: str
    explanation: str
    segment_ids: list[str] = []
    fact_ids: list[str] = []
    concepts: list[str] = []     # used to attach the finding to a task's needs
    severity: Literal["high", "medium", "low"] = "medium"
    source: Literal["rule", "llm"] = "rule"


class NeedResult(BaseModel):
    need: str                    # e.g. "antithrombotic"
    label: str                   # e.g. "Blood thinner"
    status: Literal["documented", "not_documented"]
    facts: list[Fact] = []


class Briefing(BaseModel):
    situation: str
    role: str
    task: str
    as_of: str
    needs: list[NeedResult]
    blind_spot: list[Fact] = []  # task facts missing from the latest letter
    findings: list[Finding] = []
    stats: dict = {}


class BriefingRequest(BaseModel):
    situation: str

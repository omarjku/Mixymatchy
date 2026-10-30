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
    collapsed: bool = False      # short view: behind "+N more" on its card (still linked, never dropped)
    since: Optional[str] = None  # key facts: first letter that documents the same statement (e.g. a drug since 2015)


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
    on_screen: bool = True       # False: touches nothing on this task's screen ("other record issues", long view)


class Computed(BaseModel):
    """A value the app calculates (allowed by the brief). Links every input it was computed from."""
    label: str                   # e.g. "Weight change"
    value: str                   # e.g. "-12 kg"
    formula: str                 # e.g. "66 kg (2016-04-15) - 78 kg (2015-06-28)"
    segment_ids: list[str] = Field(min_length=1)


class SourceRef(BaseModel):
    """A guideline or drug label from the routing knowledge base (why a slot is shown)."""
    id: str                      # e.g. "G01", "L02"
    title: str
    verification: Optional[str] = None
    url: Optional[str] = None


class ChecklistItem(BaseModel):
    """One sub-item of a checklist / status-check card, judged independently."""
    label: str
    status: Literal["found", "documented_none", "not_documented"]
    segment_ids: list[str] = []
    note: Optional[str] = None


class NeedResult(BaseModel):
    need: str                    # e.g. "antithrombotic" (legacy) or a KB slot id, e.g. "med_antithrombotic"
    label: str                   # e.g. "Blood thinners"
    status: Literal["documented", "not_documented", "not_applicable"]
    facts: list[Fact] = []
    computed: list[Computed] = []
    superseded: list[Fact] = []  # older values hidden by "latest as of" / newer medication list
    reason: Optional[str] = None  # why not applicable, e.g. "patient is female"
    reason_segment_ids: list[str] = []
    # Routing knowledge base (optional; empty with the legacy rulebook)
    slot: Optional[str] = None   # KB slot id
    shape: Optional[str] = None  # KB shape, e.g. "latest_value", "checklist"
    priority: Optional[str] = None  # "P1" | "P2" | "P3" (legacy: "must" | "should")
    why: Optional[str] = None    # why this is shown (bundle why_override or slot why, or the link rule)
    sources: list[SourceRef] = []  # guideline / label badges
    rules: list[str] = []        # link rules that surfaced the slot, e.g. ["R01"]
    note: Optional[str] = None   # e.g. "As of 06/2015; no later value documented."
    checklist: list[ChecklistItem] = []
    label_panel: list[dict] = []  # rule R22: listed contraindications beside patient facts (never a verdict)
    more: int = 0                # list cards in the short view: further items shown in the long view
    key: bool = False            # answered by a key-fact line (docs/DECISIONS.md 20); the card itself is 'details'


class KeyFact(BaseModel):
    """One answer-first line (docs/DECISIONS.md 20): the best current answer to one P1 need (or the safety core,
    the not-documented needs, the first contradiction). Values are the engine's own items, each linked."""
    kind: Literal["safety", "need", "not_documented", "conflict"]
    needs: list[str] = []        # need ids this line answers (two when merged, every one for not_documented)
    label: str                   # need label(s), e.g. "Antiplatelets and anticoagulants"
    facts: list[Fact] = []       # the chosen items (latest / most relevant), each with its segment_ids
    computed: list[Computed] = []  # e.g. age from the date of birth, weight change, 'no record after ...'
    text: Optional[str] = None   # sex / not-documented need labels / contradiction title (no patient value invented)
    segment_ids: list[str] = []  # passages of `text` (sex passage, both sides of a contradiction)
    more: int = 0                # further items of these needs, shown under 'Show more'
    trust: Optional[str] = None


class Briefing(BaseModel):
    situation: str
    role: str
    task: str
    as_of: str
    needs: list[NeedResult]      # full cards: the 'Show more / Details' part of an answer-first screen
    key_facts: list[KeyFact] = []  # answer-first block shown by default (empty: gated / not-applicable screens)
    layout: Literal["answer_first", "cards"] = "cards"  # answer_first: everything except key_facts is details
    blind_spot: list[Fact] = []  # task facts missing from the latest letter
    findings: list[Finding] = []
    stats: dict = {}             # always computed from the briefing itself, never typed in
    detail: Optional[str] = None  # "short" (P1, default) | "long" (P1-P3); KB rulebook only
    routing: dict = {}           # role, bundles, matched tags, rules fired, fallback note, rulebook version;
                                 # llm_used (bool) / llm_reason (str|None): the optional AI reading changed the route


class BriefingRequest(BaseModel):
    situation: str
    detail: Literal["short", "long"] = "short"

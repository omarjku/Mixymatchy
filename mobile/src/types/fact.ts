// Data contract shared with the backend. Every component imports from here — never redefine these shapes.

// The engine's trust labels: consistent (across letters), conflicting (letters disagree), outdated, single
// (mentioned once); plus not_documented and not_applicable for needs. verified / ai_inferred are kept for
// mock data only: the backend never infers facts.
export type FactTrust =
  | "consistent"
  | "single"
  | "conflicting"
  | "outdated"
  | "not_documented"
  | "not_applicable"
  | "verified"
  | "ai_inferred";

export interface SourceCitation {
  documentId: string;
  documentLabel: string; // e.g. "Discharge letter, June 2015"
  excerpt: string;       // the exact matched text snippet
  segmentId?: string;    // backend segment id: opens the letter with this passage highlighted
}

export interface GuidelineCitation {
  guidelineName: string;
  excerpt: string;
  reference?: string; // URL or document reference, optional
}

export interface Fact {
  id: string;
  label: string;          // e.g. "Blood thinner"
  value: string | null;   // null when not_documented
  trust: FactTrust;
  source?: SourceCitation;
  guideline?: GuidelineCitation;
  confidence?: number;    // 0–1, optional, for future tiered display
  isTimeSeries?: boolean; // true if this fact has historical values worth graphing
  history?: { date: string; value: string; unit?: string }[]; // only if isTimeSeries
  sources?: SourceCitation[]; // every passage the fact is quoted from (source = the first one)
  note?: string;              // e.g. formula of a computed value, "As of 06/2015; no later value documented."
  computed?: boolean;         // calculated from documented values (allowed by the brief), not quoted
  badgeLabel?: string;        // overrides the trust badge (e.g. "Calculated"); "" hides it
  priority?: string;          // knowledge-base priority of the need (P1 / P2 / P3)
  rows?: FactRow[];           // one need with several facts: one compact row each (value · date · source)
  trend?: TrendSummary;       // trend need: "78 kg → 67 kg → 66 kg (−12 kg over 10 months)"
  superseded?: FactRow[];     // older values a newer letter replaced (Details: "Medication changes")
}

// One documented statement inside a need's card. collapsed: the engine put it behind "+N more"
// (short view); it stays in the response with its sources, one tap away.
export interface FactRow {
  id: string;
  text: string;
  date?: string;              // dd.mm.yyyy
  sources: SourceCitation[];
  collapsed?: boolean;
  computed?: boolean;         // calculated from documented values; note = formula
  note?: string;
}

export interface TrendSummary {
  points: { value: string; date: string; collapsed?: boolean }[]; // oldest first, value incl. unit
  numbers: number[];
  change?: string;            // the backend's calculated change, e.g. "-12 kg over 10 months"
  formula?: string;
}

export interface Contradiction {
  id: string;
  factLabel: string;
  conflictingSources: SourceCitation[];
  severity?: "low" | "medium" | "high";
  // contradiction: passages that cannot all be true (counted); documentation_note: typos, case numbers
  tier?: "contradiction" | "documentation_note";
  explanation?: string;
}

// Things the record leaves open: facts missing from the latest letter, follow-ups with no later record.
export interface RecordGap {
  id: string;
  kind: "dropped" | "followup" | "silence";
  title: string;
  explanation: string;
  sources: SourceCitation[];
}

export interface PatientBrief {
  patientId: string;
  patientLabel: string; // display name/identifier
  role: string;
  task: string;
  facts: Fact[];
  contradictions: Contradiction[];
  generatedAt: string;
  gaps?: RecordGap[];
  stats?: Record<string, number>; // computed by the backend from this brief, never typed in
  routeNote?: string | null;      // shown when the request matched no knowledge-base entry exactly
  roleLabel?: string | null;      // backend's own label for the role it read (never a "GP" fallback)
  taskLabel?: string | null;      // backend's reading of the task, e.g. "Pre-procedure check (anaesthesia)"
  screenMode?: string | null;     // task | fallback | overview | sex_specific | not_applicable | not_authorised | needs_task
  message?: string | null;        // not_authorised / needs_task: what to type instead
  suggestions?: string[];         // tasks / situations to try (unrecognised task, not authorised)
  applicabilityNote?: string | null;
  applicabilitySources?: SourceCitation[];
  alsoRelevant?: Fact[];          // P2 needs from the long view, shown under "Also relevant"
  situation?: string;             // the exact sentence sent to the backend
}

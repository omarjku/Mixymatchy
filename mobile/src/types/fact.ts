// Data contract shared with the backend. Every component imports from here — never redefine these shapes.

// verified: quoted from the letters and consistent; conflicting: letters disagree; outdated: only old evidence.
// ai_inferred is kept for mock data only: the backend never infers facts.
export type FactTrust = "verified" | "conflicting" | "outdated" | "ai_inferred" | "not_documented";

export interface SourceCitation {
  documentId: string;
  documentLabel: string; // e.g. "Discharge letter, June 2015"
  excerpt: string;       // the exact matched text snippet
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
  history?: { date: string; value: string }[]; // only if isTimeSeries
  sources?: SourceCitation[]; // every passage the fact is quoted from (source = the first one)
  note?: string;              // e.g. formula of a computed value, "As of 06/2015; no later value documented."
  computed?: boolean;         // calculated from documented values (allowed by the brief), not quoted
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
}

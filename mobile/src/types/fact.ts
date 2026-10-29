// Data contract shared with the backend. Every component imports from here — never redefine these shapes.

export type FactTrust = "verified" | "ai_inferred" | "not_documented";

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
}

export interface Contradiction {
  id: string;
  factLabel: string;
  conflictingSources: SourceCitation[];
  severity?: "low" | "medium" | "high";
}

export interface PatientBrief {
  patientId: string;
  patientLabel: string; // display name/identifier
  role: string;
  task: string;
  facts: Fact[];
  contradictions: Contradiction[];
  generatedAt: string;
}

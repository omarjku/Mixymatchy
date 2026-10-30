import type { SourceCitation } from "@/types/fact";

// Data for the Dashboard level. Holds only DOCUMENTED inputs (what a letter states, with its source).
// Every derived number (changes, percentages, calculated BMI, agreement flags) is computed in
// src/lib/stats.ts, never stored or typed in. No predictions, scores or classifications.

export interface DocumentedValue {
  value: number;
  display: string; // as written, e.g. "81 kg"
  date: string; // ISO date the document refers to (not always the measurement date)
  source: SourceCitation;
}

// One measurement set: weight, height and the BMI written in the same document
export interface MeasurementSet {
  id: string;
  label: string; // e.g. "Entlassung Juni 2025"
  date: string;
  weightKg: number;
  heightCm: number;
  recordedBmi: number | null; // null when the letter states no BMI
  source: SourceCitation;
}

export interface DoseChange {
  id: string;
  drug: string;
  unit: string; // e.g. "mg/Tag"
  from: DocumentedValue;
  to: DocumentedValue;
  scheduleNote?: string; // documented schedule wording, e.g. "5 mg morgens → 5 mg morgens + 2,5 mg abends"
}

export interface BloodPressure {
  systolic: number;
  diastolic: number;
}

export interface BloodPressureComparison {
  id: string;
  label: string; // e.g. "Akute Episode"
  context: string; // what the two readings are, as documented
  fromLabel: string;
  toLabel: string;
  from: BloodPressure;
  to: BloodPressure;
  sources: SourceCitation[];
}

// Values that must NOT be drawn as trends (single or sparse measurements)
export interface DatedFact {
  id: string;
  label: string;
  values: { display: string; date: string; source: SourceCitation }[];
  note: string; // why no trend is shown
}

export interface PatientStats {
  patientId: string;
  recordsThrough: string; // ISO date of the latest document
  factsRemoved: number; // facts dropped by the backend verifier (reported, not computed here)
  measurements: MeasurementSet[];
  doseChanges: DoseChange[];
  bloodPressure: BloodPressureComparison[];
  reportedAverages: { label: string; value: BloodPressure; source: SourceCitation }[];
  datedFacts: DatedFact[];
  notes: string[]; // documented context, e.g. "Ursache der Gewichtsabnahme ist nicht dokumentiert."
}

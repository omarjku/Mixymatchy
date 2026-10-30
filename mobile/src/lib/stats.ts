import type { BloodPressure, MeasurementSet } from "@/types/stats";

// Arithmetic on documented values. Results are calculations, not diagnoses: no thresholds,
// no "good/bad", no classification. Formatting is German (comma decimals).

// Data-quality tolerance for "recorded BMI matches weight/height" (not a clinical threshold)
export const BMI_TOLERANCE = 0.5;

export function calculateBmi(weightKg: number, heightCm: number): number {
  const m = heightCm / 100;
  return weightKg / (m * m);
}

export interface Change {
  delta: number;
  percent: number | null; // null when the starting value is 0
}

export function change(from: number, to: number): Change {
  return { delta: to - from, percent: from === 0 ? null : ((to - from) / from) * 100 };
}

export type BmiAgreement = "agrees" | "differs" | "not_recorded";

export interface BmiCheck {
  set: MeasurementSet;
  calculated: number;
  difference: number | null; // recorded minus calculated
  agreement: BmiAgreement;
}

export function checkBmi(set: MeasurementSet): BmiCheck {
  const calculated = calculateBmi(set.weightKg, set.heightCm);
  if (set.recordedBmi === null) return { set, calculated, difference: null, agreement: "not_recorded" };
  const difference = set.recordedBmi - calculated;
  return { set, calculated, difference, agreement: Math.abs(difference) <= BMI_TOLERANCE ? "agrees" : "differs" };
}

export function bpChange(from: BloodPressure, to: BloodPressure) {
  return { systolic: change(from.systolic, to.systolic), diastolic: change(from.diastolic, to.diastolic) };
}

const numberFormats = new Map<number, Intl.NumberFormat>();
export function formatNumber(value: number, decimals = 0): string {
  let format = numberFormats.get(decimals);
  if (!format) {
    format = new Intl.NumberFormat("de-DE", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    numberFormats.set(decimals, format);
  }
  return format.format(value);
}

// Always signed ("+2,5", "−11"), with a real minus sign so it reads as a change, not a dash
export function formatSigned(value: number, decimals = 0): string {
  const text = formatNumber(Math.abs(value), decimals);
  if (value > 0) return `+${text}`;
  if (value < 0) return `−${text}`;
  return text;
}

export function formatBp(bp: BloodPressure): string {
  return `${bp.systolic}/${bp.diastolic}`;
}

export function formatDate(iso: string): string {
  return new Intl.DateTimeFormat("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }).format(new Date(iso));
}

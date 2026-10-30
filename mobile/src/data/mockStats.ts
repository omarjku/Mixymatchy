import type { SourceCitation } from "@/types/fact";
import type { PatientStats } from "@/types/stats";

// INVENTED numbers for the Dashboard level (no real patient data in git). Structure follows the team's
// "statistics worth displaying" guide: weight and dose changes, recorded vs calculated BMI, blood-pressure
// comparisons, and dated facts that must not be shown as trends. Only documented inputs live here;
// all differences, percentages and calculated BMIs are computed in src/lib/stats.ts.

const discharge2025: SourceCitation = {
  documentId: "doc-discharge-2025",
  documentLabel: "Entlassbrief Kardiologie, Juni 2025",
  excerpt: "Gewicht 81 kg, Größe 168 cm, BMI 28,7 kg/m². Ramipril 5 mg 1-0-0.",
};
const outpatient2026: SourceCitation = {
  documentId: "doc-outpatient-2026",
  documentLabel: "Ambulanzbrief, März 2026",
  excerpt: "Gewicht 70 kg, Größe 169 cm, BMI 28,4 kg/m².",
};
const admission2026: SourceCitation = {
  documentId: "doc-anamnesis-2026",
  documentLabel: "Aufnahmebogen, Okt. 2026",
  excerpt: "Gewicht 69 kg, Größe 168 cm, BMI 24,4 kg/m². Ramipril 5 mg morgens, 2,5 mg abends.",
};
const abpm2025: SourceCitation = {
  documentId: "doc-abpm-2025",
  documentLabel: "24-h-Blutdruckmessung, Juni 2025",
  excerpt: "Tagesmittel 136/86 mmHg, Nachtmittel 124/76 mmHg, 24-h-Mittel 132/83 mmHg.",
};
const emergency2025: SourceCitation = {
  ...discharge2025,
  excerpt: "Bei Aufnahme RR 178/104 mmHg, nach Akuttherapie 142/88 mmHg.",
};
const echo2025: SourceCitation = {
  ...discharge2025,
  excerpt: "Echokardiographie: LVEF 58 %. HbA1c 6,1 %.",
};

const anna: PatientStats = {
  patientId: "P-10482",
  recordsThrough: "2026-10-20",
  factsRemoved: 0,
  measurements: [
    {
      id: "m1",
      label: "Entlassung Juni 2025",
      date: "2025-06-27",
      weightKg: 81,
      heightCm: 168,
      recordedBmi: 28.7,
      source: discharge2025,
    },
    {
      id: "m2",
      label: "Ambulanz März 2026",
      date: "2026-03-12",
      weightKg: 70,
      heightCm: 169,
      recordedBmi: 28.4,
      source: outpatient2026,
    },
    {
      id: "m3",
      label: "Aufnahme Okt. 2026",
      date: "2026-10-14",
      weightKg: 69,
      heightCm: 168,
      recordedBmi: 24.4,
      source: admission2026,
    },
  ],
  doseChanges: [
    {
      id: "d1",
      drug: "Ramipril",
      unit: "mg/Tag",
      from: { value: 5, display: "5 mg/Tag", date: "2025-06-27", source: discharge2025 },
      to: { value: 7.5, display: "7,5 mg/Tag", date: "2026-10-14", source: admission2026 },
      scheduleNote:
        "5 mg morgens wurde zu 5 mg morgens + 2,5 mg abends. Beschreibt das verordnete Schema, nicht die Einnahme.",
    },
  ],
  bloodPressure: [
    {
      id: "bp1",
      label: "Akute Episode",
      context: "Vor und nach dokumentierter Notfallbehandlung",
      fromLabel: "Bei Aufnahme",
      toLabel: "Nach Akuttherapie",
      from: { systolic: 178, diastolic: 104 },
      to: { systolic: 142, diastolic: 88 },
      sources: [emergency2025],
    },
    {
      id: "bp2",
      label: "Tag und Nacht",
      context: "Mittelwerte der 24-h-Messung; Prozent bezogen auf den Tagesmittelwert",
      fromLabel: "Tag",
      toLabel: "Nacht",
      from: { systolic: 136, diastolic: 86 },
      to: { systolic: 124, diastolic: 76 },
      sources: [abpm2025],
    },
  ],
  reportedAverages: [
    { label: "24-h-Mittel (wie berichtet)", value: { systolic: 132, diastolic: 83 }, source: abpm2025 },
  ],
  datedFacts: [
    {
      id: "df1",
      label: "HbA1c",
      values: [{ display: "6,1 %", date: "2025-06-27", source: echo2025 }],
      note: "Einzelwert. Keine späteren Werte, daher kein Verlauf.",
    },
    {
      id: "df2",
      label: "Ejektionsfraktion (LVEF)",
      values: [{ display: "58 %", date: "2025-06-27", source: echo2025 }],
      note: "Einzelwert. Keine späteren Werte, daher kein Verlauf.",
    },
    {
      id: "df3",
      label: "Größe",
      values: [
        { display: "168 cm", date: "2025-06-27", source: discharge2025 },
        { display: "169 cm", date: "2026-03-12", source: outpatient2026 },
        { display: "168 cm", date: "2026-10-14", source: admission2026 },
      ],
      note: "Die Abweichung von 1 cm ist Messvariation, keine Größenänderung.",
    },
  ],
  notes: [
    "Ursache und Absicht der Gewichtsabnahme sind nicht dokumentiert.",
    "Die genauen Messtage sind nicht angegeben; daher wird keine Rate pro Tag oder Monat berechnet.",
  ],
};

const klausGp: SourceCitation = {
  documentId: "doc-gp-2025",
  documentLabel: "Hausarztbrief, Sept. 2025",
  excerpt: "Gewicht 92 kg, Größe 176 cm. Torasemid 10 mg 1-0-0.",
};
const klausPlan: SourceCitation = {
  documentId: "doc-medplan-2026b",
  documentLabel: "Medikationsplan Hausarzt, Aug. 2026",
  excerpt: "Gewicht 88 kg, Größe 176 cm, BMI 28,4 kg/m². Torasemid 5 mg 1-0-0.",
};

const klaus: PatientStats = {
  patientId: "P-20917",
  recordsThrough: "2026-09-30",
  factsRemoved: 0,
  measurements: [
    {
      id: "m1",
      label: "Hausarzt Sept. 2025",
      date: "2025-09-10",
      weightKg: 92,
      heightCm: 176,
      recordedBmi: null,
      source: klausGp,
    },
    {
      id: "m2",
      label: "Medikationsplan Aug. 2026",
      date: "2026-08-20",
      weightKg: 88,
      heightCm: 176,
      recordedBmi: 28.4,
      source: klausPlan,
    },
  ],
  doseChanges: [
    {
      id: "d1",
      drug: "Torasemid",
      unit: "mg/Tag",
      from: { value: 10, display: "10 mg/Tag", date: "2025-09-10", source: klausGp },
      to: { value: 5, display: "5 mg/Tag", date: "2026-08-20", source: klausPlan },
    },
  ],
  bloodPressure: [],
  reportedAverages: [],
  datedFacts: [],
  notes: [],
};

export const mockStats: Record<string, PatientStats> = {
  [anna.patientId]: anna,
  [klaus.patientId]: klaus,
};

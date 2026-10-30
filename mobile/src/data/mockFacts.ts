import type { PatientBrief } from "@/types/fact";
import type { RoleId } from "@/data/roles";

// Fake patient briefs so every screen can be built and demoed without the backend.

const anaesthetistBrief: PatientBrief = {
  patientId: "P-10482",
  patientLabel: "Fiktive Testperson A, 58 J.",
  role: "anaesthetist",
  task: "Prämedikation: Mamma-OP",
  generatedAt: "2026-10-29T08:12:00Z",
  facts: [
    {
      id: "an-1",
      label: "Antikoagulation",
      value: "Apixaban 5 mg 1-0-1",
      trust: "verified",
      source: {
        documentId: "doc-medplan-2026",
        documentLabel: "Bundeseinheitlicher Medikationsplan, Sept. 2026",
        excerpt: "Apixaban 5 mg, 1-0-1, bei Vorhofflimmern",
      },
      guideline: {
        guidelineName: "DGAI/DGCH Empfehlung perioperatives Gerinnungsmanagement",
        excerpt: "Pausierung direkter oraler Antikoagulanzien abhängig von Blutungsrisiko und Nierenfunktion.",
      },
      // invented: the dose a newer letter replaced (Details: "Medication changes")
      rows: [
        {
          id: "an-1:now",
          text: "Apixaban 5 mg 1-0-1",
          date: "01.09.2026",
          sources: [
            {
              documentId: "doc-medplan-2026",
              documentLabel: "Bundeseinheitlicher Medikationsplan, Sept. 2026",
              excerpt: "Apixaban 5 mg, 1-0-1, bei Vorhofflimmern",
            },
          ],
        },
      ],
      superseded: [
        {
          id: "an-1:old",
          text: "Apixaban 2,5 mg 1-0-1",
          date: "12.03.2026",
          sources: [
            {
              documentId: "doc-outpatient-2026",
              documentLabel: "Ambulanzbrief, März 2026",
              excerpt: "Apixaban 2,5 mg 1-0-1.",
            },
          ],
        },
      ],
    },
    {
      // invented: weight series as the backend sends a trend need (Details: "Changes over time")
      id: "an-6",
      label: "Gewicht",
      value: "81 kg → 70 kg → 69 kg",
      trust: "consistent",
      source: {
        documentId: "doc-discharge-2025",
        documentLabel: "Entlassbrief Kardiologie, Juni 2025",
        excerpt: "Gewicht 81 kg, Größe 168 cm.",
      },
      sources: [
        { documentId: "doc-discharge-2025", documentLabel: "Entlassbrief Kardiologie, Juni 2025", excerpt: "Gewicht 81 kg, Größe 168 cm." },
        { documentId: "doc-outpatient-2026", documentLabel: "Ambulanzbrief, März 2026", excerpt: "Gewicht 70 kg, Größe 169 cm, BMI 28,4 kg/m²." },
        { documentId: "doc-anamnesis-2026", documentLabel: "Aufnahmebogen, Okt. 2026", excerpt: "Gewicht 69 kg, Größe 168 cm." },
      ],
      isTimeSeries: true,
      history: [
        { date: "2025-06-27", value: "81", unit: "kg" },
        { date: "2026-03-12", value: "70", unit: "kg" },
        { date: "2026-10-14", value: "69", unit: "kg" },
      ],
      trend: {
        points: [
          { value: "81 kg", date: "27.06.2025" },
          { value: "70 kg", date: "12.03.2026" },
          { value: "69 kg", date: "14.10.2026" },
        ],
        numbers: [81, 70, 69],
        change: "−12 kg in 16 Monaten",
        formula: "69 kg − 81 kg",
      },
      rows: [
        {
          id: "an-6:bmi",
          text: "BMI: 24,4 kg/m²",
          computed: true,
          note: "69 kg / (1,68 m)²",
          sources: [{ documentId: "doc-anamnesis-2026", documentLabel: "Aufnahmebogen, Okt. 2026", excerpt: "Gewicht 69 kg, Größe 168 cm." }],
        },
      ],
    },
    {
      id: "an-2",
      label: "Allergien",
      value: "Penicillin (Exanthem)",
      trust: "verified",
      source: {
        documentId: "doc-discharge-2015",
        documentLabel: "Entlassbrief Innere Medizin, Juni 2015",
        excerpt: "Bekannte Allergie: Penicillin (Exanthem 2009).",
      },
    },
    {
      id: "an-3",
      label: "Atemweg / Intubation",
      value: "Schwierige Intubation möglich",
      trust: "ai_inferred",
      confidence: 0.62,
      source: {
        documentId: "doc-op-2019",
        documentLabel: "Narkoseprotokoll Cholezystektomie, März 2019",
        excerpt: "Intubation im 2. Versuch mit Videolaryngoskop, Cormack-Lehane III.",
      },
    },
    {
      id: "an-4",
      label: "Kreatinin",
      value: "1,3 mg/dl",
      trust: "verified",
      isTimeSeries: true,
      history: [
        { date: "2025-11-02", value: "1,0" },
        { date: "2026-03-14", value: "1,1" },
        { date: "2026-07-21", value: "1,2" },
        { date: "2026-10-20", value: "1,3" },
      ],
      source: {
        documentId: "doc-lab-2026-10",
        documentLabel: "Laborbefund, 20.10.2026",
        excerpt: "Kreatinin 1,3 mg/dl (Ref. 0,5–0,9)",
      },
    },
    {
      id: "an-5",
      label: "Nüchternheit / PONV-Anamnese",
      value: null,
      trust: "not_documented",
      guideline: {
        guidelineName: "S3-Leitlinie PONV",
        excerpt: "Erhebung der Risikofaktoren nach Apfel-Score vor elektiven Eingriffen.",
      },
    },
  ],
  contradictions: [
    {
      id: "an-c1",
      factLabel: "Allergien",
      severity: "high",
      conflictingSources: [
        {
          documentId: "doc-discharge-2015",
          documentLabel: "Entlassbrief Innere Medizin, Juni 2015",
          excerpt: "Bekannte Allergie: Penicillin (Exanthem 2009).",
        },
        {
          documentId: "doc-anamnesis-2026",
          documentLabel: "Aufnahmebogen, Okt. 2026",
          excerpt: "Allergien: keine bekannt.",
        },
      ],
    },
    {
      // invented: data-quality note (Details: "Record checks")
      id: "an-n1",
      factLabel: "BMI",
      tier: "documentation_note",
      explanation: "Im Ambulanzbrief steht BMI 28,4 kg/m²; aus 70 kg und 169 cm ergeben sich 24,5 kg/m².",
      conflictingSources: [
        { documentId: "doc-outpatient-2026", documentLabel: "Ambulanzbrief, März 2026", excerpt: "Gewicht 70 kg, Größe 169 cm, BMI 28,4 kg/m²." },
      ],
    },
  ],
  // invented: a task fact the latest letter no longer mentions (Details: "Blind spot")
  gaps: [
    {
      id: "an-g1",
      kind: "dropped",
      title: "Schlafapnoe",
      explanation: "Zuletzt erwähnt im Entlassbrief Kardiologie, Juni 2025; im neuesten Brief nicht mehr aufgeführt.",
      sources: [
        { documentId: "doc-discharge-2025", documentLabel: "Entlassbrief Kardiologie, Juni 2025", excerpt: "Nebendiagnosen: Obstruktive Schlafapnoe (CPAP)." },
      ],
    },
  ],
};

const pharmacistBrief: PatientBrief = {
  patientId: "P-20917",
  patientLabel: "Fiktive Testperson B, 74 J.",
  role: "pharmacist",
  task: "Medikationsanalyse: Polypharmazie",
  generatedAt: "2026-10-29T08:12:00Z",
  facts: [
    {
      id: "ph-1",
      label: "Anzahl Dauermedikamente",
      value: "11",
      trust: "verified",
      source: {
        documentId: "doc-medplan-2026b",
        documentLabel: "Medikationsplan Hausarzt, Aug. 2026",
        excerpt: "Dauermedikation (11 Wirkstoffe) siehe Tabelle.",
      },
    },
    {
      id: "ph-2",
      label: "eGFR",
      value: "38 ml/min/1,73 m²",
      trust: "verified",
      isTimeSeries: true,
      history: [
        { date: "2025-09-10", value: "52" },
        { date: "2026-02-01", value: "45" },
        { date: "2026-09-30", value: "38" },
      ],
      source: {
        documentId: "doc-lab-2026-09",
        documentLabel: "Laborbefund, 30.09.2026",
        excerpt: "eGFR (CKD-EPI) 38 ml/min/1,73 m²",
      },
      guideline: {
        guidelineName: "Hausärztliche Leitlinie Multimedikation",
        excerpt: "Dosisanpassung renal eliminierter Wirkstoffe bei eingeschränkter Nierenfunktion prüfen.",
      },
    },
    {
      id: "ph-3",
      label: "Metformin",
      value: "1000 mg 1-0-1",
      trust: "ai_inferred",
      confidence: 0.71,
      source: {
        documentId: "doc-letter-2026",
        documentLabel: "Arztbrief Diabetologie, Juli 2026",
        excerpt: "Metformin wie bisher fortführen.",
      },
    },
    {
      id: "ph-4",
      label: "Selbstmedikation (OTC)",
      value: null,
      trust: "not_documented",
    },
  ],
  contradictions: [
    {
      id: "ph-c1",
      factLabel: "Metformin",
      severity: "medium",
      conflictingSources: [
        {
          documentId: "doc-medplan-2026b",
          documentLabel: "Medikationsplan Hausarzt, Aug. 2026",
          excerpt: "Metformin 500 mg 1-0-1",
        },
        {
          documentId: "doc-letter-2026",
          documentLabel: "Arztbrief Diabetologie, Juli 2026",
          excerpt: "Metformin 1000 mg 1-0-1",
        },
      ],
    },
  ],
};

const surgeonBrief: PatientBrief = {
  patientId: "P-31055",
  patientLabel: "Fiktive Testperson C, 66 J.",
  role: "surgeon",
  task: "OP-Planung: Hüft-TEP rechts",
  generatedAt: "2026-10-29T08:12:00Z",
  facts: [
    {
      id: "su-1",
      label: "Voroperationen",
      value: "Appendektomie 1992, Hysterektomie 2011",
      trust: "verified",
      source: {
        documentId: "doc-anamnesis-2026c",
        documentLabel: "Aufnahmebogen, Okt. 2026",
        excerpt: "Vor-OPs: Appendektomie (1992), Hysterektomie (2011).",
      },
    },
    {
      id: "su-2",
      label: "Hämoglobin",
      value: "11,2 g/dl",
      trust: "verified",
      source: {
        documentId: "doc-lab-2026-10c",
        documentLabel: "Laborbefund, 22.10.2026",
        excerpt: "Hb 11,2 g/dl (Ref. 12,0–15,4)",
      },
      guideline: {
        guidelineName: "Patient Blood Management (PBM)",
        excerpt: "Präoperative Anämie vor elektiven Eingriffen mit hohem Blutungsrisiko abklären.",
      },
    },
    {
      id: "su-3",
      label: "Metallallergie",
      value: "Nickel möglich",
      trust: "ai_inferred",
      confidence: 0.48,
      source: {
        documentId: "doc-derm-2018",
        documentLabel: "Dermatologischer Befund, 2018",
        excerpt: "Kontaktekzem, V. a. Nickelsensibilisierung.",
      },
    },
    {
      id: "su-4",
      label: "Thromboserisiko",
      value: null,
      trust: "not_documented",
    },
  ],
  contradictions: [],
};

const gpBrief: PatientBrief = {
  patientId: "P-40220",
  patientLabel: "Fiktive Testperson D, 49 J.",
  role: "gp",
  task: "Nachsorge: nach Krankenhausaufenthalt",
  generatedAt: "2026-10-29T08:12:00Z",
  facts: [
    {
      id: "gp-1",
      label: "Entlassdiagnose",
      value: "NSTEMI, PCI mit DES (RIVA)",
      trust: "verified",
      source: {
        documentId: "doc-discharge-2026d",
        documentLabel: "Entlassbrief Kardiologie, Okt. 2026",
        excerpt: "Diagnose: NSTEMI. Therapie: PCI mit DES-Implantation RIVA.",
      },
    },
    {
      id: "gp-2",
      label: "Duale Plättchenhemmung: Dauer",
      value: "12 Monate",
      trust: "ai_inferred",
      confidence: 0.66,
      source: {
        documentId: "doc-discharge-2026d",
        documentLabel: "Entlassbrief Kardiologie, Okt. 2026",
        excerpt: "ASS + Ticagrelor gemäß Leitlinie fortführen.",
      },
    },
    {
      id: "gp-3",
      label: "LDL-Cholesterin",
      value: "142 mg/dl",
      trust: "verified",
      isTimeSeries: true,
      history: [
        { date: "2025-06-01", value: "168" },
        { date: "2026-01-12", value: "155" },
        { date: "2026-10-05", value: "142" },
      ],
      source: {
        documentId: "doc-lab-2026-10d",
        documentLabel: "Laborbefund, 05.10.2026",
        excerpt: "LDL-C 142 mg/dl",
      },
    },
    {
      id: "gp-4",
      label: "Kardiologische Reha",
      value: null,
      trust: "not_documented",
    },
  ],
  contradictions: [],
};

export const mockBriefs: Partial<Record<RoleId, PatientBrief>> = {
  anaesthetist: anaesthetistBrief,
  pharmacist: pharmacistBrief,
  surgeon: surgeonBrief,
  gp: gpBrief,
};

// English mode: the invented demo briefs above are written in German. Labels, values and explanations are shown
// in English; quotes from the letters (excerpt) and letter titles (documentLabel) stay as written, because
// they are the source a clinician checks against. Decimal commas become points and dates follow the UI
// language, like the backend's own fields.
const english: Record<string, string> = {
  "Fiktive Testperson A, 58 J.": "Fictitious test person A, 58 y",
  "Fiktive Testperson B, 74 J.": "Fictitious test person B, 74 y",
  "Fiktive Testperson C, 66 J.": "Fictitious test person C, 66 y",
  "Fiktive Testperson D, 49 J.": "Fictitious test person D, 49 y",
  Antikoagulation: "Anticoagulation",
  Gewicht: "Weight",
  Allergien: "Allergies",
  "Penicillin (Exanthem)": "Penicillin (rash)",
  "Atemweg / Intubation": "Airway / intubation",
  "Schwierige Intubation möglich": "Difficult intubation possible",
  Kreatinin: "Creatinine",
  "Nüchternheit / PONV-Anamnese": "Fasting / PONV history",
  "−12 kg in 16 Monaten": "−12 kg in 16 months",
  "Im Ambulanzbrief steht BMI 28,4 kg/m²; aus 70 kg und 169 cm ergeben sich 24,5 kg/m².":
    "The outpatient letter states BMI 28.4 kg/m²; 70 kg and 169 cm give 24.5 kg/m².",
  Schlafapnoe: "Sleep apnoea",
  "Zuletzt erwähnt im Entlassbrief Kardiologie, Juni 2025; im neuesten Brief nicht mehr aufgeführt.":
    "Last mentioned in the cardiology discharge letter, June 2025; not listed in the latest letter.",
  "Anzahl Dauermedikamente": "Number of regular medications",
  "Selbstmedikation (OTC)": "Self-medication (OTC)",
  Voroperationen: "Previous operations",
  "Appendektomie 1992, Hysterektomie 2011": "Appendectomy 1992, hysterectomy 2011",
  Hämoglobin: "Haemoglobin",
  Metallallergie: "Metal allergy",
  "Nickel möglich": "Nickel possible",
  Thromboserisiko: "Thrombosis risk",
  Entlassdiagnose: "Discharge diagnosis",
  "NSTEMI, PCI mit DES (RIVA)": "NSTEMI, PCI with DES (LAD)",
  "Duale Plättchenhemmung: Dauer": "Dual antiplatelet therapy: duration",
  "12 Monate": "12 months",
  "LDL-Cholesterin": "LDL cholesterol",
  "Kardiologische Reha": "Cardiac rehabilitation",
};

// Keys whose strings are display text (translated); everything else (quotes, ids, ISO dates) is left alone
const textKeys = new Set(["patientLabel", "label", "value", "text", "change", "formula", "note", "title", "explanation", "factLabel"]);
const germanDate = /^(\d{2})\.(\d{2})\.(\d{4})$/;

function toEnglish(text: string, formatDate: (iso: string) => string): string {
  const date = germanDate.exec(text);
  if (date) return formatDate(`${date[3]}-${date[2]}-${date[1]}`);
  return (english[text] ?? text).replace(/(\d),(\d)/g, "$1.$2");
}

export function mockBriefInEnglish(brief: PatientBrief, formatDate: (iso: string) => string): PatientBrief {
  const walk = (node: unknown, key = ""): unknown => {
    // history readings stay raw ("1,0"): they are parsed as numbers and formatted where they are shown
    if (key === "history") return node;
    if (typeof node === "string") {
      if (key === "date") return germanDate.test(node) ? toEnglish(node, formatDate) : node;
      return textKeys.has(key) ? toEnglish(node, formatDate) : node;
    }
    if (Array.isArray(node)) return node.map((item) => walk(item));
    if (node && typeof node === "object") {
      return Object.fromEntries(Object.entries(node).map(([k, v]) => [k, walk(v, k)]));
    }
    return node;
  };
  return walk(brief) as PatientBrief;
}

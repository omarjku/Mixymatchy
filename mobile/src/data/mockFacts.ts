import type { PatientBrief } from "@/types/fact";
import type { RoleId } from "@/data/roles";

// Fake patient briefs so every screen can be built and demoed without the backend.

const anaesthetistBrief: PatientBrief = {
  patientId: "P-10482",
  patientLabel: "Anna Musterfrau, 58 J.",
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
  ],
};

const pharmacistBrief: PatientBrief = {
  patientId: "P-20917",
  patientLabel: "Klaus Beispiel, 74 J.",
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
  patientLabel: "Maria Muster, 66 J.",
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
  patientLabel: "Peter Probe, 49 J.",
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

export const mockBriefs: Record<RoleId, PatientBrief> = {
  anaesthetist: anaesthetistBrief,
  pharmacist: pharmacistBrief,
  surgeon: surgeonBrief,
  gp: gpBrief,
};

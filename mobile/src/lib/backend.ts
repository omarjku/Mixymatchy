import { t } from "@/i18n/strings";
import type { Contradiction, Fact, FactTrust, PatientBrief, RecordGap, SourceCitation } from "@/types/fact";

// Backend contract (backend/app/schema.py, docs/INTEGRATION.md) and the mapping into the app's PatientBrief.
// Rule: every clinical string shown comes from the backend; this file only rearranges it.

// Relative paths: the Vite dev server proxies them to FastAPI, and production serves the app from FastAPI.
const API = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";

type BackendTrust = "consistent" | "conflicting" | "stale" | "single";

interface BackendFact {
  id: string;
  type: string;
  concept: string;
  label_en: string;
  value: string | null;
  unit: string | null;
  date: string | null;
  segment_ids: string[];
  trust: BackendTrust;
}

interface BackendComputed {
  label: string;
  value: string;
  formula: string;
  segment_ids: string[];
}

interface BackendSourceRef {
  id: string;
  title: string;
  url?: string | null;
}

interface BackendNeed {
  need: string;
  label: string;
  status: "documented" | "not_documented" | "not_applicable";
  facts: BackendFact[];
  computed: BackendComputed[];
  reason?: string | null;
  reason_segment_ids: string[];
  shape?: string | null;
  priority?: string | null;
  why?: string | null;
  sources?: BackendSourceRef[];
  note?: string | null;
}

interface BackendFinding {
  id: string;
  kind: "conflict" | "dropped" | "followup" | "silence";
  tier: "contradiction" | "documentation_note" | null;
  title: string;
  explanation: string;
  segment_ids: string[];
  severity: "high" | "medium" | "low";
}

export interface BackendBriefing {
  situation: string;
  role: string;
  as_of: string;
  needs: BackendNeed[];
  blind_spot: BackendFact[];
  findings: BackendFinding[];
  stats: Record<string, number>;
  detail?: "short" | "long" | null;
  routing?: { fallback_note?: string | null; anchor_date?: string };
}

interface BackendSegment {
  id: string;
  doc_id: string;
  text: string;
}

interface BackendDocument {
  id: string;
  title: string;
  date: string;
  text: string;
  segments: BackendSegment[];
}

async function getJson<T>(path: string, init: RequestInit | undefined, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API}${path}`, { ...init, signal });
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`);
  return (await response.json()) as T;
}

export function fetchBriefing(situation: string, detail: "short" | "long", signal?: AbortSignal) {
  return getJson<BackendBriefing>(
    "/briefing",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ situation, detail }) },
    signal,
  );
}

// Documents are small (8 letters) and never change, so each is fetched once per session.
const documentCache = new Map<string, Promise<BackendDocument>>();

function fetchDocument(id: string, signal?: AbortSignal): Promise<BackendDocument> {
  let pending = documentCache.get(id);
  if (!pending) {
    pending = getJson<BackendDocument>(`/documents/${encodeURIComponent(id)}`, undefined, signal);
    pending.catch(() => documentCache.delete(id));
    documentCache.set(id, pending);
  }
  return pending;
}

function segmentIdsOf(briefing: BackendBriefing): string[] {
  const ids = new Set<string>();
  for (const need of briefing.needs) {
    need.facts.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
    need.computed.forEach((c) => c.segment_ids.forEach((s) => ids.add(s)));
    need.reason_segment_ids.forEach((s) => ids.add(s));
  }
  briefing.blind_spot.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
  briefing.findings.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
  return [...ids];
}

const docIdOf = (segmentId: string) => segmentId.split(":")[0];

// Needs with more facts than this are shortened (none of the five demo situations has more than 15).
const LONG_LIST = 20;
const LONG_LIST_SHOWN = 8;

function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}.${m}.${y}` : iso;
}

type Citer = (segmentIds: string[]) => SourceCitation[];

// Loads every document the briefing cites and returns a function that turns segment ids into citations.
async function loadCiter(briefing: BackendBriefing, signal?: AbortSignal): Promise<Citer> {
  const ids = segmentIdsOf(briefing);
  const docs = await Promise.all([...new Set(ids.map(docIdOf))].map((id) => fetchDocument(id, signal)));
  const docById = new Map(docs.map((d) => [d.id, d]));
  const segById = new Map(docs.flatMap((d) => d.segments.map((s) => [s.id, s] as const)));
  return (segmentIds) =>
    segmentIds.flatMap((id) => {
      const seg = segById.get(id);
      const doc = docById.get(docIdOf(id));
      if (!seg || !doc) return [];
      return [{ documentId: doc.id, documentLabel: `${doc.title}, ${formatDate(doc.date)}`, excerpt: seg.text }];
    });
}

const trustOf: Record<BackendTrust, FactTrust> = {
  consistent: "verified",
  single: "verified",
  conflicting: "conflicting",
  stale: "outdated",
};

function factValue(f: BackendFact): string {
  const measured = f.value ? `${f.value}${f.unit ? ` ${f.unit}` : ""}` : "";
  return measured && !f.label_en.includes(f.value ?? "") ? `${f.label_en}: ${measured}` : f.label_en;
}

function toFact(id: string, label: string, f: BackendFact, cite: Citer, need: BackendNeed): Fact {
  const sources = cite(f.segment_ids);
  return {
    id,
    label,
    value: factValue(f),
    trust: trustOf[f.trust],
    source: sources[0],
    sources,
    note: need.note ?? undefined,
    guideline: guidelineOf(need),
  };
}

// "Why this is shown": the knowledge base's reason plus its first guideline. Never advice for this patient.
function guidelineOf(need: BackendNeed): Fact["guideline"] {
  const ref = need.sources?.[0];
  if (!ref || !need.why) return undefined;
  return { guidelineName: ref.title, excerpt: need.why, reference: ref.url ?? undefined };
}

function needToFacts(need: BackendNeed, cite: Citer): Fact[] {
  if (need.status === "not_documented") {
    return [{ id: need.need, label: need.label, value: null, trust: "not_documented", note: need.note ?? undefined }];
  }
  if (need.status === "not_applicable") {
    const sources = cite(need.reason_segment_ids);
    return [{
      id: need.need, label: need.label, value: `${t("results.notApplicable")}: ${need.reason ?? ""}`.trim(),
      trust: "verified", source: sources[0], sources,
    }];
  }

  const facts: Fact[] = [];
  // Trend: one card with the latest value and the documented history (oldest first).
  const numeric = need.facts.filter((f) => f.value && /\d/.test(f.value));
  if (need.shape === "trend" && numeric.length >= 2) {
    const latest = numeric[numeric.length - 1];
    facts.push({
      ...toFact(`${need.need}:${latest.id}`, need.label, latest, cite, need),
      isTimeSeries: true,
      history: numeric.map((f) => ({ date: f.date ?? "", value: `${f.value}${f.unit ? ` ${f.unit}` : ""}` })),
      sources: cite(numeric.flatMap((f) => f.segment_ids)),
    });
    need.facts.filter((f) => !numeric.includes(f)).forEach((f) =>
      facts.push(toFact(`${need.need}:${f.id}`, need.label, f, cite, need)));
  } else if (need.facts.length > LONG_LIST) {
    // Very long lists (e.g. every diagnosis mention in a general summary) would bury the screen on a phone:
    // show the first entries, then one row that keeps all remaining passages one tap away.
    need.facts.slice(0, LONG_LIST_SHOWN).forEach((f) => facts.push(toFact(`${need.need}:${f.id}`, need.label, f, cite, need)));
    const rest = need.facts.slice(LONG_LIST_SHOWN);
    const sources = cite(rest.flatMap((f) => f.segment_ids));
    facts.push({
      id: `${need.need}:more`, label: need.label, value: t("results.moreEntries", { n: rest.length }),
      trust: "verified", source: sources[0], sources, note: rest.map((f) => f.label_en).join("; "),
    });
  } else {
    need.facts.forEach((f) => facts.push(toFact(`${need.need}:${f.id}`, need.label, f, cite, need)));
  }
  need.computed.forEach((c, i) => {
    const sources = cite(c.segment_ids);
    facts.push({
      id: `${need.need}:computed:${i}`, label: c.label, value: c.value, trust: "verified",
      source: sources[0], sources, note: c.formula, computed: true,
    });
  });
  return facts;
}

export async function toPatientBrief(
  briefing: BackendBriefing,
  role: string,
  task: string,
  signal?: AbortSignal,
): Promise<PatientBrief> {
  const cite = await loadCiter(briefing, signal);
  const age = briefing.needs.flatMap((n) => n.computed).find((c) => /^age$/i.test(c.label))?.value;

  const contradictions: Contradiction[] = briefing.findings
    .filter((f) => f.kind === "conflict")
    .map((f) => ({
      id: f.id,
      factLabel: f.title,
      explanation: f.explanation,
      conflictingSources: cite(f.segment_ids),
      severity: f.severity,
      tier: f.tier ?? "contradiction",
    }));

  const gaps: RecordGap[] = [
    ...briefing.findings
      .filter((f): f is BackendFinding & { kind: RecordGap["kind"] } => f.kind !== "conflict")
      .map((f) => ({ id: f.id, kind: f.kind, title: f.title, explanation: f.explanation, sources: cite(f.segment_ids) })),
  ];

  return {
    patientId: "0000-0001",
    patientLabel: age ? `Patient 0000-0001, ${age}` : "Patient 0000-0001",
    role,
    task,
    facts: briefing.needs.flatMap((n) => needToFacts(n, cite)),
    contradictions,
    gaps,
    stats: briefing.stats,
    routeNote: briefing.routing?.fallback_note ?? null,
    // "Stand" = the date of the latest document, the time anchor for "current" values
    generatedAt: `${briefing.routing?.anchor_date ?? briefing.as_of}T12:00:00`,
  };
}

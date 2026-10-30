import { secureFetch } from "@/second-look";
import type { Contradiction, Fact, FactRow, FactTrust, PatientBrief, RecordGap, SourceCitation } from "@/types/fact";

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
  collapsed?: boolean; // short view: behind "+N more" on its card
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
  superseded?: BackendFact[]; // older values replaced by a newer letter / medication list
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
  on_screen?: boolean;
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
  task?: string;
  routing?: {
    fallback_note?: string | null;
    role_label?: string | null;
    applicability_note?: string | null;
    applicability?: { passage?: string | null } | null;
    other_record_issues?: number;
    also_relevant?: string[];
    anchor_date?: string;
    // clinical gate: "not_authorised" = no clinical role stated; "needs_task" = clinical role but no task
    // (greeting, filler, role only; docs/DECISIONS.md 19); needs/findings are empty in both
    screen_mode?: string | null;
    message?: string | null;
    suggestions?: string[];
    role_missing?: boolean;   // needs_task because no requester role was stated (DECISIONS 19)
  };
}

export interface BackendSegment {
  id: string;
  doc_id: string;
  text: string;
  start: number;
  end: number;
}

export interface BackendDocument {
  id: string;
  title: string;
  date: string;
  department?: string;
  type?: string;
  text: string;
  segments: BackendSegment[];
}

async function getJson<T>(path: string, init: RequestInit | undefined, signal?: AbortSignal): Promise<T> {
  const response = await secureFetch(`${API}${path}`, { ...init, signal });
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

export function fetchDocument(id: string, signal?: AbortSignal): Promise<BackendDocument> {
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
    need.superseded?.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
    need.reason_segment_ids.forEach((s) => ids.add(s));
  }
  briefing.blind_spot.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
  briefing.findings.forEach((f) => f.segment_ids.forEach((s) => ids.add(s)));
  const passage = briefing.routing?.applicability?.passage;
  if (passage) ids.add(passage);
  return [...ids];
}

export const docIdOf = (segmentId: string) => segmentId.split(":")[0];

export function formatDate(iso: string): string {
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}.${m}.${y}` : iso;
}

type Citer = (segmentIds: string[]) => SourceCitation[];

// Loads every document the briefing cites and returns a function that turns segment ids into citations.
async function loadCiter(briefings: BackendBriefing[], signal?: AbortSignal): Promise<Citer> {
  const ids = [...new Set(briefings.flatMap(segmentIdsOf))];
  const docs = await Promise.all([...new Set(ids.map(docIdOf))].map((id) => fetchDocument(id, signal)));
  const docById = new Map(docs.map((d) => [d.id, d]));
  const segById = new Map(docs.flatMap((d) => d.segments.map((s) => [s.id, s] as const)));
  return (segmentIds) =>
    segmentIds.flatMap((id) => {
      const seg = segById.get(id);
      const doc = docById.get(docIdOf(id));
      if (!seg || !doc) return [];
      return [{ documentId: doc.id, documentLabel: `${doc.title}, ${formatDate(doc.date)}`, excerpt: seg.text, segmentId: id }];
    });
}

const trustOf: Record<BackendTrust, FactTrust> = {
  consistent: "consistent",
  single: "single",
  conflicting: "conflicting",
  stale: "outdated",
};

function factValue(f: BackendFact): string {
  const measured = f.value ? `${f.value}${f.unit ? ` ${f.unit}` : ""}` : "";
  return measured && !f.label_en.includes(f.value ?? "") ? `${f.label_en}: ${measured}` : f.label_en;
}

// "Why this is shown": the knowledge base's reason plus its first guideline. Never advice for this patient.
function guidelineOf(need: BackendNeed): Fact["guideline"] {
  const ref = need.sources?.[0];
  if (!ref || !need.why) return undefined;
  return { guidelineName: ref.title, excerpt: need.why, reference: ref.url ?? undefined };
}

function needToFacts(need: BackendNeed, cite: Citer): Fact[] {
  if (need.status === "not_documented") {
    return [{
      id: need.need, label: need.label, value: null, trust: "not_documented", note: need.note ?? undefined,
      priority: need.priority ?? undefined,
    }];
  }
  if (need.status === "not_applicable") {
    const sources = cite(need.reason_segment_ids);
    return [{
      id: need.need, label: need.label, value: need.reason ?? null,
      trust: "not_applicable", source: sources[0], sources, priority: need.priority ?? undefined,
    }];
  }

  // One card per need: every fact is one compact row (value · date · source); facts the engine marked
  // "collapsed" sit behind "+N more" on the card, still with their source links.
  const rows: FactRow[] = need.facts.map((f) => ({
    id: `${need.need}:${f.id}`, text: factValue(f), date: f.date ? formatDate(f.date) : undefined,
    sources: cite(f.segment_ids), collapsed: f.collapsed || undefined,
  }));
  need.computed.forEach((c, i) => rows.push({
    id: `${need.need}:computed:${i}`, text: `${c.label}: ${c.value}`, sources: cite(c.segment_ids),
    computed: true, note: c.formula,
  }));
  // card trust: any conflict wins, then all outdated, then consistent (some fact in 2+ letters), else single
  const tiers = need.facts.map((f) => trustOf[f.trust]);
  const trust: FactTrust = tiers.includes("conflicting") ? "conflicting"
    : tiers.length > 0 && tiers.every((x) => x === "outdated") ? "outdated"
    : tiers.includes("consistent") ? "consistent" : "single";
  const sources = cite([...new Set([...need.facts, ...need.computed].flatMap((f) => f.segment_ids))]);
  const fact: Fact = {
    id: need.need,
    label: need.label,
    value: rows.filter((r) => !r.collapsed).map((r) => r.text).join("; ") || null,
    trust: need.facts.length === 0 && need.computed.length > 0 ? "consistent" : trust,
    source: sources[0],
    sources,
    note: need.note ?? undefined,
    guideline: guidelineOf(need),
    priority: need.priority ?? undefined,
    rows,
  };
  // Details view ("Medication changes"): the older values a newer letter replaced, each with its source
  if (need.superseded?.length) {
    fact.superseded = need.superseded.map((f) => ({
      id: `${need.need}:old:${f.id}`, text: factValue(f), date: f.date ? formatDate(f.date) : undefined,
      sources: cite(f.segment_ids),
    }));
  }

  // Trend: one line "78 kg → 67 kg → 66 kg" plus the calculated change (one numeric series in one unit).
  const numeric = need.facts.filter((f) => f.value && f.date && /^-?\d+([.,]\d+)?$/.test(f.value));
  const oneUnit = numeric.every((f) => (f.unit ?? "") === (numeric[0]?.unit ?? ""));
  if (need.shape === "trend" && numeric.length >= 2 && numeric.length === need.facts.length && oneUnit) {
    const sorted = [...numeric].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
    const change = need.computed[0];
    fact.trend = {
      points: sorted.map((f) => ({
        value: `${f.value}${f.unit ? ` ${f.unit}` : ""}`, date: formatDate(f.date!), collapsed: f.collapsed || undefined,
      })),
      numbers: sorted.map((f) => Number(f.value!.replace(",", "."))),
      change: change?.value,
      formula: change?.formula,
    };
  }
  // History view: a need with two or more dated values in one unit gets their history.
  const dated = numeric.filter((f) => (f.unit ?? "") === (numeric[0]?.unit ?? ""));
  if (dated.length >= 2 && dated.length === numeric.length) Object.assign(fact, { isTimeSeries: true, history: historyOf(dated) });
  return [fact];
}

// Dated values oldest first, number and unit as the backend sends them (value / unit fields).
function historyOf(facts: BackendFact[]): NonNullable<Fact["history"]> {
  return [...facts]
    .filter((f) => f.date && f.value)
    .sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""))
    .map((f) => ({ date: f.date ?? "", value: f.value ?? "", unit: f.unit ?? undefined }));
}

// P1 needs are the screen; the P2 needs listed in routing.also_relevant form the visible "Also relevant" group.
export async function toPatientBrief(
  briefing: BackendBriefing,
  role: string,
  task: string,
  signal?: AbortSignal,
): Promise<PatientBrief> {
  const alsoIds = new Set(briefing.routing?.also_relevant ?? []);
  const isAlso = (n: BackendNeed) => alsoIds.has(n.need);
  const alsoNeeds = briefing.needs.filter(isAlso);
  const cite = await loadCiter([briefing], signal);
  const age = briefing.needs.flatMap((n) => n.computed).find((c) => /^age$/i.test(c.label))?.value;
  // Only what touches this task's screen; the rest is counted in stats.other_record_issues.
  const onScreen = briefing.findings.filter((f) => f.on_screen !== false);

  const contradictions: Contradiction[] = onScreen
    .filter((f) => f.kind === "conflict")
    .map((f) => ({
      id: f.id,
      factLabel: f.title,
      explanation: f.explanation,
      conflictingSources: cite(f.segment_ids),
      severity: f.severity,
      tier: f.tier ?? "contradiction",
    }));

  const gaps: RecordGap[] = onScreen
    .filter((f): f is BackendFinding & { kind: RecordGap["kind"] } => f.kind !== "conflict")
    .map((f) => ({ id: f.id, kind: f.kind, title: f.title, explanation: f.explanation, sources: cite(f.segment_ids) }));

  const routing = briefing.routing ?? {};
  const passage = routing.applicability?.passage;
  return {
    patientId: "0000-0001",
    patientLabel: age ? `Patient 0000-0001, ${age}` : "Patient 0000-0001",
    role,
    task,
    situation: briefing.situation,
    facts: briefing.needs.filter((n) => !isAlso(n)).flatMap((n) => needToFacts(n, cite)),
    alsoRelevant: alsoNeeds.flatMap((n) => needToFacts(n, cite)),
    contradictions,
    gaps,
    stats: briefing.stats,
    routeNote: routing.fallback_note ?? null,
    roleLabel: routing.role_label ?? null,
    taskLabel: briefing.task ?? null,
    screenMode: routing.screen_mode ?? null,
    roleMissing: routing.role_missing ?? false,
    message: routing.message ?? null,
    suggestions: routing.suggestions ?? [],
    applicabilityNote: routing.applicability_note ?? null,
    applicabilitySources: passage ? cite([passage]) : [],
    // "As of" = the date of the latest document, the time anchor for "current" values
    // gated screens (not_authorised / needs_task) carry no record date: today's date, never an invalid one
    generatedAt: (routing.anchor_date ?? briefing.as_of) ? `${routing.anchor_date ?? briefing.as_of}T12:00:00` : new Date().toISOString(),
  };
}

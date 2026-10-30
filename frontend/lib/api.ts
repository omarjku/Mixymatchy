// Types mirror backend/app/schema.py. Keep them in sync.
export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Trust = "consistent" | "conflicting" | "stale" | "single";

export interface Fact {
  id: string;
  type: string;
  concept: string;
  classes: string[];
  label_en: string;
  value?: string | null;
  unit?: string | null;
  date?: string | null;
  side?: string | null;
  status?: string | null;
  segment_ids: string[];
  trust: Trust;
}

export interface Finding {
  id: string;
  kind: "conflict" | "dropped" | "followup" | "silence";
  tier?: "contradiction" | "documentation_note" | null;
  title: string;
  explanation: string;
  segment_ids: string[];
  severity: "high" | "medium" | "low";
  on_screen?: boolean; // false: touches nothing on this task's screen (listed in the long view only)
}

export interface Computed {
  label: string;
  value: string;
  formula: string;
  segment_ids: string[];
}

export interface SourceRef {
  id: string; // guideline (G..) or drug label (L..) from the routing knowledge base
  title: string;
  verification?: string | null;
  url?: string | null;
}

export interface ChecklistItem {
  label: string;
  status: "found" | "documented_none" | "not_documented";
  segment_ids: string[];
  note?: string | null;
}

export interface NeedResult {
  need: string;
  label: string;
  status: "documented" | "not_documented" | "not_applicable";
  facts: Fact[];
  computed: Computed[];
  superseded: Fact[];
  reason?: string | null;
  reason_segment_ids: string[];
  // Routing knowledge base (optional; absent with the legacy rulebook)
  slot?: string | null;
  shape?: string | null;
  priority?: string | null; // "P1" | "P2" | "P3"
  why?: string | null;
  sources?: SourceRef[];
  rules?: string[];
  note?: string | null;
  checklist?: ChecklistItem[];
  label_panel?: Record<string, unknown>[]; // rule R22: listed contraindications beside patient facts
  more?: number; // list cards in the short view: further items shown in the long view
}

export interface Routing {
  fallback_note?: string | null;
  applicability_note?: string | null;
  suggestions?: string[];
  screen_mode?: "task" | "fallback" | "not_applicable" | "sex_specific" | "overview" | "not_authorised" | null;
  // clinical gate: "not_authorised" = no clinical role stated, no patient data in the briefing
  message?: string | null;
  role_label?: string | null;
  clinical_gate?: "kb_role" | "clinical_term" | "clinical_task" | "not_clinical" | "no_role" | null;
  other_record_issues?: number;
  other_record_issues_en?: string | null;
  [key: string]: unknown;
}

export interface Briefing {
  situation: string;
  role: string;
  task: string;
  as_of: string;
  needs: NeedResult[];
  blind_spot: Fact[];
  findings: Finding[];
  detail?: "short" | "long" | null;
  routing?: Routing;
  // Computed by the backend from this briefing; never typed in.
  stats: {
    facts_shown: number;
    facts_verified: number;
    facts_dropped: number;
    computed_values: number;
    not_documented: number;
    not_applicable: number;
    blind_spot: number;
    task_concepts: number;
    contradictions: number;
    documentation_notes: number;
    followups_open?: number;
    other_record_issues?: number;
  };
}

export interface Segment {
  id: string;
  doc_id: string;
  text: string;
  start: number;
  end: number;
  section?: string | null;
}

export interface DocumentView {
  id: string;
  title: string;
  date: string;
  department: string;
  text: string;
  segments: Segment[];
}

export type Detail = "short" | "long";

// Short (P1 only) is the default everywhere; "Show more" re-requests the long view (P1-P3).
export async function getBriefing(situation: string, detail: Detail = "short"): Promise<Briefing> {
  const r = await fetch(`${API}/briefing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ situation, detail }),
  });
  if (!r.ok) throw new Error(`briefing failed: ${r.status}`);
  return r.json();
}

export async function getDocument(docId: string): Promise<DocumentView> {
  const r = await fetch(`${API}/documents/${docId}`);
  if (!r.ok) throw new Error(`document failed: ${r.status}`);
  return r.json();
}

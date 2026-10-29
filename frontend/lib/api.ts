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
  title: string;
  explanation: string;
  segment_ids: string[];
  severity: "high" | "medium" | "low";
}

export interface NeedResult {
  need: string;
  label: string;
  status: "documented" | "not_documented";
  facts: Fact[];
}

export interface Briefing {
  situation: string;
  role: string;
  task: string;
  as_of: string;
  needs: NeedResult[];
  blind_spot: Fact[];
  findings: Finding[];
  stats: { facts_shown?: number; facts_verified?: number; facts_dropped?: number };
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

export async function getBriefing(situation: string): Promise<Briefing> {
  const r = await fetch(`${API}/briefing`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ situation }),
  });
  if (!r.ok) throw new Error(`briefing failed: ${r.status}`);
  return r.json();
}

export async function getDocument(docId: string): Promise<DocumentView> {
  const r = await fetch(`${API}/documents/${docId}`);
  if (!r.ok) throw new Error(`document failed: ${r.status}`);
  return r.json();
}

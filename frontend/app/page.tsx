"use client";

import { useState } from "react";
import { Briefing, Fact, Finding, getBriefing, Trust } from "@/lib/api";
import { SourcePane } from "@/components/SourcePane";

const ROLES = [
  "Anaesthetist, pre-operative check before quadrantectomy with IORT on 16 May 2016",
  "Surgeon planning the operation after the tumour board, April 2016",
  "GP reviewing her diabetes in spring 2016",
  "Emergency physician at night: dizziness and blurred vision in the left eye",
];

const TRUST: Record<Trust, { mark: string; className: string; title: string }> = {
  consistent: { mark: "✓", className: "text-green-700", title: "All letters agree" },
  conflicting: { mark: "⚠", className: "text-red-700", title: "Letters disagree" },
  stale: { mark: "⌛", className: "text-amber-700", title: "Only old information" },
  single: { mark: "•", className: "text-slate-500", title: "Mentioned once" },
};

type ShowSource = (ids: string[]) => void;

function SourceLink({ ids, onSource }: { ids: string[]; onSource: ShowSource }) {
  return (
    <button className="text-sm text-[var(--teal)] underline" onClick={() => onSource(ids)}>
      source
    </button>
  );
}

function FactRow({ fact, onSource }: { fact: Fact; onSource: ShowSource }) {
  const t = TRUST[fact.trust];
  return (
    <li className="flex items-baseline gap-2 py-1">
      <span className={t.className} title={t.title}>
        {t.mark}
      </span>
      <span>
        {fact.label_en}
        {fact.value ? `: ${fact.value}${fact.unit ? ` ${fact.unit}` : ""}` : ""}
        {fact.date ? <span className="text-[var(--muted)]"> ({fact.date})</span> : null}
      </span>
      <SourceLink ids={fact.segment_ids} onSource={onSource} />
    </li>
  );
}

function FindingList({ title, items, tone, onSource }: { title: string; items: Finding[]; tone: string; onSource: ShowSource }) {
  if (!items.length) return null;
  return (
    <div className="rounded bg-white p-4 shadow-sm">
      <p className={`mb-2 text-xs font-semibold uppercase ${tone}`}>{title}</p>
      {items.map((f) => (
        <div key={f.id} className="py-1 text-sm">
          <b>{f.title}.</b> {f.explanation} <SourceLink ids={f.segment_ids} onSource={onSource} />
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const [situation, setSituation] = useState("");
  const [briefing, setBriefing] = useState<Briefing | null>(null);
  const [source, setSource] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(text: string) {
    setSituation(text);
    setLoading(true);
    setError(null);
    try {
      setBriefing(await getBriefing(text));
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const conflicts = briefing?.findings.filter((f) => f.kind === "conflict") ?? [];
  const s = briefing?.stats;

  return (
    <main className="mx-auto max-w-7xl p-6">
      <header className="mb-4">
        <h1 className="text-2xl font-bold">Second Look</h1>
        <p className="text-sm text-[var(--muted)]">Anna Musterfrau · born 15.03.1959 · 8 documents</p>
      </header>

      <form
        className="mb-3 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (situation.trim()) run(situation);
        }}
      >
        <input
          className="flex-1 rounded border border-slate-300 bg-white px-3 py-2"
          placeholder="Who are you and what are you doing?"
          value={situation}
          onChange={(e) => setSituation(e.target.value)}
        />
        <button className="rounded bg-[var(--teal)] px-4 py-2 text-white" disabled={loading}>
          {loading ? "Building…" : "Build briefing"}
        </button>
      </form>
      <div className="mb-6 flex flex-wrap gap-2">
        {ROLES.map((r) => (
          <button key={r} className="rounded-full border border-slate-300 bg-white px-3 py-1 text-xs" onClick={() => run(r)}>
            {r.split(",")[0].split(":")[0]}
          </button>
        ))}
      </div>
      {error && <p className="mb-4 text-red-700">{error}</p>}

      {briefing && s && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[3fr_2fr]">
          <section className="space-y-4">
            {briefing.blind_spot.length > 0 && (
              <div className="rounded border-l-4 border-red-700 bg-red-50 p-3">
                <p className="font-semibold text-red-800">
                  Blind spot: reading only the latest letter, you would miss {s.blind_spot} of {s.task_concepts} facts for
                  this task
                </p>
                <ul className="text-sm">
                  {briefing.blind_spot.map((f) => (
                    <FactRow key={f.id} fact={f} onSource={setSource} />
                  ))}
                </ul>
              </div>
            )}

            <div className="rounded bg-white p-4 shadow-sm">
              <p className="mb-2 text-xs font-semibold uppercase text-[var(--teal)]">
                {briefing.role.replace("_", " ")} · what you need · as of {briefing.as_of}
              </p>
              {briefing.needs.map((n) => (
                <div key={n.need} className="border-b border-slate-100 py-2 last:border-0">
                  <p className="text-sm font-semibold">{n.label}</p>
                  {n.status === "not_documented" && <p className="text-sm text-[var(--muted)]">○ Not documented</p>}
                  {n.status === "not_applicable" && (
                    <p className="text-sm text-[var(--muted)]">
                      – Not applicable ({n.reason}) <SourceLink ids={n.reason_segment_ids} onSource={setSource} />
                    </p>
                  )}
                  {n.status === "documented" && (
                    <ul className="text-sm">
                      {n.facts.map((f) => (
                        <FactRow key={f.id} fact={f} onSource={setSource} />
                      ))}
                    </ul>
                  )}
                  {n.computed.map((c) => (
                    <p key={c.label + c.value} className="text-sm" title={c.formula}>
                      <span className="text-[var(--teal)]">=</span> {c.label}: <b>{c.value}</b>{" "}
                      <span className="text-[var(--muted)]">({c.formula})</span>{" "}
                      <SourceLink ids={c.segment_ids} onSource={setSource} />
                    </p>
                  ))}
                  {n.superseded.length > 0 && (
                    <p className="text-xs text-[var(--muted)]">
                      {n.superseded.length} older value(s) replaced by newer documents{" "}
                      <SourceLink ids={n.superseded.flatMap((f) => f.segment_ids)} onSource={setSource} />
                    </p>
                  )}
                </div>
              ))}
            </div>

            <FindingList
              title={`The record disagrees · ${s.contradictions}`}
              items={conflicts.filter((f) => f.tier === "contradiction")}
              tone="text-red-700"
              onSource={setSource}
            />
            <FindingList
              title={`Documentation notes · ${s.documentation_notes}`}
              items={conflicts.filter((f) => f.tier === "documentation_note")}
              tone="text-[var(--muted)]"
              onSource={setSource}
            />

            <p className="rounded bg-green-50 p-2 text-sm">
              {s.facts_shown} facts · {s.facts_verified} verified against the letters · {s.facts_dropped} dropped ·{" "}
              {s.computed_values} computed · {s.not_documented} not documented
            </p>
          </section>

          <aside className="rounded bg-white p-4 shadow-sm lg:sticky lg:top-6 lg:self-start">
            <SourcePane segmentIds={source} />
          </aside>
        </div>
      )}
    </main>
  );
}

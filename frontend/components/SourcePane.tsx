"use client";

import { useEffect, useRef, useState } from "react";
import { DocumentView, getDocument } from "@/lib/api";

// Shows every cited passage, grouped per document (a contradiction can span letters).
// TODO(E3): English translation under each passage.
export function SourcePane({ segmentIds }: { segmentIds: string[] }) {
  const [docs, setDocs] = useState<DocumentView[]>([]);
  const firstMark = useRef<HTMLElement>(null);
  const docIds = [...new Set(segmentIds.map((s) => s.split(":")[0]))];
  const key = docIds.join(",");

  useEffect(() => {
    if (!key) return setDocs([]);
    Promise.all(key.split(",").map(getDocument))
      .then((d) => setDocs(d.sort((a, b) => a.date.localeCompare(b.date))))
      .catch(() => setDocs([]));
  }, [key]);

  useEffect(() => {
    firstMark.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [docs, segmentIds]);

  if (!key) return <p className="text-sm text-[var(--muted)]">Click a source link to see the original passage.</p>;
  if (!docs.length) return <p className="text-sm text-[var(--muted)]">Loading…</p>;

  let marked = false;
  return (
    <div className="space-y-4">
      {docs.map((doc) => {
        const spans = doc.segments.filter((s) => segmentIds.includes(s.id)).sort((a, b) => a.start - b.start);
        const parts: React.ReactNode[] = [];
        let pos = 0;
        for (const s of spans) {
          parts.push(doc.text.slice(pos, s.start));
          const ref = marked ? undefined : firstMark;
          marked = true;
          parts.push(
            <mark key={s.id} ref={ref}>
              {doc.text.slice(s.start, s.end)}
            </mark>,
          );
          pos = s.end;
        }
        parts.push(doc.text.slice(pos));
        return (
          <div key={doc.id}>
            <p className="text-sm font-semibold">{doc.title}</p>
            <p className="mb-2 text-xs text-[var(--muted)]">
              {doc.date} · {doc.department}
            </p>
            <pre className="max-h-[40vh] overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 font-sans text-sm leading-6">
              {parts}
            </pre>
          </div>
        );
      })}
    </div>
  );
}

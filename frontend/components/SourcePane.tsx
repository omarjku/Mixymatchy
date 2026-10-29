"use client";

import { useEffect, useRef, useState } from "react";
import { DocumentView, getDocument } from "@/lib/api";

// Shows one document with the cited segments highlighted. TODO(E3): English translation under the passage.
export function SourcePane({ segmentIds }: { segmentIds: string[] }) {
  const [doc, setDoc] = useState<DocumentView | null>(null);
  const markRef = useRef<HTMLElement>(null);
  const docId = segmentIds[0]?.split(":")[0];

  useEffect(() => {
    if (docId) getDocument(docId).then(setDoc).catch(() => setDoc(null));
  }, [docId]);

  useEffect(() => {
    markRef.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [doc, segmentIds]);

  if (!docId) return <p className="text-sm text-[var(--muted)]">Click a source link to see the original passage.</p>;
  if (!doc) return <p className="text-sm text-[var(--muted)]">Loading…</p>;

  const spans = doc.segments.filter((s) => segmentIds.includes(s.id)).sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let pos = 0;
  spans.forEach((s, i) => {
    parts.push(doc.text.slice(pos, s.start));
    parts.push(
      <mark key={s.id} ref={i === 0 ? markRef : undefined}>
        {doc.text.slice(s.start, s.end)}
      </mark>,
    );
    pos = s.end;
  });
  parts.push(doc.text.slice(pos));

  return (
    <div>
      <p className="text-sm font-semibold">{doc.title}</p>
      <p className="mb-3 text-xs text-[var(--muted)]">
        {doc.date} · {doc.department}
      </p>
      <pre className="max-h-[70vh] overflow-auto whitespace-pre-wrap font-sans text-sm leading-6">{parts}</pre>
    </div>
  );
}

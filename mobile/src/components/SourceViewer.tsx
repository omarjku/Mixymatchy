import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { ArrowLeft01Icon, ArrowRight01Icon, Cancel01Icon } from "@hugeicons/core-free-icons";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/strings";
import { docIdOf, fetchDocument, formatDate, type BackendDocument } from "@/lib/backend";
import type { SourceCitation } from "@/types/fact";

// The original letter, with every cited passage of this fact highlighted (<mark>) and the current one
// scrolled into view. Several passages: step between them (they may be in different letters).
// Phone: bottom sheet. Desktop (>= 1024 px): a pane on the right, so the result stays readable beside it.

export interface SourceViewerProps {
  citations: SourceCitation[];
  startIndex: number;
  title: string;
  onClose: () => void;
}

const DESKTOP = "(min-width: 1024px)";

function useIsDesktop(): boolean {
  return useSyncExternalStore(
    (listener) => {
      const mq = window.matchMedia(DESKTOP);
      mq.addEventListener("change", listener);
      return () => mq.removeEventListener("change", listener);
    },
    () => window.matchMedia(DESKTOP).matches,
    () => false,
  );
}

// One citation per passage (the same passage can back two facts of a conflict).
function uniqueCitations(citations: SourceCitation[]): SourceCitation[] {
  const seen = new Set<string>();
  return citations.filter((c) => {
    const key = c.segmentId ?? c.documentId + c.excerpt;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function SourceViewer({ citations, startIndex, title, onClose }: SourceViewerProps) {
  const isDesktop = useIsDesktop();
  const list = useMemo(() => uniqueCitations(citations), [citations]);
  const [index, setIndex] = useState(() => {
    const wanted = citations[startIndex];
    const i = list.findIndex((c) => c === wanted || (c.segmentId && c.segmentId === wanted?.segmentId));
    return Math.max(0, i);
  });
  const current = list[index];

  const body = <LetterBody list={list} index={index} onStep={setIndex} />;
  const label = current?.documentLabel ?? title;

  if (isDesktop) {
    return (
      <aside
        role="dialog"
        aria-modal="false"
        aria-label={label}
        data-source-viewer
        onKeyDown={(e) => e.key === "Escape" && onClose()}
        className="fixed inset-y-0 right-0 z-30 flex w-[min(600px,46vw)] flex-col border-l border-line bg-surface shadow-[-12px_0_32px_-20px_rgba(20,24,49,0.35)]"
      >
        <div className="flex items-start gap-2 border-b border-line px-5 py-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-ink-muted">{title}</p>
            <h2 className="text-[17px] font-semibold leading-snug text-ink">{label}</h2>
          </div>
          <Button variant="icon" icon={Cancel01Icon} label={t("source.close")} onClick={onClose} autoFocus />
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{body}</div>
      </aside>
    );
  }

  return (
    <Modal open onOpenChange={(open) => !open && onClose()} title={label} description={title}>
      <div data-source-viewer>{body}</div>
    </Modal>
  );
}

type Load = { state: "loading" } | { state: "error" } | { state: "ready"; doc: BackendDocument };

function LetterBody({
  list,
  index,
  onStep,
}: {
  list: SourceCitation[];
  index: number;
  onStep: (i: number) => void;
}) {
  const current = list[index];
  const docId = current?.segmentId ? docIdOf(current.segmentId) : null;
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const activeRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!docId) return;
    let alive = true;
    setLoad({ state: "loading" });
    fetchDocument(docId)
      .then((doc) => alive && setLoad({ state: "ready", doc }))
      .catch(() => alive && setLoad({ state: "error" }));
    return () => {
      alive = false;
    };
  }, [docId]);

  // Scroll the current passage into view once the letter is rendered (and on every step).
  useEffect(() => {
    if (load.state !== "ready") return;
    const el = activeRef.current;
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    requestAnimationFrame(() => el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" }));
  }, [load, index]);

  const stepper = list.length > 1 && (
    <div className="mb-3 flex items-center justify-between gap-2 rounded-xl bg-canvas px-2 py-1.5">
      <Button
        variant="icon"
        icon={ArrowLeft01Icon}
        label={t("source.prev")}
        disabled={index === 0}
        onClick={() => onStep(index - 1)}
        className="disabled:opacity-40"
      />
      <p className="text-sm font-medium text-ink" aria-live="polite" data-passage-counter>
        {t("source.passage", { n: index + 1, m: list.length })}
      </p>
      <Button
        variant="icon"
        icon={ArrowRight01Icon}
        label={t("source.next")}
        disabled={index === list.length - 1}
        onClick={() => onStep(index + 1)}
        className="disabled:opacity-40"
      />
    </div>
  );

  // Mock mode or a citation without a segment id: only the quoted sentence.
  if (!docId) {
    return (
      <>
        {stepper}
        <blockquote className="rounded-xl bg-primary-soft p-4 font-serif text-[15px] leading-relaxed text-ink">
          „{current?.excerpt}“
        </blockquote>
      </>
    );
  }

  if (load.state === "loading") return <>{stepper}<p className="text-sm text-ink-muted">{t("source.loading")}</p></>;
  if (load.state === "error") return <>{stepper}<p className="text-sm text-contradiction-deep">{t("source.error")}</p></>;

  const { doc } = load;
  // Every cited passage of this fact that lies in this letter is marked; the current one is emphasised.
  const marked = new Set(list.filter((c) => c.segmentId && docIdOf(c.segmentId) === doc.id).map((c) => c.segmentId!));
  const segments = doc.segments
    .filter((s) => marked.has(s.id))
    .sort((a, b) => a.start - b.start);
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (const seg of segments) {
    if (seg.start < pos) continue; // overlapping passage: already inside a mark
    if (seg.start > pos) parts.push(doc.text.slice(pos, seg.start));
    const active = seg.id === current.segmentId;
    parts.push(
      <mark
        key={seg.id}
        ref={active ? (el) => void (activeRef.current = el) : undefined}
        data-segment={seg.id}
        data-active={active || undefined}
        className={
          active
            ? "sl-sweep rounded-sm bg-transparent px-0.5 text-ink outline-2 outline-offset-1 outline-ink-blue"
            : "rounded-sm bg-highlighter/45 px-0.5 text-ink"
        }
      >
        {doc.text.slice(seg.start, seg.end)}
      </mark>,
    );
    pos = seg.end;
  }
  parts.push(doc.text.slice(pos));

  return (
    <>
      {stepper}
      <p className="mb-3 text-xs text-ink-muted">
        {[doc.title, doc.department, formatDate(doc.date)].filter(Boolean).join(", ")}
      </p>
      <div className="whitespace-pre-wrap font-serif text-[15px] leading-[1.6] text-ink" lang="de" data-letter={doc.id}>
        {parts}
      </div>
      <p className="mt-4 text-xs text-ink-muted">{t("results.patientRecord")}</p>
    </>
  );
}

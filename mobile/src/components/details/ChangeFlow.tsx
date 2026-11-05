import { useState } from "react";
import { KeepDoses } from "@/components/ui/KeepDoses";
import { Modal } from "@/components/ui/Modal";
import { t } from "@/i18n/strings";
import type { SourceCitation } from "@/types/fact";

// How one value moved through the letters, as a flowchart: one box per documented entry, oldest first,
// each box linked to its passage (the same entries as the History log). Shown as a small thumbnail in
// Details; a tap opens the readable chart. Labels compare values only (first / changed / unchanged), never a verdict.

export interface FlowStep {
  date?: string;
  value: string;
  sources: SourceCitation[];
}

type OpenSources = (citations: SourceCitation[], index: number, title: string) => void;

function stepLabel(steps: FlowStep[], i: number): string {
  if (i === 0) return t("flow.first");
  return steps[i].value === steps[i - 1].value ? t("flow.same") : t("flow.changed");
}

export function ChangeFlow({ title, steps, onOpenSources }: { title: string; steps: FlowStep[]; onOpenSources: OpenSources }) {
  const [open, setOpen] = useState(false);
  if (steps.length < 2) return null;

  return (
    <>
      {/* Thumbnail: the chart's shape only, too small to read on purpose; the whole tile opens it */}
      <button
        type="button"
        data-flow-thumb
        onClick={() => setOpen(true)}
        aria-label={`${t("flow.open")}: ${title}`}
        className="mt-3 flex w-full max-w-56 items-center gap-2 rounded-lg border border-line bg-canvas px-2.5 py-2 text-left hover:border-primary focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
      >
        <span aria-hidden className="flex flex-col items-center gap-0.5">
          {steps.slice(0, 4).map((_, i, shown) => (
            <span key={i} className="flex flex-col items-center gap-0.5">
              {i > 0 && <span className="h-1.5 w-px bg-ink-faint" />}
              <span className={i === shown.length - 1 ? "h-1.5 w-7 rounded-sm bg-primary" : "h-1.5 w-7 rounded-sm bg-ink-faint/50"} />
            </span>
          ))}
        </span>
        <span className="min-w-0 text-[13px] leading-tight">
          <span className="block font-medium text-primary-deep">{t("flow.open")}</span>
          <span className="block text-ink-muted">{t("flow.count", { n: steps.length })}</span>
        </span>
      </button>

      <Modal open={open} onOpenChange={setOpen} title={title} description={t("flow.hint")}>
        <ol className="space-y-0" data-flow>
          {steps.map((s, i) => (
            <li key={i} className="flex flex-col items-stretch">
              {i > 0 && (
                <span aria-hidden className="flex items-center gap-2 py-1 pl-5 text-[12px] text-ink-muted">
                  <span className="text-base leading-none">↓</span>
                  {stepLabel(steps, i)}
                </span>
              )}
              <div
                className={
                  i === steps.length - 1
                    ? "flex items-start justify-between gap-3 rounded-lg border-2 border-primary bg-primary-soft px-3 py-2.5"
                    : "flex items-start justify-between gap-3 rounded-lg border border-line bg-surface px-3 py-2.5"
                }
              >
                <div className="min-w-0">
                  <p className="text-[12px] text-ink-muted">
                    {s.date ?? t("history.undated")}
                    {i === 0 ? ` · ${t("flow.first")}` : ""}
                    {i === steps.length - 1 ? ` · ${t("flow.latest")}` : ""}
                  </p>
                  <p className="text-[15px] font-semibold text-ink tabular-nums">
                    <KeepDoses text={s.value} />
                  </p>
                </div>
                {s.sources.length > 0 && (
                  <button
                    type="button"
                    data-source
                    onClick={() => {
                      setOpen(false);
                      onOpenSources(s.sources, 0, title);
                    }}
                    className="-my-1 inline-flex min-h-8 shrink-0 items-center rounded px-1 text-[13px] font-medium text-primary-deep underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    {t("results.source")}
                  </button>
                )}
              </div>
            </li>
          ))}
        </ol>
      </Modal>
    </>
  );
}

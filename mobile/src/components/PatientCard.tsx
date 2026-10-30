import { useEffect, useId, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight01Icon, Cancel01Icon, File01Icon } from "@hugeicons/core-free-icons";
import { Icon } from "@/components/ui/Icon";
import { hasHistory, ValueHistory } from "@/components/ValueHistory";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { Fact, FactTrust, PatientBrief, SourceCitation } from "@/types/fact";

// Patient header, built from Watermelon UI's expandable-profile-card
// (registry.watermelon.sh/r/expandable-profile-card.json): the card morphs into a full panel.
// Collapsed: identity + trust counts. Expanded: measured values with history + source documents.

export interface PatientCardProps {
  brief: PatientBrief;
  roleName: string;
  generatedAt: string;
}

// Counts by the engine's trust labels. "Not applicable" and calculated values are never counted here
// (in particular never as consistent / verified).
const tiers: { trust: FactTrust; marker: string; matches: FactTrust[] }[] = [
  { trust: "consistent", marker: "bg-verified", matches: ["consistent", "verified"] },
  { trust: "single", marker: "border-2 border-line bg-surface", matches: ["single"] },
  {
    trust: "conflicting",
    marker: "border-2 border-dashed border-inferred-border bg-inferred-soft",
    matches: ["conflicting", "outdated", "ai_inferred"],
  },
  { trust: "not_documented", marker: "border-2 border-dashed border-undocumented/60", matches: ["not_documented"] },
];

export function PatientCard({ brief, roleName, generatedAt }: PatientCardProps) {
  const [open, setOpen] = useState(false);
  const layoutId = useId();
  const titleId = useId();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  // While open: Escape closes, the page behind doesn't scroll, focus moves into the panel and back after
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    closeRef.current?.focus();
    const trigger = triggerRef.current;
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      trigger?.focus();
    };
  }, [open]);

  const counts = tiers.map(({ trust, marker, matches }) => ({
    trust,
    marker,
    count: brief.facts.filter((f) => f.badgeLabel === undefined && matches.includes(f.trust)).length,
  }));
  const series = brief.facts.filter(hasHistory);
  const documents = collectDocuments(brief);

  return (
    <>
      <motion.div
        layoutId={layoutId}
        style={{ borderRadius: 20 }}
        className="group relative border border-line bg-surface p-4 shadow-[0_1px_2px_rgba(20,24,49,0.05)] transition-colors hover:border-primary/60"
      >
        <PatientIdentity
          brief={brief}
          roleName={roleName}
          generatedAt={generatedAt}
          layoutId={layoutId}
          heading="h1"
        />

        <div className="mt-3 grid grid-cols-4 gap-1.5" role="group" aria-label={t("patient.trustSummary")}>
          {counts.map(({ trust, marker, count }) => (
            <div key={trust} className="rounded-xl bg-canvas px-2 py-1.5">
              <span className="flex items-center gap-1.5">
                <span aria-hidden className={cn("size-2.5 shrink-0 rounded-full", marker)} />
                <span className="text-lg font-semibold leading-none text-ink">{count}</span>
              </span>
              <span className="mt-1 block text-[11px] leading-tight text-ink-muted">{t(`trust.${trust}`)}</span>
            </div>
          ))}
        </div>

        <span aria-hidden className="mt-1.5 flex items-center justify-end gap-0.5 text-[13px] font-medium text-primary-deep">
          {t("patient.details")}
          <Icon icon={ArrowRight01Icon} size={16} />
        </span>

        {/* Stretched button: the whole card opens the panel without putting headings inside a <button> */}
        <button
          ref={triggerRef}
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label={`${t("patient.openDetails")}: ${brief.patientLabel}`}
          className="absolute inset-0 rounded-[20px] focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
        />
      </motion.div>

      <AnimatePresence>
        {open && (
          <div className="fixed inset-0 z-50 flex items-stretch justify-center p-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setOpen(false)}
              className="absolute inset-0 bg-ink/50"
            />
            <motion.div
              layoutId={layoutId}
              role="dialog"
              aria-modal="true"
              aria-labelledby={titleId}
              style={{ borderRadius: 24 }}
              className="relative flex w-full max-w-md flex-col overflow-hidden border border-line bg-surface shadow-xl md:max-w-2xl"
            >
              <div className="flex items-start gap-2 border-b border-line p-4 pr-2">
                <div className="min-w-0 flex-1" id={titleId}>
                  <PatientIdentity
                    brief={brief}
                    roleName={roleName}
                    generatedAt={generatedAt}
                    layoutId={layoutId}
                    heading="h2"
                  />
                </div>
                <button
                  ref={closeRef}
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label={t("patient.closeDetails")}
                  className="flex size-11 shrink-0 items-center justify-center rounded-full text-ink-muted hover:bg-primary-soft hover:text-primary-deep focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Icon icon={Cancel01Icon} size={20} />
                </button>
              </div>

              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ delay: 0.15 }}
                className="flex-1 overflow-y-auto p-4"
              >
                <section aria-labelledby={`${titleId}-stats`}>
                  <h3 id={`${titleId}-stats`} className="text-sm font-semibold text-ink">
                    {t("patient.stats")}
                  </h3>
                  {series.length === 0 ? (
                    <p className="mt-2 text-sm text-ink-muted">{t("patient.noStats")}</p>
                  ) : (
                    <ul className="mt-3 space-y-3">
                      {series.map((fact) => (
                        <SeriesRow key={fact.id} fact={fact} />
                      ))}
                    </ul>
                  )}
                </section>

                <section aria-labelledby={`${titleId}-docs`} className="mt-6">
                  <h3 id={`${titleId}-docs`} className="text-sm font-semibold text-ink">
                    {t("patient.documents")} ({documents.length})
                  </h3>
                  <ul className="mt-3 divide-y divide-line rounded-2xl border border-line">
                    {documents.map((doc) => (
                      <li key={doc.documentId} className="flex items-center gap-3 px-3 py-3">
                        <Icon icon={File01Icon} size={18} className="text-ink-muted" />
                        <span className="min-w-0 flex-1 text-sm text-ink">{doc.documentLabel}</span>
                        <span className="shrink-0 text-right text-xs text-ink-muted">
                          {documentUsage(doc.facts, doc.contradictions)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              </motion.div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}

function PatientIdentity({
  brief,
  roleName,
  generatedAt,
  layoutId,
  heading,
}: PatientCardProps & { layoutId: string; heading: "h1" | "h2" }) {
  const Heading = heading === "h1" ? motion.h1 : motion.h2;
  return (
    <>
      <Heading layoutId={`${layoutId}-name`} className="text-[22px] font-semibold leading-tight tracking-tight text-ink">
        {brief.patientLabel}
      </Heading>
      <motion.p layoutId={`${layoutId}-meta`} className="mt-1 text-sm text-ink-muted">
        {roleName} · {brief.task}
      </motion.p>
      <p className="mt-1 text-xs text-ink-muted">
        {t("patient.id")} {brief.patientId} · {t("results.generatedAt")}: {generatedAt}
      </p>
    </>
  );
}

function SeriesRow({ fact }: { fact: Fact }) {
  return (
    <li className="rounded-2xl border border-line p-3">
      <p className="text-sm text-ink-muted">{fact.label}</p>
      <p className="text-[17px] font-semibold text-ink">{fact.value}</p>
      <ValueHistory fact={fact} />
    </li>
  );
}

// Patient-record documents the brief draws on, counting facts and contradictions separately
// (a document can matter only because it conflicts with another one).
function collectDocuments(brief: PatientBrief) {
  type DocUsage = { documentId: string; documentLabel: string; facts: number; contradictions: number };
  const docs = new Map<string, DocUsage>();
  const add = (source: SourceCitation, kind: "facts" | "contradictions") => {
    const entry = docs.get(source.documentId) ?? {
      documentId: source.documentId,
      documentLabel: source.documentLabel,
      facts: 0,
      contradictions: 0,
    };
    entry[kind] += 1;
    docs.set(source.documentId, entry);
  };
  for (const fact of brief.facts) if (fact.source) add(fact.source, "facts");
  for (const c of brief.contradictions) for (const s of c.conflictingSources) add(s, "contradictions");
  return [...docs.values()];
}

function documentUsage(facts: number, contradictions: number): string {
  const parts: string[] = [];
  if (facts > 0) parts.push(`${facts} ${facts === 1 ? t("patient.factSingular") : t("patient.factPlural")}`);
  if (contradictions > 0) parts.push(t("patient.inContradiction"));
  return parts.join(" · ");
}

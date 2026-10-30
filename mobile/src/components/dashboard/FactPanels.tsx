import { BloodPressureIcon, Calendar03Icon } from "@hugeicons/core-free-icons";
import { Panel, SourcesButton } from "@/components/dashboard/Panel";
import { t } from "@/i18n/strings";
import { bpChange, formatBp, formatDate, formatSigned } from "@/lib/stats";
import type { SourceCitation } from "@/types/fact";
import type { BloodPressure, BloodPressureComparison, DatedFact } from "@/types/stats";

// The two list panels of the Dashboard (Bionis's "Body vitals" style rows):
//   BloodPressurePanel  documented pairs with the computed change; reported averages shown as written
//   DatedFactsPanel     single or sparse values deliberately shown WITHOUT a trend

type OnPressSources = (title: string, sources: SourceCitation[]) => void;

export function BloodPressurePanel({
  comparisons,
  averages,
  onPressSources,
}: {
  comparisons: BloodPressureComparison[];
  averages: { label: string; value: BloodPressure; source: SourceCitation }[];
  onPressSources: OnPressSources;
}) {
  const unit = t("dash.bp.unit");
  return (
    <Panel title={t("dash.bp.title")} icon={BloodPressureIcon}>
      <ul className="divide-y divide-line">
        {comparisons.map((c) => {
          const d = bpChange(c.from, c.to);
          return (
            <li key={c.id} className="py-3 first:pt-0">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink">{c.label}</p>
                  <p className="text-xs text-ink-muted">{c.context}</p>
                </div>
                <SourcesButton
                  count={c.sources.length}
                  label={t("dash.sourcesFor", { label: c.label })}
                  onClick={() => onPressSources(c.label, c.sources)}
                />
              </div>
              <p className="mt-2 text-sm text-ink">
                <span className="text-ink-muted">{c.fromLabel}</span> {formatBp(c.from)} →{" "}
                <span className="text-ink-muted">{c.toLabel}</span> {formatBp(c.to)} {unit}
              </p>
              <p className="mt-1 text-sm font-semibold text-ink">
                {formatSigned(d.systolic.delta)}/{formatSigned(d.diastolic.delta)} {unit}
                <span className="ml-2 text-xs font-normal text-ink-muted">
                  {t("dash.bp.percent", {
                    sys: `${formatSigned(d.systolic.percent ?? 0, 2)} %`,
                    dia: `${formatSigned(d.diastolic.percent ?? 0, 2)} %`,
                  })}
                </span>
              </p>
            </li>
          );
        })}
        {averages.map((a) => (
          <li key={a.label} className="flex items-center justify-between gap-2 py-3 last:pb-0">
            <p className="text-sm text-ink">
              {a.label}
              <span className="ml-2 font-semibold">
                {formatBp(a.value)} {unit}
              </span>
            </p>
            <SourcesButton
              count={1}
              label={t("dash.sourcesFor", { label: a.label })}
              onClick={() => onPressSources(a.label, [a.source])}
            />
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export function DatedFactsPanel({ facts, onPressSources }: { facts: DatedFact[]; onPressSources: OnPressSources }) {
  return (
    <Panel title={t("dash.dated.title")} icon={Calendar03Icon}>
      <ul className="divide-y divide-line">
        {facts.map((f) => (
          <li key={f.id} className="py-3 first:pt-0 last:pb-0">
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium text-ink">{f.label}</p>
              <SourcesButton
                count={f.values.length}
                label={t("dash.sourcesFor", { label: f.label })}
                onClick={() =>
                  onPressSources(
                    f.label,
                    f.values.map((v) => v.source),
                  )
                }
              />
            </div>
            <p className="mt-1 flex flex-wrap gap-x-3 text-sm text-ink">
              {f.values.map((v) => (
                <span key={v.date}>
                  <span className="font-semibold">{v.display}</span>{" "}
                  <time dateTime={v.date} className="text-xs text-ink-muted">
                    {formatDate(v.date)}
                  </time>
                </span>
              ))}
            </p>
            <p className="mt-1 text-xs text-ink-muted">{f.note}</p>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

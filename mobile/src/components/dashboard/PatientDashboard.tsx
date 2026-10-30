import { useEffect, useState } from "react";
import { BloodPressureIcon, Medicine02Icon, WeightScaleIcon, Calculator01Icon } from "@hugeicons/core-free-icons";
import { BmiChart } from "@/components/dashboard/BmiChart";
import { BloodPressurePanel, DatedFactsPanel } from "@/components/dashboard/FactPanels";
import { MetricTile, type MetricTileProps } from "@/components/dashboard/MetricTile";
import { ProofRing } from "@/components/dashboard/ProofRing";
import { WeightChart } from "@/components/dashboard/WeightChart";
import { Notice } from "@/components/ui/Notice";
import { Skeleton } from "@/components/ui/Skeleton";
import { t } from "@/i18n/strings";
import { fetchPatientStats } from "@/lib/api";
import {
  bpChange,
  calculateBmi,
  change,
  checkBmi,
  formatBp,
  formatDate,
  formatNumber,
  formatSigned,
} from "@/lib/stats";
import type { PatientBrief, SourceCitation } from "@/types/fact";
import type { PatientStats } from "@/types/stats";

// Dashboard level (most detailed), laid out after Watermelon UI's bionis-dashboard: proof ring, key-change
// tiles, charts, list panels. Light theme. No wellness score, predictions or recommended actions:
// only documented values and arithmetic on them, each linked to its sources.
// Loaded lazily (recharts stays out of the first page load) and default-exported for React.lazy.

export interface PatientDashboardProps {
  brief: PatientBrief;
  onPressSources: (title: string, sources: SourceCitation[]) => void;
}

type Load = { state: "loading" } | { state: "error" } | { state: "ready"; stats: PatientStats | null };

export default function PatientDashboard({ brief, onPressSources }: PatientDashboardProps) {
  const [load, setLoad] = useState<Load>({ state: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    fetchPatientStats(brief.patientId, controller.signal)
      .then((stats) => setLoad({ state: "ready", stats }))
      .catch(() => {
        if (!controller.signal.aborted) setLoad({ state: "error" });
      });
    return () => controller.abort();
  }, [brief.patientId]);

  // Proof counts come from the brief itself: documented facts, and how many carry a source passage
  const documented = brief.facts.filter((f) => f.trust !== "not_documented");
  const backed = documented.filter((f) => f.source).length;

  if (load.state === "loading") {
    return (
      <div className="space-y-3" aria-busy="true">
        <p role="status" className="sr-only">
          {t("dash.loading")}
        </p>
        <Skeleton className="h-28 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-3">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[150px] rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    );
  }

  if (load.state === "error") return <Notice tone="warning" title={t("dash.error")} />;

  const stats = load.stats;
  const proof = <ProofRing backed={backed} total={documented.length} removed={stats?.factsRemoved ?? 0} />;
  const hasData =
    stats &&
    (stats.measurements.length > 0 ||
      stats.doseChanges.length > 0 ||
      stats.bloodPressure.length > 0 ||
      stats.datedFacts.length > 0);

  if (!stats || !hasData) {
    return (
      <div className="space-y-3">
        {proof}
        <Notice tone="info" title={t("dash.empty")} />
      </div>
    );
  }

  const tiles = buildTiles(stats, onPressSources);
  const bmiChecks = stats.measurements.map(checkBmi);

  return (
    <div className="space-y-3">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-base font-semibold text-ink">{t("dash.title")}</h3>
        <span className="rounded-full border border-line bg-surface px-3 py-1 text-xs text-ink-muted">
          {t("dash.recordsThrough", { date: formatDate(stats.recordsThrough) })}
        </span>
      </header>

      {proof}

      {tiles.length > 0 && (
        <section aria-label={t("dash.tiles")} className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {tiles.map((tile) => (
            <MetricTile key={tile.label} {...tile} />
          ))}
        </section>
      )}

      {stats.measurements.length >= 2 && (
        <div className="grid gap-3 xl:grid-cols-2">
          <WeightChart measurements={stats.measurements} onPressSources={onPressSources} />
          <BmiChart checks={bmiChecks} onPressSources={onPressSources} />
        </div>
      )}

      {(stats.bloodPressure.length > 0 || stats.datedFacts.length > 0) && (
        <div className="grid gap-3 xl:grid-cols-2">
          {stats.bloodPressure.length > 0 && (
            <BloodPressurePanel
              comparisons={stats.bloodPressure}
              averages={stats.reportedAverages}
              onPressSources={onPressSources}
            />
          )}
          {stats.datedFacts.length > 0 && <DatedFactsPanel facts={stats.datedFacts} onPressSources={onPressSources} />}
        </div>
      )}

      {stats.notes.length > 0 && (
        <Notice tone="info" title={t("dash.notes.title")}>
          <ul className="list-disc space-y-1 pl-4">
            {stats.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </Notice>
      )}
    </div>
  );
}

// Key-change tiles: first vs last documented value, change computed here. Each links both inputs.
function buildTiles(stats: PatientStats, onPressSources: PatientDashboardProps["onPressSources"]): MetricTileProps[] {
  const tiles: MetricTileProps[] = [];
  const direction = (delta: number): MetricTileProps["direction"] => (delta > 0 ? "up" : delta < 0 ? "down" : "none");
  const pct = (p: number | null) => (p === null ? "" : ` · ${formatSigned(p, 2)} %`);

  const [first, last] = [stats.measurements[0], stats.measurements[stats.measurements.length - 1]];
  if (stats.measurements.length >= 2) {
    const w = change(first.weightKg, last.weightKg);
    const label = t("dash.tile.weight");
    tiles.push({
      icon: WeightScaleIcon,
      label,
      value: formatNumber(last.weightKg),
      unit: "kg",
      direction: direction(w.delta),
      change: `${formatSigned(w.delta)} kg${pct(w.percent)}`,
      comparison: t("dash.tile.compare", {
        from: `${formatNumber(first.weightKg)} kg`,
        to: `${formatNumber(last.weightKg)} kg`,
      }),
      sourceCount: 2,
      onPressSources: () => onPressSources(label, [first.source, last.source]),
    });

    const bmiFrom = calculateBmi(first.weightKg, first.heightCm);
    const bmiTo = calculateBmi(last.weightKg, last.heightCm);
    const b = change(bmiFrom, bmiTo);
    const bmiLabel = t("dash.tile.bmi");
    tiles.push({
      icon: Calculator01Icon,
      label: bmiLabel,
      value: formatNumber(bmiTo, 2),
      unit: "kg/m²",
      direction: direction(b.delta),
      change: `${formatSigned(b.delta, 2)} kg/m²`,
      comparison: t("dash.tile.compare", { from: formatNumber(bmiFrom, 2), to: formatNumber(bmiTo, 2) }),
      sourceCount: 2,
      onPressSources: () => onPressSources(bmiLabel, [first.source, last.source]),
    });
  }

  for (const d of stats.doseChanges) {
    const c = change(d.from.value, d.to.value);
    const label = t("dash.tile.dose", { drug: d.drug });
    tiles.push({
      icon: Medicine02Icon,
      label,
      value: formatNumber(d.to.value, d.to.value % 1 === 0 ? 0 : 1),
      unit: d.unit,
      direction: direction(c.delta),
      change: `${formatSigned(c.delta, c.delta % 1 === 0 ? 0 : 1)} ${d.unit}${pct(c.percent)}`,
      comparison: t("dash.tile.compare", { from: d.from.display, to: d.to.display }),
      sourceCount: 2,
      onPressSources: () => onPressSources(label, [d.from.source, d.to.source]),
    });
  }

  const bp = stats.bloodPressure[0];
  if (bp) {
    const c = bpChange(bp.from, bp.to);
    const label = t("dash.tile.bp", { label: bp.label });
    tiles.push({
      icon: BloodPressureIcon,
      label,
      value: formatBp(bp.to),
      unit: "mmHg",
      direction: direction(c.systolic.delta),
      change: `${formatSigned(c.systolic.delta)}/${formatSigned(c.diastolic.delta)} mmHg`,
      comparison: t("dash.tile.compare", { from: formatBp(bp.from), to: formatBp(bp.to) }),
      sourceCount: bp.sources.length,
      onPressSources: () => onPressSources(label, bp.sources),
    });
  }

  return tiles;
}

import { intlLocale } from "@/i18n/locale";
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { Alert02Icon, Calculator01Icon, CheckmarkCircle02Icon } from "@hugeicons/core-free-icons";
import { Panel, SourcesButton } from "@/components/dashboard/Panel";
import { Icon } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { BMI_TOLERANCE, formatNumber, formatSigned, type BmiCheck } from "@/lib/stats";
import { cn } from "@/lib/utils";
import type { SourceCitation } from "@/types/fact";

// Recorded BMI (as written) next to the BMI calculated from the same letter's weight and height.
// A gap means a documentation inconsistency (e.g. a BMI copied forward), never which input is wrong.
// Bars start at 0 so the gap is not exaggerated.

const axisTick = { fill: "var(--color-ink-muted)", fontSize: 11 };
const monthYear = { format: (date: Date) => new Intl.DateTimeFormat(intlLocale(), { month: "short", year: "numeric" }).format(date) };

export function BmiChart({
  checks,
  onPressSources,
}: {
  checks: BmiCheck[];
  onPressSources: (title: string, sources: SourceCitation[]) => void;
}) {
  const title = t("dash.bmi.title");
  // short month/year on the axis (fits at phone width); the full set name is in the list below the chart
  const data = checks.map((c) => ({
    label: monthYear.format(new Date(c.set.date)),
    recorded: c.set.recordedBmi,
    calculated: Number(c.calculated.toFixed(2)),
  }));
  const max = Math.max(...checks.map((c) => Math.max(c.calculated, c.set.recordedBmi ?? 0)));
  // round axis in steps of 10, with headroom for the value labels above the bars
  const axisTop = Math.ceil((max + 3) / 10) * 10;

  return (
    <Panel
      title={title}
      icon={Calculator01Icon}
      action={
        <SourcesButton
          count={checks.length}
          label={t("dash.sourcesFor", { label: title })}
          onClick={() =>
            onPressSources(
              title,
              checks.map((c) => c.set.source),
            )
          }
        />
      }
    >
      <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm bg-primary-strong" />
          {t("dash.bmi.recorded")}
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="size-2.5 rounded-sm border border-primary-strong bg-primary-soft" />
          {t("dash.bmi.calculated")}
        </span>
      </div>

      <div className="h-52" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 20, right: 4, bottom: 0, left: 4 }} barGap={4} barCategoryGap="22%">
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis dataKey="label" tick={axisTick} tickLine={false} axisLine={false} interval={0} />
            <YAxis
              domain={[0, axisTop]}
              ticks={Array.from({ length: axisTop / 10 + 1 }, (_, i) => i * 10)}
              width={28}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
            />
            <Bar dataKey="recorded" fill="var(--color-primary-strong)" radius={[6, 6, 0, 0]}>
              <LabelList
                dataKey="recorded"
                position="top"
                formatter={(v: unknown) => (v == null ? "" : formatNumber(Number(v), 1))}
                style={{ fill: "var(--color-ink)", fontSize: 11, fontWeight: 600 }}
              />
            </Bar>
            <Bar
              dataKey="calculated"
              fill="var(--color-primary-soft)"
              stroke="var(--color-primary-strong)"
              strokeWidth={1}
              radius={[6, 6, 0, 0]}
            >
              <LabelList
                dataKey="calculated"
                position="top"
                formatter={(v: unknown) => formatNumber(Number(v), 2)}
                style={{ fill: "var(--color-ink-muted)", fontSize: 11 }}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <ul className="mt-3 space-y-2">
        {checks.map((c) => (
          <li key={c.set.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <span className="min-w-0 text-ink">
              {c.set.label}
              <span className="block text-xs text-ink-muted">
                {formatNumber(c.set.weightKg)} kg · {formatNumber(c.set.heightCm)} cm ·{" "}
                {c.set.recordedBmi === null
                  ? t("dash.bmi.notRecorded")
                  : `${formatNumber(c.set.recordedBmi, 1)} / ${formatNumber(c.calculated, 2)}`}
              </span>
            </span>
            <AgreementPill check={c} />
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs leading-relaxed text-ink-muted">
        {t("dash.bmi.note", { tol: formatNumber(BMI_TOLERANCE, 1) })}
      </p>
    </Panel>
  );
}

function AgreementPill({ check }: { check: BmiCheck }) {
  if (check.agreement === "not_recorded") return null;
  const differs = check.agreement === "differs";
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-semibold",
        differs ? "border-dashed border-inferred-border bg-inferred-soft text-inferred" : "border-line text-ink-muted",
      )}
    >
      <Icon icon={differs ? Alert02Icon : CheckmarkCircle02Icon} size={13} />
      {differs ? t("dash.bmi.differs", { diff: formatSigned(check.difference ?? 0, 2) }) : t("dash.bmi.agrees")}
    </span>
  );
}

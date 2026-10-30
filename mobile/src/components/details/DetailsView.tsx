import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { ContradictionCard } from "@/components/ContradictionCard";
import { parseGermanNumber } from "@/components/Sparkline";
import { hasHistory } from "@/components/ValueHistory";
import { intlLocale } from "@/i18n/locale";
import { t } from "@/i18n/strings";
import { formatDate, formatNumber, formatSigned } from "@/lib/stats";
import type { Fact, FactRow, PatientBrief, SourceCitation } from "@/types/fact";

// "Details" level of the results: the in-depth view, built only from what the brief already carries
// (real backend or mock): every value with a history as a chart plus its change, calculated values with
// their formula, medication changes (older values a newer letter replaced), documentation notes, and open
// items (facts the latest letter no longer mentions, follow-ups with no later record). Calculations only, never a diagnosis or advice.
// Default export: loaded lazily, so recharts stays out of the first page load.

type OpenSources = (citations: SourceCitation[], index: number, title: string) => void;

export interface DetailsViewProps {
  brief: PatientBrief;
  onOpenSources: OpenSources;
}

export default function DetailsView({ brief, onOpenSources }: DetailsViewProps) {
  const facts = [...brief.facts, ...(brief.alsoRelevant ?? [])];
  const series = facts.filter((f) => f.trust !== "not_documented" && hasHistory(f) && (f.history?.length ?? 0) >= 2);
  // Calculated rows, except a trend's own change (already shown on its chart)
  const calculated = facts.flatMap((f) =>
    (f.rows ?? [])
      .filter((r) => r.computed && !(f.trend?.change && r.text.includes(f.trend.change)))
      .map((row) => ({ fact: f, row })),
  );
  const medication = facts.filter((f) => (f.superseded?.length ?? 0) > 0);
  const notes = brief.contradictions.filter((c) => c.tier === "documentation_note");
  const gaps = brief.gaps ?? [];

  if (series.length + calculated.length + medication.length + notes.length + gaps.length === 0) {
    return <p className="border-y border-line px-3 py-5 text-center text-sm text-ink-muted">{t("details.empty")}</p>;
  }

  return (
    <div className="space-y-7">
      {series.length > 0 && (
        <Section title={t("details.trends")} count={series.length}>
          <div className="divide-y divide-line border-y border-line">
            {series.map((fact) => (
              <TrendBlock key={fact.id} fact={fact} onOpenSources={onOpenSources} />
            ))}
          </div>
        </Section>
      )}

      {medication.length > 0 && (
        <Section title={t("details.medication")} count={medication.length}>
          <ul className="divide-y divide-line border-y border-line">
            {medication.map((fact) => (
              <li key={fact.id} data-fact={fact.id} className="px-3 py-3">
                <h3 className="text-[14px] text-ink-muted">{fact.label}</h3>
                <div className="mt-1.5 grid gap-3 sm:grid-cols-2">
                  <RowGroup
                    heading={t("details.earlier")}
                    rows={fact.superseded ?? []}
                    title={fact.label}
                    onOpenSources={onOpenSources}
                    muted
                  />
                  <RowGroup
                    heading={t("details.now")}
                    rows={(fact.rows ?? []).filter((r) => !r.computed)}
                    title={fact.label}
                    onOpenSources={onOpenSources}
                  />
                </div>
              </li>
            ))}
          </ul>
        </Section>
      )}

      {calculated.length > 0 && (
        <Section title={t("details.calculated")} count={calculated.length}>
          <ul className="divide-y divide-line border-y border-line">
            {calculated.map(({ fact, row }) => (
              <li key={row.id} className="flex items-start justify-between gap-3 px-3 py-3">
                <div className="min-w-0">
                  <p className="text-[13px] text-ink-muted">{fact.label}</p>
                  <p className="text-[15px] font-semibold text-ink tabular-nums">{row.text}</p>
                  {row.note && (
                    <p className="mt-0.5 text-[13px] text-ink-muted">
                      {t("details.formula")}: {row.note}
                    </p>
                  )}
                </div>
                <SourcesLink sources={row.sources} title={fact.label} onOpenSources={onOpenSources} />
              </li>
            ))}
          </ul>
        </Section>
      )}

      {notes.length > 0 && (
        <Section title={t("details.checks")} count={notes.length}>
          <div className="space-y-3">
            {notes.map((c) => (
              <ContradictionCard
                key={c.id}
                contradiction={c}
                onPressSource={(source, all) => onOpenSources(all, all.indexOf(source), c.factLabel)}
              />
            ))}
          </div>
        </Section>
      )}

      {gaps.length > 0 && (
        <Section title={t("results.gapsHeading")} count={gaps.length}>
          <ul className="divide-y divide-line border-y border-line">
            {gaps.map((gap) => (
              <li key={gap.id} className="flex items-start justify-between gap-3 px-3 py-3">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-ink-muted">{t(`results.gap.${gap.kind}`)}</p>
                  <p className="mt-0.5 text-[15px] font-semibold text-ink">{gap.title}</p>
                  {gap.explanation && <p className="mt-0.5 text-[14px] text-ink-muted">{gap.explanation}</p>}
                </div>
                <SourcesLink sources={gap.sources} title={gap.title} onOpenSources={onOpenSources} />
              </li>
            ))}
          </ul>
        </Section>
      )}
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-ink-muted">
        {title} ({count})
      </h2>
      {children}
    </section>
  );
}

// One measured value over time: first → latest, the change (the backend's own calculation when it sends one,
// otherwise plain arithmetic on the documented values), the date span, and a chart on a true time axis.
function TrendBlock({ fact, onOpenSources }: { fact: Fact; onOpenSources: OpenSources }) {
  const history = fact.history ?? [];
  const unit = history.find((h) => h.unit)?.unit ?? fact.value?.replace(/^[-\d.,\s→]+/, "").split(" ")[0] ?? "";
  const points = history
    .map((h) => ({ time: new Date(h.date).getTime(), value: parseGermanNumber(h.value), date: h.date, raw: h.value }))
    .filter((p): p is { time: number; value: number; date: string; raw: string } => p.value !== null);
  const decimals = Math.max(0, ...history.map((h) => (h.value.split(/[.,]/)[1] ?? "").length));
  const first = points[0];
  const last = points[points.length - 1];
  const withUnit = (v: string) => (unit ? `${v} ${unit}` : v);

  let change = fact.trend?.change;
  if (!change && first && last) {
    const delta = last.value - first.value;
    const percent = first.value !== 0 ? (delta / first.value) * 100 : null;
    change = `${withUnit(formatSigned(delta, decimals))}${percent === null ? "" : ` (${formatSigned(percent, 1)} %)`}`;
  }
  const sources = fact.sources ?? (fact.source ? [fact.source] : []);
  const tickFormat = new Intl.DateTimeFormat(intlLocale(), { month: "short", year: "numeric" });

  return (
    <article data-fact={fact.id} className="px-3 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[14px] text-ink-muted">{fact.label}</h3>
          {first && last && (
            // numbers in the UI language's format, like the change and the chart labels (never mixed 1,0 / 0.3)
            <p className="mt-0.5 text-[17px] font-semibold text-ink tabular-nums">
              {withUnit(formatNumber(first.value, decimals))} <span className="font-normal text-ink-muted">→</span>{" "}
              {withUnit(formatNumber(last.value, decimals))}
            </p>
          )}
          {change && (
            <p className="mt-0.5 text-[14px] text-ink">
              <span className="font-semibold tabular-nums">{change}</span>{" "}
              <span className="text-ink-muted">({t("results.computed")})</span>
            </p>
          )}
          {first && last && (
            <p className="mt-0.5 text-[13px] text-ink-muted">
              {t("details.span", { from: formatDate(first.date), to: formatDate(last.date) })} ·{" "}
              {t("details.readings", { n: points.length })}
            </p>
          )}
        </div>
        <SourcesLink sources={sources} title={fact.label} onOpenSources={onOpenSources} />
      </div>

      {points.length >= 2 && (
        <div className="mt-3 h-40" aria-hidden>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={points} margin={{ top: 20, right: 24, bottom: 0, left: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--color-line)" />
              <XAxis
                type="number"
                dataKey="time"
                scale="time"
                domain={["dataMin", "dataMax"]}
                ticks={points.map((p) => p.time)}
                tickFormatter={(v: number) => tickFormat.format(new Date(v))}
                tick={{ fill: "var(--color-ink-muted)", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
                padding={{ left: 20, right: 20 }}
              />
              <YAxis
                domain={["auto", "auto"]}
                width={36}
                tick={{ fill: "var(--color-ink-muted)", fontSize: 11 }}
                tickLine={false}
                axisLine={false}
              />
              {/* straight segments: a smoothed curve would invent readings between the letters */}
              <Line
                type="linear"
                dataKey="value"
                stroke="var(--color-primary-strong)"
                strokeWidth={2}
                dot={{ r: 3.5, fill: "var(--color-primary-strong)", strokeWidth: 0 }}
                activeDot={false}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey="value"
                  position="top"
                  offset={8}
                  formatter={(v: unknown) => formatNumber(Number(v), decimals)}
                  style={{ fill: "var(--color-ink)", fontSize: 11, fontWeight: 600 }}
                />
              </Line>
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {fact.trend?.formula && (
        <p className="mt-1 text-[13px] text-ink-muted">
          {t("details.formula")}: {fact.trend.formula}
        </p>
      )}
    </article>
  );
}

function RowGroup({
  heading,
  rows,
  title,
  onOpenSources,
  muted = false,
}: {
  heading: string;
  rows: FactRow[];
  title: string;
  onOpenSources: OpenSources;
  muted?: boolean;
}) {
  return (
    <div className="min-w-0">
      <p className="text-[12px] font-medium uppercase tracking-wide text-ink-muted">{heading}</p>
      <ul className="mt-1 space-y-1">
        {rows.map((r) => (
          <li key={r.id} className="flex items-start justify-between gap-2">
            <p className="min-w-0 text-[15px] leading-snug">
              {/* no strike-through: an earlier value is replaced, not wrong, and the app never edits records */}
              <span className={muted ? "text-ink-muted" : "font-semibold text-ink"}>
                {r.text}
              </span>
              {r.date && <span className="text-[13px] text-ink-muted"> · {r.date}</span>}
            </p>
            <SourcesLink sources={r.sources} title={title} onOpenSources={onOpenSources} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function SourcesLink({
  sources,
  title,
  onOpenSources,
}: {
  sources: SourceCitation[];
  title: string;
  onOpenSources: OpenSources;
}) {
  if (sources.length === 0) return null;
  return (
    <button
      type="button"
      data-source
      onClick={() => onOpenSources(sources, 0, title)}
      className="-my-1 inline-flex min-h-8 shrink-0 items-center whitespace-nowrap rounded px-1 text-[13px] font-medium text-primary-deep underline-offset-2 hover:underline focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
    >
      {t("results.source")}
      {sources.length > 1 ? ` (${sources.length})` : ""}
    </button>
  );
}

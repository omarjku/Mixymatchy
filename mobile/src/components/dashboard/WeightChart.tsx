import { CartesianGrid, LabelList, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { WeightScaleIcon } from "@hugeicons/core-free-icons";
import { Panel, SourcesButton } from "@/components/dashboard/Panel";
import { t } from "@/i18n/strings";
import { formatDate, formatNumber } from "@/lib/stats";
import type { SourceCitation } from "@/types/fact";
import type { MeasurementSet } from "@/types/stats";

// Documented weights on a true time axis (uneven gaps stay uneven) with straight segments:
// a smoothed curve would suggest measurements between the letters that do not exist.

const axisTick = { fill: "var(--color-ink-muted)", fontSize: 11 };
const monthYear = new Intl.DateTimeFormat("de-DE", { month: "short", year: "numeric" });

export function WeightChart({
  measurements,
  onPressSources,
}: {
  measurements: MeasurementSet[];
  onPressSources: (title: string, sources: SourceCitation[]) => void;
}) {
  const data = measurements.map((m) => ({ time: new Date(m.date).getTime(), weight: m.weightKg }));
  const weights = data.map((d) => d.weight);
  const title = t("dash.weight.title");

  return (
    <Panel
      title={title}
      icon={WeightScaleIcon}
      action={
        <SourcesButton
          count={measurements.length}
          label={t("dash.sourcesFor", { label: title })}
          onClick={() =>
            onPressSources(
              title,
              measurements.map((m) => m.source),
            )
          }
        />
      }
    >
      <div className="h-52" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 24, right: 20, bottom: 0, left: 4 }}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis
              type="number"
              dataKey="time"
              scale="time"
              domain={["dataMin", "dataMax"]}
              ticks={data.map((d) => d.time)}
              tickFormatter={(v: number) => monthYear.format(new Date(v))}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              padding={{ left: 24, right: 24 }}
            />
            <YAxis
              domain={[Math.floor(Math.min(...weights) - 4), Math.ceil(Math.max(...weights) + 4)]}
              width={32}
              tick={axisTick}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
            />
            <Line
              type="linear"
              dataKey="weight"
              stroke="var(--color-primary-strong)"
              strokeWidth={2}
              dot={{ r: 4, fill: "var(--color-primary-strong)", strokeWidth: 0 }}
              activeDot={false}
            >
              <LabelList
                dataKey="weight"
                position="top"
                offset={10}
                formatter={(v: unknown) => `${formatNumber(Number(v))} kg`}
                style={{ fill: "var(--color-ink)", fontSize: 12, fontWeight: 600 }}
              />
            </Line>
          </LineChart>
        </ResponsiveContainer>
      </div>

      <table className="sr-only">
        <caption>{title}</caption>
        <tbody>
          {measurements.map((m) => (
            <tr key={m.id}>
              <td>{formatDate(m.date)}</td>
              <td>
                {formatNumber(m.weightKg)} {t("dash.weight.unit")}
              </td>
              <td>{m.source.documentLabel}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";
import { DocumentValidationIcon } from "@hugeicons/core-free-icons";
import { IconTile } from "@/components/dashboard/Panel";
import { t } from "@/i18n/strings";

// Replaces Bionis's wellness score ring. Shows how many displayed facts are backed by a source passage:
// a proof count, not a health score. Counts come from the brief (computed), removed count from the backend.

export interface ProofRingProps {
  backed: number;
  total: number;
  removed: number;
}

export function ProofRing({ backed, total, removed }: ProofRingProps) {
  const share = total === 0 ? 0 : backed / total;
  const data = [
    { name: "backed", value: share },
    { name: "rest", value: Math.max(1 - share, 0) },
  ];

  return (
    <section className="flex items-center justify-between gap-4 rounded-lg border border-line bg-surface p-4">
      <div className="min-w-0">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
          <IconTile icon={DocumentValidationIcon} />
          {t("dash.proof.title")}
        </h3>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          {t("dash.proof.text", { n: backed, m: total, r: removed })}
        </p>
      </div>
      <div className="relative size-24 shrink-0" aria-hidden>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <Pie
              data={[{ value: 1 }]}
              dataKey="value"
              innerRadius="80%"
              outerRadius="100%"
              startAngle={90}
              endAngle={-270}
              stroke="none"
              isAnimationActive={false}
            >
              <Cell fill="var(--color-primary-soft)" />
            </Pie>
            <Pie
              data={data}
              dataKey="value"
              innerRadius="80%"
              outerRadius="100%"
              startAngle={90}
              endAngle={-270}
              stroke="none"
              cornerRadius={8}
            >
              <Cell fill="var(--color-primary-strong)" />
              <Cell fill="transparent" />
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <span className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-semibold leading-none text-ink">
            {backed}/{total}
          </span>
          <span className="mt-1 text-[10px] text-ink-muted">{t("dash.proof.ring")}</span>
        </span>
      </div>
    </section>
  );
}

import { ArrowDownRight01Icon, ArrowUpRight01Icon } from "@hugeicons/core-free-icons";
import { IconTile, SourcesButton } from "@/components/dashboard/Panel";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";

// Key-metric tile after Bionis's KeyMetricCard: icon + label, latest value, then the computed change.
// Direction arrows are neutral (no green = good / red = bad): a change is shown, never judged.
// Bionis's "more" menu is replaced by the sources of both compared values.

export interface MetricTileProps {
  icon: IconGlyph;
  label: string;
  value: string;
  unit: string;
  direction: "up" | "down" | "none";
  change: string; // e.g. "−12 kg · −14,81 %"
  comparison: string; // e.g. "81 → 69 kg"
  sourceCount: number;
  onPressSources: () => void;
}

export function MetricTile({
  icon,
  label,
  value,
  unit,
  direction,
  change,
  comparison,
  sourceCount,
  onPressSources,
}: MetricTileProps) {
  return (
    <article className="flex min-h-[150px] min-w-0 flex-col justify-between gap-4 rounded-2xl border border-line bg-surface p-4">
      <div className="flex items-start justify-between gap-2">
        <h4 className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink">
          <IconTile icon={icon} />
          <span className="truncate">{label}</span>
        </h4>
        <SourcesButton count={sourceCount} label={t("dash.sourcesFor", { label })} onClick={onPressSources} />
      </div>

      <div className="flex flex-col gap-2">
        <p className="leading-none">
          <span className="text-[28px] font-semibold tracking-tight text-ink">{value}</span>{" "}
          <span className="text-sm text-ink-muted">{unit}</span>
        </p>
        <p className="flex items-center gap-1.5 text-xs text-ink-muted">
          {direction !== "none" && (
            <Icon
              icon={direction === "up" ? ArrowUpRight01Icon : ArrowDownRight01Icon}
              size={14}
              className="text-ink"
            />
          )}
          <span className="font-semibold text-ink">{change}</span>
          <span aria-hidden>·</span>
          <span>{comparison}</span>
        </p>
      </div>
    </article>
  );
}

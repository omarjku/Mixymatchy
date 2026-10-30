import { Book02Icon, File01Icon, Flag02Icon } from "@hugeicons/core-free-icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, type CardTone } from "@/components/ui/Card";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { hasHistory, ValueHistory } from "@/components/ValueHistory";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import { Sparkline } from "@/components/Sparkline";
import type { Fact, FactRow, FactTrust } from "@/types/fact";

// One patient fact. Presentational only: the parent screen decides what source/guideline/flag do.
// Trust tier shows three ways at once (outline, badge, value styling) so it never depends on color alone.

export interface FactCardProps {
  fact: Fact;
  showHistory?: boolean; // "Verlauf" view: add the value history when the fact has one
  onPressSource: (fact: Fact) => void;
  onPressGuideline: (fact: Fact) => void;
  onPressFlag?: (fact: Fact) => void; // hidden until flagging is wired to a backend
}

const tones: Record<FactTrust, CardTone> = {
  verified: "verified",
  consistent: "verified",
  single: "default",
  not_applicable: "undocumented",
  ai_inferred: "inferred",
  conflicting: "contradiction",
  outdated: "inferred",
  not_documented: "undocumented",
};

export function FactCard({ fact, showHistory = false, onPressSource, onPressGuideline, onPressFlag }: FactCardProps) {
  const documented = fact.trust !== "not_documented";
  const notApplicable = fact.trust === "not_applicable";
  // Several facts for one need: compact rows, each with its own source; the card's footer then has no
  // card-level source button (the rows carry them).
  const rows = documented && !notApplicable ? fact.rows ?? [] : [];
  const multi = rows.length > 1 || fact.trend !== undefined;
  const openRow = (row: FactRow) => onPressSource({ ...fact, source: row.sources[0], sources: row.sources });

  if (!documented && !fact.guideline) {
    // nothing found: one slim line ("label: Not documented"), the dashed outline still marks it
    return (
      <Card tone={tones[fact.trust]} className="px-4 py-2" data-fact={fact.id} data-trust={fact.trust}>
        <h3 className="text-[15px] leading-snug">
          <span className="text-ink-muted">{fact.label}: </span>
          <span className="font-medium text-undocumented">{t("trust.not_documented")}</span>
        </h3>
        {fact.note && <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">{fact.note}</p>}
      </Card>
    );
  }

  return (
    <Card tone={tones[fact.trust]} className="relative px-4 py-2.5 pr-2" data-fact={fact.id} data-trust={fact.trust}>
      <div className={onPressFlag ? "pr-11" : "pr-2"}>
        <h3 className="text-sm text-ink-muted">{fact.label}</h3>
        {notApplicable ? (
          <p className="mt-1 text-[17px] font-medium leading-snug text-ink-muted">
            {t("trust.not_applicable")}
            {fact.value ? `: ${fact.value}` : ""}
          </p>
        ) : !documented ? (
          <p className="mt-1 text-[17px] font-medium leading-snug text-undocumented">{t("trust.not_documented")}</p>
        ) : fact.trend ? (
          <TrendLine fact={fact} onPressRow={openRow} />
        ) : multi ? (
          <FactRows rows={rows} onPressRow={openRow} />
        ) : (
          <p className="mt-1 text-[17px] font-semibold leading-snug text-ink">
            {rows[0]?.text ?? fact.value}
            {rows[0]?.date && <span className="ml-2 text-[13px] font-normal text-ink-muted">{rows[0].date}</span>}
          </p>
        )}
        {/* computed values show their formula; other notes say e.g. "no later value documented" */}
        {fact.note && (
          <p className="mt-1 text-[13px] leading-snug text-ink-muted">
            {fact.computed ? `${t("results.computed")}: ` : ""}
            {fact.note}
          </p>
        )}
      </div>

      {showHistory && documented && hasHistory(fact) && (
        <div className="pr-2">
          <ValueHistory fact={fact} />
        </div>
      )}

      {onPressFlag && (
        <Button
          variant="icon"
          icon={Flag02Icon}
          tone="flag"
          label={`${t("action.flag")}: ${fact.label}`}
          onClick={() => onPressFlag(fact)}
          className="absolute right-1.5 top-1.5"
        />
      )}

      {/* "Not documented" already says it in the value: no badge row unless there is a guideline */}
      {(documented || fact.guideline) && (
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {!documented ? null : fact.badgeLabel === undefined ? (
          <Badge variant={fact.trust} />
        ) : (
          fact.badgeLabel && <Badge variant="neutral">{fact.badgeLabel}</Badge>
        )}
        {documented && !multi && fact.source && (
          <CitationButton
            icon={File01Icon}
            label={notApplicable ? t("results.evidence") : t("results.source")}
            ariaLabel={`${t("action.source")}: ${fact.source.documentLabel}`}
            onClick={() => onPressSource(fact)}
            data-source
            className="text-primary-deep hover:bg-primary-soft"
          />
        )}
        {fact.guideline && (
          <CitationButton
            icon={Book02Icon}
            label=""
            ariaLabel={`${t("action.guideline")}: ${fact.guideline.guidelineName}`}
            onClick={() => onPressGuideline(fact)}
            className="text-ink-muted hover:bg-canvas hover:text-ink"
          />
        )}
      </div>
      )}
    </Card>
  );
}

// Compact rows: "value · date · Source". Rows the engine collapsed sit behind "+N more" (one tap).
export function FactRows({ rows, onPressRow, className }: {
  rows: FactRow[];
  onPressRow: (row: FactRow) => void;
  className?: string;
}) {
  const open = rows.filter((r) => !r.collapsed);
  const hidden = rows.filter((r) => r.collapsed);
  return (
    <div className={cn("mt-1", className)}>
      <ul className="divide-y divide-line/70">
        {open.map((r) => <Row key={r.id} row={r} onPress={onPressRow} />)}
      </ul>
      {hidden.length > 0 && <MoreRows rows={hidden} onPressRow={onPressRow} />}
    </div>
  );
}

export function MoreRows({ rows, onPressRow }: { rows: FactRow[]; onPressRow: (row: FactRow) => void }) {
  return (
    <details className="group mt-1" data-collapsed-rows={rows.length}>
      <summary className="inline-flex min-h-8 cursor-pointer list-none items-center rounded-full px-2 text-[13px] font-medium text-primary-deep hover:bg-primary-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary">
        <span className="group-open:hidden">{t("results.moreRows", { n: rows.length })}</span>
        <span className="hidden group-open:inline">{t("results.lessRows")}</span>
      </summary>
      <ul className="divide-y divide-line/70">
        {rows.map((r) => <Row key={r.id} row={r} onPress={onPressRow} />)}
      </ul>
    </details>
  );
}

function Row({ row, onPress }: { row: FactRow; onPress: (row: FactRow) => void }) {
  return (
    <li className="flex items-start gap-2 py-1" data-row={row.id}>
      <p className="min-w-0 flex-1 text-[14px] leading-snug">
        <span className="font-semibold text-ink">{row.text}</span>
        {row.date && <span className="text-[13px] text-ink-muted"> · {row.date}</span>}
        {row.computed && <span className="text-[13px] text-ink-muted"> · {t("results.computed")}</span>}
      </p>
      {row.sources.length > 0 && <RowSource row={row} onPress={onPress} />}
    </li>
  );
}

export function RowSource({ row, onPress }: { row: FactRow; onPress: (row: FactRow) => void }) {
  return (
    <button
      type="button"
      data-source
      onClick={() => onPress(row)}
      aria-label={`${t("action.source")}: ${row.sources[0].documentLabel}`}
      title={row.sources[0].documentLabel}
      className="-my-0.5 inline-flex min-h-7 shrink-0 items-center gap-1 rounded-full px-2 text-[12px] font-medium text-primary-deep hover:bg-primary-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary"
    >
      <Icon icon={File01Icon} size={14} />
      {t("results.source")}
    </button>
  );
}

// Trend: "78 kg → 67 kg → 66 kg", the calculated change, a small sparkline; middle readings the engine
// collapsed show as "…" and are listed behind "+N more".
export function TrendLine({ fact, onPressRow, sparkline = true }: {
  fact: Fact;
  onPressRow: (row: FactRow) => void;
  sparkline?: boolean;
}) {
  const trend = fact.trend!;
  const rows = fact.rows ?? [];
  const points = trend.points.filter((p, i) => !p.collapsed || (i > 0 && !trend.points[i - 1].collapsed));
  const all: FactRow = { id: `${fact.id}:all`, text: fact.label, sources: fact.sources ?? [] };
  const first = trend.points[0];
  const last = trend.points[trend.points.length - 1];
  return (
    <div className="mt-1">
      <div className="flex items-start gap-2">
        <p className="min-w-0 flex-1 text-[17px] font-semibold leading-snug text-ink">
          {points.map((p, i) => (
            <span key={`${p.date}-${i}`}>
              {i > 0 && <span className="font-normal text-ink-muted"> → </span>}
              {p.collapsed ? "…" : p.value}
            </span>
          ))}
        </p>
        {all.sources.length > 0 && <RowSource row={all} onPress={onPressRow} />}
      </div>
      <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">
        {trend.change && <span className="font-medium text-ink">{trend.change} ({t("results.computed")}) · </span>}
        {first.date} – {last.date}
      </p>
      {sparkline && <Sparkline values={trend.numbers} className="mt-1 h-6 w-full max-w-48" />}
      {rows.some((r) => r.collapsed) && <MoreRows rows={rows.filter((r) => r.collapsed)} onPressRow={onPressRow} />}
    </div>
  );
}

function CitationButton({
  icon,
  label,
  ariaLabel,
  onClick,
  className,
  ...rest
}: {
  "data-source"?: boolean;
  icon: IconGlyph;
  label: string;
  ariaLabel: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      {...rest}
      onClick={onClick}
      aria-label={ariaLabel}
      title={ariaLabel}
      className={cn(
        "inline-flex h-8 items-center gap-1 rounded-full border border-line bg-surface px-2.5 text-[12px] font-medium transition-colors",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
        className,
      )}
    >
      <Icon icon={icon} size={14} />
      {label || <span className="sr-only">{t("results.guideline")}</span>}
    </button>
  );
}

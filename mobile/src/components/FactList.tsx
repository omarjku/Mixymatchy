import {
  Alert02Icon,
  CheckmarkBadge01Icon,
  Clock01Icon,
  DashedLineCircleIcon,
  File01Icon,
  MinusSignCircleIcon,
  SparklesIcon,
} from "@hugeicons/core-free-icons";
import { FactRows, TrendLine } from "@/components/FactCard";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { Fact, FactRow, FactTrust } from "@/types/fact";
import { KeepDoses } from "@/components/ui/KeepDoses";

// The facts a task needs as one dense, scannable list (clinical-record style), not a card per fact.
// Tablet/desktop: label | value | status · Source. Phone: label and status on one line, value and Source below.
// Trust tier shows three ways (patient safety: never color alone): a small colored mark, a word, and for the
// two tiers that need attention (review needed / outdated, letters disagree) a faint tint on the whole row.
// Keeps data-fact / data-trust / button[data-source]: the e2e tests rely on them.

const marks: Record<FactTrust, { icon: IconGlyph; color: string }> = {
  verified: { icon: CheckmarkBadge01Icon, color: "text-verified" },
  consistent: { icon: CheckmarkBadge01Icon, color: "text-verified" },
  single: { icon: File01Icon, color: "text-ink-muted" },
  ai_inferred: { icon: SparklesIcon, color: "text-inferred-border" },
  outdated: { icon: Clock01Icon, color: "text-inferred-border" },
  conflicting: { icon: Alert02Icon, color: "text-contradiction" },
  not_applicable: { icon: MinusSignCircleIcon, color: "text-ink-muted" },
  not_documented: { icon: DashedLineCircleIcon, color: "text-undocumented" },
};

const rowTint: Partial<Record<FactTrust, string>> = {
  ai_inferred: "bg-inferred-soft/40",
  outdated: "bg-inferred-soft/40",
  conflicting: "bg-contradiction-soft/50",
};

export interface FactListProps {
  facts: Fact[];
  onPressSource: (fact: Fact) => void;
  onPressGuideline: (fact: Fact) => void;
}

export function FactList({ facts, onPressSource, onPressGuideline }: FactListProps) {
  return (
    <ul className="divide-y divide-line border-y border-line">
      {facts.map((fact) => (
        <FactListRow
          key={fact.id}
          fact={fact}
          onPressSource={onPressSource}
          onPressGuideline={onPressGuideline}
        />
      ))}
    </ul>
  );
}

function FactListRow({
  fact,
  onPressSource,
  onPressGuideline,
}: {
  fact: Fact;
  onPressSource: (fact: Fact) => void;
  onPressGuideline: (fact: Fact) => void;
}) {
  const documented = fact.trust !== "not_documented";
  const notApplicable = fact.trust === "not_applicable";
  const rows = documented && !notApplicable ? (fact.rows ?? []) : [];
  const multi = rows.length > 1 || fact.trend !== undefined;
  const openRow = (row: FactRow) => onPressSource({ ...fact, source: row.sources[0], sources: row.sources });

  let value: React.ReactNode;
  if (notApplicable) {
    value = (
      <p className="text-[15px] text-ink-muted">
        {t("trust.not_applicable")}
        {fact.value ? `: ${fact.value}` : ""}
      </p>
    );
  } else if (!documented) {
    value = <p className="text-[15px] font-medium text-undocumented">{t("trust.not_documented")}</p>;
  } else if (fact.trend) {
    // text only: the charts are in Details
    value = <TrendLine fact={fact} onPressRow={openRow} sparkline={false} />;
  } else if (multi) {
    value = <FactRows rows={rows} onPressRow={openRow} className="mt-0" />;
  } else {
    const row = rows[0];
    value = (
      <p className="text-[15px] font-semibold leading-snug text-ink tabular-nums">
        <KeepDoses text={row?.text ?? fact.value ?? ""} />
        {row?.date && <span className="ml-2 text-[13px] font-normal text-ink-muted">{row.date}</span>}
      </p>
    );
  }

  // Single-value facts get one Source link here; multi-row facts carry a Source per row (inside FactRows)
  const showSource = documented && !multi && Boolean(fact.source);

  return (
    <li
      data-fact={fact.id}
      data-trust={fact.trust}
      className={cn(
        "grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 px-3 py-3",
        // fixed last column so status words and links line up row after row (no zigzag)
        // last column = status (9.5rem) + links (8rem, fits "Source Guideline")
        "md:grid-cols-[minmax(8rem,10rem)_minmax(0,1fr)_18rem] md:items-baseline",
        rowTint[fact.trust],
      )}
    >
      <h3 className="col-start-1 row-start-1 min-w-0 text-[13px] leading-snug text-ink-muted md:text-[14px]">
        {fact.label}
      </h3>

      {/* Phone: status on the label line, links on the value line. From tablet width both share the last
          column (the wrapper is "contents" on phones, so its children are placed in the row's grid). */}
      <div className="contents md:col-start-3 md:row-start-1 md:grid md:grid-cols-[9.5rem_minmax(0,1fr)] md:items-baseline md:gap-2">
        <div className="col-start-2 row-start-1 flex justify-end md:col-start-1 md:justify-start">
          <Status fact={fact} />
        </div>
        <div className="col-start-2 row-start-2 flex items-start justify-end gap-2 md:col-start-2 md:row-start-1 md:justify-start">
          {showSource && (
            <TextLink
              label={notApplicable ? t("results.evidence") : t("results.source")}
              ariaLabel={`${t("action.source")}: ${fact.source!.documentLabel}`}
              onClick={() => onPressSource(fact)}
              source
            />
          )}
          {fact.guideline && (
            <TextLink
              label={t("results.guideline")}
              ariaLabel={`${t("action.guideline")}: ${fact.guideline.guidelineName}`}
              onClick={() => onPressGuideline(fact)}
              muted
            />
          )}
        </div>
      </div>

      <div className="col-start-1 row-start-2 min-w-0 md:col-start-2 md:row-start-1">
        {value}
        {fact.note && (
          <p className="mt-0.5 text-[13px] leading-snug text-ink-muted">
            {fact.computed ? `${t("results.computed")}: ` : ""}
            {fact.note}
          </p>
        )}
      </div>
    </li>
  );
}

// Small colored mark + word. The word stays in the readable muted color (teal text would be too faint on
// the dark theme); the mark carries the tier color. badgeLabel overrides the word ("" hides the status).
function Status({ fact }: { fact: Fact }) {
  if (fact.trust === "not_documented") return null; // the value already says it
  if (fact.badgeLabel === "") return null;
  const mark = marks[fact.trust];
  const word = fact.badgeLabel ?? t(`trust.${fact.trust}`);
  return (
    <span className="inline-flex items-center gap-1 text-right text-[12px] leading-tight text-ink-muted">
      <Icon icon={mark.icon} size={14} className={mark.color} />
      {word}
    </span>
  );
}

function TextLink({
  label,
  ariaLabel,
  onClick,
  source = false,
  muted = false,
}: {
  label: string;
  ariaLabel: string;
  onClick: () => void;
  source?: boolean;
  muted?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      title={ariaLabel}
      {...(source ? { "data-source": true } : {})}
      className={cn(
        "-my-1 inline-flex min-h-8 items-center whitespace-nowrap rounded px-1 text-[13px] font-medium underline-offset-2 hover:underline",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
        muted ? "text-ink-muted" : "text-primary-deep",
      )}
    >
      {label}
    </button>
  );
}

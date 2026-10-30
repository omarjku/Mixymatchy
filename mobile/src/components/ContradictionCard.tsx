import { File01Icon } from "@hugeicons/core-free-icons";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { t, type StringKey } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { Contradiction, SourceCitation } from "@/types/fact";

// Two or more documents disagreeing about the same fact. Passages are stacked (phone width), each with
// its document label, and each opens its source. The app only shows the conflict; it never resolves it.

export interface ContradictionCardProps {
  contradiction: Contradiction;
  onPressSource: (source: SourceCitation, all: SourceCitation[]) => void;
}

const severityStyles: Record<NonNullable<Contradiction["severity"]>, string> = {
  high: "bg-contradiction",
  medium: "bg-inferred-border",
  low: "bg-undocumented",
};

export function ContradictionCard({ contradiction, onPressSource }: ContradictionCardProps) {
  const { severity } = contradiction;

  return (
    <Card tone="contradiction">
      <div className="flex items-center justify-between gap-2">
        {contradiction.tier === "documentation_note" ? (
          <Badge variant="neutral">{t("label.documentationNote")}</Badge>
        ) : (
          <Badge variant="contradiction" />
        )}
        {severity && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-contradiction-deep">
            <span aria-hidden className={cn("size-2 rounded-full", severityStyles[severity])} />
            {t("results.severity")}: {t(`label.severity.${severity}` as StringKey)}
          </span>
        )}
      </div>

      <h3 className="mt-3 text-[17px] font-semibold text-ink">{contradiction.factLabel}</h3>
      {contradiction.explanation && (
        <p className="mt-1 text-[14px] leading-snug text-ink-muted">{contradiction.explanation}</p>
      )}

      {/* side by side, so the passages can be compared directly; each opens its letter */}
      <ul
        className={cn(
          "mt-3 grid gap-2",
          contradiction.conflictingSources.length >= 2 ? "grid-cols-2" : "",
        )}
        data-passages={contradiction.conflictingSources.length}
      >
        {contradiction.conflictingSources.map((source) => (
          <li key={source.segmentId ?? source.documentId + source.excerpt}>
            <button
              type="button"
              data-source
              onClick={() => onPressSource(source, contradiction.conflictingSources)}
              className={cn(
                "h-full w-full rounded-xl border border-contradiction-border/50 bg-surface p-3 text-left transition-colors",
                "hover:border-contradiction-border focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs text-ink-muted">
                <Icon icon={File01Icon} size={14} />
                {source.documentLabel}
              </span>
              <span lang="de" className="mt-1 block break-words font-serif text-[14px] leading-snug text-ink">
                „{source.excerpt}“
              </span>
              <span className="mt-2 inline-flex items-center gap-1 text-[13px] font-medium text-primary-deep underline underline-offset-2">
                {t("results.source")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

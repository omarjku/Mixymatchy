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
  onPressSource: (source: SourceCitation) => void;
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
        <Badge variant="contradiction" />
        {severity && (
          <span className="flex items-center gap-1.5 text-xs font-medium text-contradiction-deep">
            <span aria-hidden className={cn("size-2 rounded-full", severityStyles[severity])} />
            {t("results.severity")}: {t(`label.severity.${severity}` as StringKey)}
          </span>
        )}
      </div>

      <h3 className="mt-3 text-[17px] font-semibold text-ink">{contradiction.factLabel}</h3>

      <ul className="mt-3 space-y-2">
        {contradiction.conflictingSources.map((source) => (
          <li key={source.documentId + source.excerpt}>
            <button
              type="button"
              onClick={() => onPressSource(source)}
              className={cn(
                "w-full rounded-xl border border-contradiction-border/50 bg-surface p-3 text-left transition-colors",
                "hover:border-contradiction-border focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs text-ink-muted">
                <Icon icon={File01Icon} size={14} />
                {source.documentLabel}
              </span>
              <span className="mt-1 block text-[15px] leading-snug text-ink">„{source.excerpt}“</span>
            </button>
          </li>
        ))}
      </ul>
    </Card>
  );
}

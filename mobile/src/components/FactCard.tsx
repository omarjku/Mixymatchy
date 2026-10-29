import { Book02Icon, File01Icon, Flag02Icon } from "@hugeicons/core-free-icons";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, type CardTone } from "@/components/ui/Card";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { hasHistory, ValueHistory } from "@/components/ValueHistory";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { Fact, FactTrust } from "@/types/fact";

// One patient fact. Presentational only: the parent screen decides what source/guideline/flag do.
// Trust tier shows three ways at once (outline, badge, value styling) so it never depends on color alone.

export interface FactCardProps {
  fact: Fact;
  showHistory?: boolean; // "Verlauf" view: add the value history when the fact has one
  onPressSource: (fact: Fact) => void;
  onPressGuideline: (fact: Fact) => void;
  onPressFlag: (fact: Fact) => void;
}

const tones: Record<FactTrust, CardTone> = {
  verified: "verified",
  ai_inferred: "inferred",
  not_documented: "undocumented",
};

export function FactCard({ fact, showHistory = false, onPressSource, onPressGuideline, onPressFlag }: FactCardProps) {
  const documented = fact.trust !== "not_documented";

  return (
    <Card tone={tones[fact.trust]} className="relative pr-2">
      <div className="pr-11">
        <h3 className="text-sm text-ink-muted">{fact.label}</h3>
        {documented ? (
          <p className="mt-1 text-[17px] font-semibold leading-snug text-ink">{fact.value}</p>
        ) : (
          <p className="mt-1 text-[17px] font-medium leading-snug text-undocumented">{t("trust.not_documented")}</p>
        )}
      </div>

      {showHistory && documented && hasHistory(fact) && (
        <div className="pr-2">
          <ValueHistory fact={fact} />
        </div>
      )}

      <Button
        variant="icon"
        icon={Flag02Icon}
        tone="flag"
        label={`${t("action.flag")}: ${fact.label}`}
        onClick={() => onPressFlag(fact)}
        className="absolute right-1.5 top-1.5"
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Badge variant={fact.trust} />
        {documented && fact.source && (
          <CitationButton
            icon={File01Icon}
            label={t("results.source")}
            ariaLabel={`${t("action.source")}: ${fact.source.documentLabel}`}
            onClick={() => onPressSource(fact)}
            className="text-primary-deep hover:bg-primary-soft"
          />
        )}
        {fact.guideline && (
          <CitationButton
            icon={Book02Icon}
            label={t("results.guideline")}
            ariaLabel={`${t("action.guideline")}: ${fact.guideline.guidelineName}`}
            onClick={() => onPressGuideline(fact)}
            className="text-ink-muted hover:bg-canvas hover:text-ink"
          />
        )}
      </div>
    </Card>
  );
}

function CitationButton({
  icon,
  label,
  ariaLabel,
  onClick,
  className,
}: {
  icon: IconGlyph;
  label: string;
  ariaLabel: string;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      title={ariaLabel}
      className={cn(
        "inline-flex h-10 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-[13px] font-medium transition-colors",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
        className,
      )}
    >
      <Icon icon={icon} size={16} />
      {label}
    </button>
  );
}

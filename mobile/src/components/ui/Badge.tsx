import { Alert02Icon, CheckmarkBadge01Icon, File01Icon, MinusSignCircleIcon, Clock01Icon, DashedLineCircleIcon, SparklesIcon } from "@hugeicons/core-free-icons";
import { Badge as PrimitiveBadge } from "@/components/primitives/badge";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { FactTrust } from "@/types/fact";

// Trust-tier badge. Variants map 1:1 to FactTrust so FactCard can do <Badge variant={fact.trust} />.
// verified and ai_inferred must never share weight or color: solid teal vs. dashed amber outline.

export type BadgeVariant = FactTrust | "contradiction" | "neutral";

const styles: Record<BadgeVariant, string> = {
  verified: "border-transparent bg-verified text-verified-ink",
  consistent: "border-transparent bg-verified text-verified-ink",
  single: "border-line bg-surface text-ink-muted",
  not_applicable: "border-dashed border-line bg-surface text-ink-muted",
  ai_inferred: "border-dashed border-inferred-border bg-inferred-soft text-inferred",
  conflicting: "border-contradiction-border bg-surface text-contradiction-deep",
  outdated: "border-dashed border-inferred-border bg-inferred-soft text-inferred",
  not_documented: "border-transparent bg-undocumented-soft text-undocumented",
  contradiction: "border-transparent bg-contradiction text-white",
  neutral: "border-line bg-surface text-ink-muted",
};

const icons: Partial<Record<BadgeVariant, IconGlyph>> = {
  verified: CheckmarkBadge01Icon,
  consistent: CheckmarkBadge01Icon,
  single: File01Icon,
  not_applicable: MinusSignCircleIcon,
  ai_inferred: SparklesIcon,
  conflicting: Alert02Icon,
  outdated: Clock01Icon,
  not_documented: DashedLineCircleIcon,
  contradiction: Alert02Icon,
};

const defaultLabels = (): Partial<Record<BadgeVariant, string>> => ({
  verified: t("trust.verified"),
  consistent: t("trust.consistent"),
  single: t("trust.single"),
  not_applicable: t("trust.not_applicable"),
  ai_inferred: t("trust.ai_inferred"),
  conflicting: t("trust.conflicting"),
  outdated: t("trust.outdated"),
  not_documented: t("trust.not_documented"),
  contradiction: t("label.contradiction"),
});

export interface BadgeProps {
  variant: BadgeVariant;
  children?: React.ReactNode; // defaults to the variant's standard label
  className?: string;
}

export function Badge({ variant, children, className }: BadgeProps) {
  const glyph = icons[variant];
  return (
    <PrimitiveBadge
      className={cn(
        "max-w-full shrink gap-1 whitespace-normal text-left rounded-full px-2.5 py-1 text-[11px] font-semibold leading-none tracking-wide shadow-none",
        styles[variant],
        className,
      )}
    >
      {glyph && <Icon icon={glyph} size={14} />}
      {children ?? defaultLabels()[variant]}
    </PrimitiveBadge>
  );
}

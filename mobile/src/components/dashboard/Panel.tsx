import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";

// Card shell for dashboard sections, after Bionis's chart cards: icon tile + title, optional right slot.

export interface PanelProps {
  title: string;
  icon: IconGlyph;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}

export function Panel({ title, icon, action, children, className }: PanelProps) {
  return (
    <section className={cn("min-w-0 rounded-2xl border border-line bg-surface p-4", className)}>
      <header className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex min-w-0 items-center gap-2 text-sm font-semibold text-ink">
          <IconTile icon={icon} />
          <span className="truncate">{title}</span>
        </h3>
        {action}
      </header>
      {children}
    </section>
  );
}

export function IconTile({ icon }: { icon: IconGlyph }) {
  return (
    <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary-deep">
      <Icon icon={icon} size={16} />
    </span>
  );
}

// Small "Quellen" pill used on tiles and panels; opens all source passages behind a number
export function SourcesButton({ count, label, onClick }: { count: number; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-8 shrink-0 items-center rounded-full border border-line px-2.5 text-xs font-medium text-primary-deep",
        "transition-colors hover:bg-primary-soft focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
      )}
    >
      {count === 1 ? t("results.source") : `${t("results.sources")} (${count})`}
    </button>
  );
}

import { useId, useRef } from "react";
import { LayoutGroup, motion } from "motion/react";
import { cn } from "@/lib/utils";

// Segmented tabs with a sliding pill, built from Watermelon UI's continuous-tabs
// (registry.watermelon.sh/r/continuous-tabs.json). Accessible tablist: arrow keys move between tabs.

export interface ViewTab<T extends string> {
  id: T;
  label: string;
}

export interface ViewTabsProps<T extends string> {
  tabs: ViewTab<T>[];
  active: T;
  onChange: (id: T) => void;
  label: string; // accessible name of the tab list
  panelId: string; // id of the region the tabs control
}

export function ViewTabs<T extends string>({ tabs, active, onChange, label, panelId }: ViewTabsProps<T>) {
  const pillId = useId(); // per instance, so two tab bars never share one sliding pill
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const next =
      e.key === "ArrowRight" ? (index === last ? 0 : index + 1)
      : e.key === "ArrowLeft" ? (index === 0 ? last : index - 1)
      : e.key === "Home" ? 0
      : e.key === "End" ? last
      : null;
    if (next === null) return;
    e.preventDefault();
    onChange(tabs[next].id);
    refs.current[next]?.focus();
  }

  return (
    <LayoutGroup id={pillId}>
      <div
        role="tablist"
        aria-label={label}
        className="grid rounded-full border border-line bg-surface p-1"
        style={{ gridTemplateColumns: `repeat(${tabs.length}, minmax(0, 1fr))` }}
      >
        {tabs.map((tab, index) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                refs.current[index] = el;
              }}
              type="button"
              role="tab"
              aria-selected={selected}
              aria-controls={panelId}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(tab.id)}
              onKeyDown={(e) => onKeyDown(e, index)}
              className="relative h-10 rounded-full outline-hidden focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2"
            >
              {selected && (
                <motion.span
                  layoutId="active-pill"
                  transition={{ type: "spring", stiffness: 380, damping: 30, mass: 0.9 }}
                  className="absolute inset-0 rounded-full bg-primary-strong"
                />
              )}
              <span
                className={cn(
                  "relative z-10 text-sm font-semibold transition-colors duration-200",
                  selected ? "text-primary-ink" : "text-ink-muted hover:text-ink",
                )}
              >
                {tab.label}
              </span>
            </button>
          );
        })}
      </div>
    </LayoutGroup>
  );
}

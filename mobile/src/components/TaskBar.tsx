import { AnimatePresence, motion, type Transition } from "motion/react";
import {
  ArrowDown01Icon,
  ArrowRight02Icon,
  ArrowUp01Icon,
  ViewIcon,
  VolumeHighIcon,
} from "@hugeicons/core-free-icons";
import { Icon } from "@/components/ui/Icon";
import { t } from "@/i18n/strings";
import { cn } from "@/lib/utils";
import type { DeliveryMode } from "@/types/request";

// Task input bar, built from Watermelon UI's quick-switcher (registry.watermelon.sh/r/quick-switcher.json).
// Left: switch between "Anzeigen" (show) and "Vorlesen" (show + read aloud). Middle: task text. Right: send.
// Controlled: the screen owns value and mode so suggestion chips can fill the field.

export interface TaskBarProps {
  value: string;
  onValueChange: (value: string) => void;
  mode: DeliveryMode;
  onModeChange: (mode: DeliveryMode) => void;
  onSubmit: () => void;
  canSubmit: boolean;
}

const spring: Transition = { type: "spring", stiffness: 300, damping: 30, mass: 0.8 };

export function TaskBar({ value, onValueChange, mode, onModeChange, onSubmit, canSubmit }: TaskBarProps) {
  const speaking = mode === "speak";
  const placeholder = speaking ? t("bar.placeholder.speak") : t("bar.placeholder.display");

  return (
    <div
      className={cn(
        "flex h-16 w-full items-center gap-1 rounded-full border border-line bg-surface p-1.5",
        "shadow-[0_1px_2px_rgba(20,24,49,0.05),0_10px_24px_-14px_rgba(20,24,49,0.25)]",
        "transition-[border-color,box-shadow] focus-within:border-primary focus-within:shadow-[0_0_0_3px_var(--color-primary-soft)]",
      )}
    >
      <button
        type="button"
        role="switch"
        aria-checked={speaking}
        aria-label={t("bar.mode.switchLabel")}
        title={t("bar.mode.switchLabel")}
        onClick={() => onModeChange(speaking ? "display" : "speak")}
        className={cn(
          "flex h-full shrink-0 items-center gap-0.5 rounded-full pl-3 pr-2 transition-colors active:scale-95",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary",
          speaking
            ? "bg-primary-strong text-primary-ink hover:bg-primary-hover"
            : "bg-primary-soft text-primary-deep hover:bg-primary/25",
        )}
      >
        <span className="relative flex size-6 items-center justify-center">
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={mode}
              initial={{ opacity: 0, scale: 0.5 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.5 }}
              transition={spring}
              className="flex"
            >
              <Icon icon={speaking ? VolumeHighIcon : ViewIcon} size={22} />
            </motion.span>
          </AnimatePresence>
        </span>
        <span className="flex flex-col opacity-70" aria-hidden>
          <Icon icon={ArrowUp01Icon} size={12} />
          <Icon icon={ArrowDown01Icon} size={12} className="-mt-0.5" />
        </span>
      </button>

      <div className="relative flex h-full min-w-0 flex-1 items-center overflow-hidden px-3">
        <AnimatePresence mode="popLayout" initial={false}>
          {value.length === 0 && (
            <AnimatedPlaceholder
              key={placeholder}
              text={placeholder}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 whitespace-nowrap text-[17px] font-medium text-ink-faint"
            />
          )}
        </AnimatePresence>
        <input
          type="text"
          value={value}
          onChange={(e) => onValueChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && canSubmit) onSubmit();
          }}
          aria-label={placeholder}
          enterKeyHint="send"
          autoComplete="off"
          // 17px keeps iOS from zooming on focus (needs >= 16px)
          className="w-full min-w-0 flex-1 border-none bg-transparent text-[17px] font-medium text-ink outline-hidden"
        />
      </div>

      <motion.button
        type="button"
        onClick={onSubmit}
        disabled={!canSubmit}
        aria-label={t("bar.send")}
        title={t("bar.send")}
        whileHover={canSubmit ? { x: 2 } : undefined}
        whileTap={canSubmit ? { scale: 0.9 } : undefined}
        className={cn(
          "flex size-12 shrink-0 items-center justify-center rounded-full transition-colors",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
          canSubmit
            ? "bg-primary-strong text-primary-ink hover:bg-primary-hover active:bg-primary-deep"
            : "bg-line text-ink-muted",
        )}
      >
        <Icon icon={ArrowRight02Icon} size={22} />
      </motion.button>
    </div>
  );
}

// Letter-by-letter placeholder swap, the signature effect of the original quick-switcher.
function AnimatedPlaceholder({ text, className }: { text: string; className?: string }) {
  return (
    <span className={className} style={{ display: "inline-flex" }} aria-hidden>
      {text.split("").map((char, i) => (
        <motion.span
          key={i}
          initial={{ y: 10, opacity: 0, scale: 0.5 }}
          animate={{ y: 0, opacity: 1, scale: 1 }}
          exit={{ y: -10, opacity: 0, scale: 0.5 }}
          transition={{ type: "spring", stiffness: 240, damping: 16, mass: 1.2, delay: i * 0.014 }}
          style={{ display: "inline-block", whiteSpace: char === " " ? "pre" : undefined }}
        >
          {char}
        </motion.span>
      ))}
    </span>
  );
}

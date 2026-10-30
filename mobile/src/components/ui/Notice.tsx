import { Alert02Icon, EditOffIcon, InformationCircleIcon } from "@hugeicons/core-free-icons";
import { Alert, AlertDescription, AlertTitle } from "@/components/primitives/alert";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { cn } from "@/lib/utils";

// Inline notice, styled after Watermelon UI's alert-18 (tinted info alert: colored border, 10% tint,
// colored title and text) on the base alert primitive.
//
//   tone="readonly"  the app never edits records or notes (role="note": read in place, not announced)
//   tone="info"      neutral information (role="note")
//   tone="warning"   needs attention now (role="alert": screen readers announce it)

export type NoticeTone = "readonly" | "info" | "warning";

const tones: Record<NoticeTone, { className: string; icon: IconGlyph; role: "note" | "alert" }> = {
  readonly: { className: "border-primary bg-primary/10 text-primary-deep", icon: EditOffIcon, role: "note" },
  info: { className: "border-primary bg-primary/10 text-primary-deep", icon: InformationCircleIcon, role: "note" },
  warning: {
    className: "border-contradiction-border bg-contradiction-soft text-contradiction-deep",
    icon: Alert02Icon,
    role: "alert",
  },
};

export interface NoticeProps {
  tone?: NoticeTone;
  title: string;
  children?: React.ReactNode;
  className?: string;
}

export function Notice({ tone = "info", title, children, className }: NoticeProps) {
  const { className: toneClass, icon, role } = tones[tone];
  return (
    <Alert role={role} className={cn("rounded-2xl px-4 py-3", toneClass, className)}>
      <Icon icon={icon} size={18} />
      <AlertTitle className="line-clamp-none font-semibold">{title}</AlertTitle>
      {children && <AlertDescription className="text-current">{children}</AlertDescription>}
    </Alert>
  );
}

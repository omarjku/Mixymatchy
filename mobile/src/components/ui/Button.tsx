import * as React from "react";
import { Button as PrimitiveButton } from "@/components/primitives/button";
import { Icon, type IconGlyph } from "@/components/ui/Icon";
import { cn } from "@/lib/utils";

// App-level button API. Screens use this, never the shadcn primitive directly.
//
//   <Button variant="primary">…</Button>                      main submit action, full-width on phone
//   <Button variant="secondary">…</Button>                    lower-emphasis action
//   <Button variant="icon" icon={Flag02Icon} label="Melden" /> icon-only (flag / source / export); label becomes aria-label + tooltip
//
// Hover and press darken or tint; they never fade the button.

type TextButtonProps = {
  variant?: "primary" | "secondary" | "ghost";
  icon?: IconGlyph;
  iconPosition?: "start" | "end";
  fullWidth?: boolean;
  children: React.ReactNode;
};

type IconButtonProps = {
  variant: "icon";
  icon: IconGlyph;
  label: string;
  tone?: "default" | "flag";
};

export type ButtonProps = (TextButtonProps | IconButtonProps) &
  Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "children">;

const textStyles = {
  primary:
    "h-12 rounded-xl bg-primary-strong px-5 text-[15px] font-semibold text-primary-ink shadow-none hover:bg-primary-hover active:bg-primary-deep disabled:bg-line disabled:text-ink-muted disabled:opacity-100",
  secondary:
    "h-11 rounded-xl border border-line bg-surface px-4 text-sm font-medium text-ink shadow-none hover:border-ink-faint hover:bg-surface active:bg-canvas",
  ghost:
    "h-10 rounded-lg px-3 text-sm font-medium text-primary-deep shadow-none hover:bg-primary-soft hover:text-primary-deep active:bg-primary-soft",
} as const;

const iconTones = {
  default: "text-ink-muted hover:bg-primary-soft hover:text-primary-deep",
  flag: "text-ink-muted hover:bg-contradiction-soft hover:text-contradiction",
} as const;

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>((props, ref) => {
  if (props.variant === "icon") {
    const { variant: _variant, icon, label, tone = "default", className, ...rest } = props;
    return (
      <PrimitiveButton
        ref={ref}
        type="button"
        variant="ghost"
        size="icon"
        aria-label={label}
        title={label}
        // 44px tap target (WCAG / iOS HIG), icon stays small
        className={cn("h-11 w-11 rounded-full [&_svg]:size-5", iconTones[tone], className)}
        {...rest}
      >
        <Icon icon={icon} size={20} />
      </PrimitiveButton>
    );
  }

  const { variant = "primary", icon, iconPosition = "start", fullWidth, className, children, ...rest } = props;
  return (
    <PrimitiveButton
      ref={ref}
      type="button"
      // primitive "ghost" is the neutral base; our textStyles carry all color
      variant="ghost"
      className={cn(textStyles[variant], fullWidth && "w-full", className)}
      {...rest}
    >
      {icon && iconPosition === "start" && <Icon icon={icon} />}
      {children}
      {icon && iconPosition === "end" && <Icon icon={icon} />}
    </PrimitiveButton>
  );
});
Button.displayName = "Button";

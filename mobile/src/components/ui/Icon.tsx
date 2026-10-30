import { HugeiconsIcon, type IconSvgElement } from "@hugeicons/react";
import { cn } from "@/lib/utils";

// The only place the app touches the icon library. Pass any icon from "@hugeicons/core-free-icons".

export type IconGlyph = IconSvgElement;

export interface IconProps {
  icon: IconGlyph;
  size?: number;
  className?: string;
}

export function Icon({ icon, size = 18, className }: IconProps) {
  return (
    <HugeiconsIcon
      icon={icon}
      size={size}
      strokeWidth={1.6}
      aria-hidden
      className={cn("shrink-0", className)}
    />
  );
}

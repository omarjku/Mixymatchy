import { cn } from "@/lib/utils";

// Selectable pill used for preset task options.

export interface ChipProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  selected: boolean;
}

export function Chip({ selected, className, ...rest }: ChipProps) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      className={cn(
        "min-h-11 rounded-full border px-4 py-2 text-left text-sm font-medium transition-colors",
        "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
        selected
          ? "border-primary-strong bg-primary-strong text-primary-ink"
          : "border-line bg-surface text-ink hover:border-primary/60",
        className,
      )}
      {...rest}
    />
  );
}

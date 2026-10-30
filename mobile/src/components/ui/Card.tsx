import * as React from "react";
import { Card as PrimitiveCard } from "@/components/primitives/card";
import { cn } from "@/lib/utils";

// Base card shape for FactCard, ContradictionCard and selectable role cards.
//
//   tone       outline style per trust tier: solid = verified, dashed = unconfirmed or missing
//   selectable renders as a <button> with a pressed state (used for role selection)

export type CardTone = "default" | "verified" | "inferred" | "undocumented" | "contradiction";

const toneStyles: Record<CardTone, string> = {
  default: "",
  verified: "",
  inferred: "border-dashed border-inferred-border bg-inferred-soft/40",
  undocumented: "border-dashed border-ink-faint/60 bg-transparent shadow-none",
  contradiction: "border-contradiction-border bg-contradiction-soft",
};

const base = "rounded-lg border border-line bg-surface p-4 text-ink shadow-[0_1px_2px_rgba(20,24,49,0.05)]";

type StaticCardProps = {
  selectable?: false;
  tone?: CardTone;
} & React.HTMLAttributes<HTMLDivElement>;

type SelectableCardProps = {
  selectable: true;
  selected: boolean;
  tone?: CardTone;
} & React.ButtonHTMLAttributes<HTMLButtonElement>;

export type CardProps = StaticCardProps | SelectableCardProps;

export function Card(props: CardProps) {
  if (props.selectable) {
    const { selectable: _s, selected, tone = "default", className, ...rest } = props;
    return (
      <button
        type="button"
        aria-pressed={selected}
        className={cn(
          base,
          toneStyles[tone],
          "w-full text-left transition-[border-color,background-color,box-shadow] duration-150",
          "focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2",
          selected
            ? "border-primary bg-primary-soft shadow-[0_0_0_1px_var(--color-primary)]"
            : "hover:border-primary/60 active:bg-canvas",
          className,
        )}
        {...rest}
      />
    );
  }

  const { selectable: _s, tone = "default", className, ...rest } = props;
  return <PrimitiveCard className={cn(base, toneStyles[tone], className)} {...rest} />;
}

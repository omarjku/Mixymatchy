import { cn } from "@/lib/utils";

// Placeholder block for loading states. Pulses only when the device allows motion.
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("rounded-xl bg-line motion-safe:animate-pulse", className)} />;
}

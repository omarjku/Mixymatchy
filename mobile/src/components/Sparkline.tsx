// Tiny trend line for a numeric history. Decorative (aria-hidden): the exact values are always listed
// next to it, so nobody has to read numbers off a line.

export function parseGermanNumber(value: string): number | null {
  const match = value.replace(/\./g, "").match(/-?\d+(,\d+)?/);
  return match ? Number(match[0].replace(",", ".")) : null;
}

export function Sparkline({ values, className }: { values: number[]; className?: string }) {
  if (values.length < 2) return null;

  const width = 120;
  const height = 36;
  const pad = 4;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1; // flat series: draw a level line in the middle
  const points = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (width - pad * 2);
    const y = max === min ? height / 2 : pad + (1 - (v - min) / span) * (height - pad * 2);
    return [x, y] as const;
  });
  const [lastX, lastY] = points[points.length - 1];

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className={className}
      aria-hidden
      preserveAspectRatio="none"
      fill="none"
    >
      <polyline
        points={points.map(([x, y]) => `${x},${y}`).join(" ")}
        stroke="var(--color-primary-strong)"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
      <circle cx={lastX} cy={lastY} r={3} fill="var(--color-primary-strong)" />
    </svg>
  );
}

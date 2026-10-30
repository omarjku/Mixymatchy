import React from "react";
import { useCurrentFrame } from "remotion";
import { C, FONT } from "../theme";
import { tween } from "../lib";

/** Masked rise: content slides up from behind an invisible edge. */
export const Rise: React.FC<{ at: number; dur?: number; children: React.ReactNode; style?: React.CSSProperties; out?: number }> = ({
  at,
  dur = 22,
  children,
  style,
  out,
}) => {
  const f = useCurrentFrame();
  const t = tween(f, at, dur);
  const o = out !== undefined ? tween(f, out, 14) : 0;
  return (
    <span data-mask="1" style={{ display: "inline-block", overflow: "hidden", verticalAlign: "bottom", paddingBottom: "0.12em", marginBottom: "-0.12em", ...style }}>
      <span
        style={{
          display: "inline-block",
          transform: `translateY(${(1 - t) * 105 - o * 105}%)`,
          opacity: Math.min(t * 1.4, 1) * (1 - o),
        }}
      >
        {children}
      </span>
    </span>
  );
};

/** Kinetic headline: words rise one after another; `accent` words are teal. */
export const Words: React.FC<{
  text: string;
  at: number;
  stagger?: number;
  size?: number;
  weight?: number;
  color?: string;
  accent?: string[];
  accentColor?: string;
  out?: number;
  style?: React.CSSProperties;
  tracking?: number;
}> = ({ text, at, stagger = 3, size = 72, weight = 700, color = C.ink, accent = [], accentColor = C.tealHi, out, style, tracking = -0.035 }) => {
  const words = text.split(" ");
  return (
    <div style={{ fontFamily: FONT, fontSize: size, fontWeight: weight, color, letterSpacing: `${tracking}em`, lineHeight: 1.08, ...style }}>
      {words.map((w, i) => (
        <React.Fragment key={i}>
          <Rise at={at + i * stagger} out={out !== undefined ? out + i * 1.5 : undefined}>
            <span style={{ color: accent.includes(w.replace(/[.,:!?]/g, "")) ? accentColor : undefined }}>{w}</span>
          </Rise>
          {i < words.length - 1 ? " " : null}
        </React.Fragment>
      ))}
    </div>
  );
};

/** Small uppercase label with a teal rule that draws in. */
export const Kicker: React.FC<{ text: string; at: number; color?: string; style?: React.CSSProperties }> = ({ text, at, color = C.tealHi, style }) => {
  const f = useCurrentFrame();
  const t = tween(f, at, 24);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 16, fontFamily: FONT, ...style }}>
      <div style={{ width: 44 * t, height: 2, background: color, borderRadius: 2 }} />
      <div style={{ fontSize: 20, fontWeight: 600, letterSpacing: "0.22em", textTransform: "uppercase", color, opacity: t, transform: `translateX(${(1 - t) * -12}px)` }}>
        {text}
      </div>
    </div>
  );
};

/** Number that counts up. */
export const Count: React.FC<{ to: number; at: number; dur?: number; decimals?: number; prefix?: string; suffix?: string }> = ({
  to,
  at,
  dur = 40,
  decimals = 0,
  prefix = "",
  suffix = "",
}) => {
  const f = useCurrentFrame();
  const v = to * tween(f, at, dur);
  return (
    <span style={{ fontVariantNumeric: "tabular-nums" }}>
      {prefix}
      {v.toFixed(decimals)}
      {suffix}
    </span>
  );
};

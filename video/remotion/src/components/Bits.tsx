import React from "react";
import { useCurrentFrame } from "remotion";
import { C, FONT } from "../theme";
import { spr } from "../lib";

export type Status = "documented" | "not_documented" | "not_applicable" | "conflicting" | "stale" | "consistent";

/** Reliability mark: check / hollow ring / warning / hourglass-ish clock. */
export const Mark: React.FC<{ status: Status; size?: number }> = ({ status, size = 22 }) => {
  const col =
    status === "conflicting" ? C.alert : status === "stale" ? C.amber : status === "not_documented" || status === "not_applicable" ? C.faint : C.tealHi;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" style={{ flex: "none" }}>
      {status === "not_documented" || status === "not_applicable" ? (
        <circle cx="12" cy="12" r="8" fill="none" stroke={col} strokeWidth="2.2" strokeDasharray={status === "not_applicable" ? "3 3" : undefined} />
      ) : status === "conflicting" ? (
        <>
          <path d="M12 3 L22 20 H2 Z" fill="none" stroke={col} strokeWidth="2.2" strokeLinejoin="round" />
          <path d="M12 10 V14" stroke={col} strokeWidth="2.2" strokeLinecap="round" />
          <circle cx="12" cy="17" r="1.3" fill={col} />
        </>
      ) : status === "stale" ? (
        <>
          <circle cx="12" cy="12" r="9" fill="none" stroke={col} strokeWidth="2.2" />
          <path d="M12 7 V12 L15.5 14" stroke={col} strokeWidth="2.2" strokeLinecap="round" fill="none" />
        </>
      ) : (
        <>
          <circle cx="12" cy="12" r="10" fill="rgba(94,234,212,0.14)" />
          <path d="M7 12.5 L10.5 16 L17 8.5" stroke={col} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none" />
        </>
      )}
    </svg>
  );
};

/** Pill that springs in. */
export const Chip: React.FC<{ at: number; children: React.ReactNode; tone?: "teal" | "plain" | "alert"; style?: React.CSSProperties; size?: number }> = ({
  at,
  children,
  tone = "plain",
  style,
  size = 24,
}) => {
  const f = useCurrentFrame();
  const s = spr(f, at, 140, 16);
  const bg = tone === "teal" ? "rgba(15,118,110,0.28)" : tone === "alert" ? C.alertDim : "rgba(245,241,234,0.06)";
  const bd = tone === "teal" ? "rgba(94,234,212,0.45)" : tone === "alert" ? "rgba(240,103,106,0.5)" : C.line2;
  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 12,
        padding: `${size * 0.45}px ${size * 0.85}px`,
        borderRadius: 999,
        background: bg,
        border: `1.5px solid ${bd}`,
        fontFamily: FONT,
        fontSize: size,
        fontWeight: 500,
        color: C.ink,
        transform: `translateY(${(1 - s) * 24}px) scale(${0.9 + 0.1 * s})`,
        opacity: Math.min(1, s * 1.5),
        whiteSpace: "nowrap",
        backdropFilter: "blur(10px)",
        ...style,
      }}
    >
      {children}
    </div>
  );
};

/** Glass card. */
export const Glass: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <div
    style={{
      background: "linear-gradient(160deg, rgba(21,37,43,0.92), rgba(12,23,27,0.92))",
      border: `1px solid ${C.line2}`,
      borderRadius: 20,
      boxShadow: "0 30px 80px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.05)",
      fontFamily: FONT,
      color: C.ink,
      ...style,
    }}
  >
    {children}
  </div>
);

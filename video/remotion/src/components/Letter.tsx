import React from "react";
import { C, FONT, MONO } from "../theme";
import { dmy, rand } from "../lib";

/** An abstract letter: date + English document type, grey bars instead of text (no letter text in code). */
export const LetterCard: React.FC<{
  w?: number;
  h?: number;
  date: string;
  title: string;
  seed: number;
  tone?: "none" | "teal" | "alert";
  dim?: number;
  style?: React.CSSProperties;
  children?: React.ReactNode;
}> = ({ w = 200, h = 270, date, title, seed, tone = "none", dim = 0, style, children }) => {
  const s = w / 200;
  const lines = Array.from({ length: 9 }, (_, i) => 0.45 + rand(seed * 31 + i) * 0.5);
  const ring = tone === "alert" ? C.alert : tone === "teal" ? C.tealMid : "transparent";
  return (
    <div
      style={{
        width: w,
        height: h,
        borderRadius: 12 * s,
        background: `linear-gradient(170deg, #faf7f1 0%, ${C.paper} 60%, #e8e1d4 100%)`,
        boxShadow: `0 ${24 * s}px ${50 * s}px rgba(0,0,0,0.45), 0 0 0 ${3 * s}px ${ring}, 0 0 ${40 * s}px ${tone === "none" ? "transparent" : ring}`,
        padding: 18 * s,
        boxSizing: "border-box",
        position: "relative",
        fontFamily: FONT,
        filter: dim ? `saturate(${1 - dim}) brightness(${1 - dim * 0.55})` : undefined,
        ...style,
      }}
    >
      <div style={{ fontFamily: MONO, fontSize: 13 * s, color: C.teal, fontWeight: 500, letterSpacing: "0.02em" }}>{dmy(date)}</div>
      <div style={{ fontSize: 15 * s, fontWeight: 700, color: C.paperInk, marginTop: 6 * s, lineHeight: 1.15, height: 36 * s }}>{title}</div>
      <div style={{ marginTop: 12 * s, display: "flex", flexDirection: "column", gap: 9 * s }}>
        {lines.map((l, i) => (
          <div key={i} style={{ height: 6 * s, width: `${l * 100}%`, background: "rgba(29,42,46,0.13)", borderRadius: 3 * s }} />
        ))}
      </div>
      {children}
    </div>
  );
};

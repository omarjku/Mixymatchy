import React from "react";
import { useCurrentFrame } from "remotion";
import { C, FONT } from "../theme";
import { spr } from "../lib";
import { Mark, Status } from "./Bits";

export const cardStatus = (c: any): Status => (c.status === "documented" ? c.trust || "consistent" : c.status);

/** Need cards from metrics.json: mark, label, first value. */
export const CardList: React.FC<{ cards: any[]; at: number; gap?: number; width: number; stagger?: number; size?: number }> = ({
  cards,
  at,
  gap = 12,
  width,
  stagger = 9,
  size = 1,
}) => {
  const f = useCurrentFrame();
  return (
    <div style={{ display: "flex", flexDirection: "column", gap, width }}>
      {cards.map((c, i) => {
        const s = spr(f, at + i * stagger, 130, 17);
        const st = cardStatus(c);
        const tone = st === "conflicting" ? C.alert : st === "stale" ? C.amber : st === "not_documented" ? C.faint : C.tealHi;
        return (
          <div
            key={c.need + i}
            style={{
              display: "flex",
              gap: 16 * size,
              alignItems: "flex-start",
              padding: `${16 * size}px ${20 * size}px`,
              borderRadius: 14 * size,
              background: "rgba(245,241,234,0.045)",
              border: `1px solid ${C.line}`,
              borderLeft: `3px solid ${tone}`,
              fontFamily: FONT,
              opacity: Math.min(1, s * 1.4),
              transform: `translateX(${(1 - s) * -40}px)`,
            }}
          >
            <div style={{ marginTop: 2 * size }}>
              <Mark status={st} size={26 * size} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div style={{ fontSize: 17 * size, fontWeight: 600, color: C.muted, letterSpacing: "0.02em", textTransform: "uppercase" }}>{c.label}</div>
              <div style={{ fontSize: 25 * size, fontWeight: 500, color: st === "not_documented" ? C.muted : C.ink, marginTop: 4 * size, fontStyle: st === "not_documented" ? "italic" : undefined }}>
                {c.value}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

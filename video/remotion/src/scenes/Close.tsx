import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { SB } from "../data";
import { C, FONT } from "../theme";
import { spr, tween } from "../lib";
import { Words } from "../components/Text";

/** Lens mark: a ring that draws itself, with a check inside. */
export const Logo: React.FC<{ at: number; size?: number }> = ({ at, size = 150 }) => {
  const f = useCurrentFrame();
  const d = tween(f, at, 40);
  const c = tween(f, at + 22, 26);
  const s = spr(f, at, 90, 14);
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" style={{ transform: `scale(${0.8 + 0.2 * s})`, overflow: "visible" }}>
      <circle cx={46} cy={46} r={32} fill="rgba(15,118,110,.18)" stroke={C.tealHi} strokeWidth={6} pathLength={1} strokeDasharray={1} strokeDashoffset={1 - d} transform="rotate(-90 46 46)" />
      <path d="M69 69 L88 88" stroke={C.tealHi} strokeWidth={8} strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - c} />
      <path d="M32 47 L42 57 L61 37" stroke={C.ink} strokeWidth={6} strokeLinecap="round" strokeLinejoin="round" fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - c} />
    </svg>
  );
};

export const Close: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const fade = interpolate(f, [dur - 26, dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const glow = tween(f, 10, 60);
  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ background: `radial-gradient(700px 400px at 50% 46%, rgba(15,118,110,${0.35 * glow}), transparent 70%)` }} />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 36 }}>
          <Logo at={6} size={160} />
          <Words text={SB.title} at={18} size={140} stagger={5} tracking={-0.045} />
        </div>
        <div style={{ width: 1300, textAlign: "center", marginTop: 46 }}>
          <Words text={SB.tagline} at={56} size={38} weight={500} color={C.ink2} stagger={2} accent={["checks"]} tracking={-0.01} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ background: "#000", opacity: fade }} data-intentional-fade="1" />
    </AbsoluteFill>
  );
};

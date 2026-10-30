import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C } from "../theme";

/** Persistent backdrop: slate gradient, drifting teal light, a perspective grid floor, vignette and grain. */
export const Background: React.FC<{ warm: number }> = ({ warm }) => {
  const f = useCurrentFrame();
  const gx = 30 + Math.sin(f / 170) * 8;
  const gy = 28 + Math.cos(f / 210) * 6;
  const hx = 74 + Math.cos(f / 190) * 7;
  const hy = 78 + Math.sin(f / 230) * 5;
  const gridShift = (f * 0.45) % 80;
  return (
    <AbsoluteFill style={{ background: `linear-gradient(160deg, ${C.bg2} 0%, ${C.bg} 55%, #060b0d 100%)` }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(900px 620px at ${gx}% ${gy}%, rgba(15,118,110,${0.32 - warm * 0.12}), transparent 70%),
            radial-gradient(760px 560px at ${hx}% ${hy}%, rgba(20,163,148,0.14), transparent 70%),
            radial-gradient(700px 500px at 70% 30%, rgba(240,103,106,${warm * 0.16}), transparent 70%)`,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: -600,
          right: -600,
          top: 560,
          height: 900,
          transform: "perspective(900px) rotateX(64deg)",
          transformOrigin: "50% 0%",
          backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
          backgroundPosition: `0 ${gridShift}px`,
          maskImage: "linear-gradient(to bottom, transparent 0%, black 30%, transparent 85%)",
          WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 30%, transparent 85%)",
          opacity: interpolate(warm, [0, 1], [0.55, 0.35]),
        }}
      />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, transparent 45%, rgba(0,0,0,0.55) 100%)" }} />
      <AbsoluteFill style={{ opacity: 0.07, mixBlendMode: "overlay" }}>
        <svg width="100%" height="100%">
          <filter id="grain">
            <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" seed={3} stitchTiles="stitch" />
          </filter>
          <rect width="100%" height="100%" filter="url(#grain)" />
        </svg>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { M } from "../data";
import { C, FONT, MONO } from "../theme";
import { spr, tween } from "../lib";
import { Kicker, Words } from "../components/Text";
import { Glass } from "../components/Bits";

const NW = 300;
const GAPX = 50;
const NY = 400;
const NH = 190;

export const How: React.FC<{ dur: number }> = () => {
  const f = useCurrentFrame();
  const F = M.facts;
  const nodes = [
    { big: `${M.documents.length}`, unit: "letters", sub: "German clinical documents, read as they are" },
    { big: `${F.passages}`, unit: "passages", sub: "sentences with exact character offsets" },
    { big: `${F.total}`, unit: "facts", sub: "each quotes its sentence word for word" },
    { big: `${F.verified_at_load}`, unit: "verified", sub: `re-checked at every load · ${F.dropped_at_load + F.dropped_at_build} dropped` },
    { big: "1", unit: "screen", sub: "role → task → needs, from the rulebook" },
  ];
  const left0 = (1920 - (nodes.length * NW + (nodes.length - 1) * GAPX)) / 2;
  const nx = (i: number) => left0 + i * (NW + GAPX);
  const at = (i: number) => 40 + i * 26;
  const principles = [
    { t: "Nothing made up", d: "A fact without its source sentence never reaches the screen." },
    { t: "Rules where rules suffice", d: `${F.rule} facts from deterministic rules · ${Math.round(M.latency.median_ms)} ms per screen` },
    { t: "Built on IBM MLA and IPS", d: `${F.ibm} facts found via the MLA output, re-anchored to the letters · IPS sections` },
  ];
  return (
    <AbsoluteFill>
      <div style={{ position: "absolute", left: 120, top: 100 }}>
        <Kicker text="How it works" at={0} />
        <div style={{ height: 24 }} />
        <Words text="AI points. Code verifies." at={6} size={76} accent={["verifies."]} />
      </div>

      {/* AI lane */}
      <div style={{ position: "absolute", left: nx(4) + NW - (NW + 80), top: 236, width: NW + 80, opacity: tween(f, 170, 20), transform: `translateY(${(1 - tween(f, 170, 26)) * -20}px)` }}>
        <div style={{ border: `1.5px dashed rgba(94,234,212,.55)`, borderRadius: 14, padding: "12px 16px", fontFamily: FONT, fontSize: 19, color: C.ink2, lineHeight: 1.35, background: "rgba(15,118,110,.12)" }}>
          <span style={{ fontFamily: MONO, color: C.tealHi, fontSize: 15, letterSpacing: "0.14em" }}>AI · OPTIONAL</span>
          <br />
          reads unusual wording, may only pick rulebook IDs
        </div>
      </div>

      <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
        {nodes.slice(0, -1).map((_, i) => {
          const x1 = nx(i) + NW;
          const x2 = nx(i + 1);
          const y = NY + NH / 2;
          const d = tween(f, at(i) + 14, 22);
          const dot = (f - at(i) - 30) / 40;
          const dp = dot - Math.floor(dot);
          return (
            <g key={i}>
              <line x1={x1} y1={y} x2={x1 + (x2 - x1) * d} y2={y} stroke={C.tealMid} strokeWidth={3} />
              {d >= 1 && <circle cx={x1 + (x2 - x1) * dp} cy={y} r={5} fill={C.tealHi} />}
              <path d={`M ${x2 - 10} ${y - 8} L ${x2} ${y} L ${x2 - 10} ${y + 8}`} stroke={C.tealMid} strokeWidth={3} fill="none" opacity={d >= 1 ? 1 : 0} />
            </g>
          );
        })}
        <line x1={nx(4) + NW / 2 - 40} y1={326} x2={nx(4) + NW / 2 - 40} y2={326 + (NY - 326) * tween(f, 186, 16)} stroke={C.tealHi} strokeWidth={2} strokeDasharray="6 6" />
      </svg>

      {nodes.map((n, i) => {
        const s = spr(f, at(i), 120, 16);
        const verify = i === 3;
        return (
          <div key={i} style={{ position: "absolute", left: nx(i), top: NY, width: NW, height: NH, opacity: Math.min(1, s * 1.5), transform: `translateY(${(1 - s) * 40}px) scale(${0.92 + 0.08 * s})` }}>
            <Glass style={{ height: "100%", boxSizing: "border-box", padding: "22px 24px", border: `1px solid ${verify ? "rgba(94,234,212,.55)" : C.line2}`, boxShadow: verify ? "0 0 50px rgba(20,163,148,.25), 0 30px 80px rgba(0,0,0,.45)" : undefined }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                <div style={{ fontSize: 56, fontWeight: 800, letterSpacing: "-0.04em", color: verify ? C.tealHi : C.ink }}>{n.big}</div>
                <div style={{ fontSize: 24, fontWeight: 600, color: C.ink2 }}>{n.unit}</div>
              </div>
              <div style={{ fontSize: 19, color: C.muted, marginTop: 8, lineHeight: 1.35 }}>{n.sub}</div>
            </Glass>
          </div>
        );
      })}

      <div style={{ position: "absolute", left: left0, top: 690, width: 1920 - 2 * left0, display: "flex", gap: 28 }}>
        {principles.map((p, i) => {
          const s = spr(f, 230 + i * 22, 120, 17);
          return (
            <div key={p.t} style={{ flex: 1, opacity: Math.min(1, s * 1.4), transform: `translateY(${(1 - s) * 30}px)` }}>
              <div style={{ height: 3, width: 56 * s, background: i === 0 ? C.tealHi : C.tealMid, borderRadius: 2 }} />
              <div style={{ fontFamily: FONT, fontSize: 34, fontWeight: 700, marginTop: 18, letterSpacing: "-0.02em", color: C.ink }}>{p.t}</div>
              <div style={{ fontFamily: FONT, fontSize: 22, color: C.muted, marginTop: 10, lineHeight: 1.4 }}>{p.d}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

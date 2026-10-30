import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { M } from "../data";
import { C, FONT, MONO } from "../theme";
import { dmy, spr, tween } from "../lib";
import { LetterCard } from "../components/Letter";
import { Kicker, Words, Count } from "../components/Text";

const CW = 192;
const CH = 262;
const GAP = 20;

const SidePill: React.FC<{ side: string; alert?: boolean; s: number; shake?: number }> = ({ side, alert, s, shake = 0 }) => (
  <div
    style={{
      display: "inline-block",
      padding: "6px 14px",
      borderRadius: 8,
      fontFamily: MONO,
      fontWeight: 600,
      fontSize: 20,
      letterSpacing: "0.08em",
      color: alert ? "#fff" : C.ink,
      background: alert ? C.alert : C.teal,
      boxShadow: alert ? `0 0 30px ${C.alert}` : `0 8px 24px rgba(15,118,110,0.5)`,
      transform: `scale(${s}) translateX(${shake}px)`,
      textTransform: "uppercase",
    }}
  >
    {side}
  </div>
);

export const Problem: React.FC<{ dur: number }> = () => {
  const f = useCurrentFrame();
  const docs: any[] = M.documents;
  const chain: any[] = M.carotid_chain;
  const cc = M.carotid_counts;
  const W = M.weight;
  const left0 = (1920 - (docs.length * CW + (docs.length - 1) * GAP)) / 2;
  const cx = (i: number) => left0 + i * (CW + GAP) + CW / 2;
  const idx = (docId: string) => docs.findIndex((d) => d.id === docId);

  // the carotid side travels from letter to letter
  const stops = chain.filter((c) => c.side).map((c) => ({ ...c, i: idx(c.doc_id) }));
  const HOP0 = 64;
  const HOP = 34;
  const arrive = (k: number) => HOP0 + k * HOP;
  const conflictK = stops.findIndex((s) => s.conflict_side);
  const tConflict = conflictK >= 0 ? arrive(conflictK) + 10 : 9999;
  const lastStop = stops.length ? stops[stops.length - 1] : null;
  const absentAt = (lastStop ? arrive(stops.length - 1) : 0) + 34;

  let tokX = stops.length ? cx(stops[0].i) : 0;
  let tokY = 0;
  for (let k = 1; k < stops.length; k++) {
    const t = tween(f, arrive(k - 1) + 6, HOP - 6);
    if (t > 0) {
      tokX = cx(stops[k - 1].i) + (cx(stops[k].i) - cx(stops[k - 1].i)) * t;
      tokY = -Math.sin(Math.PI * t) * 110;
    }
  }
  const tokIn = spr(f, HOP0 - 14, 160, 14);
  const exitA = tween(f, 226, 18);
  const conflictS = spr(f, tConflict, 200, 10);
  const shake = f > tConflict && f < tConflict + 18 ? Math.sin((f - tConflict) * 2.4) * (18 - (f - tConflict)) * 0.8 : 0;

  // part B: the weight change no letter states
  const bIn = 248;
  const months = /over (\d+) months/.exec(W?.computed?.value ?? "")?.[1];
  const drawLine = tween(f, bIn + 40, 50);
  return (
    <AbsoluteFill>
      <div style={{ opacity: 1 - exitA, transform: `translateY(${-exitA * 40}px)` }}>
        <div style={{ position: "absolute", left: 140, top: 110 }}>
          <Kicker text="The problem" at={0} />
          <div style={{ height: 26 }} />
          <Words text="Letters copy each other. Errors travel." at={6} size={66} accent={["travel."]} accentColor={C.alert} />
        </div>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          {stops.slice(1).map((st, k) => {
            const a = stops[k];
            const x1 = cx(a.i);
            const x2 = cx(st.i);
            const y = 440 - 14;
            const t = tween(f, arrive(k) + 6, HOP - 6);
            const bad = st.conflict_side && f >= tConflict;
            return (
              <path key={k} d={`M ${x1} ${y} Q ${(x1 + x2) / 2} ${y - 120} ${x2} ${y}`} stroke={bad ? C.alert : C.tealMid} strokeWidth={3} fill="none" strokeDasharray="2 10" strokeLinecap="round" opacity={0.9 * t} />
            );
          })}
        </svg>
        <div style={{ position: "absolute", left: 140, top: 300, fontFamily: MONO, fontSize: 20, letterSpacing: "0.12em", color: C.muted, opacity: tween(f, HOP0 - 10, 20) }}>
          FOLLOWING ONE FACT · CAROTID STENOSIS SIDE
        </div>
        {docs.map((d, i) => {
          const s = spr(f, 8 + i * 4, 110, 16);
          const stopK = stops.findIndex((st) => st.i === i);
          const reached = stopK >= 0 && f >= arrive(stopK);
          const isConflict = stopK >= 0 && stops[stopK].conflict_side && f >= tConflict;
          const later = lastStop && i > lastStop.i;
          const dim = later ? tween(f, absentAt, 20) * 0.6 : stopK < 0 ? 0.35 * tween(f, HOP0, 20) : 0;
          return (
            <div key={d.id} style={{ position: "absolute", left: cx(i) - CW / 2, top: 440 + (1 - s) * 300, opacity: Math.min(1, s * 1.6) }}>
              <LetterCard w={CW} h={CH} date={d.date} title={d.title_en} seed={i + 1} tone={isConflict ? "alert" : reached ? "teal" : "none"} dim={dim}>
                {reached && (
                  <div style={{ position: "absolute", left: 14, bottom: 14, display: "flex", gap: 6 }}>
                    <SidePill side={stops[stopK].side} s={spr(f, arrive(stopK), 220, 14)} />
                    {isConflict && <SidePill side={stops[stopK].conflict_side} alert s={conflictS} shake={shake} />}
                  </div>
                )}
                {later && f > absentAt && (
                  <div style={{ position: "absolute", left: 14, bottom: 18, fontFamily: FONT, fontSize: 15, fontWeight: 600, color: C.paperInk, opacity: 0.55 * tween(f, absentAt, 16) }}>
                    not mentioned
                  </div>
                )}
              </LetterCard>
            </div>
          );
        })}
        {stops.length > 0 && f < arrive(stops.length - 1) + 4 && (
          <div style={{ position: "absolute", left: tokX - 40, top: 440 + CH - 58 + tokY, opacity: tokIn, filter: "drop-shadow(0 10px 20px rgba(0,0,0,.5))" }}>
            <SidePill side={stops[0].side} s={tokIn} />
          </div>
        )}
        <div style={{ position: "absolute", left: 140, top: 780, width: 1640, fontFamily: FONT, fontSize: 32, color: C.ink2, opacity: tween(f, tConflict + 10, 20) }}>
          Carotid stenosis, {dmy(stops[conflictK]?.date)}: <span style={{ color: C.alert, fontWeight: 700 }}>{cc?.odd} passage says {cc?.odd_side}</span>,{" "}
          <span style={{ color: C.tealHi, fontWeight: 700 }}>{cc?.main} say {cc?.main_side}</span>.
          <span style={{ color: C.muted, opacity: tween(f, absentAt + 6, 20) }}> The newer letters drop it entirely.</span>
        </div>
      </div>

      {/* Part B */}
      {f >= bIn - 2 && W?.from_kg && (
        <>
          <div style={{ position: "absolute", left: 140, top: 110 }}>
            <Kicker text="Facts vanish" at={bIn} color={C.amber} />
            <div style={{ height: 26 }} />
            <Words text="A weight loss no letter mentions." at={bIn + 6} size={66} accent={["no"]} accentColor={C.amber} />
          </div>
          <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
            <defs>
              <linearGradient id="wl" x1="0" x2="1">
                <stop offset="0" stopColor={C.tealHi} />
                <stop offset="1" stopColor={C.amber} />
              </linearGradient>
            </defs>
            <path d="M 420 470 C 760 470, 1100 690, 1500 690" stroke="url(#wl)" strokeWidth={5} fill="none" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - drawLine} />
            <circle cx={420} cy={470} r={14 * spr(f, bIn + 30, 200, 14)} fill={C.tealHi} />
            <circle cx={1500} cy={690} r={14 * spr(f, bIn + 86, 200, 14)} fill={C.amber} />
          </svg>
          {[
            { x: 420, y: 470, kg: W.from_kg, d: W.from_date, at: bIn + 30, col: C.tealHi, up: true },
            { x: 1500, y: 690, kg: W.to_kg, d: W.to_date, at: bIn + 86, col: C.amber, up: false },
          ].map((p, i) => {
            const s = spr(f, p.at, 130, 16);
            return (
              <div key={i} style={{ position: "absolute", left: p.x - 150, top: p.up ? p.y - 150 : p.y + 34, width: 300, textAlign: "center", fontFamily: FONT, opacity: s, transform: `translateY(${(1 - s) * 20}px)` }}>
                <div style={{ fontSize: 76, fontWeight: 700, color: C.ink, letterSpacing: "-0.03em" }}>{p.kg} kg</div>
                <div style={{ fontFamily: MONO, fontSize: 22, color: C.muted }}>{dmy(p.d)}</div>
              </div>
            );
          })}
          <div style={{ position: "absolute", left: 760, top: 360, width: 480, textAlign: "center", fontFamily: FONT, opacity: tween(f, bIn + 100, 20) }}>
            <div style={{ fontSize: 150, fontWeight: 800, color: C.amber, letterSpacing: "-0.05em", lineHeight: 1 }}>
              <Count to={Math.abs(W.delta_kg)} at={bIn + 100} dur={36} prefix="−" />
              <span style={{ fontSize: 64 }}> kg</span>
            </div>
          </div>
          <div style={{ position: "absolute", left: 140, top: 860, width: 1640, fontFamily: FONT, fontSize: 30, color: C.ink2, opacity: tween(f, bIn + 124, 20) }}>
            {W.pct}%{months ? ` in ${months} months` : ""}. Stated in none of the letters,{" "}
            <span style={{ color: C.tealHi, fontWeight: 600 }}>computed by Second Eye from two documented weights.</span>
          </div>
        </>
      )}
    </AbsoluteFill>
  );
};

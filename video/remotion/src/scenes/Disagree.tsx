import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { M } from "../data";
import { C, FONT, MONO } from "../theme";
import { dmy, spr, tween } from "../lib";
import { Kicker, Words, Count } from "../components/Text";
import { Mark } from "../components/Bits";

const ROW0 = 168;
const RH = 150;
const LX = 760;
const RX = 1340;
const PW = 440;

const Claim: React.FC<{ c: any; s: number; side: "l" | "r"; alert?: boolean }> = ({ c, s, side, alert }) => (
  <div
    style={{
      width: PW,
      padding: "14px 20px",
      boxSizing: "border-box",
      borderRadius: 14,
      background: alert ? "rgba(240,103,106,0.10)" : "rgba(245,241,234,0.05)",
      border: `1px solid ${alert ? "rgba(240,103,106,.45)" : C.line2}`,
      fontFamily: FONT,
      opacity: Math.min(1, s * 1.4),
      transform: `translateX(${(1 - s) * (side === "l" ? -50 : 50)}px)`,
    }}
  >
    <div style={{ fontFamily: MONO, fontSize: 15, color: C.muted }}>letter of {dmy(c.date)}</div>
    <div style={{ fontSize: 25, fontWeight: 600, color: C.ink, marginTop: 4, whiteSpace: "nowrap" }}>{c.text}</div>
  </div>
);

export const Disagree: React.FC<{ dur: number }> = () => {
  const f = useCurrentFrame();
  const list: any[] = M.contradictions.list;
  const PB = 270;
  const exitA = tween(f, PB - 18, 18);
  const at = (i: number) => 40 + i * 30;
  const shown = list.filter((_, i) => f >= at(i) + 8).length;
  const bs = M.blind_spot;
  const fu = M.followups;
  const ringT = tween(f, PB + 30, 50);
  const R = 150;
  const circ = 2 * Math.PI * R;
  return (
    <AbsoluteFill>
      <div style={{ opacity: 1 - exitA, transform: `translateY(${-exitA * 30}px)` }}>
        <div style={{ position: "absolute", left: 120, top: 150, width: 560 }}>
          <Kicker text="The record disagrees" at={0} color={C.alert} />
          <div style={{ fontFamily: FONT, fontSize: 260, fontWeight: 800, color: C.alert, letterSpacing: "-0.06em", lineHeight: 1, marginTop: 30, fontVariantNumeric: "tabular-nums" }}>
            {shown}
          </div>
          <Words text="contradictions, each shown with both passages." at={20} size={44} weight={600} />
          <div style={{ marginTop: 34, fontFamily: FONT, fontSize: 23, color: C.muted, opacity: tween(f, 210, 20), lineHeight: 1.4 }}>
            + {M.contradictions.notes} documentation notes (typo, case number, side to check), shown apart and not counted.
          </div>
        </div>
        <svg width={1920} height={1080} style={{ position: "absolute", inset: 0 }}>
          {list.map((c, i) => {
            const y = ROW0 + i * RH + 30 + 46;
            const d = tween(f, at(i) + 10, 22);
            return (
              <path key={c.id} d={`M ${LX + PW} ${y} C ${LX + PW + 50} ${y - 34}, ${RX - 50} ${y - 34}, ${RX} ${y}`} stroke={C.alert} strokeWidth={2.5} fill="none" pathLength={1} strokeDasharray={1} strokeDashoffset={1 - d} opacity={0.85} />
            );
          })}
        </svg>
        {list.map((c, i) => {
          const s = spr(f, at(i), 130, 17);
          const s2 = spr(f, at(i) + 8, 130, 17);
          const b = spr(f, at(i) + 22, 220, 12);
          const y = ROW0 + i * RH;
          return (
            <div key={c.id} style={{ position: "absolute", left: LX, top: y, width: RX + PW - LX }}>
              <div style={{ fontFamily: FONT, fontSize: 18, fontWeight: 600, letterSpacing: "0.08em", textTransform: "uppercase", color: C.ink2, opacity: s, height: 30 }}>{c.headline}</div>
              <div style={{ position: "relative", height: 92 }}>
                <div style={{ position: "absolute", left: 0, top: 0 }}>
                  <Claim c={c.left} s={s} side="l" alert={c.kind === "laterality"} />
                </div>
                <div style={{ position: "absolute", left: RX - LX, top: 0 }}>
                  <Claim c={c.right} s={s2} side="r" />
                </div>
                <div style={{ position: "absolute", left: (RX - LX + PW) / 2 - 22 + 0, top: 20, width: 44, height: 44, borderRadius: 22, background: C.alert, color: "#fff", display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT, fontWeight: 800, fontSize: 28, transform: `scale(${b})`, boxShadow: `0 0 26px rgba(240,103,106,.6)` }}>
                  ≠
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {f >= PB - 2 && (
        <>
          <div style={{ position: "absolute", left: 120, top: 120 }}>
            <Kicker text="What a reader would miss" at={PB} color={C.amber} />
            <div style={{ height: 24 }} />
            <Words text="Blind spots and open follow-ups." at={PB + 6} size={62} />
          </div>
          {/* blind spot ring */}
          <div style={{ position: "absolute", left: 140, top: 330, width: 820, display: "flex", gap: 50, alignItems: "center" }}>
            <svg width={340} height={340} style={{ flex: "none", transform: "rotate(-90deg)" }}>
              <circle cx={170} cy={170} r={R} stroke={C.line2} strokeWidth={18} fill="none" />
              <circle cx={170} cy={170} r={R} stroke={C.amber} strokeWidth={18} fill="none" strokeLinecap="round" strokeDasharray={`${circ * (bs.missed / bs.important) * ringT} ${circ}`} />
            </svg>
            <div style={{ position: "absolute", left: 0, top: 0, width: 340, height: 340, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", fontFamily: FONT }}>
              <div style={{ fontSize: 110, fontWeight: 800, color: C.ink, letterSpacing: "-0.05em", lineHeight: 1 }}>
                <Count to={bs.missed} at={PB + 30} dur={50} />
              </div>
              <div style={{ fontSize: 28, color: C.muted, marginTop: 6 }}>of {bs.important}</div>
            </div>
            <div style={{ fontFamily: FONT, width: 430 }}>
              <div style={{ fontSize: 32, fontWeight: 600, lineHeight: 1.25, opacity: tween(f, PB + 40, 20) }}>
                important facts are missing from the latest letter ({dmy(bs.latest_date)}).
              </div>
              <div style={{ marginTop: 22, display: "flex", flexDirection: "column", gap: 10 }}>
                {bs.examples.slice(0, 4).map((e: string, i: number) => (
                  <div key={e} style={{ fontSize: 22, color: C.ink2, opacity: tween(f, PB + 70 + i * 10, 16), transform: `translateX(${(1 - tween(f, PB + 70 + i * 10, 20)) * 20}px)` }}>
                    <span style={{ color: C.amber }}>—</span> {e}
                  </div>
                ))}
              </div>
            </div>
          </div>
          {/* follow-ups */}
          <div style={{ position: "absolute", left: 1080, top: 350, width: 720, fontFamily: FONT }}>
            <div style={{ display: "flex", gap: 14 }}>
              {Array.from({ length: fu.total }, (_, i) => {
                const open = i < fu.open;
                const s = spr(f, PB + 60 + i * 5, 200, 14);
                return <div key={i} style={{ width: 44, height: 44, borderRadius: 22, border: `4px solid ${open ? C.alert : C.tealMid}`, background: open ? "transparent" : "rgba(20,163,148,.35)", transform: `scale(${s})` }} />;
              })}
            </div>
            <div style={{ fontSize: 64, fontWeight: 800, marginTop: 28, letterSpacing: "-0.04em", opacity: tween(f, PB + 80, 20) }}>
              {fu.open} of {fu.total} <span style={{ fontSize: 34, fontWeight: 600, color: C.ink2, letterSpacing: "-0.01em" }}>follow-ups still open</span>
            </div>
            <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 12 }}>
              {fu.open_list.map((t: string, i: number) => (
                <div key={t} style={{ display: "flex", gap: 14, alignItems: "center", fontSize: 25, color: C.ink, opacity: tween(f, PB + 104 + i * 12, 16) }}>
                  <Mark status="not_documented" size={26} />
                  {t}
                </div>
              ))}
            </div>
            <div style={{ marginTop: 20, fontSize: 21, color: C.muted, opacity: tween(f, PB + 130, 16) }}>“nothing recorded after” the recommendation, with the source sentence</div>
          </div>
        </>
      )}
    </AbsoluteFill>
  );
};

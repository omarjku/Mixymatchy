import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { M, hasShot, shot } from "../data";
import { C, FONT, MONO } from "../theme";
import { spr, tween } from "../lib";
import { DeviceFrame, ShotView, projectBox } from "../components/Device";
import { CardList } from "../components/CardList";
import { Words } from "../components/Text";

const ORDER = ["anaesthetist", "surgeon", "emergency"];
const FOCUS: Record<string, string> = { anaesthetist: "blood_thinner", surgeon: "tumour", emergency: "carotid" };
const DW = 1040;
const DH = 690;

export const Switch: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const per = Math.floor(dur / ORDER.length);
  const k = Math.min(ORDER.length - 1, Math.floor(f / per));
  const tabX = ORDER.slice(1).reduce((acc, _r, j) => acc + spr(f, (j + 1) * per - 4, 160, 20), 0);
  const TABW = 300;
  return (
    <AbsoluteFill>
      {/* role tabs */}
      <div style={{ position: "absolute", left: (1920 - TABW * 3 - 12) / 2, top: 70, width: TABW * 3 + 12, height: 64, borderRadius: 32, background: "rgba(245,241,234,0.05)", border: `1px solid ${C.line2}`, padding: 6, boxSizing: "border-box", opacity: tween(f, 0, 16) }}>
        <div style={{ position: "absolute", top: 6, left: 6 + tabX * TABW, width: TABW, height: 50, borderRadius: 26, background: C.teal, boxShadow: "0 8px 30px rgba(15,118,110,.55)" }} />
        {ORDER.map((r, i) => (
          <div key={r} style={{ position: "absolute", top: 6, left: 6 + i * TABW, width: TABW, height: 50, display: "flex", alignItems: "center", justifyContent: "center", fontFamily: FONT, fontSize: 22, fontWeight: 600, color: i === k ? "#fff" : C.muted }}>
            {M.roles[r].title}
          </div>
        ))}
      </div>

      {ORDER.map((r, i) => {
        const R = M.roles[r];
        const start = i * per;
        const local = f - start;
        if (local < -20 || local > per + 20) return null;
        const inS = i === 0 ? spr(f, 0, 90, 18) : spr(f, start, 90, 18);
        const outS = i === ORDER.length - 1 ? 0 : spr(f, start + per - 2, 120, 20);
        const rot = (1 - inS) * 28 - outS * 28;
        const tx = (1 - inS) * 140 - outS * 140;
        const op = Math.min(1, inS * 1.3) * (1 - outS);
        const b = shot(r)?.boxes?.[FOCUS[r]];
        const cx = b ? b.x + b.w / 2 + 40 : 720;
        const cy0 = b ? b.y + b.h / 2 : 450;
        const zoom = 1.32 + local * 0.0012;
        const cy = cy0 - 60 + local * 0.5;
        const focus = R.focus;
        return (
          <React.Fragment key={r}>
            <div style={{ position: "absolute", left: 100, top: 190, perspective: 2200, opacity: op, filter: outS > 0.02 ? `blur(${outS * 10}px)` : undefined }}>
              <div style={{ transform: `rotateY(${rot}deg) translateX(${tx}px) scale(${0.94 + 0.06 * inS})`, transformOrigin: "50% 50%" }}>
                <DeviceFrame w={DW} h={DH}>
                  {hasShot(r) ? (
                    <>
                      <ShotView name={r} vw={DW} vh={DH - 46} cx={cx} cy={cy} zoom={zoom} />
                      {b && (() => {
                        const p = projectBox(r, b, DW, DH - 46, cx, cy, zoom);
                        const t = tween(f, start + 26, 18);
                        return (
                          <div style={{ position: "absolute", left: p.x - 12, top: p.y - 8, width: p.w + 24, height: p.h + 16, borderRadius: 12, border: `3px solid ${C.tealMid}`, boxShadow: "0 0 34px rgba(20,163,148,.45)", opacity: t, transform: `scale(${1.04 - 0.04 * t})` }} />
                        );
                      })()}
                    </>
                  ) : (
                    <div style={{ position: "absolute", inset: 0, background: C.panel, padding: 36 }}>
                      <CardList cards={focus} at={start + 6} width={DW - 72} />
                    </div>
                  )}
                </DeviceFrame>
              </div>
            </div>
            <div style={{ position: "absolute", left: 1200, top: 196, width: 620, opacity: 1 - outS }}>
              <div style={{ fontFamily: MONO, fontSize: 18, letterSpacing: "0.18em", color: C.tealHi, textTransform: "uppercase", opacity: tween(f, start + 4, 16) }}>
                {R.situation_title}
              </div>
              <div style={{ height: 14 }} />
              <Words text={R.title} at={start + 6} size={58} stagger={3} />
              <div style={{ fontFamily: FONT, fontSize: 24, color: C.muted, marginTop: 10, opacity: tween(f, start + 14, 16) }}>{R.task}</div>
              <div style={{ height: 26 }} />
              <CardList cards={focus} at={start + 16} width={620} gap={10} stagger={6} size={0.94} />
            </div>
          </React.Fragment>
        );
      })}
      <div style={{ position: "absolute", left: 100, top: 926, width: 1720, textAlign: "center", fontFamily: FONT, fontSize: 30, color: C.ink2, opacity: tween(f, 30, 20) }}>
        Same patient, same {M.documents.length} letters. <span style={{ color: C.tealHi, fontWeight: 600 }}>A different screen for every role.</span>
      </div>
    </AbsoluteFill>
  );
};

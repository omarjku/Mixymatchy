import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { M, hasShot, shot } from "../data";
import { C, FONT, MONO } from "../theme";
import { dmy, keys, spr, tween } from "../lib";
import { DeviceFrame, ShotView, projectBox } from "../components/Device";
import { Glass, Mark } from "../components/Bits";
import { Kicker, Words } from "../components/Text";
import { CardList } from "../components/CardList";

const DX = 700;
const DY = 150;
const DW = 1124;
const DH = 790;
const VW = DW;
const VH = DH - 46;

export const Screen: React.FC<{ dur: number }> = ({ dur }) => {
  const f = useCurrentFrame();
  const R = M.roles.anaesthetist;
  const src = M.source_click;
  const live = hasShot("anaesthetist") && hasShot("source");
  const SW = 262; // switch to the source view
  const A = shot("anaesthetist")?.boxes ?? {};
  const B = shot("source")?.boxes ?? {};
  const bt = A.blood_thinner ?? { x: 120, y: 690, w: 690, h: 65 };
  const lv = A.lvef ?? bt;
  const center = (b: any) => [b.x + b.w / 2, b.y + b.h / 2];
  const [btx, bty] = center(bt);
  const [, lvy] = center(lv);

  // camera on the full page
  const nd = A.not_documented ?? lv;
  const [, ndy] = center(nd);
  const cx = keys(f, [[0, 720], [40, 720], [92, btx], [250, btx]]);
  const cy = keys(f, [[0, 450], [40, 450], [92, bty - 60], [140, bty - 40], [190, Math.max(lvy, ndy) - 80], [222, Math.max(lvy, ndy) - 80], [250, bty]]);
  const zoom = keys(f, [[0, 1.0], [40, 1.0], [92, 1.9], [196, 1.95], [250, 2.05]]);

  // camera on the source view
  const mk = B.mark ?? { x: 877, y: 417, w: 425, h: 65 };
  const [mx, my] = center(mk);
  const sf = f - SW;
  const scx = keys(sf, [[0, 720], [20, 720], [80, mx - 20], [999, mx + 10]]);
  const scy = keys(sf, [[0, 450], [20, 450], [80, my], [999, my]]);
  const sz = keys(sf, [[0, 1.0], [20, 1.0], [80, 1.85], [999, 1.95]]);
  const swT = tween(f, SW, 18);

  // pointer: moves onto the blood-thinner "source" link and clicks
  const link = { x: bt.x + bt.w * 0.68, y: bt.y + bt.h * 0.72 };
  const lp = projectBox("anaesthetist", { ...link, w: 0, h: 0 }, VW, VH, cx, cy, zoom);
  const pT = tween(f, 214, 30);
  const px = interpolate(pT, [0, 1], [VW * 0.92, lp.x]);
  const py = interpolate(pT, [0, 1], [VH * 0.95, lp.y]);
  const click = interpolate(f, [248, 252, 260], [1, 0.8, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const ring = tween(f, 250, 16);

  const mb = projectBox("source", mk, VW, VH, scx, scy, sz);
  const glow = 0.5 + 0.5 * Math.sin(f / 8);

  const tilt = keys(f, [[0, -10], [60, -3], [dur, -1]]);
  const deviceIn = spr(f, 2, 70, 18);
  const listA = R.pick;

  return (
    <AbsoluteFill>
      {/* left column, part A */}
      <div style={{ position: "absolute", left: 120, top: 150, width: 520, opacity: 1 - tween(f, SW - 16, 16) }}>
        <Kicker text={`${R.title} · one screen`} at={4} />
        <div style={{ height: 26 }} />
        <Words text="Only the facts this task needs." at={10} size={62} accent={["this", "task"]} />
        <div style={{ height: 40 }} />
        <CardList cards={listA} at={60} gap={14} width={520} />
        <div style={{ marginTop: 26, fontFamily: MONO, fontSize: 19, color: C.muted, opacity: tween(f, 150, 20) }}>
          {R.cards_total} needs · {R.facts_shown} facts · each linked to its sentence
        </div>
      </div>

      {/* left column, part B */}
      {f > SW - 4 && (
        <div style={{ position: "absolute", left: 120, top: 150, width: 540 }}>
          <Kicker text="Proof for every fact" at={SW + 2} />
          <div style={{ height: 26 }} />
          <Words text="Click a fact. The original sentence lights up." at={SW + 8} size={54} accent={["lights", "up."]} />
          <div style={{ height: 36 }} />
          {src && (
            <>
              <Glass style={{ padding: "22px 26px", opacity: tween(f, SW + 60, 20), transform: `translateY(${(1 - tween(f, SW + 60, 26)) * 30}px)` }}>
                <div style={{ fontFamily: MONO, fontSize: 15, letterSpacing: "0.16em", color: C.muted, textTransform: "uppercase" }}>
                  German · {src.doc_title_en} · {dmy(src.doc_date)}
                </div>
                <div style={{ marginTop: 10, fontSize: 25, lineHeight: 1.4, color: C.ink2, fontStyle: "italic" }}>
                  <span style={{ backgroundImage: "linear-gradient(rgba(226,180,90,.38), rgba(226,180,90,.38))", backgroundSize: `${tween(f, SW + 80, 30) * 100}% 100%`, backgroundRepeat: "no-repeat", WebkitBoxDecorationBreak: "clone", boxDecorationBreak: "clone", padding: "0 4px", borderRadius: 4 }}>
                    “{src.quote_de}”
                  </span>
                </div>
              </Glass>
              <div style={{ display: "flex", alignItems: "center", gap: 12, margin: "14px 0 14px 26px", fontFamily: MONO, fontSize: 16, color: C.tealHi, opacity: tween(f, SW + 100, 16) }}>
                <svg width="18" height="26">
                  <path d="M9 0 V22 M3 16 L9 23 L15 16" stroke={C.tealHi} strokeWidth="2" fill="none" />
                </svg>
                ENGLISH ON SCREEN
              </div>
              <Glass style={{ padding: "22px 26px", border: `1px solid rgba(94,234,212,.4)`, opacity: tween(f, SW + 110, 20), transform: `translateY(${(1 - tween(f, SW + 110, 26)) * 30}px)` }}>
                <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
                  <Mark status="consistent" size={28} />
                  <div style={{ fontSize: 27, fontWeight: 600 }}>{src.label_en}</div>
                </div>
                <div style={{ marginTop: 8, marginLeft: 42, fontSize: 19, color: C.muted }}>
                  {src.need} · agrees across {src.letters_repeating} letters
                </div>
              </Glass>
            </>
          )}
        </div>
      )}

      {/* device */}
      <div style={{ position: "absolute", left: DX, top: DY, perspective: 2400 }}>
        <div style={{ transform: `rotateY(${tilt}deg) translateY(${(1 - deviceIn) * 120}px)`, opacity: deviceIn, transformOrigin: "0% 50%" }}>
          <DeviceFrame w={DW} h={DH}>
            {live ? (
              <>
                <div style={{ position: "absolute", inset: 0, opacity: 1 - swT }}>
                  <ShotView name="anaesthetist" vw={VW} vh={VH} cx={cx} cy={cy} zoom={zoom} />
                </div>
                <div style={{ position: "absolute", inset: 0, opacity: swT }}>
                  <ShotView name="source" vw={VW} vh={VH} cx={scx} cy={scy} zoom={sz} />
                  <div
                    style={{
                      position: "absolute",
                      left: mb.x - 10,
                      top: mb.y - 8,
                      width: mb.w + 20,
                      height: mb.h + 16,
                      borderRadius: 12,
                      border: `3px solid rgba(15,118,110,${0.6 + 0.4 * glow})`,
                      boxShadow: `0 0 ${20 + 20 * glow}px rgba(20,163,148,.55)`,
                      opacity: tween(f, SW + 70, 16),
                    }}
                  />
                </div>
                {f < SW + 4 && (
                  <div style={{ position: "absolute", left: px, top: py, opacity: tween(f, 210, 8) * (1 - swT) }}>
                    <div style={{ position: "absolute", left: -30, top: -30, width: 60, height: 60, borderRadius: 30, border: `3px solid ${C.teal}`, opacity: ring > 0 ? 1 - ring : 0, transform: `scale(${0.4 + ring})` }} />
                    <svg width="34" height="40" style={{ transform: `scale(${click})`, transformOrigin: "0 0", filter: "drop-shadow(0 4px 8px rgba(0,0,0,.4))" }}>
                      <path d="M2 2 L2 30 L10 23 L16 36 L21 34 L15 21 L26 21 Z" fill="#fff" stroke="#111" strokeWidth="2" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}
              </>
            ) : (
              <div style={{ position: "absolute", inset: 0, background: C.panel, padding: 40 }}>
                <CardList cards={[...R.shared, ...R.focus].slice(0, 8)} at={20} gap={12} width={VW - 80} />
              </div>
            )}
          </DeviceFrame>
        </div>
      </div>
    </AbsoluteFill>
  );
};

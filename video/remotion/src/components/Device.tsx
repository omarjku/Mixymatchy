import React from "react";
import { Img, staticFile } from "remotion";
import { C, FONT } from "../theme";
import { shot } from "../data";

/** Stylised browser window. */
export const DeviceFrame: React.FC<{ w: number; h: number; children: React.ReactNode; style?: React.CSSProperties; url?: string }> = ({
  w,
  h,
  children,
  style,
  url = "second-look · patient view",
}) => (
  <div
    style={{
      width: w,
      height: h,
      borderRadius: 22,
      background: "#0d171b",
      boxShadow: `0 60px 140px rgba(0,0,0,0.6), 0 0 0 1px ${C.line2}, inset 0 1px 0 rgba(255,255,255,0.06)`,
      overflow: "hidden",
      position: "relative",
      ...style,
    }}
  >
    <div style={{ height: 46, display: "flex", alignItems: "center", gap: 9, padding: "0 20px", borderBottom: `1px solid ${C.line}` }}>
      {["#3b4a4f", "#3b4a4f", "#3b4a4f"].map((c, i) => (
        <div key={i} style={{ width: 12, height: 12, borderRadius: 6, background: c }} />
      ))}
      <div
        style={{
          marginLeft: 24,
          flex: 1,
          maxWidth: 420,
          height: 26,
          borderRadius: 8,
          background: "rgba(255,255,255,0.05)",
          display: "flex",
          alignItems: "center",
          padding: "0 12px",
          fontFamily: FONT,
          fontSize: 13,
          color: C.muted,
          gap: 8,
        }}
      >
        <div style={{ width: 8, height: 8, borderRadius: 4, background: C.tealMid }} />
        {url}
      </div>
    </div>
    <div style={{ position: "absolute", top: 46, left: 0, right: 0, bottom: 0, overflow: "hidden", background: "#f8fafc" }}>{children}</div>
    <div
      style={{
        position: "absolute",
        inset: 0,
        background: "linear-gradient(115deg, rgba(255,255,255,0.07) 0%, transparent 28%, transparent 70%, rgba(255,255,255,0.03) 100%)",
        pointerEvents: "none",
      }}
    />
  </div>
);

/**
 * A captured screenshot seen through a camera. (cx, cy) is the focus point in page CSS pixels
 * (1440-wide capture); zoom 1 fits the page width to the viewport.
 */
export const ShotView: React.FC<{ name: string; vw: number; vh: number; cx: number; cy: number; zoom: number }> = ({ name, vw, vh, cx, cy, zoom }) => {
  const s = shot(name);
  if (!s) return null;
  const pageW = 1440;
  const pageH = s.size?.h ?? s.size?.height ?? 900;
  const scale = (vw / pageW) * zoom;
  let tx = vw / 2 - cx * scale;
  let ty = vh / 2 - cy * scale;
  tx = Math.min(0, Math.max(vw - pageW * scale, tx));
  ty = Math.min(0, Math.max(vh - pageH * scale, ty));
  return (
    <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
      <Img
        src={staticFile(`capture/${s.file}`)}
        style={{ position: "absolute", left: 0, top: 0, width: pageW * scale, height: pageH * scale, transform: `translate(${tx}px, ${ty}px)` }}
      />
    </div>
  );
};

/** Map a page-space box to viewport space using the same camera as ShotView. */
export const projectBox = (
  name: string,
  box: { x: number; y: number; w: number; h: number },
  vw: number,
  vh: number,
  cx: number,
  cy: number,
  zoom: number,
) => {
  const s = shot(name);
  const pageW = 1440;
  const pageH = s?.size?.h ?? s?.size?.height ?? 900;
  const scale = (vw / pageW) * zoom;
  let tx = vw / 2 - cx * scale;
  let ty = vh / 2 - cy * scale;
  tx = Math.min(0, Math.max(vw - pageW * scale, tx));
  ty = Math.min(0, Math.max(vh - pageH * scale, ty));
  return { x: box.x * scale + tx, y: box.y * scale + ty, w: box.w * scale, h: box.h * scale };
};

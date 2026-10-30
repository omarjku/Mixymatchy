import { Easing, interpolate, spring } from "remotion";

export const FPS = 30;
export const expoOut = Easing.bezier(0.16, 1, 0.3, 1);
export const inOut = Easing.bezier(0.65, 0, 0.35, 1);

/** 0 -> 1 over [start, start + dur] with an ease. */
export const tween = (frame: number, start: number, dur: number, ease = expoOut) =>
  interpolate(frame, [start, start + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: ease });

/** A soft spring that starts at `delay`. */
export const spr = (frame: number, delay = 0, stiff = 120, damping = 18, mass = 1) =>
  spring({ frame: frame - delay, fps: FPS, config: { stiffness: stiff, damping, mass } });

export const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
export const clamp01 = (t: number) => Math.max(0, Math.min(1, t));

/** '2015-06-28' -> '28.06.2015' (the letters are Austrian). */
export const dmy = (iso?: string | null) => {
  if (!iso) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : iso;
};

/** Deterministic pseudo-random in [0,1) from a seed. */
export const rand = (seed: number) => {
  const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

/** Piecewise camera keys: [[frame, value], ...] with ease-in-out between keys. */
export const keys = (frame: number, ks: [number, number][]) => {
  if (frame <= ks[0][0]) return ks[0][1];
  for (let i = 1; i < ks.length; i++) {
    const [f1, v1] = ks[i];
    const [f0, v0] = ks[i - 1];
    if (frame <= f1) {
      const t = (frame - f0) / Math.max(1, f1 - f0);
      const e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
      return v0 + (v1 - v0) * e;
    }
  }
  return ks[ks.length - 1][1];
};

export const NUM_WORDS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven", "Twelve"];

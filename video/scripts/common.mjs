// Shared helpers for render.mjs and check_visual.mjs.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const HERE = path.dirname(fileURLToPath(import.meta.url));
export const VIDEO = path.resolve(HERE, "..");
export const PROJECT = path.join(VIDEO, "remotion");
export const OUT = path.join(VIDEO, "out");
export const require = createRequire(path.join(PROJECT, "package.json"));

/** Copy metrics.json and the capture manifest into src/generated (read at bundle time). */
export function prepare() {
  const gen = path.join(PROJECT, "src", "generated");
  fs.mkdirSync(gen, { recursive: true });
  const metrics = path.join(VIDEO, "metrics.json");
  if (!fs.existsSync(metrics)) {
    console.error("video/metrics.json is missing. Run: python3 video/scripts/export_metrics.py");
    process.exit(2);
  }
  fs.copyFileSync(metrics, path.join(gen, "metrics.json"));
  const man = path.join(PROJECT, "public", "capture", "manifest.json");
  let caps = { available: false, shots: {} };
  if (fs.existsSync(man)) {
    const m = JSON.parse(fs.readFileSync(man, "utf8"));
    const ok = Object.values(m.shots || {}).every((s) => fs.existsSync(path.join(PROJECT, "public", "capture", s.file)));
    caps = { available: ok, ...m };
    if (!ok) caps.available = false;
  } else {
    console.warn("No app captures (video/remotion/public/capture). Screen scenes use the metrics-only fallback. Run: node video/scripts/capture_app.mjs");
  }
  fs.writeFileSync(path.join(gen, "captures.json"), JSON.stringify(caps, null, 1));
  return JSON.parse(fs.readFileSync(path.join(VIDEO, "storyboard.json"), "utf8"));
}

/** Remotion downloads its own headless shell; when that is blocked, fall back to a local Chromium. */
export function browserExecutable() {
  if (process.env.REMOTION_BROWSER) return process.env.REMOTION_BROWSER;
  const cands = [
    "/opt/pw-browsers/chromium_headless_shell-1243/chrome-headless-shell-linux64/chrome-headless-shell",
    "/opt/pw-browsers/chromium-1243/chrome-linux64/chrome",
  ];
  const base = "/opt/pw-browsers";
  if (fs.existsSync(base)) {
    for (const d of fs.readdirSync(base)) {
      if (d.startsWith("chromium_headless_shell-")) cands.unshift(path.join(base, d, "chrome-headless-shell-linux64", "chrome-headless-shell"));
    }
  }
  return cands.find((c) => fs.existsSync(c)) ?? null;
}

export async function bundleProject() {
  const { bundle } = require("@remotion/bundler");
  return bundle({ entryPoint: path.join(PROJECT, "src", "index.ts"), publicDir: path.join(PROJECT, "public"), onProgress: () => {} });
}

/** Key frame per scene for stills: late enough that the scene has settled. Overridable here. */
export const STILL_AT = { hook: 0.85, problem: 0.45, ask: 0.9, screen: 0.88, switch: 0.6, disagree: 0.45, how: 0.85, results: 0.42, close: 0.6 };

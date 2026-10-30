// npm run stills  -> video/out/stills/NN-<scene>.png + video/out/contact_sheet.png
// npm run render  -> video/out/second-look.mp4 (muxes video/out/audio/mix.wav when it exists)
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { OUT, STILL_AT, browserExecutable, bundleProject, prepare, require } from "./common.mjs";

const mode = process.argv[2] || "stills";
const only = mode === "stills" ? process.argv[3] : undefined; // optional scene id for quick iteration
const sb = prepare();
const { renderStill, renderMedia, selectComposition } = require("@remotion/renderer");

const serveUrl = await bundleProject();
const browser = browserExecutable();
const common = { serveUrl, browserExecutable: browser, chromiumOptions: { gl: "angle" } };
const inputProps = { check: false };
const composition = await selectComposition({ ...common, id: "SecondLook", inputProps });
fs.mkdirSync(OUT, { recursive: true });

if (mode === "frame") {
  // node render.mjs frame <n> [<n> ...]  -> video/out/frames/f<n>.png (spot-check motion states)
  const dir = path.join(OUT, "frames");
  fs.mkdirSync(dir, { recursive: true });
  for (const n of process.argv.slice(3).map(Number)) {
    const out = path.join(dir, `f${String(n).padStart(4, "0")}.png`);
    await renderStill({ ...common, composition, frame: n, output: out, inputProps, imageFormat: "png" });
    console.log(`frame ${n} -> ${path.relative(process.cwd(), out)}`);
  }
} else if (mode === "stills") {
  const dir = path.join(OUT, "stills");
  fs.mkdirSync(dir, { recursive: true });
  const files = [];
  for (const [i, s] of sb.scenes.entries()) {
    if (only && s.id !== only) continue;
    const frame = Math.round((s.start + (s.end - s.start) * (STILL_AT[s.id] ?? 0.7)) * sb.fps);
    const out = path.join(dir, `${String(i + 1).padStart(2, "0")}-${s.id}.png`);
    await renderStill({ ...common, composition, frame, output: out, inputProps, imageFormat: "png" });
    files.push(out);
    console.log(`still ${s.id} @ frame ${frame} -> ${path.relative(process.cwd(), out)}`);
  }
  if (!only) {
    const sheet = path.join(OUT, "contact_sheet.png");
    const listed = fs.readdirSync(dir).filter((f) => f.endsWith(".png")).sort().map((f) => path.join(dir, f));
    const cols = 3;
    const rows = Math.ceil(listed.length / cols);
    execFileSync("ffmpeg", [
      "-y", "-loglevel", "error",
      ...listed.flatMap((f) => ["-i", f]),
      "-filter_complex",
      listed.map((_, i) => `[${i}:v]scale=640:360[s${i}]`).join(";") + ";" + listed.map((_, i) => `[s${i}]`).join("") + `xstack=inputs=${listed.length}:layout=` +
        listed.map((_, i) => `${(i % cols) * 640}_${Math.floor(i / cols) * 360}`).join("|") + `:fill=black[v]`,
      "-map", "[v]", "-frames:v", "1", sheet,
    ]);
    console.log(`contact sheet -> ${path.relative(process.cwd(), sheet)} (${cols}x${rows})`);
  }
} else {
  const silent = path.join(OUT, "second-look.silent.mp4");
  const final = path.join(OUT, "second-look.mp4");
  let last = -1;
  await renderMedia({
    ...common,
    composition,
    codec: "h264",
    crf: 17,
    pixelFormat: "yuv420p",
    outputLocation: silent,
    inputProps,
    concurrency: Number(process.env.CONCURRENCY || 4),
    onProgress: ({ progress }) => {
      const p = Math.floor(progress * 20);
      if (p !== last) {
        last = p;
        process.stdout.write(`render ${Math.round(progress * 100)}%\n`);
      }
    },
  });
  const mix = path.join(OUT, "audio", "mix.wav");
  if (fs.existsSync(mix)) {
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", silent, "-i", mix, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", String(composition.durationInFrames / composition.fps), final]);
    fs.rmSync(silent);
    console.log(`rendered with audio -> ${path.relative(process.cwd(), final)}`);
  } else {
    fs.renameSync(silent, final);
    console.log(`rendered (silent; no video/out/audio/mix.wav) -> ${path.relative(process.cwd(), final)}`);
  }
}

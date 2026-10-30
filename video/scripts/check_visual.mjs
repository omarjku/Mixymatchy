// Scene-level visual checks, so humans (and CI) can see right/wrong without watching the video.
//
//   npm run check            (from video/remotion)
//
// 1. layout: at several frames per scene, every visible text run must sit inside the 5% title-safe area and
//    must not be cut off by an overflow:hidden box (DOM bounds measured inside the real render, via
//    src/components/Probe.tsx and the browser console)
// 2. black frames: one frame per second (small render); none may be fully black except the intentional
//    fade at the very end of the "close" scene; if video/out/second-look.mp4 exists, ffmpeg blackdetect too
// 3. duration: composition length == storyboard, scenes contiguous, <= max_seconds; MP4 length if present
// Writes video/out/check_report.json; exits 1 on any failure.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { OUT, browserExecutable, bundleProject, prepare, require } from "./common.mjs";

const sb = prepare();
const { renderStill, selectComposition } = require("@remotion/renderer");
const serveUrl = await bundleProject();
const common = { serveUrl, browserExecutable: browserExecutable(), chromiumOptions: { gl: "angle" } };
const failures = [];
const report = { layout: [], black: [], duration: {} };

// 3. duration
const comp = await selectComposition({ ...common, id: "SecondLook", inputProps: { check: false } });
const last = sb.scenes[sb.scenes.length - 1];
const want = Math.round(last.end * sb.fps);
report.duration = { composition_frames: comp.durationInFrames, storyboard_frames: want, seconds: comp.durationInFrames / comp.fps };
if (comp.durationInFrames !== want) failures.push(`duration: composition ${comp.durationInFrames} frames != storyboard ${want}`);
if (last.end > sb.max_seconds) failures.push(`duration: ${last.end}s > max ${sb.max_seconds}s`);
if (comp.width !== sb.width || comp.height !== sb.height || comp.fps !== sb.fps) failures.push("composition size/fps differs from storyboard");
sb.scenes.forEach((s, i) => {
  if (i > 0 && sb.scenes[i - 1].end !== s.start) failures.push(`scenes not contiguous at ${s.id}`);
  if (!(s.end > s.start)) failures.push(`scene ${s.id} has no length`);
});
const mp4 = path.join(OUT, "second-look.mp4");
if (fs.existsSync(mp4)) {
  const d = parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", mp4]).toString());
  report.duration.mp4_seconds = d;
  if (Math.abs(d - want / sb.fps) > 0.1) failures.push(`mp4 duration ${d}s != ${want / sb.fps}s`);
}

// 1. layout
const checkComp = await selectComposition({ ...common, id: "SecondLook", inputProps: { check: true } });
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "slcheck-"));
for (const s of sb.scenes) {
  const fracs = [0.3, 0.55, 0.8, 0.93];
  for (const fr of fracs) {
    const frame = Math.round((s.start + (s.end - s.start) * fr) * sb.fps);
    let got = null;
    await renderStill({
      ...common,
      composition: checkComp,
      frame,
      inputProps: { check: true },
      output: path.join(tmp, "l.jpeg"),
      imageFormat: "jpeg",
      scale: 0.25,
      onBrowserLog: (log) => {
        if (log.text.startsWith("LAYOUT ")) got = JSON.parse(log.text.slice(7));
      },
    });
    if (!got) {
      failures.push(`layout: no probe result for ${s.id} @${frame}`);
      continue;
    }
    report.layout.push({ scene: s.id, frame, texts: got.texts, issues: got.issues });
    for (const is of got.issues) failures.push(`layout ${s.id} @${frame}: ${is.kind} "${is.text}"${is.box ? " " + JSON.stringify(is.box) : ""}`);
  }
  process.stdout.write(`layout ${s.id} ok\n`);
}

// 2. black frames (mean luma of a 1x1 downscale; 0..255)
const luma = (file) => {
  const r = spawnSync("ffmpeg", ["-loglevel", "error", "-i", file, "-vf", "scale=1:1:flags=area,format=gray", "-f", "rawvideo", "-"]);
  return r.stdout[0];
};
const closeScene = sb.scenes.find((s) => s.id === "close");
for (let sec = 0; sec * sb.fps < want; sec += 1) {
  const frame = Math.min(want - 1, sec * sb.fps + 15);
  const f = path.join(tmp, `b${sec}.png`);
  await renderStill({ ...common, composition: comp, frame, output: f, imageFormat: "png", scale: 0.1, inputProps: { check: false } });
  const y = luma(f);
  report.black.push({ frame, luma: y });
  const intentional = closeScene && frame >= closeScene.end * sb.fps - 26;
  if (y <= 3 && !intentional) failures.push(`black frame at ${frame} (${(frame / sb.fps).toFixed(1)} s), luma ${y}`);
}
if (fs.existsSync(mp4)) {
  const r = spawnSync("ffmpeg", ["-i", mp4, "-vf", "blackdetect=d=0.2:pix_th=0.04", "-an", "-f", "null", "-"]);
  const hits = [...r.stderr.toString().matchAll(/black_start:([\d.]+) black_end:([\d.]+)/g)].map((m) => [parseFloat(m[1]), parseFloat(m[2])]);
  report.mp4_black = hits;
  for (const [a] of hits) if (!closeScene || a < closeScene.end - 1.0) failures.push(`mp4 black segment from ${a}s`);
}
fs.rmSync(tmp, { recursive: true, force: true });

report.failures = failures;
fs.mkdirSync(OUT, { recursive: true });
fs.writeFileSync(path.join(OUT, "check_report.json"), JSON.stringify(report, null, 1));
const minL = Math.min(...report.black.map((b) => b.luma));
console.log(`\nduration ${report.duration.seconds}s · ${report.layout.length} layout probes · darkest sampled frame luma ${minL}`);
if (failures.length) {
  console.log(`FAIL (${failures.length}):\n  ` + failures.join("\n  "));
  process.exit(1);
}
console.log("PASS: text inside safe area, nothing clipped, no unintended black frames, duration matches storyboard");

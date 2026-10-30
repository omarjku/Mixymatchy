// Renders walkthrough.html frame by frame into a 1080x1920 30 fps MP4 (H.264), muxed with audio.wav if present.
//   node video/walkthrough/render.mjs                 -> video/out/walkthrough/second-eye-walkthrough.mp4
//   node video/walkthrough/render.mjs stills 2 7 12   -> PNG stills at those seconds (quick check)
import { createRequire } from "node:module";
import { spawn } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";

const require = createRequire(new URL("../../mobile/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const HERE = fileURLToPath(new URL(".", import.meta.url));
const OUT = process.env.OUT_DIR ?? fileURLToPath(new URL("../out/walkthrough/", import.meta.url));
const FPS = 30;
mkdirSync(OUT, { recursive: true });

const exe = process.env.CHROMIUM ?? "/opt/pw-browsers/chromium";
const browser = await chromium.launch(existsSync(exe) ? { executablePath: exe } : {});
const page = await browser.newPage({ viewport: { width: 432, height: 768 }, deviceScaleFactor: 2.5 });
await page.goto("file://" + HERE + "walkthrough.html");
await page.evaluate(() => document.fonts.ready);
const duration = await page.evaluate(() => window.DURATION);

try {
  if (process.argv[2] === "stills") {
    for (const s of process.argv.slice(3).map(Number)) {
      await page.evaluate((t) => window.render(t), s);
      await page.screenshot({ path: `${OUT}still-${String(s).padStart(5, "0")}.png` });
    }
  } else {
    const audio = OUT + "audio.wav";
    const args = ["-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-"];
    if (existsSync(audio)) args.push("-i", audio, "-c:a", "aac", "-b:a", "192k", "-shortest");
    args.push("-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", String(FPS),
      "-movflags", "+faststart", OUT + "second-eye-walkthrough.mp4");
    const ff = spawn("ffmpeg", args, { stdio: ["pipe", "inherit", "inherit"] });
    const total = Math.round(duration * FPS);
    for (let i = 0; i < total; i++) {
      await page.evaluate((t) => window.render(t), i / FPS);
      const png = await page.screenshot({ type: "png" });
      if (!ff.stdin.write(png)) await new Promise((r) => ff.stdin.once("drain", r));
      if (i % 150 === 0) console.log(`frame ${i}/${total}`);
    }
    ff.stdin.end();
    await new Promise((r, j) => ff.on("close", (c) => (c ? j(new Error("ffmpeg " + c)) : r())));
    console.log("wrote " + OUT + "second-eye-walkthrough.mp4");
  }
} finally {
  await browser.close();
}

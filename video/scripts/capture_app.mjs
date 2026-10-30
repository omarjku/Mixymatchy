// Capture the real Second Look app for the "screen" and "switch" scenes.
//
//   node video/scripts/capture_app.mjs [--root <checkout>] [--port 8765] [--no-build]
//
// 1. builds the static frontend (STATIC_EXPORT=1 NEXT_PUBLIC_API_URL="" -> frontend/out) unless --no-build
// 2. starts the real FastAPI backend with uvicorn, serving that export via STATIC_DIR (same as the Dockerfile)
// 3. drives it with Playwright (require('playwright'), chromium.launch()): anaesthetist (typed), source click,
//    surgeon, emergency physician. Writes 2x screenshots, a short WebM of the typing, and manifest.json with
//    the bounding boxes of the elements the video zooms into.
// Output: video/remotion/public/capture/ (git-ignored: the screenshots show patient-derived text).
import { spawn, execSync } from "node:child_process";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "..", "..");
const args = process.argv.slice(2);
const opt = (name, dflt) => {
  const i = args.indexOf(name);
  return i >= 0 ? args[i + 1] : dflt;
};
const ROOT = path.resolve(opt("--root", REPO)); // checkout whose backend we run
const PORT = Number(opt("--port", "8765"));
const OUT = path.join(REPO, "video", "remotion", "public", "capture");
const STATIC = path.join(REPO, "frontend", "out");
const BASE = `http://127.0.0.1:${PORT}`;

let playwright;
try {
  playwright = require("playwright");
} catch {
  // globally installed playwright (NODE_PATH is not honoured by ESM resolution)
  const g = execSync("npm root -g").toString().trim();
  playwright = require(path.join(g, "playwright"));
}

const SITUATION_ANAESTHETIST = "Anaesthetist, pre-operative check before quadrantectomy with IORT on 16 May 2016";

async function waitHealth() {
  for (let i = 0; i < 240; i++) {
    try {
      const r = await fetch(`${BASE}/health`);
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error("backend did not start");
}

async function box(page, locator) {
  const b = await locator.first().boundingBox().catch(() => null);
  if (!b) return null;
  const scroll = await page.evaluate(() => ({ x: window.scrollX, y: window.scrollY }));
  return { x: Math.round(b.x + scroll.x), y: Math.round(b.y + scroll.y), w: Math.round(b.width), h: Math.round(b.height) };
}

async function main() {
  if (!args.includes("--no-build")) {
    console.log("building static frontend…");
    execSync("npm run build", {
      cwd: path.join(REPO, "frontend"),
      stdio: "inherit",
      env: { ...process.env, STATIC_EXPORT: "1", NEXT_PUBLIC_API_URL: "" },
    });
  }
  fs.mkdirSync(OUT, { recursive: true });
  const server = spawn(
    "python3",
    ["-m", "uvicorn", "--app-dir", "backend", "app.main:app", "--port", String(PORT), "--log-level", "warning"],
    { cwd: ROOT, env: { ...process.env, STATIC_DIR: STATIC, SITE_PASSWORD: "" }, stdio: "inherit" },
  );
  const manifest = { viewport: { width: 1440, height: 900 }, scale: 2, shots: {} };
  let browser;
  try {
    await waitHealth();
    browser = await playwright.chromium.launch();
    const context = await browser.newContext({
      viewport: manifest.viewport,
      deviceScaleFactor: manifest.scale,
      recordVideo: { dir: path.join(OUT, "_video"), size: manifest.viewport },
    });
    const page = await context.newPage();
    await page.goto(BASE + "/", { waitUntil: "networkidle" });
    await page.addStyleTag({ content: "html{scroll-behavior:auto!important}" });
    await page.waitForTimeout(400);
    await page.screenshot({ path: path.join(OUT, "empty.png") });
    manifest.shots.empty = { file: "empty.png", full: false };

    // Anaesthetist: type the situation like a clinician would.
    const input = page.locator("input").first();
    await input.click();
    await input.pressSequentially(SITUATION_ANAESTHETIST, { delay: 35 });
    await page.waitForTimeout(250);
    await page.screenshot({ path: path.join(OUT, "typed.png") });
    manifest.shots.typed = { file: "typed.png", full: false };
    await page.keyboard.press("Enter");
    await page.locator("text=what you need").first().waitFor();
    await page.waitForTimeout(600);

    const needBlock = (label) =>
      page.locator("div.border-b", { has: page.locator("p.font-semibold", { hasText: label }) });
    const shoot = async (name, extra = {}) => {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.waitForTimeout(200);
      const boxes = {};
      for (const [k, loc] of Object.entries(extra)) boxes[k] = await box(page, loc);
      const size = await page.evaluate(() => ({ w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight }));
      // the top of the page is what the video shows; cap the height to keep the 2x image a sane size
      size.h = Math.min(size.h, 4200);
      await page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage: true, clip: { x: 0, y: 0, width: size.w, height: size.h } });
      manifest.shots[name] = { file: `${name}.png`, full: true, size, boxes };
    };

    await shoot("anaesthetist", {
      blood_thinner: needBlock(/Blood thinners|Antiplatelet|anticoagul/i),
      allergy: needBlock(/Allerg/i),
      lvef: needBlock(/LVEF|ejection fraction/i),
      not_documented: page.locator("text=Not documented").first(),
      blind_spot: page.locator("div.border-l-4").first(),
      needs: page.locator("div.rounded.bg-white.p-4").first(),
    });

    // Source click on the blood-thinner fact: the German sentence lights up in the source pane.
    const blk = needBlock(/Blood thinners|Antiplatelet|anticoagul/i).first();
    await blk.scrollIntoViewIfNeeded();
    await blk.locator("button", { hasText: "source" }).first().click();
    await page.locator("aside mark").first().waitFor();
    await page.waitForTimeout(900);
    const vp = async (name, extra = {}) => {
      const boxes = {};
      for (const [k, loc] of Object.entries(extra)) {
        const b = await loc.first().boundingBox().catch(() => null);
        boxes[k] = b && { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) };
      }
      await page.screenshot({ path: path.join(OUT, `${name}.png`) });
      manifest.shots[name] = { file: `${name}.png`, full: false, size: manifest.viewport, boxes };
    };
    await vp("source", { mark: page.locator("aside mark"), aside: page.locator("aside"), fact: blk });

    // Switch doctor, same patient.
    for (const [name, chip] of [
      ["surgeon", "Surgeon planning the operation"],
      ["emergency", "Emergency physician at night"],
    ]) {
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.locator("button", { hasText: chip.split(" ")[0] }).first().click();
      await page.waitForFunction(
        (want) => document.querySelector("p.text-xs.font-semibold.uppercase")?.textContent?.toLowerCase().includes(want),
        name === "surgeon" ? "surgeon" : "emergency",
      );
      await page.waitForTimeout(600);
      await shoot(name, {
        needs: page.locator("div.rounded.bg-white.p-4").first(),
        tumour: needBlock(/histology/i),
        carotid: needBlock(/Carotid/i),
        contrast: needBlock(/contrast/i),
        contradictions: page.locator("text=The record disagrees").first(),
      });
    }
    const video = page.video();
    await context.close();
    if (video) {
      const src = await video.path();
      fs.renameSync(src, path.join(OUT, "session.webm"));
      manifest.video = "session.webm";
    }
    fs.rmSync(path.join(OUT, "_video"), { recursive: true, force: true });
    manifest.captured_at = new Date().toISOString();
    fs.writeFileSync(path.join(OUT, "manifest.json"), JSON.stringify(manifest, null, 1));
    console.log(`captured ${Object.keys(manifest.shots).length} shots -> ${path.relative(REPO, OUT)}`);
  } finally {
    if (browser) await browser.close();
    server.kill("SIGTERM");
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

// Phone page heights of the 5 official situations (390x844); with SHOT_DIR also full-page screenshots.
// Not a test. Screenshots contain patient text: write them outside the repo, never commit them.
// E2E_BASE_URL=http://127.0.0.1:5181 SHOT_DIR=/tmp/shots node e2e/shots.mjs
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
const base = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5181";
const out = process.env.SHOT_DIR;
const prefix = process.env.SHOT_PREFIX ?? "keyfacts-case";
const md = readFileSync(new URL("../../cases/situations.md", import.meta.url), "utf8");
const parts = md.split(/\n## (\d+)\. /).slice(1);
const sits = [];
for (let i = 0; i < parts.length; i += 2) {
  const [title, ...rest] = parts[i + 1].split("\n");
  sits.push({ n: Number(parts[i]), text: `${title.trim()}. ${rest.join("\n").trim().split(/\n\n/)[0]}` });
}
const browser = await chromium.launch({ executablePath: "/opt/pw-browsers/chromium" });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
for (const s of sits) {
  await page.goto(base + "/", { waitUntil: "networkidle" });
  if (await page.locator("#sl-staff").isVisible().catch(() => false)) {
    await page.locator("#sl-staff").fill("dr.demo");
    await page.locator("#sl-pass").fill("SecondLook-demo-2026");
    await page.locator("#sl-pass").press("Enter");
    await page.locator(".sl-shell").waitFor({ state: "hidden" });
  }
  const box = page.locator("textarea, input").first();
  await box.fill(s.text);
  await box.press("Enter");
  await page.locator("[data-read-as]").waitFor({ timeout: 15000 });
  await page.waitForTimeout(800);
  const h = await page.evaluate(() => document.documentElement.scrollHeight);
  if (out) await page.screenshot({ path: `${out}/${prefix}${s.n}.png`, fullPage: true });
  console.log(`case ${s.n}: ${h}px`);
}
await browser.close();

import { expect, test } from "@playwright/test";
import { collapse, documentTexts, situations, submitSituation, trackErrors } from "./helpers";

// v2 router (docs/DECISIONS.md 23), run against a backend started with SECOND_LOOK_ROUTER=v2:
//   E2E_V2=1 E2E_BACKEND_URL=http://127.0.0.1:8012 E2E_BASE_URL=http://127.0.0.1:5182 npm run e2e -- v2.spec.ts
// One sentence first with numbered Source chips; every list behind "Show more"; different questions differ.
test.skip(process.env.E2E_V2 !== "1", "needs a backend with SECOND_LOOK_ROUTER=v2 (E2E_V2=1)");

const sentences = (s: string) => s.split(/(?<=[.!?])\s+(?=[A-Z])/).filter(Boolean).length;

test("one cited sentence first, no list until 'Show more'", async ({ page }) => {
  const errors = trackErrors(page);
  const s = situations()[0];
  await submitSituation(page, `${s.title}. ${s.description}`);
  const text = page.locator("[data-answer-text]");
  await expect(text).toBeVisible();
  expect(sentences(await text.innerText())).toBeLessThanOrEqual(2);
  await expect(page.locator("[data-answer-line]")).toHaveCount(0);
  await expect(page.locator("[data-key-facts]")).toHaveCount(0);
  expect(await page.locator("[data-source-chip]").count()).toBeGreaterThan(0);
  await page.locator("[data-show-more]").click();
  await expect(page.locator("[data-key-facts]")).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("a source chip opens the letter with the passage highlighted", async ({ page }) => {
  const docs = (await documentTexts()).map(collapse);
  await submitSituation(page, "GP, diabetes review");
  await page.locator("[data-source-chip]").first().click();
  const viewer = page.getByRole("dialog");
  await expect(viewer).toBeVisible();
  const active = viewer.locator("mark[data-active]");
  await expect(active).toBeInViewport();
  const marked = collapse(await active.innerText());
  expect(docs.some((d) => d.includes(marked))).toBe(true);
});

test("different questions give different sentences; contrast only where it matters", async ({ page }) => {
  const qs = ["Female doctor, Pap smear", "ED doctor, CT angiography with contrast tonight - anything to consider?",
    "GP, diabetes review", "Anaesthetist, pre-op check before knee surgery"];
  const seen: string[] = [];
  for (const q of qs) {
    await submitSituation(page, q);
    const t = await page.locator("[data-answer-text]").innerText();
    expect(seen).not.toContain(t);
    seen.push(t);
    expect(/contrast/i.test(t), `${q}: ${t}`).toBe(/contrast/i.test(q));
  }
});

test("normal clinical wording is answered (no block)", async ({ page }) => {
  await submitSituation(page, "Gynäkologin, Vorsorge");
  await expect(page.locator("[data-answer-text]")).toBeVisible();
  await expect(page.locator('[data-banner="needs_task"]')).toHaveCount(0);
});

test("'hi' gets the describe-your-task banner and nothing from the record", async ({ page }) => {
  await submitSituation(page, "hi");
  await expect(page.locator('[data-banner="needs_task"]')).toBeVisible();
  await expect(page.locator("[data-answer-text]")).toHaveCount(0);
});

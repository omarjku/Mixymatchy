import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  answerKeys,
  collapse,
  documentTexts,
  normalise,
  type RoleKey,
  situations,
  submitSituation,
  trackErrors,
  unseenSituations,
} from "./helpers";

// docs/FRONTEND.md §6. Role chip per case, as a clinician would pick it.
const ROLE_FOR: Record<number, RoleKey> = { 1: "anaesthetist", 2: "surgeon", 3: "gp", 4: "emergency", 5: "gp" };
const SPEED_LIMIT_MS = 2_000;
const keys = answerKeys();

for (const s of situations()) {
  test.describe(`situation ${s.n}: ${s.title}`, () => {
    test("expected answers are visible without clicking", async ({ page }) => {
      const errors = trackErrors(page);
      await submitSituation(page, ROLE_FOR[s.n], `${s.title}. ${s.description}`);
      const screen = normalise(await page.locator("main").innerText());
      const missing: string[] = [];
      for (const [qid, q] of Object.entries(keys).filter(([id]) => id.startsWith(`${s.n}.`))) {
        for (const item of q.items) {
          // every group needs one alternative on screen (date-only alternatives are checked by the eval harness)
          const absent = item.groups.filter((alts) => {
            const textual = alts.filter((a) => !a.startsWith("@date:"));
            return textual.length > 0 && !textual.some((a) => screen.includes(normalise(a)));
          });
          if (absent.length) missing.push(`${qid} ${item.name}: none of ${absent.map((g) => g.join("|")).join(" / ")}`);
        }
      }
      expect(missing, missing.join("\n")).toEqual([]);
      expect(errors, errors.join("\n")).toEqual([]);
    });

    test("source opens the original letter with the cited passage highlighted", async ({ page }) => {
      const docs = (await documentTexts()).map(collapse);
      await submitSituation(page, ROLE_FOR[s.n], `${s.title}. ${s.description}`);
      const buttons = page.locator("#facts-panel button[data-source]");
      const count = Math.min(await buttons.count(), 6);
      expect(count, "facts with a source link").toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        await buttons.nth(i).click();
        const viewer = page.getByRole("dialog");
        await expect(viewer).toBeVisible();
        // the full letter is shown, and the current passage is marked and scrolled into view
        const letter = viewer.locator("[data-letter]");
        await expect(letter).toBeVisible();
        const active = viewer.locator("mark[data-active]");
        await expect(active).toBeInViewport();
        const marked = collapse(await active.innerText());
        expect(marked.length).toBeGreaterThan(0);
        expect(docs.some((d) => d.includes(marked)), `not found verbatim in any document: "${marked}"`).toBe(true);
        expect(collapse(await letter.innerText()).length).toBeGreaterThan(marked.length);
        await page.keyboard.press("Escape");
        await expect(viewer).toBeHidden();
      }
    });

    test(`loads in under ${SPEED_LIMIT_MS} ms`, async ({ page }) => {
      const ms = await submitSituation(page, ROLE_FOR[s.n], `${s.title}. ${s.description}`);
      expect(ms).toBeLessThan(SPEED_LIMIT_MS);
    });
  });
}

test.describe("unseen situations (free text via 'Other role')", () => {
  for (const u of unseenSituations()) {
    test(`${u.id}: ${u.situation}`, async ({ page }) => {
      const errors = trackErrors(page);
      await submitSituation(page, "other", u.situation);
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }
});

test.describe("accessibility (axe, WCAG 2 A/AA)", () => {
  test("start screen", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });

  test("results screen", async ({ page }) => {
    const s = situations()[0];
    await submitSituation(page, "anaesthetist", `${s.title}. ${s.description}`);
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
});

test.describe("source viewer", () => {
  test("several passages: all highlighted, step between them", async ({ page }) => {
    await submitSituation(page, "anaesthetist", "Pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
    // the first fact with more than one passage
    const cards = page.locator("[data-fact]");
    let opened = false;
    for (let i = 0; i < (await cards.count()) && !opened; i++) {
      await cards.nth(i).locator("button[data-source]").first().click();
      const counter = page.locator("[data-passage-counter]");
      if (await counter.isVisible().catch(() => false)) {
        opened = true;
        await expect(counter).toHaveText(/1 (of|von) \d+/);
        expect(await page.locator("[data-source-viewer] mark").count()).toBeGreaterThan(0);
        const first = await page.locator("mark[data-active]").getAttribute("data-segment");
        await page.getByRole("button", { name: /Next passage|Nächste Stelle/ }).click();
        await expect(counter).toHaveText(/2 (of|von) \d+/);
        await expect(page.locator("mark[data-active]")).toBeInViewport();
        expect(await page.locator("mark[data-active]").getAttribute("data-segment")).not.toBe(first);
      } else {
        await page.keyboard.press("Escape");
      }
    }
    expect(opened, "a fact with several passages").toBe(true);
  });

  test("desktop: the letter opens in a side pane", async ({ page }) => {
    await page.setViewportSize({ width: 1366, height: 900 });
    await submitSituation(page, "anaesthetist", "Pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
    await page.locator("#facts-panel button[data-source]").first().click();
    const pane = page.locator("aside[data-source-viewer]");
    await expect(pane).toBeVisible();
    await expect(pane.locator("mark[data-active]")).toBeInViewport();
    await expect(page.locator("#facts-panel")).toBeVisible();
  });
});

test.describe("contradictions", () => {
  test("both passages side by side, each with a source link", async ({ page }) => {
    await submitSituation(page, "other", "Vascular surgeon reviewing the carotid stenosis before surgery");
    const lists = page.locator("ul[data-passages]");
    test.skip((await lists.count()) === 0, "no contradiction on this screen");
    const first = lists.first().locator("button[data-source]");
    expect(await first.count()).toBeGreaterThanOrEqual(2);
    const [a, b] = [await first.nth(0).boundingBox(), await first.nth(1).boundingBox()];
    expect(Math.abs((a?.y ?? 0) - (b?.y ?? 1))).toBeLessThan(2); // same row
    await first.nth(1).click();
    await expect(page.locator("mark[data-active]")).toBeInViewport();
  });
});

test.describe("language toggle", () => {
  test("English by default, German on toggle, back to English", async ({ page }) => {
    await submitSituation(page, "anaesthetist", "Pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
    await expect(page.getByRole("heading", { name: /^What you need/ })).toBeVisible();
    await page.getByRole("button", { name: /Language: English/ }).click();
    await expect(page.getByRole("heading", { name: /^Erforderliche Angaben/ })).toBeVisible();
    await expect(page.locator("[data-read-as]")).toContainText("Gelesen als");
    await page.getByRole("button", { name: /Sprache: Deutsch/ }).click();
    await expect(page.getByRole("heading", { name: /^What you need/ })).toBeVisible();
  });
});

test.describe("banners", () => {
  test("not authorised (firefighter): banner, suggestions, no patient facts", async ({ page }) => {
    await submitSituation(page, "other", "Firefighter checking the patient");
    await expect(page.locator('[data-banner="not_authorised"]')).toBeVisible();
    await expect(page.locator("[data-suggestions] button").first()).toBeVisible();
    await expect(page.locator("[data-fact]")).toHaveCount(0);
    await expect(page.locator("text=/Consistent across letters|Verified/")).toHaveCount(0);
  });

  test("no task, no data (chip Anaesthetist + 'hi'): banner, examples, nothing from the record", async ({ page }) => {
    await submitSituation(page, "anaesthetist", "hi");
    const banner = page.locator('[data-banner="needs_task"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/Please describe your task|Bitte beschreiben Sie Ihre Aufgabe/);
    await expect(banner.locator("[data-suggestions] button").first()).toBeVisible();
    await expect(page.locator("[data-patient-card]")).toHaveCount(0);
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await expect(page.locator("[data-fact]")).toHaveCount(0);
    await expect(page.locator("button[data-source]")).toHaveCount(0);
    await expect(page.locator('[data-banner="fallback"], [data-blind-spot], [data-other-issues]')).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(/Patientin|female|weiblich|\b(19|20)\d\d\b/);
    // an example re-runs as a real task
    await banner.locator("[data-suggestions] button").first().click();
    await expect(page.locator("[data-fact]").first()).toBeVisible({ timeout: 10_000 });
  });

  test("not applicable: banner with evidence, never counted as consistent", async ({ page }) => {
    await submitSituation(page, "other", "Urologist, prostate cancer screening");
    const banner = page.locator('[data-banner="not_applicable"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/female/);
    const na = page.locator('[data-fact][data-trust="not_applicable"]');
    await expect(na.first()).toContainText(/Not applicable/);
    await expect(na.first()).not.toContainText(/Consistent across letters|Verified/);
    await banner.locator("button[data-source]").click();
    await expect(page.locator("mark[data-active]")).toBeInViewport();
  });

  test("unknown role keeps its own label (never GP), unrecognised task offers suggestions", async ({ page }) => {
    await submitSituation(page, "other", "Rheumatologist reviewing joint pain");
    await expect(page.locator("[data-read-as]")).toContainText("Rheumatologist");
    await expect(page.locator("[data-read-as]")).not.toContainText(/\bGP\b|General practitioner/);
    await expect(page.locator("[data-other-issues]")).toBeVisible();
    await submitSituation(page, "other", "Dermatologist checking a mole");
    await expect(page.locator("[data-read-as]")).toContainText("Dermatologist");
    await expect(page.locator('[data-banner="fallback"] [data-suggestions] button').first()).toBeVisible();
  });
});

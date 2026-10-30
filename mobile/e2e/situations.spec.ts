import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  answerKeys,
  collapse,
  documentTexts,
  normalise,
  situations,
  submitSituation,
  signIn,
  trackErrors,
  unseenSituations,
} from "./helpers";

// docs/FRONTEND.md §6. The situation is typed as one sentence (title + description name the role).
const SPEED_LIMIT_MS = 2_000;
const keys = answerKeys();

for (const s of situations()) {
  test.describe(`situation ${s.n}: ${s.title}`, () => {
    test("expected answers are in the key facts, visible without clicking", async ({ page }) => {
      const errors = trackErrors(page);
      await submitSituation(page, `${s.title}. ${s.description}`);
      // answer first (docs/DECISIONS.md 20): the details are collapsed, the key facts alone must answer
      await expect(page.locator("[data-show-more]")).toHaveAttribute("aria-expanded", "false");
      await expect(page.locator("#details-more")).toHaveCount(0);
      const lines = await page.locator("[data-key-fact]").count();
      expect(lines, "key-fact lines").toBeLessThanOrEqual(8);
      const screen = normalise(await page.locator("[data-key-facts]").innerText());
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

    test("'Show more' opens the full cards; one tap, collapsed by default", async ({ page }) => {
      await submitSituation(page, `${s.title}. ${s.description}`);
      const before = await page.locator("[data-fact]").count();
      await page.locator("[data-show-more]").click();
      await expect(page.locator("#details-more")).toBeVisible();
      await expect(page.getByRole("heading", { name: /^(What you need|Erforderliche Angaben)/ })).toBeVisible();
      expect(await page.locator("[data-fact]").count()).toBeGreaterThan(before);
    });

    test("source opens the original letter with the cited passage highlighted", async ({ page }) => {
      const docs = (await documentTexts()).map(collapse);
      await submitSituation(page, `${s.title}. ${s.description}`);
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
      const ms = await submitSituation(page, `${s.title}. ${s.description}`);
      expect(ms).toBeLessThan(SPEED_LIMIT_MS);
    });
  });
}

test.describe("start screen", () => {
  test("one free-text field, no role or example chips; the sentence is sent as typed", async ({ page }) => {
    await page.goto("/", { waitUntil: "networkidle" });
    await signIn(page);
    await expect(page.getByRole("heading", { name: /Who are you and what do you need|Wer sind Sie und was brauchen Sie/ })).toBeVisible();
    await expect(page.locator("main button", { hasText: /^(Anaesthetist|Surgeon|GP|Other role|Anästhesie)$/ })).toHaveCount(0);
    const sent = page.waitForRequest((r) => r.url().endsWith("/briefing") && r.method() === "POST");
    await page.locator("input").first().fill("GP, diabetes review");
    await page.locator("input").first().press("Enter");
    expect(JSON.parse((await sent).postData() ?? "{}").situation).toBe("GP, diabetes review");
  });
});

test.describe("unseen situations (free text via 'Other role')", () => {
  for (const u of unseenSituations()) {
    test(`${u.id}: ${u.situation}`, async ({ page }) => {
      const errors = trackErrors(page);
      await submitSituation(page, u.situation);
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
    await submitSituation(page, `${s.title}. ${s.description}`);
    const result = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    const serious = result.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`)).toEqual([]);
  });
});

test.describe("source viewer", () => {
  test("several passages: all highlighted, step between them", async ({ page }) => {
    await submitSituation(page, "Anaesthetist, pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
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
    await submitSituation(page, "Anaesthetist, pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
    await page.locator("#facts-panel button[data-source]").first().click();
    const pane = page.locator("aside[data-source-viewer]");
    await expect(pane).toBeVisible();
    await expect(pane.locator("mark[data-active]")).toBeInViewport();
    await expect(page.locator("#facts-panel")).toBeVisible();
  });
});

test.describe("contradictions", () => {
  test("both passages side by side, each with a source link", async ({ page }) => {
    await submitSituation(page, "Vascular surgeon reviewing the carotid stenosis before surgery");
    await expect(page.locator('[data-key-fact="conflict"]')).toBeVisible(); // flagged in the key facts
    await page.locator("[data-show-more]").click();
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
    await submitSituation(page, "Anaesthetist, pre-operative anaesthesia check. Quadrantectomy on 16 May 2016.");
    await expect(page.getByRole("heading", { name: /^Key facts/ })).toBeVisible();
    await page.getByRole("button", { name: /Language: English/ }).click();
    await expect(page.getByRole("heading", { name: /^Das Wichtigste/ })).toBeVisible();
    await expect(page.locator("[data-read-as]")).toContainText("Gelesen als");
    await page.getByRole("button", { name: /Sprache: Deutsch/ }).click();
    await expect(page.getByRole("heading", { name: /^Key facts/ })).toBeVisible();
  });
});

test.describe("banners", () => {
  test("not authorised (firefighter): plain banner, no example chips, no patient facts", async ({ page }) => {
    await submitSituation(page, "Firefighter checking the patient");
    await expect(page.locator('[data-banner="not_authorised"]')).toBeVisible();
    await expect(page.locator("[data-suggestions]")).toHaveCount(0);
    await expect(page.locator("[data-fact]")).toHaveCount(0);
    await expect(page.locator("text=/Consistent across letters|Verified/")).toHaveCount(0);
  });

  test("no task, no data ('Anaesthetist: hi'): plain banner, nothing from the record", async ({ page }) => {
    await submitSituation(page, "Anaesthetist: hi");
    const banner = page.locator('[data-banner="needs_task"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/Please describe your task|Bitte beschreiben Sie Ihre Aufgabe/);
    await expect(banner.locator("[data-suggestions]")).toHaveCount(0);
    await expect(page.locator("[data-patient-card]")).toHaveCount(0);
    await expect(page.getByRole("tablist")).toHaveCount(0);
    await expect(page.locator("[data-fact]")).toHaveCount(0);
    await expect(page.locator("button[data-source]")).toHaveCount(0);
    await expect(page.locator('[data-banner="fallback"], [data-blind-spot], [data-other-issues]')).toHaveCount(0);
    await expect(page.locator("main")).not.toContainText(/Patientin|female|weiblich|\b(19|20)\d\d\b/);
  });

  test("clear task but no role: 'who is asking' banner, nothing from the record", async ({ page }) => {
    await submitSituation(page, "STAT CT head, any bleeding risk meds?");
    const banner = page.locator('[data-banner="needs_task"]');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText(/Who is asking|Wer fragt/);
    await expect(page.locator("[data-patient-card]")).toHaveCount(0);
    await expect(page.locator("[data-fact]")).toHaveCount(0);
  });

  test("not applicable: banner with evidence, never counted as consistent", async ({ page }) => {
    await submitSituation(page, "Urologist, prostate cancer screening");
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
    await submitSituation(page, "Rheumatologist reviewing joint pain");
    await expect(page.locator("[data-read-as]")).toContainText("Rheumatologist");
    await expect(page.locator("[data-read-as]")).not.toContainText(/\bGP\b|General practitioner/);
    if (await page.locator("[data-show-more]").count()) await page.locator("[data-show-more]").click();
    await expect(page.locator("[data-other-issues]")).toBeVisible();
    await submitSituation(page, "Dermatologist checking a mole");
    await expect(page.locator("[data-read-as]")).toContainText("Dermatologist");
    await expect(page.locator('[data-banner="fallback"] [data-suggestions] button').first()).toBeVisible();
  });
});

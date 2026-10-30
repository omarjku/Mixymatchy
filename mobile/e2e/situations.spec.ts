import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import {
  answerKeys,
  collapse,
  documentTexts,
  normalise,
  type RoleKey,
  situations,
  SOURCE_BUTTON,
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

    test("source links show passages that exist verbatim in the documents", async ({ page }) => {
      const docs = (await documentTexts()).map(collapse);
      await submitSituation(page, ROLE_FOR[s.n], `${s.title}. ${s.description}`);
      const buttons = page.locator("#facts-panel button").filter({ hasText: SOURCE_BUTTON });
      const count = Math.min(await buttons.count(), 10);
      expect(count, "facts with a source link").toBeGreaterThan(0);
      for (let i = 0; i < count; i++) {
        await buttons.nth(i).click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toBeVisible();
        const excerpt = collapse((await dialog.locator("text=/„/").first().innerText()).replace(/^„|“$/g, ""));
        expect(excerpt.length).toBeGreaterThan(0);
        expect(docs.some((d) => d.includes(excerpt)), `not found verbatim in any document: "${excerpt}"`).toBe(true);
        await page.keyboard.press("Escape");
        await expect(dialog).toBeHidden();
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

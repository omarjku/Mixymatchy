import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { expect, type Page } from "@playwright/test";

// Shared helpers. Selectors match both the English and the German UI.

const ROOT = fileURLToPath(new URL("../../", import.meta.url));
export const BACKEND_URL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8011";

export const ROLE = {
  anaesthetist: /^(Anaesthetist|Anästhesie)$/,
  surgeon: /^(Surgeon|Chirurgie)$/,
  gp: /^(GP|General practitioner|Hausarztpraxis)$/,
  emergency: /^(Emergency|Notaufnahme)$/,
  other: /^(Other role|Andere Rolle)$/,
} as const;
export type RoleKey = keyof typeof ROLE;

// Demo user (security/README.md): every page load needs a sign-in, the API needs the Bearer token.
export const DEMO_USER = { staff_id: "dr.demo", password: "SecondLook-demo-2026" };

export async function signIn(page: Page): Promise<void> {
  await page.locator("#sl-staff").fill(DEMO_USER.staff_id);
  await page.locator("#sl-pass").fill(DEMO_USER.password);
  await page.locator("#sl-pass").press("Enter");
  await expect(page.locator(".sl-shell")).toBeHidden();
}

async function apiToken(): Promise<string> {
  const r = await fetch(`${BACKEND_URL}/auth/login`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(DEMO_USER),
  });
  return ((await r.json()) as { token: string }).token;
}

export const FACTS_HEADING = /What you need|Erforderliche Angaben/;
export const RESULT_READY = '[data-read-as]';
export const SOURCE_BUTTON = /^(Source|Quelle)$/;

export interface Situation {
  n: number;
  title: string;
  description: string;
}

// The five situations exactly as the jury types them: title + description from cases/situations.md.
export function situations(): Situation[] {
  const md = readFileSync(`${ROOT}cases/situations.md`, "utf8");
  return md
    .split(/\n## (\d+)\. /)
    .slice(1)
    .reduce<Situation[]>((out, part, i, arr) => {
      if (i % 2 === 0) {
        const [title, ...rest] = arr[i + 1].split("\n");
        const description = rest.join("\n").trim().split(/\n\n/)[0];
        out.push({ n: Number(part), title: title.trim(), description });
      }
      return out;
    }, []);
}

export function unseenSituations(): { id: string; situation: string }[] {
  return JSON.parse(readFileSync(`${ROOT}eval/unseen_situations.json`, "utf8"));
}

export interface AnswerItem {
  name: string;
  groups: string[][];
}
export function answerKeys(): Record<string, { question: string; items: AnswerItem[] }> {
  const raw = JSON.parse(readFileSync(`${ROOT}eval/answer_keys.json`, "utf8"));
  delete raw._doc;
  return raw;
}

// Same normalisation idea as eval/answer_keys.json: decimal comma -> point, separators -> space, "100mg" == "100 mg".
export function normalise(text: string): string {
  return text
    .toLowerCase()
    .replace(/(\d),(\d)/g, "$1.$2")
    .replace(/[-:_()[\]„“"]/g, " ")
    .replace(/(\d)(mg|µg|mcg|kg|cm|mmhg|%)/g, "$1 $2")
    .replace(/\s+/g, " ");
}

// Collects console errors and uncaught page errors for one page.
export function trackErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}

// Start screen -> role chip -> type task -> submit; resolves when the facts heading is visible.
// Returns the time from submit to the facts heading in ms.
export async function submitSituation(page: Page, role: RoleKey, text: string): Promise<number> {
  await page.goto("/", { waitUntil: "networkidle" });
  await signIn(page);
  await page.getByRole("button", { name: ROLE[role] }).click();
  const box = page.locator("textarea, input").first();
  await box.fill(text);
  const start = Date.now();
  await box.press("Enter");
  await expect(page.locator(RESULT_READY)).toBeVisible({ timeout: 10_000 });
  return Date.now() - start;
}

// All document texts from the backend (the source of truth for every quote on screen).
export async function documentTexts(): Promise<string[]> {
  const init = { headers: { Authorization: `Bearer ${await apiToken()}` } };
  const list: { id: string }[] = await (await fetch(`${BACKEND_URL}/documents`, init)).json();
  return Promise.all(
    list.map(async (d) => ((await (await fetch(`${BACKEND_URL}/documents/${d.id}`, init)).json()) as { text: string }).text),
  );
}

export const collapse = (s: string) => s.replace(/\s+/g, " ").trim();

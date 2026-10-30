import { mockBriefs } from "@/data/mockFacts";
import { mockStats } from "@/data/mockStats";
import type { RoleId } from "@/data/roles";
import type { PatientBrief } from "@/types/fact";
import type { PatientStats } from "@/types/stats";
import { fetchBriefing, toPatientBrief } from "@/lib/backend";

// The only place the app fetches a patient brief. Real backend by default (src/lib/backend.ts);
// VITE_MOCK=1 uses the invented mock briefs instead (never for the demo: they are not patient facts).
export const USE_MOCK = import.meta.env.VITE_MOCK === "1";

export const BRIEF_TIMEOUT_MS = 10_000; // grading ceiling: slowest situation must load in under 10 s
const MOCK_DELAY_MS = 1_200;

export class BriefTimeoutError extends Error {
  constructor() {
    super("Patient brief request timed out");
    this.name = "BriefTimeoutError";
  }
}

export async function fetchPatientBrief(role: RoleId, task: string, signal?: AbortSignal): Promise<PatientBrief> {
  // Dev only, to test the failure screens: in the browser console run
  //   localStorage.setItem("simulate", "error")   or   localStorage.setItem("simulate", "slow")
  // and localStorage.removeItem("simulate") to go back to normal.
  const simulate = import.meta.env.DEV ? readSimulateFlag() : null;
  if (!USE_MOCK && !simulate) {
    // The clinician's own sentence, sent as typed (who they are + what they need); the backend reads it.
    // Short view: key facts + the full cards for "Show more", one request.
    const briefing = await fetchBriefing(task, "short", signal);
    return toPatientBrief(briefing, role, task, signal);
  }
  await wait(simulate === "slow" ? BRIEF_TIMEOUT_MS + 5_000 : MOCK_DELAY_MS, signal);
  if (simulate === "error") throw new Error("Simulated backend error");
  // Mock: one fixed brief per role; echo the requested task so the header shows what was asked
  const mock = mockBriefs[role] ?? mockBriefs.gp!;
  return { ...mock, task, generatedAt: new Date().toISOString() };
}

// Dashboard level: documented measurements for one patient, or null when none exist.
// Fetched only when the Dashboard tab is opened. Replace the body with the API call later.
export async function fetchPatientStats(patientId: string, signal?: AbortSignal): Promise<PatientStats | null> {
  // No stats endpoint yet: show nothing rather than invented numbers (mock stats only in mock mode)
  if (!USE_MOCK) return null;
  await wait(400, signal);
  return mockStats[patientId] ?? null;
}

// Runs fetchPatientBrief with the 10 s ceiling. Rejects with BriefTimeoutError when it is exceeded,
// or with an AbortError when the caller's signal aborts (e.g. the screen unmounts).
export async function fetchPatientBriefWithTimeout(
  role: RoleId,
  task: string,
  signal: AbortSignal,
): Promise<PatientBrief> {
  const controller = new AbortController();
  const onAbort = () => controller.abort();
  signal.addEventListener("abort", onAbort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, BRIEF_TIMEOUT_MS);

  try {
    return await fetchPatientBrief(role, task, controller.signal);
  } catch (error) {
    if (timedOut) throw new BriefTimeoutError();
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        reject(abortError());
      },
      { once: true },
    );
  });
}

function readSimulateFlag(): string | null {
  try {
    return window.localStorage.getItem("simulate");
  } catch {
    return null; // storage blocked (private mode etc.)
  }
}

function abortError(): DOMException {
  return new DOMException("Aborted", "AbortError");
}

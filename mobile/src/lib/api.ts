import { mockBriefs } from "@/data/mockFacts";
import type { RoleId } from "@/data/roles";
import type { PatientBrief } from "@/types/fact";

// The only place the app fetches a patient brief. To switch to the real backend, replace the body of
// fetchPatientBrief with the API call; keep the signature and the PatientBrief return type (the contract).

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
  await wait(simulate === "slow" ? BRIEF_TIMEOUT_MS + 5_000 : MOCK_DELAY_MS, signal);
  if (simulate === "error") throw new Error("Simulated backend error");
  // Mock: one fixed brief per role; echo the requested task so the header shows what was asked
  return { ...mockBriefs[role], task, generatedAt: new Date().toISOString() };
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

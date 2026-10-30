import type { ResultsState } from "@/types/request";

// The current briefing lives in memory only: never in history.state, sessionStorage or localStorage,
// so patient data does not outlive the tab or end up in the browser's session restore.
let current: ResultsState | null = null;

export function setResults(state: ResultsState | null): void {
  current = state;
}

export function getResults(): ResultsState | null {
  return current;
}

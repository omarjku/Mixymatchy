import { useSyncExternalStore } from "react";

// Light / dark theme. Follows the device setting until the AppBar toggle is used; that choice is a
// per-device convenience (like the UI language in src/i18n/locale.ts). The resolved theme is written to
// <html data-theme>, which switches the color tokens in src/theme/theme.css. index.html sets it once
// before the first paint (same storage key), so there is no light flash in dark mode.

export type Theme = "light" | "dark";

const STORAGE_KEY = "secondlook.theme";
const listeners = new Set<() => void>();
const systemDark = typeof window !== "undefined" ? window.matchMedia("(prefers-color-scheme: dark)") : null;

function readStored(): Theme | null {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return value === "light" || value === "dark" ? value : null;
  } catch {
    return null; // storage blocked (private mode etc.)
  }
}

let chosen: Theme | null = typeof window === "undefined" ? null : readStored();

function resolve(): Theme {
  return chosen ?? (systemDark?.matches ? "dark" : "light");
}

let current: Theme = typeof window === "undefined" ? "light" : resolve();

function apply(): void {
  current = resolve();
  document.documentElement.dataset.theme = current;
  listeners.forEach((listener) => listener());
}

// Follow the device setting live, as long as nobody chose a theme with the toggle
systemDark?.addEventListener("change", () => {
  if (chosen === null) apply();
});

export function getTheme(): Theme {
  return current;
}

export function toggleTheme(): void {
  chosen = current === "dark" ? "light" : "dark";
  try {
    window.localStorage.setItem(STORAGE_KEY, chosen);
  } catch {
    // not persisted; the choice still applies until reload
  }
  apply();
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getTheme,
    getTheme,
  );
}

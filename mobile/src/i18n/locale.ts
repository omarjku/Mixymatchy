import { useSyncExternalStore } from "react";

// UI language. English by default (the jury writes situations in English and backend labels are English);
// German stays available through the language toggle. The choice is a per-device convenience.

export type Locale = "en" | "de";

const STORAGE_KEY = "secondlook.locale";
const listeners = new Set<() => void>();

function readStored(): Locale {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "de" ? "de" : "en";
  } catch {
    return "en"; // storage blocked (private mode etc.)
  }
}

let current: Locale = typeof window === "undefined" ? "en" : readStored();
if (typeof document !== "undefined") document.documentElement.lang = current;

export function getLocale(): Locale {
  return current;
}

export function setLocale(next: Locale): void {
  if (next === current) return;
  current = next;
  try {
    window.localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // not persisted; the choice still applies until reload
  }
  document.documentElement.lang = next;
  listeners.forEach((listener) => listener());
}

export function toggleLocale(): void {
  setLocale(current === "en" ? "de" : "en");
}

// BCP 47 tag for Intl formatting and speech
export function intlLocale(locale: Locale = current): string {
  return locale === "de" ? "de-DE" : "en-GB";
}

export function useLocale(): Locale {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    getLocale,
    getLocale,
  );
}

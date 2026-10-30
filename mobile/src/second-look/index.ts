// Sign-in and PIN lock (security/web/second-look-lock.js, copied here; backend: backend/app/auth.py).
// Imported by main.tsx before the app renders. All API calls go through secureFetch (Bearer token, 401/423 handling).
import "./second-look-lock.js";
import "./lock.css";
import "./theme.css";

interface SecondLookLock {
  init(options: Record<string, unknown>): SecondLookLock;
  fetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response>;
  lock(): void;
  logout(): void;
}

const lock = (window as unknown as { SecondLook: { lock: SecondLookLock } }).SecondLook.lock;

// Demo/test hook: ?idle=10 shortens the client idle lock (never lengthens it; the server keeps its 3 min).
const idleParam = Number(new URLSearchParams(window.location.search).get("idle"));
const idleSeconds = idleParam > 0 && idleParam < 180 ? idleParam : undefined;

lock.init({
  apiBase: "",
  appRoot: "#root",
  stylesheet: false, // bundled above
  idleSeconds,
  // A different person may be next: drop all patient data from memory and the DOM.
  onLoggedOut: (reason: string) => {
    if (reason === "not_me" || reason === "user" || reason === "revoked") window.location.replace("/");
  },
});

export const secureFetch: typeof fetch = (input, init) => lock.fetch(input, init);
export const lockNow = () => lock.lock();

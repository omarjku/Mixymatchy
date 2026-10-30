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

// SECOND_LOOK_AUTH=0 on the backend turns sign-in and the PIN lock off: GET /auth/config -> {"auth": false}.
// Any failure means auth stays on. VITE_MOCK=1 (local dev only, invented mock briefs, no backend) skips it too:
// there is no patient data to protect and no /auth to sign in against.
async function authEnabled(): Promise<boolean> {
  if (import.meta.env.VITE_MOCK === "1") return false;
  try {
    const r = await fetch("/auth/config", { cache: "no-store" });
    if (!r.ok) return true;
    return (await r.json()).auth !== false;
  } catch {
    return true;
  }
}

const authOn = await authEnabled();
const lock = (window as unknown as { SecondLook: { lock: SecondLookLock } }).SecondLook.lock;

// Demo/test hook: ?idle=10 shortens the client idle lock (never lengthens it; the server keeps its 3 min).
const idleParam = Number(new URLSearchParams(window.location.search).get("idle"));
const idleSeconds = idleParam > 0 && idleParam < 180 ? idleParam : undefined;

if (authOn) {
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
}

export const secureFetch: typeof fetch = (input, init) => (authOn ? lock.fetch(input, init) : fetch(input, init));
export const lockNow = () => {
  if (authOn) lock.lock();
};

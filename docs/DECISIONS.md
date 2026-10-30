# Integration decisions (30 Oct 2026, approved by Omar)

Submission UI = Zoha's `mobile/` app on main (backend-wired). The Next.js `frontend/` stays only as fallback.

1. **Language:** English default, German toggle (whole UI; patient quotes stay in the original German).
2. **Source click is mandatory:** tapping "source" opens the original letter with the relevant passage highlighted and scrolled into view (not just the bare sentence).
3. **Zoha's newer UI** (AppBar, Help/FAQ, error pages from `origin/mobile-frontend`) is ported onto main's backend wiring. Never ship mock data.
4. **Screen content:** short view, plus a visible "Also relevant" section for P2 (no click needed). Dashboard tab hidden.
5. **Not applicable / not authorised** get their own banner screens (not "Verified").
6. **Trust labels:** use the engine's four: Consistent across letters / Letters disagree / Outdated / Mentioned once (+ Not documented, Not applicable).
7. **Safety core on every clinical screen:** allergies and age/sex always shown.
8. **History tab works:** backend fills `value`/`unit` on numeric facts.
9. **Readable contradiction titles:** no raw passage IDs in titles.
10. **Routing gaps:** weight review, rheumatologist and other unseen roles route sensibly; unknown clinical roles show their own label, never "GP".
11. **Login:** the PIN lock replaces the site password, inside FastAPI. Demo PIN stays **2468**. Audit log may reset on redeploy (accepted for the demo).
12. **Hosting:** Docker image builds `mobile/`, FastAPI serves it with an SPA fallback for deep links.
13. **Privacy fixes:** no patient data in browser history state, self-hosted fonts, on-device voices only, mock patient renamed.
14. **English translation under German quotes:** deferred (needs an LLM key); toggle shows UI language only.
15. **Lymph-node item:** stays a documentation note until the medical team decides.

Working mode: commit straight to `main` after the full test suite passes; checkpoints are branches `checkpoint/N-*`.

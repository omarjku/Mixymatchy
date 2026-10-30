import { defineConfig, devices } from "@playwright/test";

// End-to-end tests against the running app + backend (see e2e/README.md).
// The backend is started separately; vite is reused if already running on E2E_BASE_URL.
const baseURL = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5181";
const backendURL = process.env.E2E_BACKEND_URL ?? "http://127.0.0.1:8011";

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL,
    viewport: { width: 390, height: 844 },
    // Screenshots and traces would contain patient text: keep them off (and git-ignored anyway).
    screenshot: "off",
    trace: "off",
    video: "off",
  },
  webServer: {
    command: `npx vite --port ${new URL(baseURL).port} --strictPort --host 127.0.0.1`,
    url: baseURL,
    reuseExistingServer: true,
    env: { BACKEND_URL: backendURL },
    timeout: 60_000,
  },
});

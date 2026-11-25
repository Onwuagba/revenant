import { defineConfig } from "@playwright/test";

// Smoke test runs against a built console served by the real API (see tests/smoke.spec.ts).
export default defineConfig({
  testDir: "tests",
  timeout: 60_000,
  // A remote host (E2E_BASE_URL, e.g. the free-tier demo) can take several seconds per USSD round trip;
  // give each wait 20 s there. Local runs keep the 5 s default. Assertions are the same either way.
  expect: { timeout: process.env.E2E_BASE_URL ? 20_000 : 5_000 },
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173" },
  webServer: process.env.E2E_BASE_URL ? undefined : [
    {
      command: "cd .. && REVENANT_INSECURE_COOKIES=1 .venv/bin/python -m uvicorn revenant.api.main:app --app-dir backend/src --port 8765",
      url: "http://127.0.0.1:8765/healthz", reuseExistingServer: true, timeout: 60_000,
    },
    { command: "REVENANT_API=http://127.0.0.1:8765 npx vite --host 127.0.0.1 --port 5173 --strictPort", url: "http://127.0.0.1:5173", reuseExistingServer: true },
  ],
});

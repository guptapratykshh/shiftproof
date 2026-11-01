import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests",
  outputDir: "./offline-test-results",
  testMatch: "offline-production.spec.ts",
  workers: 1,
  timeout: 45000,
  use: {
    baseURL: "http://127.0.0.1:5175",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    permissions: ["microphone"],
    launchOptions: {
      args: [
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
      ],
    },
  },
  webServer: [
    {
      command:
        "../.venv/bin/uvicorn shiftproof.api:app --host 127.0.0.1 --port 8002",
      url: "http://127.0.0.1:8002/health",
      reuseExistingServer: false,
      env: {
        SHIFTPROOF_ENV: "local",
        SHIFTPROOF_DATA_DIR: `../.local/offline-e2e-${Date.now()}`,
        EXTRACTION_PROVIDER: "scripted",
        GNANI_API_KEY: "",
      },
    },
    {
      command: "npm run preview -- --port 5175",
      url: "http://127.0.0.1:5175",
      reuseExistingServer: false,
      env: { VITE_DEV_API_TARGET: "http://127.0.0.1:8002" },
    },
  ],
});

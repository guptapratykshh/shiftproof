import { defineConfig } from "@playwright/test";
const testData = process.env.SHIFTPROOF_BROWSER_DATA_DIR || `../.local/e2e-${Date.now()}`;
process.env.SHIFTPROOF_BROWSER_DATA_DIR = testData;
export default defineConfig({
  testDir: "./tests",
  testIgnore: "offline-production.spec.ts",
  fullyParallel: false,
  workers: 1,
  timeout: 30000,
  use: {
    baseURL: "http://127.0.0.1:5174",
    // Tests use explicit English; production defaults remain Hindi.
    storageState: { cookies: [], origins: [{ origin: "http://127.0.0.1:5174", localStorage: [{ name: "shiftproof-language", value: "en" }] }] },
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
        "../.venv/bin/uvicorn shiftproof.api:app --host 127.0.0.1 --port 8001",
      url: "http://127.0.0.1:8001/health",
      reuseExistingServer: false,
      env: {
        SHIFTPROOF_ENV: "local",
        SHIFTPROOF_DATA_DIR: testData,
        EXTRACTION_PROVIDER: "scripted",
        GNANI_API_KEY: "",
      },
    },
    {
      command: "npm run dev -- --port 5174",
      url: "http://127.0.0.1:5174",
      reuseExistingServer: false,
      env: { VITE_DEV_API_TARGET: "http://127.0.0.1:8001" },
    },
  ],
});

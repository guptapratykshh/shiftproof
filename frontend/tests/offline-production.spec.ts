import { test, expect } from "@playwright/test";
test("installed public shell reopens offline for bounded capture and reauthenticates before sending", async ({
  page,
  context,
}) => {
  const created = await (
    await page.request.post("/api/auth/signup", {
      data: {
        name: "Offline Pilot",
        email: `offline-${Date.now()}@example.com`,
        password: "offline-pilot-password",
        industry: "manufacturing",
      },
    })
  ).json();
  const session = await (await page.request.get("/api/auth/session")).json();
  const org = created.organization_id;
  const response = await page.request.post(
    `/api/organizations/${org}/work-items`,
    {
      headers: { "X-CSRF-Token": session.csrf_token },
      data: { id: "OFFLINE-1", name: "Offline carton batch", target: 50 },
    },
  );
  expect(response.ok()).toBeTruthy();
  await page.goto(`/app/${org}`);
  await expect(page.locator(".item-card")).toContainText("OFFLINE-1");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await expect
    .poll(() => page.evaluate(() => !!navigator.serviceWorker.controller))
    .toBeTruthy();
  await expect
    .poll(() =>
      page.evaluate(
        () => !!localStorage.getItem("shiftproof-offline-capture-context-v1"),
      ),
    )
    .toBeTruthy();
  const stored = await page.evaluate(() =>
    localStorage.getItem("shiftproof-offline-capture-context-v1"),
  );
  expect(stored).not.toContain("csrf");
  expect(stored).not.toContain("password");
  expect(stored).not.toContain("transcripts");
  await context.setOffline(true);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "अपडेट सुरक्षित रखें", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "English", exact: true }).click();
  await expect(
    page.getByText("These are cached assignment details.", { exact: false }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Reconnect and verify account" }),
  ).toBeDisabled();
  let submitted = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname.endsWith("/notes")
    )
      submitted++;
  });
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(
    page.getByText("Draft saved on this device.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(page.locator(".offline-capture audio")).toBeVisible();
  await context.setOffline(false);
  await expect(
    page.getByRole("button", { name: "Reconnect and verify account" }),
  ).toBeEnabled();
  await page
    .getByRole("button", { name: "Reconnect and verify account" })
    .click();
  await expect(page.locator(".organization-sidebar")).toBeVisible();
  await page.locator(".draft-drawer summary").click();
  await page.getByRole("button", { name: "Open draft", exact: true }).click();
  await expect(page.locator(".item-select select")).toHaveValue("OFFLINE-1");
  await expect(page.locator(".capture-panel audio")).toBeVisible();
  expect(submitted).toBe(0);
  const cached = await page.evaluate(async () => {
    const output: string[] = [];
    for (const key of await caches.keys()) {
      for (const request of await (await caches.open(key)).keys())
        output.push(new URL(request.url).pathname);
    }
    return output;
  });
  expect(cached.some((path) => path.startsWith("/api"))).toBeFalsy();
});

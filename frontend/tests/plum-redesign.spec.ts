import { appearance, choose } from './controls';
import { test, expect, type Page } from "./fixtures";
import fs from "node:fs";
test.use({ video: { mode: "on", size: { width: 1280, height: 900 } } });
async function shot(page: Page, name: string) {
  fs.mkdirSync("../artifacts/redesign/after", { recursive: true });
  await page.screenshot({
    path: `../artifacts/redesign/after/${name}.png`,
    fullPage: true,
  });
}
async function setup(page: Page) {
  const r = await page.request.post("/api/auth/signup", {
    data: {
      name: "Meera",
      email: `plum-${Date.now()}-${Math.random()}@example.com`,
      password: "FictionalDesign!2026",
      industry: "manufacturing",
    },
  });
  expect(r.ok()).toBeTruthy();
  const { organization_id: org } = await r.json();
  const session = await (await page.request.get("/api/auth/session")).json();
  const call = async (path: string, data?: unknown, method?: string) => {
    const r = await page.request.fetch(`/api/organizations/${org}${path}`, {
      method: method || (data ? "POST" : "GET"),
      headers: { "X-CSRF-Token": session.csrf_token },
      data,
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  const loc = await call("/locations", { name: "Fictional packing floor" }),
    team = await call("/teams", { name: "Packing team", location_id: loc.id });
  await call("/work-items", {
    id: "PLUM-17",
    name: "Fictional cartons",
    location_id: loc.id,
    team_id: team.id,
  });
  const shift = await call("/shift-occurrences", {
    name: "Morning shift",
    location_id: loc.id,
    team_id: team.id,
    starts_at: new Date(Date.now() - 3600000).toISOString(),
    ends_at: new Date(Date.now() + 3600000).toISOString(),
  });
  await call(
    `/shift-occurrences/${shift.id}/assignments`,
    {
      user_ids: [session.user.id],
      supervisor_id: session.user.id,
      work_item_ids: ["PLUM-17"],
    },
    "PUT",
  );
  return { org, call, shift, session };
}
test("appearance persists on public and account pages and System follows device changes", async ({
  page,
}) => {
  await page.emulateMedia({ colorScheme: "dark", reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await appearance(page, "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  for (const route of [
    "/login",
    "/signup",
    "/recover",
    "/worker/login",
    "/organizations",
  ]) {
    await page.goto(route);
    await expect(page.locator(".appearance-control")).toBeVisible();
    await appearance(page, "dark");
    await shot(page, `dark-${route.slice(1)}`.replaceAll("/", "-"));
    await appearance(page, "light");
  }
  await page.goto("/");
  await appearance(page, "system");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.emulateMedia({ colorScheme: "light" });
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".appearance-control")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: "हिन्दी में बदलें" }).click();
  await expect(page.locator(".appearance-control")).toBeVisible();
  await shot(page, "hi-public-mobile");
});
test("management screens use real data in both languages and themes with stable navigation", async ({
  page,
}) => {
  test.setTimeout(180000);
  // This visual matrix requires an online browser. Offline recovery has its own
  // production test; a host-network change must not replace these screens.
  await page.context().setOffline(false);
  const { org, call } = await setup(page);
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  for (const lang of ["en", "hi"]) {
    await page.goto(`/app/${org}?view=overview`);
    if (lang === "hi")
      await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
    for (const theme of ["light", "dark"]) {
      await appearance(page
        , theme);
      for (const width of [390, 768, 1440, 1920]) {
        await page.setViewportSize({ width, height: 900 });
        for (const view of [
          "overview",
          "work",
          "reports",
          "capture",
          "handover",
          "team",
          "settings",
        ]) {
          await page.goto(`/app/${org}?view=${view}`);
          await expect(page.locator(".workspace-heading h1")).toBeVisible();
          await expect(page.locator("html")).toHaveAttribute(
            "data-theme",
            theme,
          );
          expect(
            await page.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
            `${lang} ${theme} ${view} ${width}`,
          ).toBeTruthy();
          await shot(page, `${lang}-${theme}-${view}-${width}`);
        }
      }
    }
  }
  await page.getByRole("button", { name: "English", exact: true }).click();
  for (const width of [390, 768, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(`/app/${org}?view=reports`);
    await expect(page.getByLabel("Search reports")).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      String(width),
    ).toBeTruthy();
    await shot(page, `dark-reports-${width}`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "Work items", exact: true }).click();
  await expect(page.locator(".item-card")).toContainText("PLUM-17");
  await page.reload();
  await expect(page).toHaveURL(/view=work/);
  await page.goBack();
  await expect(page).toHaveURL(/view=reports/);
  await expect(page.getByText("Viewing as", { exact: true })).toHaveCount(0);
  expect(errors).toEqual([]);
  const cancelled = await call("/notes", {
    batch_id: "PLUM-17",
    recorded_at: new Date().toISOString(),
    idempotency_key: "cancelled-ui-" + Date.now(),
  });
  await call("/notes/" + cancelled.note.id, undefined, "DELETE");
  await page.reload();
  await expect(page.locator(".report-list-row")).toContainText(
    "Report closed; original evidence is retained",
  );
  await expect(
    page.getByRole("button", { name: "Listen and check", exact: true }),
  ).toHaveCount(0);
  await choose(page.getByRole("combobox", { name: "Status", exact: true }), "review");
  await expect(page.locator(".report-list-row")).toHaveCount(0);
});
test("worker has three destinations and real recording survives saved-draft navigation", async ({
  page,
  browser,
}) => {
  test.setTimeout(180000);
  const owner = await setup(page);
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:5174",
    permissions: ["microphone"],
    recordVideo: {
      dir: "../artifacts/redesign/walkthrough",
      size: { width: 390, height: 844 },
    },
    viewport: { width: 390, height: 844 },
    storageState: {
      cookies: [],
      origins: [
        {
          origin: "http://127.0.0.1:5174",
          localStorage: [{ name: "shiftproof-language", value: "en" }],
        },
      ],
    },
  });
  const worker = await context.newPage();
  const email = `worker-${Date.now()}@example.com`;
  await worker.request.post("/api/auth/signup", {
    data: {
      name: "Ravi",
      email,
      password: "FictionalWorker!2026",
      industry: "manufacturing",
    },
  });
  const session = await (await worker.request.get("/api/auth/session")).json();
  const invitation = await owner.call("/invitations", {
    name: "Ravi",
    email,
    role: "operator",
  });
  expect(
    (
      await worker.request.post("/api/invitations/accept", {
        data: { token: invitation.join_path.split("/").at(-1) },
        headers: { "X-CSRF-Token": session.csrf_token },
      })
    ).ok(),
  ).toBeTruthy();
  await owner.call(
    `/shift-occurrences/${owner.shift.id}/assignments`,
    {
      user_ids: [owner.session.user.id, session.user.id],
      supervisor_id: owner.session.user.id,
      work_item_ids: ["PLUM-17"],
    },
    "PUT",
  );
  await worker.goto(`/app/${owner.org}`);
  await expect(worker).toHaveURL(/view=home/);
  const nav = worker.getByRole("navigation", { name: "Main navigation" });
  await expect(nav.getByRole("button")).toHaveCount(3);
  await expect(nav).not.toContainText("Settings");
  await shot(worker, "en-worker-home-390");
  await worker
    .getByRole("button", { name: "Record an update", exact: true })
    .click();
  await worker
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(
    worker.locator(".microphone-meter .is-lit").first(),
  ).toBeVisible();
  await worker.waitForTimeout(1200);
  await worker
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  const audio = worker.locator(".capture-panel audio");
  await expect(audio).toBeVisible();
  await audio.evaluate((a: HTMLAudioElement) => a.play());
  await expect
    .poll(() => audio.evaluate((a: HTMLAudioElement) => a.currentTime))
    .toBeGreaterThan(0.1);
  await worker
    .getByText("Check transcript before sending (optional)", { exact: true })
    .click();
  await expect(
    worker.getByRole("button", { name: "Show my transcript", exact: true }),
  ).toBeVisible();
  await nav.getByRole("button", { name: "My work", exact: true }).click();
  await worker
    .getByRole("button", { name: "Save draft and leave", exact: true })
    .click();
  await expect(worker).toHaveURL(/view=mywork/);
  await worker.reload();
  await worker.locator("summary").filter({ hasText: "Saved drafts" }).click();
  await worker.getByRole("button", { name: "Open draft", exact: true }).click();
  await expect(worker.locator(".capture-panel audio")).toBeVisible();
  await worker
    .getByRole("button", { name: "Send update", exact: true })
    .click();
  await expect(worker.getByText("Update sent", { exact: true })).toBeVisible();
  await nav.getByRole("button", { name: "Home", exact: true }).click();
  await expect(worker.getByRole("dialog")).toHaveCount(0);
  await expect(worker.locator(".activity-row")).toContainText("PLUM-17");
  await page.goto(`/app/${owner.org}?view=reports`);
  await expect(page.locator(".report-list-row")).toContainText("Ravi", {
    timeout: 12000,
  });
  await shot(page, "owner-received-voice-report");
  await shot(worker, "worker-delivery-home");
  await appearance(worker, "dark");
  await worker.getByRole("button", { name: "हिन्दी", exact: true }).click();
  await shot(worker, "hi-dark-worker-home-390");
  // Controlled transcription fixture, not a live speech/model result. The audio,
  // note storage, transcript revision, submission and review use the real API.
  await worker.getByRole("button", { name: "English", exact: true }).click();
  const transcript = "Packing complete hai, lekin quality check pending hai.";
  await worker.route(
    `**/api/organizations/${owner.org}/notes/*/process`,
    async (route) => {
      if (!route.request().postDataJSON()?.transcribe_only) {
        await route.continue();
        return;
      }
      const url = route
        .request()
        .url()
        .replace(/process$/, "transcript");
      const result = await worker.request.post(url, {
        headers: {
          "X-CSRF-Token": session.csrf_token,
          "X-Shift-ID": owner.shift.id,
        },
        data: { transcript },
      });
      expect(result.ok()).toBeTruthy();
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ status: "received" }),
      });
    },
  );
  await worker
    .getByRole("button", { name: "Record an update", exact: true })
    .click();
  await worker
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await worker.waitForTimeout(1200);
  await worker
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await worker
    .getByText("Check transcript before sending (optional)", { exact: true })
    .click();
  await worker
    .getByRole("button", { name: "Show my transcript", exact: true })
    .click();
  await expect(worker.getByLabel("Transcript", { exact: true })).toHaveValue(
    transcript,
  );
  const saved = (await owner.call("/workspace")).notes.find(
    (n: any) => n.transcripts?.at(-1)?.text === transcript,
  );
  expect(saved.submitted_at).toBeFalsy();
  await shot(worker, "worker-optional-transcript-before-send");
  await worker
    .getByRole("button", { name: "Send update", exact: true })
    .click();
  await expect(worker.getByText("Update sent", { exact: true })).toBeVisible();
  const row = page.locator(".report-list-row").filter({ hasText: transcript });
  await expect(row).toBeVisible({ timeout: 12000 });
  await row
    .getByRole("button", { name: "Listen and check", exact: true })
    .click();
  const dialog = page.getByRole("dialog"),
    packing = dialog.locator('[data-property="packing"]');
  await expect(packing).toBeVisible();
  const status = packing.getByLabel("Status stated in the recording");
  if (await status.isVisible()) await choose(status, "complete");
  await choose(packing.getByLabel("Your check"), "correct");
  await dialog
    .getByLabel("Checked against the recording", { exact: true })
    .check();
  await dialog.evaluate((el) => {
    el.scrollTop = 0;
  });
  await shot(page, "supervisor-packing-review");
  await dialog
    .getByRole("button", { name: "Save checked updates", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  const current = await owner.call("/workspace");
  expect(
    current.batches[0].claims.some(
      (c: any) => c.property === "packing" && c.status === "confirmed",
    ),
  ).toBeTruthy();
  expect(current.batches[0].status).not.toBe("verified");
  await shot(page, "owner-report-after-review");
  for (const lang of ["en", "hi"]) {
    if (lang === "hi")
      await worker.getByRole("button", { name: "हिन्दी", exact: true }).click();
    for (const theme of ["light", "dark"]) {
      await appearance(worker
        , theme);
      for (const width of [390, 768, 1440, 1920]) {
        await worker.setViewportSize({ width, height: 900 });
        for (const view of ["home", "capture", "mywork", "handover"]) {
          await worker.goto(`/app/${owner.org}?view=${view}`);
          await expect(worker.locator(".workspace-heading h1")).toBeVisible();
          expect(
            await worker.evaluate(
              () => document.documentElement.scrollWidth <= innerWidth,
            ),
          ).toBeTruthy();
          await shot(worker, `${lang}-${theme}-worker-${view}-${width}`);
        }
      }
    }
  }
  await context.close();
});

test("ownership retains management visibility without granting operational review", async ({
  page,
}) => {
  const { org, session, call } = await setup(page);
  const note = await call("/notes", {
    batch_id: "PLUM-17",
    recorded_at: new Date().toISOString(),
    idempotency_key: "owner-permissions-" + Date.now(),
  });
  await call(`/notes/${note.note.id}/transcript`, {
    transcript: "Packing complete hai, lekin quality check pending hai.",
  });
  await call(`/notes/${note.note.id}/process`, {});
  await call(
    `/members/${session.user.id}`,
    { access: "owner", role: "operator" },
    "PUT",
  );
  await page.goto(`/app/${org}?view=reports`);
  await expect(
    page.getByRole("button", { name: "Team", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Settings", exact: true }),
  ).toBeVisible();
  await expect(page).toHaveURL(/view=reports/);
  await expect(page.locator(".report-list-row")).toHaveCount(1);
  await expect(
    page.getByRole("button", { name: "Listen and check", exact: true }),
  ).toHaveCount(0);
  const denied = await page.request.post(
    `/api/organizations/${org}/notes/${note.note.id}/review`,
    {
      headers: { "X-CSRF-Token": session.csrf_token },
      data: {
        expected_version: 1,
        request_id: "no-owner-clearance",
        decisions: [
          {
            candidate: {
              property: "packing",
              value: "complete",
              excerpt: "Packing complete hai",
              modality: "actual",
            },
            action: "confirm",
            reason: "Checked against the recording",
          },
        ],
      },
    },
  );
  expect(denied.status()).toBe(403);
  await shot(page, "owner-without-operational-review");
});

import { choose } from './controls';
import { test, expect, type Page } from "./fixtures";

test.beforeEach(async ({ page }) => {
  page.on("dialog", (dialog) => void dialog.accept());
});

test("minimal mobile signup validates confirmation and gives local strength feedback", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/signup");
  await expect(
    page.getByLabel("Organization name", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Timezone", { exact: true })).toHaveCount(0);
  await page.getByLabel("Your name").fill("Meera");
  await page
    .getByLabel("Email address")
    .fill(`minimal-${Date.now()}@example.com`);
  await page.getByLabel("Password", { exact: true }).fill("password123456");
  await expect(page.getByText("Weak estimate", { exact: false })).toBeVisible();
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("different password");
  await expect(
    page.getByText("Passwords do not match.", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(page).toHaveURL(/\/signup$/);
  await page
    .getByLabel("Password", { exact: true })
    .fill("copper meadow lantern otter");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("copper meadow lantern otter");
  await expect(
    page.getByText("Strong estimate", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Show password", exact: true })
    .click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "text",
  );
  await page
    .getByRole("button", { name: "Hide password", exact: true })
    .click();
  await expect(page.getByLabel("Password", { exact: true })).toHaveAttribute(
    "type",
    "password",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../artifacts/team-signup-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await page
    .getByRole("link", { name: "I’ve saved my codes · Open workspace" })
    .click();
  await expect(page.locator(".organization-person")).toContainText(
    "Organization owner",
  );
  const session = await (await page.request.get("/api/auth/session")).json();
  expect(session.organizations[0].name).toBe("Meera’s workspace");
  expect(session.organizations[0].timezone).toBe(
    await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
  );
});

test("owner manages named activation links, rename and access history", async ({
  page,
}) => {
  await signup(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Edit", exact: true }).click();
  await page
    .getByLabel("Workspace name", { exact: true })
    .fill("Meera Packaging");
  await page
    .getByRole("dialog")
    .getByText("Advanced settings", { exact: true })
    .click();
  await page.getByLabel("Display timezone").fill("Asia/Kolkata");
  await page.getByRole("button", { name: "Save workspace details" }).click();
  await expect(page.getByLabel("Switch organization")).toHaveCount(0);
  await expect(page.locator(".current-organization strong")).toHaveText(
    "Meera Packaging",
  );
  await expect(
    page.getByText("The name your team sees", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Team", exact: true }).click();
  await page.getByRole("button", { name: "Manage", exact: true }).click();
  const ownerRow = page.getByRole("dialog");
  await choose(ownerRow.getByLabel("Operational role"), "quality");
  await ownerRow.getByRole("button", { name: "Save permissions" }).click();
  await expect(page.locator(".organization-person")).toContainText(
    "Authorized reviewer",
  );
  await page.getByRole("button", { name: "Manage", exact: true }).click();
  await choose(ownerRow.getByLabel("Operational role"), "supervisor");
  await ownerRow.getByRole("button", { name: "Save permissions" }).click();
  await expect(page.locator(".organization-person")).toContainText(
    "Shift supervisor",
  );
  await page
    .getByRole("button", { name: "Add team member", exact: true })
    .click();
  await choose(page
    .getByRole("dialog")
    .locator(".role-choice select"), "email");
  await page.getByLabel("Team member name").fill("Kavya Shift");
  await page.getByLabel("Email address").fill("activation-test@example.com");
  await page.getByRole("button", { name: "Create invitation link" }).click();
  const oldLink = await page.getByLabel("Invitation link").inputValue();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close dialog", exact: true })
    .click();
  await page.getByRole("button", { name: "Invitations", exact: true }).click();
  await expect(page.locator(".invitation-row")).toContainText("pending");
  await page.getByRole("button", { name: "Replace link", exact: true }).click();
  await expect(page.getByLabel("Invitation link")).not.toHaveValue(oldLink);
  const newLink = await page.getByLabel("Invitation link").inputValue();
  await expect(
    page.locator(".invitation-row").filter({ hasText: "revoked" }),
  ).toHaveCount(1);
  const guest = await page.context().browser()!.newContext();
  const invitee = await guest.newPage();
  await invitee.goto(oldLink);
  await expect(invitee.getByRole("alert")).toContainText("revoked");
  await invitee.goto(newLink);
  await expect(invitee.getByLabel("Your name")).toHaveValue("Kavya Shift");
  await expect(invitee.getByLabel("Organization type")).toHaveCount(0);
  await guest.close();
  await page
    .getByRole("button", { name: "Cancel invitation", exact: true })
    .click();
  await expect(
    page.locator(".invitation-row").filter({ hasText: "revoked" }),
  ).toHaveCount(2);
  await page
    .getByRole("button", { name: "Access history", exact: true })
    .click();
  await expect(
    page.getByText("Browser Owner · invitation replaced", { exact: true }),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../artifacts/team-management.png",
    fullPage: true,
  });
});
async function signup(page: Page, industry = "manufacturing") {
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Browser Owner");
  await page
    .getByLabel("Email address")
    .fill(`owner-${Date.now()}-${Math.random()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-test-password");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("browser-test-password");
  await choose(page.getByLabel("Organization type"), industry);
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Keep your recovery codes." }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "I’ve saved my codes · Open workspace" })
    .click();
  await page.getByRole("button", { name: "Finish later", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Shift overview" }),
  ).toBeVisible();
}
async function addItem(page: Page, label: string, id: string) {
  await page.getByRole("button", { name: "Add " + label, exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Identifier", { exact: true }).fill(id);
  await dialog.getByLabel("Name", { exact: true }).fill("Evidence test item");
  await dialog
    .getByRole("button", { name: "Create " + label, exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  await page.locator(".item-card").filter({ hasText: id }).click();
}

test("landing has eight industries, accessible fallback and independent account routes", async ({
  page,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      type: string,
      ...args: unknown[]
    ) {
      if (type.startsWith("webgl")) return null;
      return (original as Function).call(this, type, ...args);
    } as typeof original;
  });
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "Work changes hands. The details shouldn’t.",
    }),
  ).toBeVisible();
  await expect(page.locator(".industry-picker button")).toHaveCount(8);
  await page
    .getByRole("button", { name: "Equipment maintenance Working workflow" })
    .click();
  await expect(page.locator(".scene-report")).toContainText("Machine running");
  await expect(page.locator(".scene-fallback")).toContainText(
    "An unresolved issue stays visible",
  );
  await page
    .getByRole("button", { name: "Healthcare Planned workflow" })
    .click();
  await expect(page.locator(".availability")).toContainText("Preview");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "How would you like to sign in?" }),
  ).toBeVisible();
});

test("real signup, private workspace, invitations, switching and preview organization", async ({
  page,
}) => {
  await signup(page);
  await expect(
    page.getByText("This workspace contains no fictional reports.", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Team", exact: true }).click();
  await page
    .getByRole("button", { name: "Add team member", exact: true })
    .click();
  await choose(page
    .getByRole("dialog")
    .locator(".role-choice select"), "email");
  await page.getByLabel("Team member name").fill("Invited Reviewer");
  await page.getByLabel("Email address").fill("invited-worker@example.com");
  await choose(page
    .locator("form")
    .last()
    .getByLabel("Operational role"), "quality");
  await page.getByRole("button", { name: "Create invitation link" }).click();
  await expect(page.getByLabel("Invitation link")).toHaveValue(/\/join\//);
  const invite = await page.getByLabel("Invitation link").inputValue();
  const guest = await page.context().browser()!.newContext();
  const worker = await guest.newPage();
  await worker.goto(invite);
  await worker.getByLabel("Your name").fill("Invited Reviewer");
  await worker.getByLabel("Email address").fill("invited-worker@example.com");
  await worker
    .getByLabel("Password", { exact: true })
    .fill("another-long-password");
  await worker
    .getByLabel("Confirm password", { exact: true })
    .fill("another-long-password");
  await worker.getByRole("button", { name: "Create account and join" }).click();
  await worker
    .getByRole("link", { name: "I’ve saved my codes · Open workspace" })
    .click();
  await expect(worker.locator(".organization-person")).toContainText(
    "Authorized reviewer",
  );
  await guest.close();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Close dialog", exact: true })
    .click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByRole("button", { name: "Locations & teams", exact: true })
    .click();
  await page.getByRole("button", { name: "Add location", exact: true }).click();
  const locationForm = page.getByRole("dialog");
  await locationForm.getByLabel("Name", { exact: true }).fill("Main plant");
  await locationForm.getByRole("button", { name: "Add location" }).click();
  await expect(page.locator(".operations-setup")).toContainText("Saved.");
  await page.getByRole("button", { name: "My account", exact: true }).click();
  await page
    .getByRole("button", { name: "Create another organization" })
    .click();
  await page.getByText("Create an organization", { exact: true }).click();
  await page
    .getByLabel("Organization name", { exact: true })
    .fill("Future Clinic");
  await choose(page.getByLabel("Organization type"), "healthcare");
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Healthcare is on the roadmap." }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Record update" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Locations & teams", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Recording & data", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Edit", exact: true }),
  ).toBeEnabled();
  await choose(page
    .getByLabel("Switch organization"), { label: "Browser Owner’s workspace" });
  await expect(page.getByText("Start with your first batch.")).toBeVisible();
});
for (const variant of [
  {
    industry: "manufacturing",
    item: "batch",
    id: "CARTON-77",
    property: "quality",
    value: "pending",
  },
  {
    industry: "maintenance",
    item: "asset",
    id: "PUMP-42",
    property: "fault",
    value: "open",
  },
  {
    industry: "warehousing",
    item: "order",
    id: "ORDER-582",
    property: "documents",
    value: "pending",
  },
]) {
  test(`${variant.industry} saved transcript recovery and handover`, async ({
    page,
  }) => {
    await signup(page, variant.industry);
    await addItem(page, variant.item, variant.id);
    await page
      .getByLabel("Transcript", { exact: true })
      .fill("Inspection issue remains pending");
    await page.getByRole("button", { name: "Send update" }).click();
    await expect(
      page.getByRole("button", { name: "Interpret transcript manually" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Interpret transcript manually" })
      .click();
    const d = page.getByRole("dialog");
    const row = d.locator(`[data-property="${variant.property}"]`);
    await choose(row.getByLabel("Status stated in the recording"), variant.value);
    await choose(row.getByLabel("Your check"), "correct");
    await d.getByLabel("Explain if needed").fill("The original source reports an unresolved inspection issue");
    await d.getByRole("button", { name: "Save checked updates" }).click();
    await expect(d).toHaveCount(0);
    await expect(page.locator(".claim-row")).toContainText("Human-reviewed");
    await page.getByRole("button", { name: "Evidence & history" }).first().click();
    await expect(d).toContainText("The original source reports an unresolved inspection issue");
    await d.getByRole("button", { name: "Close" }).click();
    // A submitted manual-review report is no longer an unsent capture draft.
    await page.getByRole("button", { name: "Handover", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Keep your unfinished update?" })).toHaveCount(0);
    await expect(page.locator(".handover-item")).toContainText(
      "Unresolved hold",
    );
    await page
      .getByLabel("Your readback")
      .fill(
        "This inspection must be verified before the work is considered complete",
      );
    await page.getByRole("button", { name: /^Acknowledge v/ }).click();
    await expect(
      page.getByText("Acknowledged the exact stored snapshot."),
    ).toBeVisible();
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await page.getByRole("button", { name: "Downloads", exact: true }).click();
    const downloadEvent = page.waitForEvent("download");
    await page
      .getByRole("button", { name: "Download organization data" })
      .click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toMatch(/^shiftproof-org_.*\.json$/);
    const { readFile } = await import("node:fs/promises");
    const exported = JSON.parse(
      await readFile((await download.path())!, "utf8"),
    );
    expect(Object.keys(exported.claims)).toHaveLength(1);
    expect(Object.keys(exported.acknowledgements)).toHaveLength(1);
    if (variant.industry === "manufacturing") {
      await page
        .getByRole("button", { name: "Record update", exact: true })
        .click();
      await page
        .getByRole("button", { name: "Correct saved transcript" })
        .click();
      await d
        .getByLabel("Revised transcript")
        .fill("Inspection issue remains pending. Packing complete.");
      await d.getByRole("button", { name: "Save transcript revision" }).click();
      await expect(d).toHaveCount(0);
      await page.getByRole("button", { name: "Retry saved note" }).click();
      await expect(
        page.getByRole("button", { name: "Interpret transcript manually" }),
      ).toBeVisible();
      await page.getByRole("button", { name: "Evidence & history" }).click();
      await expect(d).toContainText("Transcript v2");
      await expect(d).toContainText("Human-reviewed");
      await expect(d).toContainText("The original source reports an unresolved inspection issue");
      await d.getByRole("button", { name: "Close" }).click();
      await page.getByRole("button", { name: "Handover", exact: true }).click();
      await expect(page.locator(".handover-item")).toContainText(
        "Unresolved hold",
      );
    }
  });
}

test("private voice capture saves WAV, pauses for transcript inspection and reuses its note", async ({
  page,
}) => {
  await signup(page);
  await addItem(page, "batch", "VOICE-1");
  await page.route("**/api/organizations/*/notes/*/process", async (route) => {
    if (!route.request().postDataJSON()?.transcribe_only)
      return route.continue();
    const session = await page.request.get("/api/auth/session");
    const csrf = (await session.json()).csrf_token;
    const r = await page.request.post(
      route
        .request()
        .url()
        .replace(/\/process$/, "/transcript"),
      {
        headers: { "X-CSRF-Token": csrf },
        data: { transcript: "Packing complete nahi hai." },
      },
    );
    expect(r.ok()).toBeTruthy();
    return route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ job_id: route.request().url().split("/").at(-2) }),
    });
  });
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(page.locator(".record-caption")).toHaveText(
    /^[2-9] \/ 45 seconds$/,
  );
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await page.getByRole("button", { name: "Upload & transcribe" }).click();
  await expect(page.getByLabel("Transcript", { exact: true })).toHaveValue(
    "Packing complete nahi hai.",
  );
  await page.getByRole("button", { name: "Send update" }).click();
  await expect(page.locator(".claim-row")).toContainText("pending");
  await expect(page.locator(".report-card")).toHaveCount(1);
});

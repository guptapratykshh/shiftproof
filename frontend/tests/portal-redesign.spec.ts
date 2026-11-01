import { choose } from './controls';
import { test, expect, type Page } from "./fixtures";
import fs from "node:fs";
async function account(page: Page) {
  const r = await page.request.post("/api/auth/signup", {
    data: {
      name: "Meera Sharma",
      email: `portal-${Date.now()}-${Math.random()}@example.com`,
      password: "portal-long-test-password",
      industry: "manufacturing",
    },
  });
  expect(r.ok()).toBeTruthy();
  const { organization_id: org } = await r.json();
  const session = await (await page.request.get("/api/auth/session")).json();
  const post = async (path: string, data: unknown, method = "POST") => {
    const r = await page.request.fetch(`/api/organizations/${org}${path}`, {
      method,
      headers: { "X-CSRF-Token": session.csrf_token },
      data,
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  return { org, session, post };
}
async function shot(page: Page, name: string) {
  fs.mkdirSync("../artifacts/portal", { recursive: true });
  await page.screenshot({
    path: `../artifacts/portal/${name}.png`,
    fullPage: true,
  });
}
test("guided setup resumes saved entities without duplication and assigns the first shift", async ({
  page,
}) => {
  const { org } = await account(page);
  await page.goto(`/app/${org}?view=setup`);
  await page.getByLabel("Location name", { exact: true }).fill("Packing floor");
  await page
    .getByRole("button", { name: "Save and continue", exact: true })
    .click();
  await expect(page.getByLabel("Team name", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Finish later", exact: true }).click();
  await expect(page).toHaveURL(/view=overview/);
  await page.reload();
  await page
    .getByRole("button", { name: "Continue setup", exact: true })
    .click();
  await expect(page.getByLabel("Team name", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Back", exact: true }).click();
  await expect(
    page.getByRole("combobox", { name: "Location", exact: true }).locator("..").locator("select"),
  ).toHaveValue(/location_/);
  await page
    .getByRole("button", { name: "Save and continue", exact: true })
    .click();
  await page.getByLabel("Team name", { exact: true }).fill("Packing team");
  await page.getByLabel("Identifier", { exact: true }).fill("CARTON-17");
  await page
    .getByLabel("Work item name", { exact: true })
    .fill("Corrugated cartons");
  await page
    .getByRole("button", { name: "Save and continue", exact: true })
    .click();
  await page.getByLabel("Shift name", { exact: true }).fill("Evening shift");
  await page.getByLabel("Starts", { exact: true }).fill("2027-01-15T16:00");
  await page.getByLabel("Ends", { exact: true }).fill("2027-01-16T00:00");
  await page
    .getByRole("button", { name: "Save and continue", exact: true })
    .click();
  await expect(
    page.getByText("Invited people are not active", { exact: false }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Continue to recording setup", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save data policy", exact: true })
    .click();
  await expect(
    page.getByText("Data policy saved.", { exact: false }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Finish setup", exact: true }).click();
  const ops = await (
    await page.request.get(`/api/organizations/${org}/operations`)
  ).json();
  expect(ops.locations).toHaveLength(1);
  expect(ops.teams).toHaveLength(1);
  expect(ops.shifts).toHaveLength(1);
  expect(ops.assignments[0].work_item_ids).toEqual(["CARTON-17"]);
  await expect(page.locator(".item-card")).toContainText("CARTON-17");
});
test("settings sections restore on refresh and Back; checkboxes stay beside their labels", async ({
  page,
}) => {
  const { org } = await account(page);
  await page.goto(`/app/${org}?view=settings&section=recording`);
  await expect(
    page.getByRole("heading", {
      name: "Recording and data policy",
      exact: true,
    }),
  ).toBeVisible();
  const boxes = page.getByRole("checkbox");
  expect(await boxes.count()).toBe(4);
  for (const box of await boxes.all()) {
    const b = await box.boundingBox();
    expect(b!.width).toBeLessThanOrEqual(24);
    expect(b!.height).toBeLessThanOrEqual(24);
    const label = await box.locator("..").boundingBox();
    expect(Math.abs(b!.y - label!.y)).toBeLessThan(20);
  }
  await page.getByText("Factory approval obtained", { exact: true }).click();
  await expect(boxes.first()).toBeChecked();
  await page.getByRole("button", { name: "Downloads", exact: true }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  await page.reload();
  await expect(page).toHaveURL(/section=downloads/);
  await expect(
    page.getByRole("button", {
      name: "Download organization data",
      exact: true,
    }),
  ).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(/section=recording/);
  await expect(page.getByRole("checkbox")).toHaveCount(4);
  await page.goto(`/app/${org}?view=invalid&section=invalid`);
  await expect(page).toHaveURL(/view=overview/);
});
test("saved recording policy can be edited again after refresh", async ({ page }) => {
  const { org } = await account(page);
  await page.goto(`/app/${org}?view=settings&section=recording`);
  for (const days of [45, 60]) {
    await page.getByLabel("Retention days", { exact: true }).fill(String(days));
    const response = page.waitForResponse(r => r.url().endsWith("/pilot-policy") && r.request().method() === "PUT");
    await page.getByRole("button", { name: "Save data policy", exact: true }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByText("Data policy saved.", { exact: false })).toBeVisible();
    await page.reload();
    await expect(page.getByLabel("Retention days", { exact: true })).toHaveValue(String(days));
    await expect(page.getByRole("combobox", { name: /^Data mode/ }).locator("..").locator("select")).toHaveValue("fictional");
  }
});
test("portal screenshots cover pages, languages and responsive layouts", async ({
  page,
}) => {
  test.setTimeout(180000);
  const { org, post } = await account(page);
  await post("/work-items", {
    id: "B-17",
    name: "Corrugated cartons",
    target: 50,
  });
  const pages = ["overview", "capture", "handover", "team", "settings"];
  for (const lang of ["en", "hi"]) {
    await page.goto(`/app/${org}`);
    if (lang === "hi")
      await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
    for (const width of [390, 768, 1440, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      for (const view of pages) {
        await page.goto(`/app/${org}?view=${view}`);
        await expect(page.locator(".workspace-heading h1")).toBeVisible();
        await expect(page.locator(".organization-main")).toBeVisible();
        expect(
          await page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
          `${view} ${lang} ${width}`,
        ).toBeTruthy();
        await shot(page, `${lang}-${view}-${width}`);
      }
    }
    for (const section of ["places", "shifts", "recording", "downloads"]) {
      await page.goto(`/app/${org}?view=settings&section=${section}`);
      await expect(page.locator(".settings-page")).toBeVisible();
      await shot(page, `${lang}-settings-${section}`);
    }
  }
  await page.setViewportSize({ width: 768, height: 900 });
  await page.goto(`/app/${org}?view=team`);
  await page.getByRole("button", { name: "English", exact: true }).click();
  await page.getByRole("button", { name: "Menu", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Overview", exact: true }),
  ).toBeVisible();
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement?.tagName)).toBe(
    "BUTTON",
  );
  await page.evaluate(() => {
    document.documentElement.style.zoom = "2";
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await shot(page, "team-200-percent");
});
test("member permissions are opened one at a time and keyboard dismissal returns focus", async ({
  page,
}) => {
  const { org } = await account(page);
  await page.goto(`/app/${org}?view=team`);
  await expect(page.locator(".team-member")).toHaveCount(1);
  await expect(page.locator('select[name="role"]')).toHaveCount(0);
  await page.getByRole("button", { name: "Manage", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(1);
  await expect(
    page.getByRole("dialog").getByLabel("Operational role").locator("..").locator("select"),
  ).toHaveValue("supervisor");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Manage", exact: true }),
  ).toBeFocused();
  await page
    .getByLabel("Find a team member", { exact: true })
    .fill("not-present");
  await expect(page.locator(".team-member")).toHaveCount(0);
});

test("Back never discards an unfinished update and can be retried after Stay", async ({
  page,
}) => {
  const { org, post } = await account(page);
  await post("/work-items", {
    id: "B-17",
    name: "Corrugated cartons",
    target: 50,
  });
  await page.goto(`/app/${org}`);
  await page.locator(".item-card").click();
  await page
    .getByLabel("Transcript", { exact: true })
    .fill("Keep this unfinished update.");
  await page.goBack();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.getByRole("button", { name: "Stay here", exact: true }).click();
  await expect(page).toHaveURL(/view=capture/);
  await expect(page.getByLabel("Transcript", { exact: true })).toHaveValue(
    "Keep this unfinished update.",
  );
  await page.goBack();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page
    .getByRole("button", { name: "Save draft and leave", exact: true })
    .click();
  await expect(page).toHaveURL(/view=overview/);
  await expect(page.locator(".draft-drawer")).toContainText("B-17");
});

test("populated report, recovery, review and evidence screens preserve the hold", async ({
  page,
}) => {
  test.setTimeout(60000);
  page.on("dialog", (d) => void d.accept());
  const { org, post } = await account(page);
  await post("/work-items", {
    id: "B-17",
    name: "Corrugated cartons",
    target: 50,
  });
  await page.goto(`/app/${org}`);
  await page.locator(".item-card").click();
  await page
    .getByLabel("Transcript", { exact: true })
    .fill("Seal problem still needs inspection.");
  await page.getByRole("button", { name: "Send update", exact: true }).click();
  await expect(
    page.getByRole("button", {
      name: "Interpret transcript manually",
      exact: true,
    }),
  ).toBeVisible();
  await shot(page, "en-capture-recovery");
  await page
    .getByRole("button", { name: "Interpret transcript manually", exact: true })
    .click();
  const d = page.getByRole("dialog");
  const row = d.locator('[data-property="quality"]');
  await choose(row.getByLabel("Status stated in the recording"), "pending");
  await choose(row.getByLabel("Your check"), "correct");
  await d.getByLabel("Explain if needed").fill("The source reports a seal problem requiring inspection.");
  await shot(page, "en-review-dialog");
  await d.getByRole("button", { name: "Save checked updates" }).click();
  await expect(d).toHaveCount(0);
  await expect(page.locator(".claim-row")).toContainText("Human-reviewed");
  await page.getByRole("button", { name: "Evidence & history", exact: false }).first().click();
  await expect(d.locator(".evidence-timeline li")).not.toHaveCount(0);
  await shot(page, "en-evidence-timeline");
  await d.getByRole("button", { name: "Close dialog", exact: true }).click();
  await page
    .getByRole("button", { name: "Start a new update", exact: true })
    .click();
  await page.getByRole("button", { name: "Handover", exact: true }).click();
  await expect(page.locator(".handover-item")).toContainText("Unresolved hold");
  await shot(page, "en-handover-populated");
  await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
  await shot(page, "hi-handover-populated");
  await page.goto(`/app/${org}?view=capture`);
  await expect(page.locator(".claim-row")).toBeVisible();
  await shot(page, "hi-capture-populated");
  await page
    .getByRole("button", { name: "मूल जानकारी और इतिहास", exact: false })
    .first()
    .click();
  await shot(page, "hi-evidence-timeline");
});

test("account, preview and access states remain compact and translated", async ({
  page,
}) => {
  test.setTimeout(60000);
  const { org } = await account(page);
  for (const lang of ["en", "hi"]) {
    await page.goto(`/app/${org}`);
    await expect(page.locator(".workspace-heading")).toBeVisible();
    if (lang === "hi")
      await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });
    for (const path of [
      "/login",
      "/signup",
      "/recover",
      "/worker/login",
      "/join/expired-example-link",
      "/organizations",
    ]) {
      await page.goto(path);
      await expect(page.locator("main")).toBeVisible();
      await shot(page, `${lang}-account-${path.replaceAll("/", "-")}`);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBeTruthy();
    }
    await page.goto(`/app/${org}?view=setup`);
    await expect(page.locator(".setup-wizard")).toBeVisible();
    await shot(page, `${lang}-setup-mobile`);
    await page.goto("/app/org_unavailable");
    await expect(page.getByRole("alert")).toBeVisible();
    await shot(page, `${lang}-access-restricted`);
  }
});

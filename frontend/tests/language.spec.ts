import { choose } from './controls';
import { createOrganization } from "./workspace-fixture";
import { test, expect, type Page } from "./fixtures";
import fs from "node:fs";
async function englishFragments(page: Page, name: string) {
  const labels = await page.locator("body").evaluate((el) => {
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    const out = [];
    while (walker.nextNode()) {
      const n = walker.currentNode;
      const p = n.parentElement;
      if (
        p &&
        p.getClientRects().length &&
        !["SCRIPT", "STYLE", "OPTION"].includes(p.tagName) &&
        /[A-Za-z]{3}/.test(n.textContent || "")
      )
        out.push(n.textContent?.trim());
    }
    return out;
  });
  fs.mkdirSync("../.local/i18n/screens", { recursive: true });
  fs.writeFileSync(
    "../.local/i18n/screens/" + name + ".json",
    JSON.stringify(labels, null, 2),
  );
}
test("Hindi preference covers public pages, mobile signup and survives reload", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "हिन्दी में बदलें" }).click();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page).toHaveTitle("ShiftProof | हर शिफ्ट को पूरी जानकारी");
  await englishFragments(page, "landing");
  await page.goto("/signup");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Switch to English" }),
  ).toBeVisible();
  await englishFragments(page, "signup");
  await expect(page.getByLabel("संगठन का प्रकार").locator("..").locator("select")).toHaveValue("manufacturing");
  await expect(
    page.getByLabel("संगठन का प्रकार").locator("..").locator("select").locator("option:checked"),
  ).toHaveText("फैक्ट्री उत्पादन");
  await expect(page.getByLabel("आपका नाम")).toBeVisible();
  await page.getByLabel("पासवर्ड", { exact: true }).fill("password123456");
  await page
    .getByLabel("पासवर्ड फिर से लिखें", { exact: true })
    .fill("different password");
  await expect(
    page.getByText("दोनों पासवर्ड एक जैसे नहीं हैं।", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page).toHaveTitle("ShiftProof | हर शिफ्ट को पूरी जानकारी");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../artifacts/hindi-signup-mobile.png",
    fullPage: true,
  });
  await page.goto("/login");
  await englishFragments(page, "login");
  await page.getByRole("button", { name: "Switch to English" }).click();
  await expect(page.getByRole("heading", { name: "Sign in to ShiftProof" })).toBeVisible();
});
test("Hindi owner workspace covers operational and administration pages without translating user data", async ({
  page,
}) => {
  page.on("dialog", (d) => d.accept());
  await page.goto("/signup");
  await page.getByLabel("Your name").fill("Machine Pending");
  await page
    .getByLabel("Email address")
    .fill(`hindi-${Date.now()}@example.com`);
  await page
    .getByLabel("Password", { exact: true })
    .fill("language-test-password");
  await page
    .getByLabel("Confirm password", { exact: true })
    .fill("language-test-password");
  await page
    .getByRole("button", { name: "Create organization", exact: true })
    .click();
  await page
    .getByRole("link", { name: "I’ve saved my codes · Open workspace" })
    .click();
  await page.getByRole("button", { name: "Finish later", exact: true }).click();
  await page.getByRole("button", { name: "Add batch", exact: true }).click();
  await page.getByLabel("Identifier", { exact: true }).fill("HI-17");
  await page.getByLabel("Name", { exact: true }).fill("Packing Complete");
  await page.getByRole("button", { name: "Create batch", exact: true }).click();
  await page.getByRole("button", { name: "हिन्दी", exact: true }).click();
  await expect(
    page.getByText("Packing Complete", { exact: true }).first(),
  ).toBeVisible();
  await expect(page.locator(".current-organization")).toContainText(
    "Machine Pending",
  );
  await englishFragments(page, "overview");
  await page.screenshot({
    path: "../artifacts/hindi-workspace.png",
    fullPage: true,
  });
  const nav = page.locator("aside nav button");
  const count = await nav.count();
  expect(count).toBeGreaterThan(2);
  for (let i = 0; i < count; i++) {
    await nav.nth(i).click();
    await page
      .locator("details")
      .evaluateAll((nodes) =>
        nodes.forEach((n) => ((n as HTMLDetailsElement).open = true)),
      );
    await englishFragments(page, `workspace-${i}`);
    await expect(page.locator(".workspace-heading h1")).toContainText(
      /[\u0900-\u097f]/,
    );
    if ((await nav.nth(i).innerText()).trim() === "टीम")
      await expect(
        page.getByRole("button", { name: "टीम सदस्य जोड़ें", exact: true }),
      ).toBeVisible();
    if ((await nav.nth(i).innerText()).trim() === "सेटिंग्स")
      await expect(
        page.getByRole("button", { name: "सामान्य", exact: true }),
      ).toBeVisible();
  }
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("lang", "hi");
  await expect(page).toHaveTitle("ShiftProof | हर शिफ्ट को पूरी जानकारी");
});

test("Hindi review preserves API enum values, entered text and source evidence", async ({ page }) => {
  const { organization, call } = await createOrganization(page);
  const transcript = "Packing will be complete tomorrow. Inspect seal tomorrow.";
  const note = await call('/notes', { batch_id: 'B-17', recorded_at: new Date().toISOString(), idempotency_key: 'hindi-source-'+Date.now() });
  await call(`/notes/${note.note.id}/transcript`, { transcript });
  await call(`/notes/${note.note.id}/process`, {});
  await page.goto(`/app/${organization}?view=reports`);
  await page.getByRole('button', { name: 'हिन्दी', exact: true }).click();
  await page.getByRole('button', { name: 'सुनें और जाँचें', exact: true }).click();
  const dialog = page.getByRole('dialog');
  const packing = dialog.locator('section').filter({ has: page.getByRole('heading', { name: 'पैकिंग पूरी हुई?', exact: true }) });
  await expect(packing).toBeVisible();
  await choose(packing.getByRole('combobox').nth(0), 'complete');
  await choose(packing.getByRole('combobox').nth(1), 'cannot');
  await packing.locator('summary').click();
  await packing.getByLabel('रिकॉर्डिंग के ठीक वही शब्द').fill('Packing will be complete tomorrow.');
  await choose(packing.getByRole('combobox').nth(2), 'planned');
  await dialog.getByLabel('ज़रूरत हो तो कारण लिखें').fill('Human wording remains original');
  const sent = page.waitForRequest(r => r.method()==='POST' && r.url().endsWith('/review'));
  await dialog.getByRole('button', { name: 'जाँचे हुए अपडेट सहेजें' }).click();
  expect((await sent).postDataJSON().decisions[0]).toMatchObject({ action: 'draft', candidate: { property:'packing', value:'complete', modality:'planned', excerpt:'Packing will be complete tomorrow.' } });
  await expect(dialog).toHaveCount(0);
  await expect(page.locator('.report-list-row')).toContainText(transcript);
  await page.getByRole('button', { name:'English', exact:true }).click();
  await expect(page.locator('.report-list-row')).toContainText(transcript);
});

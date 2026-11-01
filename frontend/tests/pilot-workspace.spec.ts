import { choose } from './controls';
import { test, expect, type Page } from "./fixtures";
test.use({ timezoneId: "UTC" });

async function setup(page: Page) {
  const suffix = Date.now() + "-" + Math.random().toString(36).slice(2, 6);
  const response = await page.request.post("/api/auth/signup", {
    data: {
      name: "Pilot Owner",
      email: `pilot-${suffix}@example.com`,
      password: "pilot-owner-long-password",
      industry: "manufacturing",
    },
  });
  expect(response.ok()).toBeTruthy();
  const account = await response.json();
  const org = account.organization_id;
  const session = await (await page.request.get("/api/auth/session")).json();
  const headers = { "X-CSRF-Token": session.csrf_token };
  const post = async (path: string, data: unknown, method = "POST") => {
    const r = await page.request.fetch(`/api/organizations/${org}${path}`, {
      method,
      headers,
      data,
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  const location = await post("/locations", { name: "Packing floor" });
  const team = await post("/teams", {
    name: "Carton team",
    location_id: location.id,
  });
  const first = await post("/work-items", {
    id: "CARTON-A",
    name: "Carton batch A",
    target: 50,
    location_id: location.id,
    team_id: team.id,
  });
  await post("/work-items", {
    id: "CARTON-B",
    name: "Carton batch B",
    target: 100,
    location_id: location.id,
    team_id: team.id,
  });
  const shift = await post("/shift-occurrences", {
    name: "Today evening",
    starts_at: new Date(Date.now() - 3600000).toISOString(),
    ends_at: new Date(Date.now() + 7 * 3600000).toISOString(),
    location_id: location.id,
    team_id: team.id,
  });
  await post(
    `/shift-occurrences/${shift.id}/assignments`,
    {
      user_ids: [session.user.id],
      supervisor_id: session.user.id,
      work_item_ids: ["CARTON-A", "CARTON-B"],
    },
    "PUT",
  );
  await page.goto("/app/" + org);
  return { org, shift, session, post, first };
}

test("capture context cannot change while recording and saved drafts recover without sending", async ({
  page,
  context,
}) => {
  const { org } = await setup(page);
  await page.locator(".item-card").filter({ hasText: "CARTON-A" }).click();
  let submitted = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === `/api/organizations/${org}/notes`
    )
      submitted++;
  });
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Stop recording", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(
    page.getByText("Finish recording or sending before changing pages."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Stop recording", exact: true }),
  ).toBeVisible();
  // Capture actual PCM before stopping; an empty sub-second click is no longer a valid recording.
  await page.waitForTimeout(1200);
  await page
    .getByRole("button", { name: "Stop recording", exact: true })
    .click();
  await expect(page.locator(".local-save-status")).toContainText(
    "Saved on this device",
  );
  await context.setOffline(true);
  await expect(
    page.getByRole("button", { name: "Upload & transcribe" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "Keep your unfinished update?",
  );
  await page
    .getByRole("button", { name: "Save draft and leave", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await context.setOffline(false);
  await page.reload();
  await page.locator(".draft-drawer summary").click();
  await expect(page.locator(".draft-drawer")).toContainText("CARTON-A");
  await page.getByRole("button", { name: "Open draft", exact: true }).click();
  await expect(page.locator(".item-select select")).toHaveValue("CARTON-A");
  await expect(page.locator(".capture-panel audio")).toBeVisible();
  expect(submitted).toBe(0);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page
    .getByRole("button", { name: "Save draft and leave", exact: true })
    .click();
  await page.locator(".item-card").filter({ hasText: "CARTON-B" }).click();
  await expect(page.locator(".item-select select")).toHaveValue("CARTON-B");
  await expect(page.locator(".capture-panel audio")).toHaveCount(0);
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.screenshot({
    path: "../artifacts/pilot-supervisor-overview.png",
    fullPage: true,
  });
});

test("employee activation opens a Hindi worker workspace with assigned work and no administrative controls", async ({
  page,
  browser,
}) => {
  const { org, post, shift, session } = await setup(page);
  const invitation = await post("/worker-invitations", {
    name: "सीमा कुमार",
    employee_id: "EMP-017",
  });
  const workerContext = await browser.newContext({
    storageState: { cookies: [], origins: [] },
    viewport: { width: 390, height: 844 },
    permissions: ["microphone"],
  });
  const worker = await workerContext.newPage();
  await worker.goto(new URL(invitation.join_path, page.url()).toString());
  await worker
    .getByLabel("पासवर्ड", { exact: true })
    .fill("worker-long-password");
  await worker
    .getByLabel("पासवर्ड फिर से लिखें", { exact: true })
    .fill("worker-long-password");
  await worker.getByRole("button", { name: "आगे बढ़ें", exact: true }).click();
  await expect(worker).toHaveURL(new RegExp(`/app/${org}(\\?|$)`));
  const employee = await (await worker.request.get("/api/auth/session")).json();
  await post(
    `/shift-occurrences/${shift.id}/assignments`,
    {
      user_ids: [session.user.id, employee.user.id],
      supervisor_id: session.user.id,
      work_item_ids: ["CARTON-A", "CARTON-B"],
    },
    "PUT",
  );
  await worker.reload();
  await expect(
    worker.getByRole("button", { name: "अपडेट बोलें", exact: true }),
  ).toBeVisible();
  await expect(worker.locator(".organization-sidebar nav button")).toHaveCount(
    3,
  );
  await expect(
    worker.getByRole("button", { name: "People & access", exact: true }),
  ).toHaveCount(0);
  await expect(
    worker.getByRole("button", { name: "Download organization data" }),
  ).toHaveCount(0);
  await worker.getByRole("button", { name: "अपडेट बोलें", exact: true }).click();
  await expect(worker.locator(".item-select select")).toHaveValue("CARTON-A");
  expect(
    (await worker.request.get(`/api/organizations/${org}/export`)).status(),
  ).toBe(403);
  expect(
    await worker.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await worker.screenshot({
    path: "../artifacts/pilot-worker-hindi-mobile.png",
    fullPage: true,
  });
  await worker.getByRole("button", { name: "English", exact: true }).click();
  await worker.getByRole("button", { name: "My work", exact: true }).click();
  await expect(worker.getByRole("heading", { name: "My work" })).toBeVisible();
  await worker.screenshot({
    path: "../artifacts/portal/en-worker-mywork-390.png",
    fullPage: true,
  });
  await worker.getByRole("button", { name: "Handover", exact: true }).click();
  await worker.screenshot({
    path: "../artifacts/portal/en-worker-handover-390.png",
    fullPage: true,
  });
  await worker
    .getByRole("button", { name: "Record readback", exact: true })
    .click();
  await expect(
    worker.getByRole("button", { name: /Stop · [2-9]s/ }),
  ).toBeVisible();
  await worker.getByRole("button", { name: /Stop ·/ }).click();
  await expect(worker.locator(".voice-ack audio")).toBeVisible();
  await worker
    .getByRole("button", {
      name: "I received this handover · confirm",
      exact: true,
    })
    .click();
  await expect(
    worker.getByText("Acknowledged by voice.", { exact: true }),
  ).toBeVisible();
  await expect(worker.locator(".reason-row audio")).toHaveCount(1);
  await workerContext.close();
});

test("empty membership account stays on account home instead of attempting a duplicate signup", async ({
  page,
}) => {
  await page.route("**/api/auth/session", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        user: {
          id: "no-membership",
          name: "Former member",
          email: "former@example.com",
        },
        csrf_token: "test",
        organizations: [],
        no_organization_access: true,
        capabilities: { create_organization: false, change_password: true },
      }),
    }),
  );
  await page.goto("/organizations");
  await expect(
    page.getByText(
      "Your account is active, but you do not currently belong to an organization.",
      { exact: false },
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Create organization", exact: true }),
  ).toHaveCount(0);
  await expect(page).toHaveURL(/\/organizations$/);
});

test("reloading during recording restores a playable checkpoint for the original item", async ({
  page,
}) => {
  page.on("dialog", (dialog) => void dialog.accept());
  const { org } = await setup(page);
  await page.locator(".item-card").filter({ hasText: "CARTON-A" }).click();
  let uploads = 0;
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === `/api/organizations/${org}/notes`
    )
      uploads++;
  });
  await page
    .getByRole("button", { name: "Start recording", exact: true })
    .click();
  await expect(page.locator(".local-save-status")).toContainText(
    "Recording checkpoint saved on this device.",
  );
  await page.reload();
  await page.locator(".draft-drawer summary").click();
  await page.getByRole("button", { name: "Open draft", exact: true }).click();
  await expect(page.locator(".item-select select")).toHaveValue("CARTON-A");
  const audio = page.locator(".capture-panel audio");
  await expect(audio).toBeVisible();
  await expect
    .poll(() => audio.evaluate((element: HTMLAudioElement) => element.duration))
    .toBeGreaterThan(0.5);
  expect(uploads).toBe(0);
});

test("shift entry uses the organization timezone and policy controls keep unconfigured capture disabled", async ({
  page,
}) => {
  const { org } = await setup(page);
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Shifts", exact: true }).click();
  await page
    .getByRole("button", { name: "Create dated shift", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toContainText("Asia/Kolkata");
  const form = page.locator("form").filter({
    has: page.getByRole("heading", { name: "3. Dated shift", exact: true }),
  });
  await form
    .getByLabel("Shift name", { exact: true })
    .fill("India night shift");
  await choose(form
    .getByRole("combobox", { name: "Location", exact: true }), { label: "Packing floor" });
  await choose(form
    .getByRole("combobox", { name: "Team", exact: true }), { label: "Carton team" });
  await form.getByLabel("Starts", { exact: true }).fill("2027-01-15T22:00");
  await form.getByLabel("Ends", { exact: true }).fill("2027-01-16T06:00");
  await choose(form
    .getByRole("combobox", { name: "Shift supervisor", exact: true }), { label: "Pilot Owner" });
  const sent = page.waitForRequest(
    (r) => r.method() === "POST" && r.url().endsWith("/shift-occurrences"),
  );
  await form.getByRole("button", { name: "Create dated shift" }).click();
  const body = (await sent).postDataJSON();
  expect(body.starts_at).toBe("2027-01-15T16:30:00.000Z");
  expect(body.ends_at).toBe("2027-01-16T00:30:00.000Z");
  await expect(
    page.getByText(
      "Saved. Assigned people can now find this shift and its work.",
    ),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Recording & data", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save data policy", exact: true })
    .click();
  await expect(
    page.getByText(
      "Data policy saved. Provider access remains subject to server configuration.",
    ),
  ).toBeVisible();
  await page.route(`**/api/organizations/${org}/workspace*`, async (route) => {
    const response = await route.fetch();
    const json = await response.json();
    json.capture_policy_ready = false;
    json.data_mode = "unconfigured";
    await route.fulfill({ response, json });
  });
  await page.reload();
  await page.getByRole("button", { name: "Overview", exact: true }).click();
  await page.locator(".item-card").filter({ hasText: "CARTON-A" }).click();
  await expect(
    page.getByRole("button", { name: "Start recording", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByText(
      "Ask the organization owner to choose a data policy in Settings before recording.",
    ),
  ).toBeVisible();
  expect(
    await page.evaluate(() =>
      localStorage.getItem("shiftproof-offline-capture-context-v1"),
    ),
  ).toBeNull();
});

test("an ended membership clears workspace records and cached offline identity", async ({
  page,
}) => {
  const { org } = await setup(page);
  await expect(page.locator(".item-card").first()).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(
        () => !!localStorage.getItem("shiftproof-offline-capture-context-v1"),
      ),
    )
    .toBeTruthy();
  await page.route(`**/api/organizations/${org}`, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Organization access ended" }),
    }),
  );
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.locator(".item-card")).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(() =>
        localStorage.getItem("shiftproof-offline-capture-context-v1"),
      ),
    )
    .toBeNull();
});

test("supervisor recovery imports a late text file without changing original authorship or inferring review", async ({
  page,
}) => {
  const { org, post, session, shift } = await setup(page);
  const old = await post("/shift-occurrences", {
    name: "Recovered night shift",
    starts_at: new Date(Date.now() - 100 * 3600000).toISOString(),
    ends_at: new Date(Date.now() - 92 * 3600000).toISOString(),
    location_id: shift.location_id,
    team_id: shift.team_id,
  });
  await post(
    `/shift-occurrences/${old.id}/assignments`,
    {
      user_ids: [session.user.id],
      supervisor_id: session.user.id,
      work_item_ids: ["CARTON-A"],
    },
    "PUT",
  );
  await page.locator(".item-card").filter({ hasText: "CARTON-A" }).click();
  await page.getByText("More actions", { exact: true }).click();
  await page
    .getByText("Recover an older offline report", { exact: true })
    .click();
  const original = {
    format: "shiftproof-offline-capture-v1",
    id: crypto.randomUUID(),
    userId: session.user.id,
    organizationId: org,
    itemId: "CARTON-A",
    shiftId: old.id,
    recordedAt: new Date(Date.now() - 99 * 3600000).toISOString(),
    transcript: "Packing complete hai, quality check abhi pending hai.",
    corrections: [],
    reply: null,
    audio_base64: null,
  };
  await page.getByLabel("Worker recovery file", { exact: true }).setInputFiles({
    name: "original-worker-report.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify(original)),
  });
  await page
    .getByLabel("Why is this late report being recovered?", { exact: true })
    .fill("Worker device stayed offline for several days.");
  const saved = page.waitForResponse(
    (r) =>
      r.request().method() === "POST" &&
      r.url().endsWith("/recovered-captures"),
  );
  await page
    .getByRole("button", { name: "Save recovery report", exact: true })
    .click();
  const result = await saved;
  expect(result.ok(), await result.text()).toBeTruthy();
  const data = await result.json();
  expect(data.note.actor.id).toBe(session.user.id);
  expect(data.note.shift_id).toBe(old.id);
  expect(data.note.transcripts[0].text).toBe(original.transcript);
  expect(data.note.supervised_import.original_actor_id).toBe(session.user.id);
  await expect(
    page.getByText(
      "Original report saved. Open it below to inspect or process the saved evidence. No review was inferred.",
    ),
  ).toBeVisible();
});

test("non-owner reviewer can review and recover existing notes but cannot coordinate work", async ({
  page,
  browser,
}) => {
  const { org, post, shift, session } = await setup(page);
  const note = await post("/notes", {
    batch_id: "CARTON-A",
    shift_id: shift.id,
    recorded_at: new Date().toISOString(),
    idempotency_key: crypto.randomUUID(),
  });
  await post(`/notes/${note.note.id}/transcript`, {
    transcript: "Packing complete. Quality cleared. Inspect seal.",
  });
  await post(`/notes/${note.note.id}/process`, {});
  await expect
    .poll(async () => {
      const r = await page.request.get(
        `/api/organizations/${org}/notes/${note.note.id}`,
      );
      return (await r.json()).status;
    })
    .toMatch(/manual_review|failed/);
  const workspace = await (
    await page.request.get(
      `/api/organizations/${org}/workspace?shift_id=${shift.id}`,
    )
  ).json();
  await post(`/notes/${note.note.id}/review-transcript`, {
    expected_version: workspace.version,
    reason: "Controlled supported interpretations for reviewer permissions",
    claims: [
      { property: "packing", value: "complete", excerpt: "Packing complete" },
      { property: "quality", value: "cleared", excerpt: "Quality cleared" },
      { property: "task", value: "Inspect seal", excerpt: "Inspect seal" },
    ],
  });
  await post("/notes", {
    batch_id: "CARTON-A",
    shift_id: shift.id,
    recorded_at: new Date().toISOString(),
    idempotency_key: crypto.randomUUID(),
  });
  const email = `reviewer-${Date.now()}@example.com`;
  const invite = await post("/invitations", {
    name: "Scoped Reviewer",
    email,
    role: "quality",
    access: "member",
  });
  const guest = await browser.newContext();
  const reviewer = await guest.newPage();
  const activation = await reviewer.request.post(
    new URL("/api/auth/signup", page.url()).toString(),
    {
      data: {
        name: "Scoped Reviewer",
        email,
        password: "reviewer-long-password",
        invitation_token: invite.join_path.split("/").at(-1),
      },
    },
  );
  expect(activation.ok(), await activation.text()).toBeTruthy();
  const account = await (
    await reviewer.request.get(
      new URL("/api/auth/session", page.url()).toString(),
    )
  ).json();
  await post(
    `/shift-occurrences/${shift.id}/assignments`,
    {
      user_ids: [session.user.id, account.user.id],
      supervisor_id: session.user.id,
      work_item_ids: ["CARTON-A"],
    },
    "PUT",
  );
  await reviewer.goto(new URL(`/app/${org}`, page.url()).toString());
  await expect(
    reviewer.getByRole("button", { name: "Add batch", exact: true }),
  ).toHaveCount(0);
  await reviewer.locator(".item-card").click();
  await expect(
    reviewer.getByRole("button", {
      name: "Edit work item details",
      exact: true,
    }),
  ).toHaveCount(0);
  await expect(
    reviewer.getByText("Recover an older offline report", { exact: true }),
  ).toHaveCount(0);
  await expect(
    reviewer.getByRole("button", { name: "Assign", exact: true }),
  ).toHaveCount(0);
  await expect(
    reviewer.getByText("Recover unfinished update", { exact: true }),
  ).toBeVisible();
  const clearance = reviewer
    .locator(".claim-row")
    .filter({ hasText: "quality: cleared" });
  await clearance
    .getByRole("button", { name: "Review report", exact: true })
    .click();
  const dialog=reviewer.getByRole("dialog");
  await choose(dialog.locator('[data-property="quality"]').getByLabel("Your check"), "correct");
  await dialog.getByLabel("Explain if needed").fill("Authorized reviewer checked this controlled clearance");
  await dialog.getByRole("button", {name:"Save checked updates"}).click();
  await expect(dialog).toHaveCount(0);
  await expect(clearance).toContainText("Human-reviewed");
  await guest.close();
});

test("password change retains local report drafts and logout always warns about every organization", async ({
  page,
}) => {
  const { org, session } = await setup(page);
  await page.locator(".item-card").filter({ hasText: "CARTON-A" }).click();
  await page
    .getByLabel("Transcript", { exact: true })
    .fill("This unfinished report must survive a password change.");
  await expect(page.locator(".local-save-status")).toContainText(
    "Saved on this device",
  );
  await page.getByRole("button", { name: "My account", exact: true }).click();
  await page
    .getByRole("dialog")
    .locator("summary")
    .filter({ hasText: "Change password" })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("Current password", { exact: true })
    .fill("pilot-owner-long-password");
  await dialog
    .getByLabel("New password", { exact: true })
    .fill("updated-pilot-long-password");
  await dialog
    .getByLabel("Confirm password", { exact: true })
    .fill("updated-pilot-long-password");
  await dialog
    .getByRole("button", { name: "Change password", exact: true })
    .click();
  await expect(page).toHaveURL(/\/login$/);
  const login = await page.request.post("/api/auth/login", {
    data: {
      email: session.user.email,
      password: "updated-pilot-long-password",
    },
  });
  expect(login.ok()).toBeTruthy();
  await page.goto(`/app/${org}`);
  await page.locator(".draft-drawer summary").click();
  await page.getByRole("button", { name: "Open draft", exact: true }).click();
  await expect(page.getByLabel("Transcript", { exact: true })).toHaveValue(
    "This unfinished report must survive a password change.",
  );
  let warning = "";
  page.once("dialog", async (dialog) => {
    warning = dialog.message();
    await dialog.dismiss();
  });
  await page
    .locator(".organization-person")
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  expect(warning).toContain("every organization");
  await expect(page).toHaveURL(new RegExp(`/app/${org}(\\?|$)`));
});

test("unfinished voice readback survives reload with its snapshot and requires explicit confirmation", async ({
  page,
}) => {
  await setup(page);
  page.on("dialog", (dialog) => void dialog.accept());
  await page.getByRole("button", { name: "Handover", exact: true }).click();
  let acknowledgements = 0;
  page.on("request", (r) => {
    if (
      r.method() === "POST" &&
      new URL(r.url()).pathname.endsWith("/acknowledgements")
    )
      acknowledgements++;
  });
  await page
    .getByRole("button", { name: "Record readback", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Stop · [2-9]s/ }),
  ).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: "Handover", exact: true }).click();
  await expect(page.locator(".voice-ack audio")).toBeVisible();
  expect(acknowledgements).toBe(0);
  await page
    .getByRole("button", {
      name: "I received this handover · confirm",
      exact: true,
    })
    .click();
  await expect(
    page.getByText("Acknowledged by voice.", { exact: true }),
  ).toBeVisible();
  expect(acknowledgements).toBe(1);
});

test('expired shift warns before recording and wrong-shift draft recovery keeps audio', async ({page,browser})=>{
  const {org,post,shift,session}=await setup(page);
  const old=await post('/shift-occurrences',{name:'Old PG shift',location_id:shift.location_id,team_id:shift.team_id,starts_at:new Date(Date.now()-14*86400000).toISOString(),ends_at:new Date(Date.now()-13*86400000).toISOString()});
  const invite=await post('/worker-invitations',{name:'Recovery worker',employee_id:'RECOVERY-1'});
  const wc=await browser.newContext({storageState:{cookies:[],origins:[{origin:'http://127.0.0.1:5174',localStorage:[{name:'shiftproof-language',value:'en'}]}]}});
  const worker=await wc.newPage();
  try {
    const activation=await worker.request.post('/api/auth/worker/activate',{data:{token:invite.join_path.split('/').pop(),password:'recovery-worker-password'}});
    expect(activation.ok()).toBeTruthy();
    const ws=await(await worker.request.get('/api/auth/session')).json();
    await post(`/shift-occurrences/${old.id}/assignments`,{user_ids:[ws.user.id,session.user.id],supervisor_id:session.user.id,work_item_ids:['CARTON-A']},'PUT');
    await worker.goto('/app/'+org+'?view=capture');
    await expect(worker.getByRole('button',{name:'Start recording',exact:true})).toBeDisabled();
    await expect(worker.getByText('Check the shift date',{exact:true})).toBeVisible();
    await expect(worker.getByText(/This shift is not available for a new update now/)).toBeVisible();
    const recordedAt=new Date().toISOString(), captureId=crypto.randomUUID();
    // Recreate the previous bug's local draft using a controlled WAV, never private audio.
    await worker.evaluate(async({org,uid,oldId,recordedAt,captureId})=>{
      const {saveDraft}=await import('/src/platform/drafts.ts');
      const buffer=new ArrayBuffer(44+32000),v=new DataView(buffer);
      const text=(offset:number,s:string)=>{for(let i=0;i<s.length;i++)v.setUint8(offset+i,s.charCodeAt(i));};
      text(0,'RIFF');v.setUint32(4,buffer.byteLength-8,true);text(8,'WAVE');text(12,'fmt ');v.setUint32(16,16,true);v.setUint16(20,1,true);v.setUint16(22,1,true);v.setUint32(24,16000,true);v.setUint32(28,32000,true);v.setUint16(32,2,true);v.setUint16(34,16,true);text(36,'data');v.setUint32(40,32000,true);
      for(let i=0;i<16000;i++)v.setInt16(44+i*2,Math.sin(i*2*Math.PI*440/16000)*10000,true);
      await saveDraft({id:captureId,userId:uid,organizationId:org,itemId:'CARTON-A',shiftId:oldId,recordedAt,updatedAt:recordedAt,transcript:'',audio:new Blob([buffer],{type:'audio/wav'}),corrections:[],reply:null});
    },{org,uid:ws.user.id,oldId:old.id,recordedAt,captureId});
    await worker.reload();await worker.locator('.draft-drawer summary').click();
    await worker.getByRole('button',{name:'Open draft',exact:true}).click();
    await expect(worker.locator('.capture-panel audio')).toBeVisible();
    await expect(worker.getByText(/This recording belongs to a different date/)).toBeVisible();
    await expect(worker.getByRole('button',{name:'Send update',exact:true})).toBeDisabled();
    const original=await worker.locator('.capture-panel audio').evaluate(async(el:HTMLAudioElement)=>Array.from(new Uint8Array(await(await fetch(el.src)).arrayBuffer())));
    await worker.screenshot({path:'../artifacts/shift-date-before-recovery.png',fullPage:true});
    await post(`/shift-occurrences/${shift.id}/assignments`,{user_ids:[ws.user.id,session.user.id],supervisor_id:session.user.id,work_item_ids:['CARTON-A']},'PUT');
    const useShift=worker.getByRole('button',{name:/Use shift: Today evening/});
    await expect(useShift).toBeVisible({timeout:12000});worker.once('dialog',d=>d.accept());await useShift.click();
    await expect(worker.getByText('Recording kept. Check the selected shift, then press Send.')).toBeVisible();
    await expect(worker.getByRole('button',{name:'Send update',exact:true})).toBeEnabled();
    expect(await worker.locator('.capture-panel audio').evaluate(async(el:HTMLAudioElement)=>Array.from(new Uint8Array(await(await fetch(el.src)).arrayBuffer())))).toEqual(original);
    const sent=worker.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/notes'));
    await worker.getByRole('button',{name:'Send update',exact:true}).click();
    const note=(await(await sent).json()).note;
    expect(note.shift_id).toBe(shift.id);expect(Date.parse(note.recorded_at)).toBe(Date.parse(recordedAt));
    await expect(worker.getByText('Update sent',{exact:true})).toBeVisible();
    const audio=await worker.request.get(`/api/organizations/${org}/notes/${note.id}/audio`,{headers:{'X-Shift-ID':shift.id}});
    expect(Array.from(await audio.body())).toEqual(original);
    const ownerView=await(await page.request.get(`/api/organizations/${org}/workspace?shift_id=${shift.id}`)).json();
    expect(ownerView.notes.filter((n:any)=>n.id===note.id)).toHaveLength(1);
    expect(ownerView.notes.find((n:any)=>n.id===note.id).actor.id).toBe(ws.user.id);
    await page.goto('/app/'+org+'?view=reports');
    await expect(page.getByRole('heading',{name:'CARTON-A · Recovery worker',exact:true})).toBeVisible();
    await page.screenshot({path:'../artifacts/shift-date-owner-report.png',fullPage:true});
    await expect.poll(()=>worker.evaluate(async()=>{
      const {listDrafts}=await import('/src/platform/drafts.ts');
      const s=await(await fetch('/api/auth/session')).json();return (await listDrafts(s.user.id,s.scoped_organization_id)).length;
    })).toBe(0);
  } finally {await wc.close();}
});

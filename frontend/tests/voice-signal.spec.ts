import { createOrganization } from "./workspace-fixture";
import { test, expect } from './fixtures';

test('native capture produces nonzero portable PCM and drains final frames', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const path = '/src/recorder.ts'; const recorder = await import(path);
    const source = new AudioContext({ sampleRate: 48000 }); await source.resume();
    const oscillator = source.createOscillator(), gain = source.createGain(), output = source.createMediaStreamDestination();
    gain.gain.value = 0.1; oscillator.connect(gain); gain.connect(output); oscillator.start();
    navigator.mediaDevices.getUserMedia = async () => output.stream;
    const stop = await recorder.startRecorder(() => {}, () => {});
    await new Promise(r => setTimeout(r, 2200));
    const audio = await stop(); const q = await recorder.inspectRecording(audio), v = new DataView(await audio.arrayBuffer());
    await source.close();
    return { ...q, rate: v.getUint32(24, true), channels: v.getUint16(22, true), bytes: audio.size, frameBytes: v.getUint32(40, true), trackEnded: output.stream.getAudioTracks()[0].readyState };
  });
  expect(result.rate).toBe(16000); expect(result.channels).toBe(1);
  expect(result.silent).toBe(false); expect(result.peak).toBeGreaterThan(0.05);
  expect(result.duration).toBeGreaterThan(1.5); expect(result.frameBytes + 44).toBe(result.bytes);
  expect(result.trackEnded).toBe('ended');
});

test('silent input is rejected, tracks are released and the next recording can succeed', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const path = '/src/recorder.ts'; const recorder = await import(path);
    async function capture(volume: number) {
      const context = new AudioContext(); await context.resume(); const oscillator = context.createOscillator(), gain = context.createGain(), output = context.createMediaStreamDestination();
      gain.gain.value = volume; oscillator.connect(gain); gain.connect(output); oscillator.start();
      navigator.mediaDevices.getUserMedia = async () => output.stream;
      const stop = await recorder.startRecorder(() => {}, () => {}); await new Promise(r => setTimeout(r, 450));
      let status: any;
      try { status = await recorder.inspectRecording(await stop()); } catch (e) { status = { category: (e as any).category }; }
      await context.close(); return { ...status, ended: output.stream.getAudioTracks()[0].readyState };
    }
    return { silent: await capture(0), quiet: await capture(0.001), good: await capture(0.1) };
  });
  expect(result.silent.category).toBe('silent_audio'); expect(result.silent.ended).toBe('ended');
  expect(result.quiet.quiet).toBe(true); expect(result.quiet.silent).toBe(false);
  expect(result.good.silent).toBe(false);
});

test('microphone test has playback and makes no report or provider request', async ({ page }) => {
  const { organization } = await createOrganization(page);
  await page.goto(`/app/${organization}?view=capture`);
  let requests = 0;
  page.on('request', r => { if (r.method() === 'POST' && /\/(notes|speech)(\/|$)/.test(new URL(r.url()).pathname)) requests++; });
  await page.getByRole('button', { name: 'Test microphone', exact: true }).click();
  await expect(page.getByText('This is a microphone test only. It will not be submitted.')).toBeVisible();
  const audio = page.locator('.microphone-panel audio'); await expect(audio).toBeVisible();
  const playback = await audio.evaluate(async a => { const el = a as HTMLAudioElement; await el.play(); return { paused: el.paused, muted: el.muted, volume: el.volume }; });
  expect(playback).toEqual({ paused: false, muted: false, volume: 1 }); expect(requests).toBe(0);
});

test('selected task and recording survive refresh; failed extraction stays visible to owner', async ({ page, browser }) => {
  const signup = await page.request.post('/api/auth/signup', { data: { name: 'Voice Owner', email: `voice-${Date.now()}@example.com`, password: 'voice-owner-password', industry: 'manufacturing' } });
  const org = (await signup.json()).organization_id, base = `/api/organizations/${org}`;
  const owner = await (await page.request.get('/api/auth/session')).json();
  let shiftId = '';
  const call = async (path: string, data?: any, method = data === undefined ? 'GET' : 'POST') => {
    const r = await page.request.fetch(base + path, { method, data, headers: { 'X-CSRF-Token': owner.csrf_token, ...(shiftId ? { 'X-Shift-ID': shiftId } : {}) } });
    expect(r.ok(), await r.text()).toBeTruthy(); return r.json();
  };
  const loc = await call('/locations', { name: 'Packing floor' });
  const team = await call('/teams', { name: 'Packing', location_id: loc.id });
  await call('/work-items', { id: 'VOICE-A', name: 'Voice batch', location_id: loc.id, team_id: team.id });
  shiftId = (await call('/shift-occurrences', { name: 'Voice shift', starts_at: new Date(Date.now() - 3600000).toISOString(), ends_at: new Date(Date.now() + 3600000).toISOString(), location_id: loc.id, team_id: team.id })).id;
  const invite = await call('/worker-invitations', { name: 'Voice Worker', employee_id: 'VOICE-1' });
  const wc = await browser.newContext({ baseURL: 'http://127.0.0.1:5174', permissions: ['microphone'] });
  try {
    const activation = await wc.request.post('/api/auth/worker/activate', { data: { token: invite.join_path.split('/').at(-1), password: 'worker-voice-password', confirm_password: 'worker-voice-password' } });
    expect(activation.ok()).toBeTruthy();
    const worker = await (await wc.request.get('/api/auth/session')).json();
    await call(`/shift-occurrences/${shiftId}/assignments`, { user_ids: [worker.user.id, owner.user.id], supervisor_id: owner.user.id, work_item_ids: ['VOICE-A'] }, 'PUT');
    const created = await call('/notes', { batch_id: 'VOICE-A', shift_id: shiftId, recorded_at: new Date().toISOString(), idempotency_key: 'voice-task-setup' });
    await call(`/notes/${created.note.id}/transcript`, { transcript: 'Agli shift mein carton labels dobara check karne hain.' });
    await call(`/notes/${created.note.id}/process`, {});
    await expect.poll(async () => (await call(`/notes/${created.note.id}`)).claims.length).toBeGreaterThan(0);
    const task = (await call(`/notes/${created.note.id}`)).claims[0].id;
    await call(`/claims/${task}/resolve`, { action: 'confirm', reason: 'Reviewed source', expected_version: (await call('/workspace')).version });
    await call(`/tasks/${task}`, { action: 'assign', owner_id: worker.user.id, reason: 'Assigned worker', expected_version: (await call('/workspace')).version });
    const wp = await wc.newPage();
    await wp.addInitScript(id => { localStorage.setItem('shiftproof-language', 'en'); localStorage.setItem('shiftproof-language:' + id, 'en'); }, worker.user.id);
    await wp.goto(`/app/${org}?view=mywork`);
    await wp.getByRole('button', { name: 'Record completion update', exact: true }).click();
    await expect(wp.getByText('Completion update for', { exact: false })).toBeVisible();
    await wp.getByRole('button', { name: 'Start recording', exact: true }).click();
    await wp.waitForTimeout(1800);
    const workerMeter = wp.getByRole('meter', { name: 'Microphone level' });
    await expect(workerMeter).toBeVisible();
    await expect.poll(async () => Number(await workerMeter.getAttribute('aria-valuenow'))).toBeGreaterThan(0);
    await wp.screenshot({ path: '../artifacts/microphone-worker-recording.png', fullPage: true });
    await wp.getByRole('button', { name: 'Stop recording', exact: true }).click();
    await expect(wp.locator('.local-save-status')).toContainText('Saved on this device');
    wp.on('dialog', d => void d.accept()); await wp.reload();
    await wp.locator('summary').filter({ hasText: 'Saved drafts' }).click();
    await wp.getByRole('button', { name: 'Open draft', exact: true }).first().click();
    await expect(wp.getByText('Completion update for', { exact: false })).toBeVisible();
    // Controlled ASR only; audio storage, task context and scopes use the real backend.
    await wp.route('**/api/organizations/*/notes/*/process', async route => {
      const path = new URL(route.request().url()).pathname.replace(/\/process$/, '/transcript');
      const r = await wc.request.post(path, { data: { transcript: 'Maine labels check kar diya.' }, headers: { 'X-CSRF-Token': worker.csrf_token, 'X-Shift-ID': shiftId } });
      expect(r.ok()).toBeTruthy(); await route.continue();
    });
    await wp.getByRole('button', { name: 'Send update', exact: true }).click();
    await expect(wp.getByRole('status').filter({ hasText: 'Your report was sent. Your supervisor will check it.' })).toBeVisible();
    await expect.poll(async () => (await call('/workspace')).notes.find((n:any)=>n.task_id===task)?.status).toBe('manual_review');
    const view = await call('/workspace'), report = view.notes.find((n: any) => n.task_id === task);
    expect(report.task_context.id).toBe(task); expect(report.actor.id).toBe(worker.user.id); expect(report.has_audio).toBe(true);
    expect(view.batches[0].tasks.find((t: any) => t.id === task).status).toBe('open');
    await wp.getByRole('button', { name: 'My work', exact: true }).click();
    await expect(wp.getByRole('dialog', { name: 'Keep your unfinished update?' })).toHaveCount(0);
    await wp.getByRole('button', { name: 'Record update', exact: true }).click();
    await wp.waitForTimeout(400);
    await expect(wp.getByRole('button', { name: 'Open draft', exact: true })).toHaveCount(0);
    await wp.screenshot({ path: '../artifacts/voice-task-worker.png', fullPage: true });
  } finally { await wc.close(); }
});

for (const failure of ['suspended-context', 'failed-worklet'] as const) {
  test(`direct capture remains audible with ${failure}`, async ({ page }) => {
    await page.goto('/');
    const result = await page.evaluate(async failure => {
      const path = '/src/recorder.ts', recorder = await import(path);
      const Original = window.AudioContext;
      const source = new Original(); await source.resume();
      const oscillator = source.createOscillator(), gain = source.createGain(), destination = source.createMediaStreamDestination();
      gain.gain.value = 0.15; oscillator.connect(gain); gain.connect(destination); oscillator.start();
      navigator.mediaDevices.getUserMedia = async () => destination.stream;
      window.AudioContext = class extends Original {
        constructor() {
          super();
          if (failure === 'suspended-context') {
            void this.suspend();
            this.resume = () => new Promise<void>(() => {});
          } else this.audioWorklet.addModule = async () => { throw new Error('Simulated worklet load failure'); };
        }
      };
      const start = performance.now();
      const stop = await recorder.startRecorder(() => {}, () => {});
      const startupMs = performance.now() - start;
      await new Promise(r => setTimeout(r, 1700));
      const state = recorder.currentMicrophoneState(), audio = await stop(), quality = await recorder.inspectRecording(audio);
      await source.close(); window.AudioContext = Original;
      return { startupMs, state, quality, ended: destination.stream.getAudioTracks()[0].readyState };
    }, failure);
    expect(result.startupMs).toBeLessThan(2500);
    expect(result.state.path).toContain('native');
    if (failure === 'suspended-context') expect(result.state.state).toBe('paused');
    expect(result.quality.silent).toBe(false); expect(result.quality.duration).toBeGreaterThan(0.5);
    expect(result.ended).toBe('ended');
  });
}

test('microphone indicator visibly moves and blocked access gives an actionable error', async ({ page }) => {
  const { organization } = await createOrganization(page);
  await page.goto(`/app/${organization}?view=capture`);
  const meter = page.getByRole('meter', { name: 'Microphone level' });
  await expect(meter).toBeVisible();
  expect((await meter.boundingBox())!.height).toBeGreaterThanOrEqual(28);
  await page.getByRole('button', { name: 'Test microphone', exact: true }).click();
  await expect.poll(async () => Number(await meter.getAttribute('aria-valuenow'))).toBeGreaterThan(0);
  await page.screenshot({ path: '../artifacts/microphone-indicator.png', fullPage: true });
  await expect(page.locator('.microphone-panel audio')).toBeVisible();
  await page.evaluate(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); };
  });
  await page.getByRole('button', { name: 'Test microphone', exact: true }).click();
  await expect(page.locator('.microphone-panel [role="alert"]')).toContainText('Microphone access is blocked');
  await expect(page.getByRole('button', { name: 'Test microphone', exact: true })).toBeEnabled();
});

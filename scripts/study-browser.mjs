/** Private, opt-in measurement session. No fake microphone and no participant results generated. */
import { chromium } from '../frontend/node_modules/@playwright/test/index.mjs';
import { mkdir, appendFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { randomUUID } from 'node:crypto';
const target = new URL(process.env.STUDY_URL || 'http://localhost:5173');
if (!['localhost', '127.0.0.1'].includes(target.hostname)) throw new Error('Study sessions must use the private local workspace.');
const configuration = await fetch(new URL('/api/config', target)).then(response => { if (!response.ok) throw new Error('Private application is unavailable'); return response.json(); });
if ('public_read_only' in configuration) throw new Error('Use the private frontend, not the visitor preview, for participant sessions.');
const folder = resolve('.local/study-sessions', randomUUID());
await mkdir(folder, {recursive:true});
await writeFile(`${folder}/session.json`, JSON.stringify({started_at:new Date().toISOString(), target:target.origin, status:'measurement_session', participant_id:process.env.STUDY_PARTICIPANT || null, limitation:'Timing events alone do not establish participation, consent, or correctness.'},null,2));
const browser = await chromium.launch({headless:false});
const context = await browser.newContext({permissions:['microphone']});
let pending = Promise.resolve();
await context.exposeBinding('saveStudyEvent', (_source, event) => {
  pending = pending.then(() => appendFile(`${folder}/events.jsonl`, JSON.stringify(event)+'\n'));
  return pending;
});
await context.addInitScript(() => {
  window.__shiftproofStudy = true;
  const documentId = crypto.randomUUID();
  window.addEventListener('shiftproof:study', e => window.saveStudyEvent({document_id:documentId,...e.detail}));
});
const page = await context.newPage();
await page.goto(target.href);
console.log(`Private session ready. Perform the assigned task, then close this browser. Events: ${folder}/events.jsonl`);
await new Promise(resolve => browser.on('disconnected',resolve));
await pending;

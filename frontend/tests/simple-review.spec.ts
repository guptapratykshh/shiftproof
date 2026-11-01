import { choose } from './controls';
import { test, expect } from './fixtures';

test('one report review updates worker and owner, preserves document checks and reopens mistaken closures',async({browser,page})=>{
 test.setTimeout(90000);
 const signup=async(p:any,name:string,industry='warehousing')=>{
  const email=`simple-${name}-${Date.now()}@example.com`;
  const r=await p.request.post('/api/auth/signup',{data:{name,email,password:'FictionalReview!2026',industry}});expect(r.ok()).toBeTruthy();
  const created=await r.json(), session=await(await p.request.get('/api/auth/session')).json();return {...created,session,email};
 };
 const owner=await signup(page,'owner');const org=owner.organization_id,base=`/api/organizations/${org}`;
 const other=await browser.newContext({baseURL:'http://127.0.0.1:5174',storageState:{cookies:[],origins:[{origin:'http://127.0.0.1:5174',localStorage:[{name:'shiftproof-language',value:'en'}]}]}});
 const workerPage=await other.newPage();const worker=await signup(workerPage,'worker');
 const call=async(path:string,data?:unknown,method?:string)=>{
  const r=await page.request.fetch(base+path,{method:method||(data?'POST':'GET'),data,headers:{'X-CSRF-Token':owner.session.csrf_token}});expect(r.ok(),await r.text()).toBeTruthy();return r.json();
 };
 const invitation=await call('/invitations',{name:'worker',email:worker.email,role:'operator'});
 const accept=await workerPage.request.post('/api/invitations/accept',{headers:{'X-CSRF-Token':worker.session.csrf_token},data:{token:invitation.join_path.split('/').at(-1)}});expect(accept.ok()).toBeTruthy();
 const loc=await call('/locations',{name:'Fictional warehouse'}),team=await call('/teams',{name:'Phone packing',location_id:loc.id});
 await call('/work-items',{id:'PHONE-01',name:'Fictional phones',location_id:loc.id,team_id:team.id});
 const shift=await call('/shift-occurrences',{name:'Current shift',team_id:team.id,location_id:loc.id,starts_at:new Date(Date.now()-3600000).toISOString(),ends_at:new Date(Date.now()+3600000).toISOString()});
 await call(`/shift-occurrences/${shift.id}/assignments`,{user_ids:[owner.session.user.id,worker.session.user.id],supervisor_id:owner.session.user.id,work_item_ids:['PHONE-01']},'PUT');
 await page.goto(`/app/${org}?view=capture`);await workerPage.goto(`/app/${org}?view=capture`);
 await workerPage.getByRole('button',{name:'Write instead of speaking'}).click();
 await workerPage.getByLabel('Transcript',{exact:true}).fill('Packing is complete. Dispatch is ready.');
 await workerPage.getByRole('button',{name:'Send update',exact:true}).click();
 await expect(workerPage.getByText('Update sent',{exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Listen and check',exact:true})).toBeVisible({timeout:12000});
 await page.getByRole('button',{name:'Listen and check',exact:true}).click();
 let d=page.getByRole('dialog');
 // Empty submission must not approve or close anything.
 await d.getByLabel('Checked against the recording',{exact:true}).check();
 await d.getByRole('button',{name:'Save checked updates'}).click();
 await expect(d.getByRole('alert')).toContainText('Check at least one statement');
 for(const [property,value] of [['packing','complete'],['dispatch','ready']]){
  const row=d.locator(`[data-property="${property}"]`);
  await choose(row.getByLabel('Status stated in the recording'), value);
  await choose(row.getByLabel('Your check'), 'correct');
 }
 await d.getByRole('button',{name:'Save checked updates'}).click();await expect(d).toHaveCount(0);
 await expect(workerPage.locator('section[aria-label="Current update"]')).toContainText('Report checked.',{timeout:12000});
 await expect(workerPage.locator('section[aria-label="Current update"]')).toContainText('Dispatch documents still needs verification');
 const v=await call('/workspace');expect(v.batches[0].claims.filter((c:any)=>c.status==='confirmed')).toHaveLength(2);
 const summary=page.locator('section[aria-label="Current update"]');await expect(summary).toContainText('Report checked.');
 // A deliberately closed, fictional note remains recoverable without erasing evidence.
 const created=await call('/notes',{batch_id:'PHONE-01',shift_id:shift.id,recorded_at:new Date().toISOString(),idempotency_key:'reopen-ui-'+Date.now()});
 const nid=created.note.id;
 await call(`/notes/${nid}/transcript`,{transcript:'Packing complete for the next lot.'});await call(`/notes/${nid}/process`,{});
 await expect.poll(async()=>(await call(`/notes/${nid}`)).status).toBe('manual_review');
 await call(`/notes/${nid}/review-transcript`,{expected_version:(await call('/workspace')).version,claims:[],no_operational_update:true,reason:'Controlled mistaken closure for recovery verification'});
 await page.reload();await page.getByRole('button',{name:'Reopen report for review',exact:true}).click();
 d=page.getByRole('dialog');await d.getByLabel('Reason for reopening').fill('The report describes completed packing, not a microphone test.');
 await d.getByRole('button',{name:'Reopen report for review'}).click();
 await expect(d.getByRole('button',{name:'Save checked updates'})).toBeVisible();
 await choose(d.locator('[data-property="packing"]').getByLabel('Status stated in the recording'), 'complete');
 await choose(d.locator('[data-property="packing"]').getByLabel('Your check'), 'correct');
 await d.getByRole('button',{name:'Save checked updates'}).click();await expect(d).toHaveCount(0);
 await page.screenshot({path:'../artifacts/simple-review-owner.png',fullPage:true});
 await workerPage.screenshot({path:'../artifacts/simple-review-worker.png',fullPage:true});
 await page.getByRole('button',{name:'Team',exact:true}).click();
 await page.getByText('Shared-phone recording assistance',{exact:true}).click();
 const permissions=page.locator('details').filter({has:page.getByText('Shared-phone recording assistance',{exact:true})});
 await choose(permissions.getByLabel('Helper',{exact:false}), owner.session.user.id);
 await permissions.getByLabel('Current shift',{exact:true}).check();
 await permissions.getByRole('button',{name:'Save helper permission'}).click();
 await expect(permissions.getByRole('status')).toHaveText('Permission saved');
 await page.getByRole('button',{name:'Record update',exact:true}).click();
 await expect(page.getByLabel('Who is speaking?',{exact:false})).toBeVisible({timeout:12000});
 await choose(page.getByLabel('Who is speaking?',{exact:false}), worker.session.user.id);
 await page.getByLabel('Transcript',{exact:true}).fill('Assisted report: packing is pending.');
 await choose(page.getByLabel('Who is speaking?',{exact:false}), '');
 await page.getByRole('button',{name:'Save draft and leave'}).click();
 await expect(page.getByRole('dialog')).toHaveCount(0);
 await expect(page.getByLabel('Who is speaking?',{exact:false}).locator('..').locator('select')).toHaveValue('');
 await expect(page.getByRole('button',{name:'Open draft',exact:true})).toHaveCount(0);
 await choose(page.getByLabel('Who is speaking?',{exact:false}), worker.session.user.id);
 await page.locator('summary').filter({hasText:'Saved drafts'}).click();
 await page.getByRole('button',{name:'Open draft',exact:true}).click();
 await expect(page.getByLabel('Transcript',{exact:true})).toHaveValue('Assisted report: packing is pending.');
 await page.getByRole('button',{name:'Send update',exact:true}).click();
 const assisted=(await call('/workspace')).notes.find((n:any)=>n.reported_by?.id===worker.session.user.id);
 expect(assisted.actor.id).toBe(owner.session.user.id);expect(assisted.assisted_by.id).toBe(owner.session.user.id);
 await page.screenshot({path:'../artifacts/simple-review-assisted.png',fullPage:true});
 // Refresh during assisted recording must retain the selected worker in the audio checkpoint.
 await page.getByRole('button',{name:'Start recording',exact:true}).click();
 await page.getByRole('button',{name:'Correct, start recording',exact:true}).click();
 await expect(page.locator('.local-save-status')).toContainText('Recording checkpoint saved',{timeout:10000});
 page.on('dialog',dialog=>void dialog.accept());
 await page.reload();
 await expect(page.getByRole('button',{name:'Open draft',exact:true})).toHaveCount(0);
 await choose(page.getByLabel('Who is speaking?',{exact:false}), worker.session.user.id);
 await page.locator('summary').filter({hasText:'Saved drafts'}).click();
 await page.getByRole('button',{name:'Open draft',exact:true}).click();
 await expect(page.locator('audio').first()).toBeVisible();
 await expect(page.getByLabel('Who is speaking?',{exact:false}).locator('..').locator('select')).toHaveValue(worker.session.user.id);

 // Reuse this controlled browser recording as an original source for the review player.
 const bytes=await page.locator('audio').first().evaluate(async(a:HTMLAudioElement)=>Array.from(new Uint8Array(await(await fetch(a.src)).arrayBuffer())));
 const voice=await call('/notes',{batch_id:'PHONE-01',shift_id:shift.id,recorded_at:new Date().toISOString(),idempotency_key:'review-playback-'+Date.now()});
 const uploaded=await page.request.put(base+`/notes/${voice.note.id}/audio`,{data:Buffer.from(bytes),headers:{'Content-Type':'audio/wav','X-CSRF-Token':owner.session.csrf_token}});expect(uploaded.ok()).toBeTruthy();
 await call(`/notes/${voice.note.id}/transcript`,{transcript:'Playback verification packing complete.'});await call(`/notes/${voice.note.id}/process`,{});
 await expect.poll(async()=>(await call(`/notes/${voice.note.id}`)).status).toBe('manual_review');
 await page.reload();
 await page.locator('.report-card').filter({hasText:'Playback verification packing complete.'}).getByRole('button',{name:'Listen and check',exact:true}).click();
 const original=page.getByRole('dialog').locator('audio');
 await original.evaluate((a:HTMLAudioElement)=>a.play());
 await expect.poll(()=>original.evaluate((a:HTMLAudioElement)=>a.currentTime)).toBeGreaterThan(0.2);
 expect(await original.evaluate((a:HTMLAudioElement)=>a.paused)).toBe(false);
 await other.close();
});

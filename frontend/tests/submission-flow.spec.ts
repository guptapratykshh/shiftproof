import { choose } from './controls';
import { test, expect } from './fixtures';

test('late draft writes cannot resurrect a sent capture and other drafts remain', async ({page}) => {
  await page.goto('/');
  const result=await page.evaluate(async () => {
    const path='/src/platform/drafts.ts';const drafts=await import(path);
    const data={id:'retired-capture',userId:'worker',organizationId:'factory',itemId:'A',shiftId:'shift',recordedAt:new Date().toISOString(),updatedAt:new Date().toISOString(),transcript:'Saved words',audio:null,corrections:[],reply:null};
    await drafts.saveDraft(data);
    await drafts.saveDraft({...data,id:'keep-other-capture'});
    await drafts.deleteDraft(data.id);
    await drafts.saveDraft(data); // late autosave from the previous React render
    return await drafts.listDrafts(data.userId,data.organizationId);
  });
  expect(result.map((d:any)=>d.id)).toEqual(['keep-other-capture']);
});

test('sent clarification leaves no discard loop; handover links to manual review', async ({page}) => {
  const created=await page.request.post('/api/auth/signup',{data:{name:'Flow Owner',email:`flow-${Date.now()}@example.com`,password:'flow-owner-long-password',industry:'manufacturing'}});
  expect(created.ok()).toBeTruthy();const org=(await created.json()).organization_id, base=`/api/organizations/${org}`;
  const session=await (await page.request.get('/api/auth/session')).json();
  const headers:Record<string,string>={'X-CSRF-Token':session.csrf_token};
  const call=async(path:string,data?:any,method=data===undefined?'GET':'POST')=>{
    const r=await page.request.fetch(base+path,{headers,method,data});expect(r.ok(),await r.text()).toBeTruthy();return r.json();
  };
  const location=await call('/locations',{name:'Packing floor'});
  const team=await call('/teams',{name:'Packing team',location_id:location.id});
  await call('/work-items',{id:'FLOW-A',name:'Flow batch',location_id:location.id,team_id:team.id});
  const shift=await call('/shift-occurrences',{name:'Current shift',location_id:location.id,team_id:team.id,starts_at:new Date(Date.now()-3600000).toISOString(),ends_at:new Date(Date.now()+3600000).toISOString()});
  await call(`/shift-occurrences/${shift.id}/assignments`,{user_ids:[session.user.id],supervisor_id:session.user.id,work_item_ids:['FLOW-A']},'PUT');
  headers['X-Shift-ID']=shift.id;
  const note=await call('/notes',{batch_id:'FLOW-A',shift_id:shift.id,recorded_at:new Date().toISOString(),idempotency_key:'initial-hold'});
  await call(`/notes/${note.note.id}/transcript`,{transcript:'Sirf packing complete hai. Quality check abhi pending hai.'});
  await call(`/notes/${note.note.id}/process`,{});
  await expect.poll(async()=>(await call(`/notes/${note.note.id}`)).status).toBe('processed');
  await page.goto(`/app/${org}?view=capture`);
  await page.getByRole('button',{name:'Answer this question',exact:true}).click();
  const text='Quality inspection is still pending; the checker arrives later.';
  await page.getByRole('textbox',{name:'Transcript',exact:true}).fill(text);
  await page.getByRole('button',{name:'Send update',exact:true}).click();
  await expect(page.getByText('Answer received. Waiting for supervisor review; do not send the same answer again.')).toBeVisible();
  await expect(page.getByRole('button',{name:'Answer this question',exact:true})).toHaveCount(0);
  const view=await call('/workspace');const reply=view.notes.find((n:any)=>n.clarification_ref);
  expect(reply.status).toBe('manual_review');expect(reply.submitted_at).toBeTruthy();
  await page.getByRole('button',{name:'Handover',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Keep your unfinished update?'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:/^Acknowledge v/})).toBeDisabled();
  await page.getByRole('button',{name:'Review saved report',exact:true}).first().click();
  const dialog=page.getByRole('dialog',{name:'Listen and check report',exact:true});
  await expect(dialog).toContainText(text);
  await expect(dialog).toContainText('Answering this question');
  const row=dialog.locator('[data-property="quality"]');
  await choose(row.getByLabel('Status stated in the recording'), 'pending');
  await choose(row.getByLabel('Your check'), 'correct');
  await dialog.getByLabel('Explain if needed').fill('Checked the saved answer and original question');
  await dialog.getByRole('button',{name:'Save checked updates'}).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('button',{name:/^Acknowledge v/})).toBeEnabled();
  expect((await call('/workspace')).batches[0].status).toBe('hold');
  // An old client saved this ghost after sending. Restore must recognize the
  // existing server note and retire the local copy, never create another note.
  await page.evaluate(async ({org,session,shift,reply,text})=>{
    const path='/src/platform/drafts.ts';const drafts=await import(path);
    await drafts.saveDraft({id:'legacy-ghost',userId:session.user.id,organizationId:org,itemId:'FLOW-A',shiftId:shift.id,recordedAt:reply.recorded_at,updatedAt:new Date().toISOString(),transcript:text,audio:null,noteId:reply.id,corrections:[],reply:reply.clarification_context});
  },{org,session,shift,reply,text});
  await page.goto(`/app/${org}?view=capture`);
  await page.locator('summary').filter({hasText:'Saved drafts'}).click();
  await page.getByRole('button',{name:'Open draft',exact:true}).click();
  await expect(page.getByText('This update has already been reviewed. Open its details for the saved decision.')).toBeVisible();
  await page.getByRole('button',{name:'Handover',exact:true}).click();
  await expect(page.getByRole('dialog',{name:'Keep your unfinished update?'})).toHaveCount(0);
  expect((await call('/workspace')).notes).toHaveLength(2);
  await page.screenshot({path:'../artifacts/submission-handover.png',fullPage:true});
});

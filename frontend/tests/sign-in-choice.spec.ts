import { test, expect, type Page } from './fixtures';
import fs from 'node:fs';

test('landing sign-in offers three role cards with Back, refresh and email-worker access', async ({ page }) => {
  await page.goto('/');
  await page.locator('.public-nav').getByRole('link', { name:'Sign in', exact:true }).click();
  await expect(page).toHaveURL(/\/signin$/);
  await expect(page.getByRole('heading', { name:'How would you like to sign in?' })).toBeVisible();
  await expect(page.locator('.sign-in-option')).toHaveCount(3);
  for (const [role, path] of [['worker','/worker/login'],['supervisor','/login?role=supervisor'],['an organisation','/login?role=organization']]) {
    const title = `Sign in as ${role === 'an organisation' ? role : 'a '+role}`;
    const card = page.getByRole('link', { name:title, exact:true });
    await card.focus(); await page.keyboard.press('Enter');
    await expect(page).toHaveURL(url => url.pathname + url.search === path);
    await expect(page.getByRole('heading', { name:title, exact:true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole('heading', { name:title, exact:true })).toBeVisible();
    if (role==='worker') {
      await expect(page.getByLabel('Organization code')).toBeVisible();
      await expect(page.getByLabel('Employee ID')).toBeVisible();
      await page.getByRole('link', { name:'Sign in with email', exact:true }).click();
      await expect(page).toHaveURL(/\/login\?role=worker$/);
      await expect(page.getByLabel('Email address')).toBeVisible();
      await expect(page.getByRole('heading', { name:'Sign in as a worker' })).toBeVisible();
      await page.goBack();
    } else {
      await expect(page.getByLabel('Email address')).toBeVisible();
      await expect(page.getByLabel('Password', {exact:true})).toBeVisible();
      await expect(page.getByLabel('Employee ID')).toHaveCount(0);
    }
    await page.getByRole('link', { name:'Choose another sign-in option' }).click();
    await expect(page.locator('.sign-in-option')).toHaveCount(3);
  }
  await page.goto('/login?role=unrecognised');
  await expect(page.getByRole('heading', {name:'Sign in to ShiftProof'})).toBeVisible();
});

test('role chooser is responsive and translated in both themes', async ({ page }) => {
  fs.mkdirSync('../artifacts/sign-in-choice', {recursive:true});
  await page.goto('/signin');
  for (const language of ['en','hi']) {
    if(language==='hi') await page.getByRole('button',{name:'हिन्दी में बदलें'}).click();
    for (const theme of ['light','dark']) {
      if(await page.locator('html').getAttribute('data-theme')!==theme)await page.locator('.appearance-control').click();
      for(const width of [390,768,1440]) {
        await page.setViewportSize({width,height:900});
        expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
        await page.screenshot({path:`../artifacts/sign-in-choice/${language}-${theme}-${width}.png`,fullPage:true});
      }
    }
  }
  await expect(page.getByRole('link',{name:'कर्मचारी के रूप में साइन इन करें',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'सुपरवाइज़र के रूप में साइन इन करें',exact:true}).click();
  await expect(page.getByRole('heading',{name:'सुपरवाइज़र के रूप में साइन इन करें'})).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await page.getByRole('link',{name:'पासवर्ड भूल गए?',exact:true}).click();
  await expect(page).toHaveURL(/\/recover\?role=supervisor$/);
});

test('real owner, supervisor and employee logins keep their assigned permissions', async ({ page, browser }) => {
  const password='FictionalSignIn!2026';
  const ownerEmail=`owner-signin-${crypto.randomUUID()}@example.com`;
  const created=await page.request.post('/api/auth/signup',{data:{name:'Sign in owner',email:ownerEmail,password,industry:'manufacturing'}});
  expect(created.ok()).toBeTruthy();
  const {organization_id:org,csrf_token:csrf}=await created.json();
  async function post(path:string,data:unknown){const r=await page.request.post(`/api/organizations/${org}${path}`,{headers:{'X-CSRF-Token':csrf},data});expect(r.ok(),await r.text()).toBeTruthy();return r.json();}
  const supervisorEmail=`supervisor-${crypto.randomUUID()}@example.com`;
  const invite=await post('/invitations',{name:'Shift supervisor',email:supervisorEmail,role:'supervisor',access:'member'});
  const employeeInvite=await post('/worker-invitations',{name:'Shift worker',employee_id:'EMP-1'});
  const context=await browser.newContext({storageState:{cookies:[],origins:[{origin:'http://127.0.0.1:5174',localStorage:[{name:'shiftproof-language',value:'en'}]}]}});
  const guest=await context.newPage();
  try {
    const joined=await guest.request.post('/api/auth/signup',{data:{name:'Shift supervisor',email:supervisorEmail,password,invitation_token:invite.join_path.split('/').pop()}});
    expect(joined.ok(),await joined.text()).toBeTruthy();
    const activated=await guest.request.post('/api/auth/worker/activate',{data:{token:employeeInvite.join_path.split('/').pop(),password}});
    expect(activated.ok(),await activated.text()).toBeTruthy();
    const employee=await activated.json();
    await context.clearCookies();
    const go=async(p:Page,title:string)=>{await p.goto('/signin');await p.getByRole('link',{name:title,exact:true}).click();};
    const emailLogin=async(title:string,email:string)=>{
      await go(guest,title);await guest.getByLabel('Email address').fill(email);await guest.getByLabel('Password',{exact:true}).fill(password);
      const sent=guest.waitForRequest(r=>r.url().endsWith('/api/auth/login')&&r.method()==='POST');
      await guest.getByRole('button',{name:'Sign in',exact:true}).click();
      expect(Object.keys((await sent).postDataJSON()).sort()).toEqual(['email','password']);
      await expect(guest).toHaveURL(new RegExp(`/app/${org}(\\?|$)`));
    };
    await emailLogin('Sign in as an organisation',ownerEmail);
    await expect(guest.getByRole('button',{name:'Team',exact:true})).toBeVisible();
    await context.clearCookies();
    await emailLogin('Sign in as a supervisor',supervisorEmail);
    await expect(guest.getByRole('button',{name:'Reports & evidence',exact:true})).toBeVisible();
    expect((await guest.request.get(`/api/organizations/${org}/export`)).status()).toBe(403);
    await context.clearCookies();
    // A URL/card selection cannot grant owner permissions to a supervisor.
    await emailLogin('Sign in as an organisation',supervisorEmail);
    expect((await guest.request.get(`/api/organizations/${org}/export`)).status()).toBe(403);
    const supervisorSession=await (await guest.request.get('/api/auth/session')).json();
    expect(supervisorSession.organizations[0].access).toBe('member');
    await context.clearCookies();
    await go(guest,'Sign in as a worker');
    await guest.getByLabel('Organization code').fill(employee.organization_code);
    await guest.getByLabel('Employee ID').fill('EMP-1');
    await guest.getByLabel('Password',{exact:true}).fill(password);
    await guest.getByRole('button',{name:'Continue',exact:true}).click();
    await expect(guest).toHaveURL(new RegExp(`/app/${org}(\\?|$)`));
    await expect(guest.locator('.organization-sidebar nav button')).toHaveCount(3);
    const session=await (await guest.request.get('/api/auth/session')).json();
    expect(session.auth_kind).toBe('employee');expect(session.organizations[0].role).toBe('operator');
    expect((await guest.request.get(`/api/organizations/${org}/export`)).status()).toBe(403);
  } finally { await context.close(); }
});

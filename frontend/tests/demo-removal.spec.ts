import { test, expect } from './fixtures';
import { createOrganization } from './workspace-fixture';

test('public pages have no demo entry and old demo links go to sign in', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('a[href*="/demo"]')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'Build your workspace' })).toBeVisible();
  for (const path of ['/demo', '/demo/voice']) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByLabel('Email address')).toBeVisible();
    await expect(page.getByText('Viewing as', { exact:true })).toHaveCount(0);
  }
});

test('demo access is removed while organization signup and editing still work', async ({ page }) => {
  const { organization, call } = await createOrganization(page);
  const before = await call('/workspace');
  expect(before.notes).toHaveLength(0);
  expect(before.batches).toHaveLength(1);
  await page.goto(`/app/${organization}?view=work`);
  await expect(page.locator('.item-card')).toContainText('B-17');
  await call('/work-items', { id:'NEW-ORDER', name:'New organization work' });
  await page.reload();
  await expect(page.locator('.item-register')).toContainText('New organization work');
  for (const path of ['/api/workspace', '/api/notes/fixture-1', '/api/samples'])
    expect((await page.request.get(path)).status()).toBe(404);
  expect((await page.request.post('/api/auth/demo', { data:{ role:'quality' } })).status()).toBe(404);
});

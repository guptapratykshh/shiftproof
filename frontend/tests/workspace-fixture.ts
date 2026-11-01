import { expect, type Page } from './fixtures';

// Authenticated, empty organization in the isolated browser-test database.
export async function createOrganization(page: Page) {
  const response = await page.request.post('/api/auth/signup', { data: {
    name: 'Test Owner', email: `workspace-${crypto.randomUUID()}@example.com`,
    password: 'FictionalTestPassword!2026', industry: 'manufacturing',
  } });
  expect(response.ok(), await response.text()).toBeTruthy();
  const { organization_id: organization, csrf_token: csrf } = await response.json();
  const call = async (path: string, data?: unknown) => {
    const r = await page.request.fetch(`/api/organizations/${organization}${path}`, {
      method: data === undefined ? 'GET' : 'POST', data,
      headers: { 'X-CSRF-Token': csrf },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.json();
  };
  await call('/work-items', { id: 'B-17', name: 'Fictional test batch' });
  return { organization, call };
}

import { test, expect } from './fixtures';
import { choose } from './controls';
import fs from 'node:fs';

function contrast(a: number[], b: number[]) {
  const lum = (rgb: number[]) => rgb.slice(0, 3).map(c => c / 255).map(c => c <= .04045 ? c / 12.92 : ((c + .055) / 1.055) ** 2.4).reduce((sum, c, i) => sum + c * [.2126, .7152, .0722][i], 0);
  const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05);
}
test('landing contrast, themed branding and removal of illustrative evidence results', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await page.goto('/');
  await expect(page.locator('#evidence,.results-strip')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'The evidence', exact: true })).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText(/[↗→←]/);
  for (const theme of ['light', 'dark']) {
    if (theme === 'dark') await page.getByRole('button', { name: 'Switch to dark theme' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
    const pairs = await page.locator('.scene-report strong,.scene-report small,.scene-hold strong,.scene-hold span,.industry-picker .selected small,.steps-section h2,.steps-grid p,.landing-hero h1 em,.public-brand > span:first-child,.public-footer > span').evaluateAll(nodes => nodes.map(n => {
      const fg = getComputedStyle(n).color;
      let node: Element | null = n, bg = '';
      while (node) { bg = getComputedStyle(node).backgroundColor; if (bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') break; node = node.parentElement; }
      return { text: n.textContent, fg: fg.match(/[\d.]+/g)!.map(Number), bg: bg.match(/[\d.]+/g)!.map(Number) };
    }));
    for (const pair of pairs) expect(contrast(pair.fg, pair.bg), `${theme}: ${pair.text}`).toBeGreaterThanOrEqual(4.5);
    await expect(page.locator('link[rel=icon]')).toHaveAttribute('href', theme === 'dark' ? '/favicon-dark.svg' : '/favicon.svg');
  }
});
test('styled industry select supports keyboard, dismissal and synchronized industry cards', async ({ page }) => {
  await page.goto('/');
  const control = page.getByRole('combobox', { name: '3D scene industry' });
  await control.focus(); await page.keyboard.press('ArrowDown');
  await expect(page.getByRole('listbox')).toBeVisible();
  await page.keyboard.press('End'); await page.keyboard.press('Enter');
  await expect(control).toContainText('Facility management');
  await expect(page.locator('.industry-picker .selected')).toContainText('Facility management');
  await control.click(); await page.keyboard.press('Escape');
  await expect(page.getByRole('listbox')).toHaveCount(0); await expect(control).toBeFocused();
  await page.keyboard.type('ware'); await page.keyboard.press('Enter');
  await expect(control).toContainText('Warehousing');
  await control.click(); await page.getByRole('heading', { level: 1 }).click();
  await expect(page.getByRole('listbox')).toHaveCount(0);
  await choose(control, 'manufacturing');
  await expect(control).toContainText('Manufacturing');
});
test('responsive theme and dropdown screenshots in both languages', async ({ page }) => {
  test.setTimeout(90000);
  fs.mkdirSync('../artifacts/theme-refresh/screenshots', { recursive: true });
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'light' });
  await page.goto('/');
  for (const language of ['en', 'hi']) {
    if (language === 'hi') await page.getByRole('button', { name: 'हिन्दी में बदलें' }).click();
    for (const theme of ['light', 'dark']) {
      if (await page.locator('html').getAttribute('data-theme') !== theme) await page.locator('.appearance-control').click();
      for (const width of [390, 768, 1440, 1920]) {
        await page.setViewportSize({ width, height: 900 });
        await expect(page.locator('.appearance-control')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
        const combo = page.getByRole('combobox');
        await combo.click();
        const r = await page.getByRole('listbox').boundingBox();
        expect(r!.x).toBeGreaterThanOrEqual(0); expect(r!.x + r!.width).toBeLessThanOrEqual(width);
        await page.screenshot({ path: `../artifacts/theme-refresh/screenshots/${language}-${theme}-${width}-dropdown.png` });
        await page.keyboard.press('Escape');
        await page.screenshot({ path: `../artifacts/theme-refresh/screenshots/${language}-${theme}-${width}.png`, fullPage: true });
      }
    }
  }
});
test('select menu in a dialog keeps focus and selects a role', async ({ page }) => {
  const signup = await page.request.post('/api/auth/signup', { data: { name:'Theme owner', email:`theme-${Date.now()}@example.com`, password:'FictionalTheme!2026', industry:'manufacturing' } });
  const { organization_id: org } = await signup.json();
  await page.goto(`/app/${org}?view=team`);
  await page.getByRole('button', { name:'Manage', exact:true }).click();
  const dialog = page.getByRole('dialog');
  const role = dialog.getByLabel('Operational role');
  await role.click(); await page.keyboard.press('Escape');
  await expect(dialog).toBeVisible(); await expect(role).toBeFocused();
  await choose(role, 'quality');
  await expect(role).toContainText(/reviewer/i);
  // The existing organization suite verifies saving permissions and authority.
});

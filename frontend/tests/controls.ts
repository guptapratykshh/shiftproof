import { expect, type Locator, type Page } from '@playwright/test';

// Exercise the visible listbox, including options rendered inside modal dialogs.
export async function choose(control: Locator, selection: string | { label?: string; value?: string }) {
  const trigger = await control.evaluate(n => n.tagName === 'SELECT')
    ? control.locator('..').getByRole('combobox') : control.and(control.page().getByRole('combobox'));
  await trigger.click();
  const listId = await trigger.getAttribute('aria-controls');
  if (!listId) throw new Error('Select did not open its options');
  const menu = trigger.page().locator(`[id=${JSON.stringify(listId)}]`);
  const option = typeof selection === 'object' && selection.label !== undefined
    ? menu.getByRole('option', { name: selection.label, exact: true })
    : menu.locator(`[role="option"][data-value=${JSON.stringify(typeof selection === 'string' ? selection : selection.value)}]`);
  await option.click();
  await expect(trigger).toHaveAttribute('aria-expanded', 'false');
}
export async function appearance(page: Page, theme: 'light' | 'dark' | 'system') {
  if (theme === 'system') {
    // System is only the initial preference, no longer a selectable UI action.
    await page.evaluate(() => localStorage.removeItem('shiftproof-theme'));
    await page.reload();
  } else if (await page.locator('html').getAttribute('data-theme') !== theme) {
    await page.locator('.appearance-control:visible').first().click();
  }
  if (theme !== 'system') await expect(page.locator('html')).toHaveAttribute('data-theme', theme);
}

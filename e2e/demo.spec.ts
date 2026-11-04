import { expect, test } from '@playwright/test';

test('demo switches profiles and remembers the selected theme', async ({ page }) => {
  await page.goto('/demo');
  const profile = page.getByLabel('Profilo dimostrativo');
  await expect(page.getByRole('heading', { name: 'Il mio percorso di cura' })).toBeVisible();
  await profile.selectOption('professional');
  await expect(page.getByRole('heading', { name: 'La mia attività clinica' })).toBeVisible();
  await profile.selectOption('organization');
  await expect(page.getByRole('heading', { name: 'La mia organizzazione' })).toBeVisible();
  await profile.selectOption('platform');
  await expect(page.getByRole('heading', { name: 'Verifiche della piattaforma' })).toBeVisible();
  await profile.selectOption('research');
  await expect(page.getByRole('heading', { name: 'Spazio ricerca' })).toBeVisible();

  await page.getByLabel('Aspetto').selectOption('dark');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.getByRole('link', {name: 'Apri la demo di agenda e gestionale'}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByRole('link', {name: /Centro Clarìa/})).toBeVisible();
  await page.getByLabel('Aspetto').selectOption('light');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390);
});

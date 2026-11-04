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

test('patient forms retain focus while typing and deletion removes related demo records', async ({ page }) => {
  await page.goto('/demo/agenda');
  await page.getByRole('button', { name: 'Pazienti', exact: true }).click();
  await page.getByRole('button', { name: /EL Emma Laurent/ }).click();
  await page.getByRole('button', { name: 'Modifica scheda' }).click();
  const email = page.getByLabel('Email', { exact: true });
  await email.fill('');
  await email.pressSequentially('emma.updated@example.test');
  await expect(email).toBeFocused();
  await expect(email).toHaveValue('emma.updated@example.test');
  await page.getByRole('button', { name: /Salva paziente/ }).click();
  await page.getByRole('button', { name: 'Elimina paziente', exact: true }).click();
  const confirmation = page.getByLabel('Per confermare digita: Emma Laurent');
  await confirmation.pressSequentially('Emma Laurent');
  await expect(confirmation).toBeFocused();
  await page.getByRole('button', { name: 'Elimina definitivamente' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Emma Laurent/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Agenda', exact: true }).click();
  await expect(page.getByRole('button', { name: /Emma Laurent/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Fatture', exact: true }).click();
  await expect(page.getByRole('cell', { name: /Emma Laurent/ })).toHaveCount(0);
});

test('legacy system preference becomes light and only two modes are offered', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('health-theme', 'system'));
  await page.goto('/demo/agenda');
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  await expect(page.getByLabel('Aspetto').locator('option')).toHaveText(['Light mode', 'Dark mode']);
});

test('archive and reactivate a patient; cancelling deletion preserves the record', async ({ page }) => {
  await page.goto('/demo/agenda');
  await page.getByRole('button', { name: 'Pazienti', exact: true }).click();
  await page.getByRole('button', { name: /EL Emma Laurent/ }).click();
  await page.getByRole('button', { name: 'Elimina paziente', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Elimina definitivamente' })).toBeDisabled();
  await page.getByRole('button', { name: 'Annulla', exact: true }).click();
  await page.getByRole('button', { name: /EL Emma Laurent/ }).click();
  await page.getByRole('button', { name: 'Archivia percorso' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Chiudi', exact: true }).click();
  await expect(page.getByRole('button', { name: /EL Emma Laurent/ })).toHaveCount(0);
  await page.getByRole('button', { name: 'Archiviati', exact: true }).click();
  await page.getByRole('button', { name: /EL Emma Laurent/ }).click();
  await page.getByRole('button', { name: 'Riattiva percorso' }).click();
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Attivi', exact: true }).click();
  await expect(page.getByRole('button', { name: /EL Emma Laurent/ })).toBeVisible();
});

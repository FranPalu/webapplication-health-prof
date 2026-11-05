import { expect, test } from '@playwright/test';

test('opening the demo portal preserves the selected role and its work area', async ({page}) => {
  await page.setViewportSize({width:320,height:800});
  await page.goto('/demo');
  await page.getByLabel('Profilo dimostrativo').selectOption('physician');
  await page.getByRole('link', {name:'Apri il portale · Medico'}).click();
  await expect(page).toHaveURL(/\/demo\/portale\/physician$/);
  await expect(page.getByRole('heading', {name:'Fascicolo clinico DEMO-042'})).toBeVisible();
  await expect(page.getByRole('img', {name:'Schema di una sezione assiale del torace'})).toBeVisible();

  await expect(page.getByRole('navigation', {name:'Spazi per ruolo'})).toHaveCount(0);
  async function openWorkspace(role: string, label: string) {
    await page.getByRole('link', {name:'Torna ai profili demo'}).click();
    await page.getByLabel('Profilo dimostrativo').selectOption(role);
    await page.getByRole('link', {name:'Apri il portale · '+label}).click();
  }
  await openWorkspace('nurse', 'Infermiere');
  await expect(page).toHaveURL(/\/demo\/portale\/nurse$/);
  await expect(page.getByRole('heading', {name:'Piano del turno e consegne'})).toBeVisible();
  await expect(page.getByRole('img')).toHaveCount(0);
  await page.getByLabel('Solo da seguire').check();
  await expect(page.getByText(/Accoglienza DEMO-042/)).toHaveCount(0);
  await page.getByText(/Consegna al turno del pomeriggio/).click();
  await expect(page.getByText(/Verificare il contatto in agenda/)).toBeVisible();

  await openWorkspace('research', 'Ricercatore');
  await expect(page).toHaveURL(/\/demo\/portale\/research$/);
  await page.reload();
  await expect(page.getByRole('table', {name:'Osservazioni sintetiche per anno e codice'})).toBeVisible();
  await expect(page.getByText(/DEMO-042/)).toHaveCount(0);
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth',320);
  await openWorkspace('organization', 'Amministrazione struttura');
  await expect(page.getByRole('heading', {name:'Accettazione e capacità'})).toBeVisible();
  await openWorkspace('pharmacy', 'Farmacia');
  await expect(page.getByRole('heading', {name:'Richieste e ritiri'})).toBeVisible();
  await expect(page.getByRole('link', {name:'Accedi con un account'})).toHaveAttribute('href','/');
});

test('clinical demo shows synthetic imaging and keeps drafts in the physician view', async ({page}) => {
  await page.setViewportSize({width:320, height:800});
  await page.goto('/demo');
  const profile = page.getByLabel('Profilo dimostrativo');
  await profile.selectOption('physician');
  await expect(page.getByRole('heading', {name:'Analisi automatica preliminare – non è una diagnosi'})).toBeVisible();
  await expect(page.getByRole('img', {name:'Schema di una sezione assiale del torace'})).toBeVisible();
  await page.getByLabel('Sezione o fotogramma').selectOption('0');
  await expect(page.getByText('TC torace · Apice', {exact:true})).toBeVisible();
  await page.getByLabel('Esame illustrativo').selectOption('eco');
  await expect(page.getByRole('img', {name:'Schema di un fotogramma ecocardiografico'})).toBeVisible();
  await page.getByLabel('Mostra il marcatore illustrativo').uncheck();
  await expect(page.getByText('Ecocardiogramma · Fotogramma 2', {exact:true})).toBeVisible();
  await expect(page.getByText(/la misura non viene pubblicata/)).toBeVisible();
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 320);
  await profile.selectOption('nurse');
  await expect(page.getByRole('heading', {name:'Consegne infermieristiche'})).toBeVisible();
  await profile.selectOption('research');
  await expect(page.getByText('28 account distinti')).toBeVisible();
  await expect(page.getByText(/DEMO-042 presa in carico/)).toHaveCount(0);
  await expect(page.getByRole('heading', {name:'Analisi automatica preliminare – non è una diagnosi'})).toHaveCount(0);
  await profile.selectOption('pharmacy');
  await expect(page.getByRole('heading', {name:'Banco e prenotazioni'})).toBeVisible();
});

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

for (const theme of ['light', 'dark']) {
  test('patient form contrast and fiscal field in ' + theme, async ({ page }) => {
    await page.goto('/demo/agenda');
    await page.getByLabel('Aspetto').selectOption(theme);
    await page.getByRole('button', { name: 'Pazienti', exact: true }).click();
    await page.getByRole('button', { name: /EL Emma Laurent/ }).click();
    await page.getByRole('button', { name: 'Modifica scheda' }).click();
    await expect(page.getByLabel(/^Codice Fiscale/)).toBeVisible();
    await expect(page.getByLabel('Codice del Comune o Stato di nascita')).not.toBeVisible();
    const contrast = await page.locator('.modal').evaluate(modal => {
      function rgb(value: string) { return value.match(/[\d.]+/g)!.slice(0, 3).map(Number); }
      function luminance(channels: number[]) {
        const linear = channels.map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4);
        return linear[0] * .2126 + linear[1] * .7152 + linear[2] * .0722;
      }
      return [...modal.querySelectorAll('h2,.modal-heading p,.field > span:first-child,.field small,input,select,.modal-footer button')].filter(el => (el as HTMLElement).checkVisibility()).map(el => {
        let ancestor: Element | null = el;
        let background = '';
        while (ancestor) {
          background = getComputedStyle(ancestor).backgroundColor;
          if (background !== 'rgba(0, 0, 0, 0)' && background !== 'transparent') break;
          ancestor = ancestor.parentElement;
        }
        const fg = luminance(rgb(getComputedStyle(el).color)), bg = luminance(rgb(background));
        return { text: el.textContent?.slice(0, 45), ratio: (Math.max(fg, bg) + .05) / (Math.min(fg, bg) + .05) };
      });
    });
    for (const item of contrast) expect(item.ratio, item.text).toBeGreaterThanOrEqual(4.5);
    await page.screenshot({ path: '/tmp/claria-form-' + theme + '.png' });
    await page.setViewportSize({ width: 390, height: 844 });
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth', 390);
  });
}

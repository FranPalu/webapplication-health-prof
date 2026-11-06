import {expect, test} from '@playwright/test';

const profiles = [
  {role:'patient', kind:'clinic', it:'Il mio percorso di cura', en:'My care journey', section:'workspace-bookings'},
  {role:'professional', kind:'clinic', it:'La mia attività clinica', en:'My clinical work', section:'workspace-patients'},
  {role:'organization_admin', kind:'clinic', it:'La mia organizzazione', en:'My organization', section:'workspace-management'},
  {role:'organization_admin', kind:'pharmacy', it:'La mia farmacia', en:'My pharmacy', section:'workspace-management'},
  {role:'researcher', kind:'research', it:'Spazio ricerca', en:'Research workspace', section:'workspace-research'},
  {role:'organization_admin', kind:'clinic', platform:true, it:'Verifiche della piattaforma', en:'Platform reviews', section:'workspace-reviews'},
];

for (const profile of profiles) {
  test(`workspace accessibility and localization for ${profile.en}`, async ({page}) => {
    const empty = {results:[], next:null};
    // Exercise the rendered UI for every profile. Authentication and permission
    // enforcement are exercised separately with the Django and clinical fixtures.
    await page.route('**/api/v1/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/api/v1/', '');
      const responses: Record<string, unknown> = {
        'auth/session/': {
          id:'synthetic-user', email:'synthetic@patients.example', role:profile.role,
          email_verified:true, mfa_enabled:true, mfa_verified:true, requires_mfa:true,
          is_platform_admin:!!profile.platform, verification_status:'approved',
        },
        'organizations/': {results:[{id:'synthetic-organization', name:'Organizzazione sintetica', kind:profile.kind}], next:null},
        'patients/':empty, 'shares/':empty, 'notifications/':[],
        'consents/texts/':[], 'consents/':[], 'patients/access-history/':[],
        'admin/verifications/':empty,
      };
      if (!(path in responses)) return route.fulfill({status:404});
      await route.fulfill({json:responses[path]});
    });
    await page.setViewportSize({width:320, height:800});
    await page.goto('/');
    await page.getByLabel('Seleziona organizzazione').selectOption('synthetic-organization');
    await expect(page.getByRole('heading',{name:profile.it, exact:true})).toBeVisible();
    const nav = page.getByRole('navigation',{name:'Accesso rapido'});
    const shortcut = nav.locator(`a[href="#${profile.section}"]`);
    for (const theme of ['light', 'dark']) {
      await page.getByLabel('Aspetto').selectOption(theme);
      await shortcut.focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('#'+profile.section)).toBeFocused();
      await expect(page.locator('body')).toHaveJSProperty('scrollWidth',320);
    }
    expect(await nav.ariaSnapshot()).toContain('- link');
    await page.getByLabel('Lingua / Language').selectOption('en');
    await expect(page.locator('html')).toHaveAttribute('lang','en');
    await expect(page.getByRole('heading',{name:profile.en, exact:true})).toBeVisible();
    await expect(page.getByRole('navigation',{name:'Quick navigation'})).toBeVisible();
  });
}

test('synthetic lab queue confirms patient before recording acknowledgment', async ({page}) => {
  let acknowledgments = 0;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '');
    const empty = {results:[], next:null};
    if (path === 'clinical/result-reviews/synthetic-review/acknowledge/') {
      expect(route.request().postDataJSON()).toEqual({patient:'synthetic-patient'});
      acknowledgments++;
      return route.fulfill({json:{id:'synthetic-review'}});
    }
    const responses: Record<string, unknown> = {
      'auth/session/': {
        id:'synthetic-user', email:'synthetic@patients.example', role:'professional',
        email_verified:true, mfa_enabled:true, mfa_verified:true, requires_mfa:true,
        verification_status:'approved',
      },
      'organizations/': {results:[{id:'synthetic-organization', name:'Struttura sintetica', kind:'clinic'}], next:null},
      'patients/': {results:[{id:'synthetic-patient', first_name:'Paziente', last_name:'Fittizio', birth_date:'1990-01-01', organization:'synthetic-organization'}], next:null},
      'shares/':empty, 'notifications/':[], 'consents/texts/':[],
      'clinical/patients/synthetic-patient/result-reviews/': acknowledgments ? empty : {
        results:[{id:'synthetic-review', outcome:'critical', report:'synthetic-report', version:2, escalation_assigned:false}],
        next:null,
      },
    };
    if (!(path in responses)) return route.fulfill({status:404});
    return route.fulfill({json:responses[path]});
  });
  await page.goto('/');
  await page.getByText('Referti da prendere in visione', {exact:true}).click();
  await page.getByRole('button', {name:'Aggiorna coda'}).click();
  await expect(page.getByText('Limite critico configurato raggiunto')).toBeVisible();
  await expect(page.getByText('Escalation senza destinatario.', {exact:false})).toBeVisible();
  await expect(page.getByRole('link', {name:'Apri versione del referto 2'})).toHaveAttribute(
    'href', '/api/v1/fhir/DiagnosticReport/synthetic-report/_history/2'
  );
  page.once('dialog', async dialog => {
    expect(dialog.message()).toContain('Paziente Fittizio · 1990-01-01');
    await dialog.dismiss();
  });
  await page.getByRole('button', {name:'Registra presa visione'}).click();
  expect(acknowledgments).toBe(0);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Registra presa visione'}).click();
  await expect(page.getByText('Nessun referto in coda.')).toBeVisible();
  expect(acknowledgments).toBe(1);
});

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
  let completions = 0;
  let overrides = 0;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/v1/', '');
    const empty = {results:[], next:null};
    if (path === 'clinical/result-reviews/synthetic-review/acknowledge/') {
      expect(route.request().postDataJSON()).toEqual({patient:'synthetic-patient'});
      acknowledgments++;
      return route.fulfill({json:{id:'synthetic-review'}});
    }
    if (path === 'clinical/patients/synthetic-patient/medication-checks/') {
      expect(route.request().postDataJSON()).toMatchObject({context_confirmed:true, medications:[
        {code:'SYN-A', route:'SYN-ROUTE', unit:'mg', daily_dose:'2'},
      ]});
      return route.fulfill({json:{id:'synthetic-check', result:{
        status:'findings',
        source:{name:'Catalogo fittizio', version:'test-1', license:'fixture', reference:'fonte sintetica', evidence_level:'synthetic'},
        findings:[{kind:'allergy', medications:['SYN-A'], reference:'riferimento test', evidence_level:'synthetic'}],
      }}});
    }
    if (path === 'clinical/medication-checks/synthetic-check/override/') {
      expect(route.request().postDataJSON()).toEqual({patient:'synthetic-patient', reason:'Prova sintetica'});
      overrides++;
      return route.fulfill({json:{status:'recorded'}});
    }
    if (path === 'clinical/result-reviews/synthetic-review/complete/') {
      expect(route.request().postDataJSON()).toEqual({patient:'synthetic-patient', note:'Fonte sintetica verificata'});
      completions++;
      return route.fulfill({json:{status:'reviewed'}});
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
      'clinical/patients/synthetic-patient/lab-orders/': empty,
      'clinical/patients/synthetic-patient/result-reviews/': completions ? empty : {
        results:[{id:'synthetic-review', outcome:'critical', report:'synthetic-report', version:2, escalation_assigned:false, acknowledged_at:acknowledgments ? '2026-01-02T00:00:00Z' : null}],
        next:null,
      },
    };
    if (!(path in responses)) return route.fulfill({status:404});
    return route.fulfill({json:responses[path]});
  });
  await page.goto('/');
  await page.getByText('Esami e referti in sospeso', {exact:true}).click();
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
  await page.getByLabel('Nota di revisione').fill('Fonte sintetica verificata');
  expect(acknowledgments).toBe(1);
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Completa revisione'}).click();
  await expect(page.getByText('Nessun referto in coda.')).toBeVisible();
  expect(completions).toBe(1);

  await page.getByText('Screening farmacologico sintetico', {exact:true}).click();
  await page.getByLabel('Identificativo per screening', {exact:true}).fill('SYN-ID');
  await page.getByLabel('Data di nascita per screening').fill('1990-01-01');
  const medication = page.getByRole('group', {name:'Medicinale 1'});
  await medication.getByLabel('Codice', {exact:true}).fill('SYN-A');
  await medication.getByLabel('Via', {exact:true}).fill('SYN-ROUTE');
  await medication.getByLabel('Unità', {exact:true}).fill('mg');
  await medication.getByLabel('Dose giornaliera', {exact:true}).fill('2');
  await page.getByLabel('Confermo la completezza del contesto').check();
  await page.getByRole('button', {name:'Esegui screening'}).click();
  await expect(page.getByText('Catalogo fittizio · test-1', {exact:false})).toBeVisible();
  await expect(page.getByText('riferimento test · synthetic', {exact:false})).toBeVisible();
  await page.getByLabel('Motivazione override').fill('Prova sintetica');
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Registra override'}).click();
  await expect(page.getByText('Motivazione registrata.')).toBeVisible();
  expect(overrides).toBe(1);
});

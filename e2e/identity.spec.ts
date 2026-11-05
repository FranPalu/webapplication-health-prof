import {makePdf} from '../lib/pdf';
import {test,expect} from '@playwright/test';
import {readFileSync,readdirSync} from 'node:fs';
import {join} from 'node:path';
import {createHmac,randomUUID} from 'node:crypto';
const password='Synthetic-E2E-Only!847long';
function totp(secret:string){
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits=[...secret].map(c=>alphabet.indexOf(c).toString(2).padStart(5,'0')).join('');
  const key=Buffer.from(bits.match(/.{8}/g)!.map(b=>parseInt(b,2)));
  const counter=Buffer.alloc(8);counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const hash=createHmac('sha1',key).update(counter).digest(), offset=hash[19]&15;
  return String((hash.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}
async function emailLink(email:string){
  let result='';
  await expect.poll(async()=>{
    if(process.env.MAILPIT_URL){
      const list=await (await fetch(process.env.MAILPIT_URL+'/api/v1/messages')).json() as {messages:{ID:string;To:{Address:string}[]}[]};
      const item=list.messages.find(m=>m.To.some(t=>t.Address===email));
      if(item){
        const message=await (await fetch(process.env.MAILPIT_URL+'/api/v1/message/'+item.ID)).json() as {HTML:string};
        result=message.HTML.match(/href="(https?:\/\/[^"\s]+\?action=verify#token=[\w-]+)"/)?.[1]||'';
      }
    }else{
      const directory=process.env.E2E_MAIL_DIR||'backend/.test-mail';
      for(const file of readdirSync(directory)){
        const body=readFileSync(join(directory,file),'utf8');
        if(body.includes(`To: ${email}`)) result=body.match(/https?:\/\/[^\s]+\?action=verify#token=[\w-]+/)?.[0]||'';
      }
    }
    return result;
  }).not.toBe('');
  return result;
}
test('registration, verified email, login and logout; legacy API unavailable',async({page})=>{
  const email=`patient-${randomUUID()}@patients.example`;
  await page.goto('/');
  await page.getByRole('button',{name:'Registrati',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).first().fill(email);
  await page.getByLabel('Nuova password').fill(password);
  await page.getByRole('button',{name:'Registrati',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Controlla');
  await page.goto(await emailLink(email));
  await page.reload();
  await page.getByRole('button',{name:'Conferma',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('completata');
  await page.getByLabel('Email',{exact:true}).first().fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Accedi',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Anagrafiche autorizzate'})).toBeVisible();
  const legacy=await page.request.get('/api/studio');expect(legacy.status()).toBe(404);
  await page.getByRole('button',{name:'Esci',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Accedi',exact:true})).toBeVisible();
  await page.getByLabel('Lingua / Language').selectOption('en');
  await expect(page.getByRole('heading',{name:'Your care workspace'})).toBeVisible();
});
test('organization onboarding requires TOTP and creates a tenant',async({page})=>{
  const email=`admin-${randomUUID()}@patients.example`;
  await page.goto('/');await page.getByRole('button',{name:'Registrati',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).first().fill(email);
  await page.getByLabel('Nuova password').fill(password);
  await page.getByRole('combobox',{name:'Profilo',exact:true}).selectOption('organization_admin');
  await page.getByRole('button',{name:'Registrati',exact:true}).click();
  await expect(page.getByRole('status')).toContainText('Controlla');
  await page.goto(await emailLink(email));
  await page.getByRole('button',{name:'Conferma',exact:true}).click();
  await page.getByLabel('Email',{exact:true}).first().fill(email);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Accedi',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Le tue organizzazioni'})).toHaveCount(0);
  await page.getByLabel('Password',{exact:true}).fill(password);
  await page.getByRole('button',{name:'Configura autenticatore'}).click();
  const secret=await page.locator('.identity-secret').innerText();
  await page.getByLabel('Codice TOTP o di recupero').fill(totp(secret));
  await page.getByRole('button',{name:'Conferma',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Le tue organizzazioni'})).toBeVisible();
  await expect(page.getByText('Conserva questi codici', {exact:false})).toBeVisible();
  await page.getByLabel('Nome',{exact:true}).fill('Clinica E2E FITTIZIA');
  await page.getByRole('button',{name:'Crea',exact:true}).click();
  await expect(page.getByRole('listitem').filter({hasText:'Clinica E2E FITTIZIA'})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await expect(page.locator('body')).toHaveJSProperty('scrollWidth',390);
});

test('professional uploads, searches, downloads and archives a clinical document', async ({page}) => {
  const fixture = process.env.E2E_CLINICAL_FIXTURE;
  test.skip(!fixture, 'Requires the synthetic clinical browser fixture and ClamAV.');
  const account = JSON.parse(readFileSync(fixture!, 'utf8')) as {email:string;password:string};
  await page.goto('/');
  await page.getByLabel('Email', {exact:true}).first().fill(account.email);
  await page.getByLabel('Password', {exact:true}).fill(account.password);
  await page.getByRole('button', {name:'Accedi',exact:true}).click();
  await expect(page.getByRole('button', {name:'Configura autenticatore'})).toBeVisible();
  await page.getByLabel('Password', {exact:true}).fill(account.password);
  await page.getByRole('button', {name:'Configura autenticatore'}).click();
  await page.getByLabel('Codice TOTP o di recupero').fill(totp(await page.locator('.identity-secret').innerText()));
  await page.getByRole('button', {name:'Conferma',exact:true}).click();
  await page.getByText('Documenti clinici', {exact:true}).click();
  await page.getByLabel('Titolo del documento').fill('Documento E2E sintetico');
  await page.getByLabel('File (massimo 10 MiB)').setInputFiles({
    name:'synthetic.pdf',mimeType:'application/pdf',buffer:Buffer.from(makePdf(['KeywordSaffron'])),
  });
  await page.getByRole('button', {name:'Carica documento',exact:true}).click();
  await expect(page.getByRole('button', {name:/Documento E2E sintetico/})).toBeVisible();
  await page.getByLabel('Cerca nei documenti').fill('KeywordSaffron');
  await page.getByRole('button', {name:'Cerca o mostra tutti'}).click();
  await page.getByRole('button', {name:/Documento E2E sintetico/}).click();
  const download = page.waitForEvent('download');
  await page.getByRole('link', {name:'Scarica versione 1'}).click();
  expect(await (await download).failure()).toBeNull();
  page.once('dialog', dialog => dialog.accept());
  await page.getByRole('button', {name:'Archivia documento'}).click();
  await expect(page.getByText('Nessun documento trovato.')).toBeVisible();
});

test('professional reviews a local analysis and publishes only the final opinion', async ({page, browser}) => {
  const fixture = process.env.E2E_CLINICAL_FIXTURE;
  test.skip(process.env.E2E_ANALYSIS !== '1' || !fixture, 'Requires an enabled local analysis worker.');
  const account = JSON.parse(readFileSync(fixture!, 'utf8')) as {
    email:string; password:string; patient_email:string; patient_password:string; patient:string;
  };
  await page.goto('/');
  await page.getByLabel('Email', {exact:true}).first().fill(account.email);
  await page.getByLabel('Password', {exact:true}).fill(account.password);
  await page.getByRole('button', {name:'Accedi',exact:true}).click();
  await expect(page.getByRole('button', {name:'Configura autenticatore'})).toBeVisible();
  await page.getByLabel('Password', {exact:true}).fill(account.password);
  await page.getByRole('button', {name:'Configura autenticatore'}).click();
  await page.getByLabel('Codice TOTP o di recupero').fill(totp(await page.locator('.identity-secret').innerText()));
  await page.getByRole('button', {name:'Conferma',exact:true}).click();
  await page.getByText('Documenti clinici', {exact:true}).click();
  await page.getByLabel('Titolo del documento').fill('Referto sintetico M4');
  await page.getByLabel('Categoria').selectOption('report');
  await page.getByLabel('File (massimo 10 MiB)').setInputFiles({
    name:'lab.pdf',mimeType:'application/pdf',buffer:Buffer.from(makePdf(['Glucosio 110 mg/dL 60-100'])),
  });
  await page.getByRole('button', {name:'Carica documento',exact:true}).click();
  await page.getByRole('button', {name:/Referto sintetico M4/}).click();
  await page.getByText('Analisi preliminare', {exact:true}).click();
  const created = page.waitForResponse(response => response.request().method() === 'POST' && response.url().endsWith('/analysis/'));
  await page.getByRole('button', {name:'Avvia analisi del referto'}).click();
  const job = await (await created).json() as {id:string};
  await expect(async () => {
    await page.getByRole('button', {name:'Aggiorna analisi'}).click();
    await expect(page.getByText('Sopra intervallo', {exact:false})).toBeVisible({timeout:1000});
  }).toPass({timeout:45000, intervals:[1500,3000]});
  await page.getByLabel('Decisione').selectOption('modify');
  const text = 'Parere sintetico verificato per il collaudo.';
  await page.getByLabel('Parere finale').fill(text);
  await page.getByLabel('Ho verificato il referto e attesto il testo finale').check();
  await page.getByRole('button', {name:'Registra revisione'}).click();

  const patient = await browser.newPage();
  try {
    await patient.goto('/');
    await patient.getByLabel('Email', {exact:true}).first().fill(account.patient_email);
    await patient.getByLabel('Password', {exact:true}).fill(account.patient_password);
    await patient.getByRole('button', {name:'Accedi',exact:true}).click();
    await patient.getByText('Pareri professionali pubblicati', {exact:true}).click();
    await expect(patient.getByText('Nessun parere pubblicato.')).toBeVisible();
    expect((await patient.request.get('/api/v1/clinical/analysis/' + job.id + '/')).status()).toBe(403);
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', {name:'Pubblica il parere al paziente'}).click();
    await expect(page.getByText('Parere pubblicato', {exact:true})).toBeVisible();
    await patient.getByText('Pareri professionali pubblicati', {exact:true}).click();
    await patient.getByText('Pareri professionali pubblicati', {exact:true}).click();
    await expect(patient.getByText(text, {exact:true})).toBeVisible();
    await expect(patient.getByText('Analisi automatica preliminare', {exact:false})).toHaveCount(0);
  } finally {
    await patient.close();
  }
});

test('patient grants and withdraws research consent from the portal', async ({page}) => {
  const fixture = process.env.E2E_CLINICAL_FIXTURE;
  test.skip(!fixture, 'Requires a linked synthetic patient.');
  const account = JSON.parse(readFileSync(fixture!, 'utf8')) as {patient_email:string; patient_password:string};
  await page.goto('/');
  await page.getByLabel('Email', {exact:true}).first().fill(account.patient_email);
  await page.getByLabel('Password', {exact:true}).fill(account.patient_password);
  await page.getByRole('button', {name:'Accedi',exact:true}).click();
  await expect(page.getByRole('heading', {name:'Prenotazioni e farmacia'})).toBeVisible();
  await page.getByText('Consenso alla ricerca', {exact:true}).click();
  await expect(page.getByText('Consenso assente', {exact:true})).toBeVisible();
  await page.getByRole('button', {name:'Acconsento alla ricerca'}).click();
  await expect(page.getByText('Consenso attivo', {exact:true})).toBeVisible();
  await page.getByRole('button', {name:'Revoca consenso ricerca'}).click();
  await expect(page.getByText('Consenso assente', {exact:true})).toBeVisible();
});

test('workspace shortcuts support keyboard navigation and mobile layout in both themes', async ({page}) => {
  const fixture = process.env.E2E_CLINICAL_FIXTURE;
  test.skip(!fixture, 'Requires a linked synthetic patient.');
  const account = JSON.parse(readFileSync(fixture!, 'utf8')) as {patient_email:string; patient_password:string};
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Accedi',exact:true})).toBeVisible();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link',{name:'Vai al contenuto'})).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#portal-content')).toBeFocused();
  await page.getByLabel('Email',{exact:true}).first().fill(account.patient_email);
  await page.getByLabel('Password',{exact:true}).fill(account.patient_password);
  await page.getByRole('button',{name:'Accedi',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Il mio percorso di cura'})).toBeVisible();
  const shortcuts = page.getByRole('navigation',{name:'Accesso rapido'});
  const appointments = shortcuts.getByRole('link',{name:'Prenotazioni e farmacia'});
  for (const theme of ['light', 'dark']) {
    await page.getByLabel('Aspetto').selectOption(theme);
    await appointments.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('#workspace-bookings')).toBeFocused();
    await expect(page.locator('body')).toHaveJSProperty('scrollWidth',390);
  }
  await page.getByLabel('Lingua / Language').selectOption('en');
  await expect(page.getByRole('heading',{name:'My care journey'})).toBeVisible();
  await expect(page.getByRole('navigation',{name:'Quick navigation'})).toBeVisible();
});

test('app manifest points to public icons and does not register a worker', async ({page}) => {
  await page.goto('/');
  const manifestPath = await page.locator('link[rel="manifest"]').getAttribute('href');
  expect(manifestPath).toBeTruthy();
  const manifest = await (await page.request.get(manifestPath!)).json() as {display:string; start_url:string; icons:{src:string}[]};
  expect(manifest.display).toBe('standalone');
  expect(manifest.start_url).toBe('/');
  for (const icon of manifest.icons) expect((await page.request.get(icon.src)).ok()).toBe(true);
  expect(await page.evaluate(async () => (await navigator.serviceWorker?.getRegistrations())?.length ?? 0)).toBe(0);
});

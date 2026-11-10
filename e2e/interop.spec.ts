import {test, expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
import {createHmac} from 'node:crypto';

function totp(secret: string) {
  const alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
  const bits=[...secret].map(c=>alphabet.indexOf(c).toString(2).padStart(5,'0')).join('');
  const key=Buffer.from(bits.match(/.{8}/g)!.map(b=>parseInt(b,2)));
  const counter=Buffer.alloc(8); counter.writeBigUInt64BE(BigInt(Math.floor(Date.now()/30000)));
  const hash=createHmac('sha1',key).update(counter).digest(); const offset=hash[19]&15;
  return String((hash.readUInt32BE(offset)&0x7fffffff)%1000000).padStart(6,'0');
}

test('P5 authenticated OHIF retrieves a mapped synthetic image through the clinical gateway', async ({page, browser}) => {
  const fixture=process.env.E2E_INTEROP_FIXTURE;
  test.skip(!fixture, 'Requires the isolated synthetic PACS/OHIF fixture.');
  const account=JSON.parse(readFileSync(fixture!, 'utf8')) as {email:string;password:string;totp_secret:string;study_uid:string};
  const viewer=process.env.E2E_PACS_VIEWER_URL || 'http://localhost:8090';
  const anonymous=await browser.newContext();
  try {
    expect((await anonymous.request.get(viewer+'/api/v1/dicom-web/studies?StudyInstanceUID='+account.study_uid)).status()).toBe(403);
  } finally {await anonymous.close();}
  await page.goto('/');
  await page.getByLabel('Email', {exact:true}).first().fill(account.email);
  await page.getByLabel('Password', {exact:true}).fill(account.password);
  await page.getByRole('button',{name:'Accedi',exact:true}).click();
  await page.getByLabel('Codice TOTP o di recupero').fill(totp(account.totp_secret));
  await page.getByRole('button',{name:'Verifica',exact:true}).click();
  await expect(page.getByRole('heading',{name:'La mia attività clinica',exact:true})).toBeVisible();
  const pixels=page.waitForResponse(response=>response.url().includes('/frames/1') && response.status()===200);
  await page.goto(viewer+'/viewer?StudyInstanceUIDs='+account.study_uid);
  await pixels;
  await expect(page.locator('canvas').first()).toBeVisible();
  await page.screenshot({path:process.env.E2E_PACS_SCREENSHOT || 'test-results/p5-ohif-synthetic.png', fullPage:true});
});

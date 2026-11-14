/** Read-only integration smoke against the local server; never starts an LLM run. */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin = process.env.APP_URL || 'http://127.0.0.1:8000';
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page = await browser.newPage({viewport:{width:1440,height:1050}});
const errors = [], prohibited = [];
page.on('pageerror', error => errors.push(error.message));
await page.route('**/api/feedback-pricing/**', async route => {
  if (route.request().method() !== 'GET') {prohibited.push(route.request().url()); return route.abort();}
  return route.continue();
});
try {
  await mkdir(new URL('test-results/',import.meta.url),{recursive:true});
  await page.goto(`${origin}/admin#optimization`);
  const link = page.getByRole('link',{name:'LLM feedback pricing',exact:true});
  await link.waitFor(); await link.click();
  await page.locator('#feedback-route').selectOption('HKG-KMQ');
  await page.locator('#feedback-flight').selectOption('NET-HKG-KMQ-20270518');
  await page.waitForFunction(()=>document.getElementById('feedback-initial').value==='410');
  assert.equal(await page.locator('#feedback-initial').getAttribute('readonly'),'');
  assert.match(await page.locator('#feedback-scope').textContent(),/HKG → KMQ/);
  assert.match(await page.locator('#feedback-initial-help').textContent(),/HK\$0/);
  assert.equal(await page.getByLabel('Pass fee',{exact:false}).count(),0);
  assert.equal(await page.locator('#feedback-error').isHidden(),true);
  await page.screenshot({path:'test-results/feedback-pricing-live-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:'test-results/feedback-pricing-live-mobile.png',fullPage:true});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth <= window.innerWidth),true);
  assert.deepEqual(prohibited,[]); assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',source:'real local server, read-only',initial_fare:410,flight:'NET-HKG-KMQ-20270518',checks:['Admin link','flight scope','dataset fare','no fee control','mobile width','no JS errors'],llm_runs_started:0}));
} finally {await browser.close();}

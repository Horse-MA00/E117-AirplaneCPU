/** Customer panel integration: actual 100-person rules run, no live calls.
 * Also checks a mocked paused live batch cannot auto-resume or spend.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const origin = process.env.APP_URL || 'http://127.0.0.1:8000';
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
try {
  await page.goto(`${origin}/admin#customers`, { waitUntil: 'networkidle' });
  assert.equal(await page.locator('#agent-count').inputValue(), '100');
  assert.equal(await page.locator('#agent-count').getAttribute('max'), '1000');
  if (!await page.locator('#live-mode-option').isDisabled()) {
    await page.locator('#agent-count').fill('1000'); await page.locator('#agent-mode').selectOption('live');
    assert.equal(await page.locator('#agent-count').getAttribute('max'), '100');
    assert.equal(await page.locator('#agent-count').inputValue(), '100');
    assert.equal(await page.locator('#agent-call-budget').getAttribute('max'), '120');
    await page.locator('#agent-mode').selectOption('deterministic');
  }
  const start = page.waitForResponse(r => r.url().endsWith('/api/agents/panels') && r.request().method() === 'POST');
  await page.locator('#agent-button').click();
  const started = await (await start).json(); assert.ok(started.run_id, JSON.stringify(started));
  await page.waitForFunction(() => document.getElementById('panel-run-status').textContent.startsWith('Complete'), null, { timeout: 120000 });
  const report = await (await page.request.get(`${origin}/api/agents/panels/${started.run_id}`)).json();
  assert.equal(report.count, 100); assert.equal(report.progress.completed_stages, 600);
  assert.equal(report.runtime.provider_calls, 0);
  assert.equal(await page.locator('#panel-people tr').count(), 20);
  assert.equal(await page.locator('#panel-completed').textContent(), '100');
  assert.equal(await page.locator('#panel-joined').textContent(), String(report.summary.joined));
  assert.match(await page.locator('#panel-joined-detail').textContent(), new RegExp(`Of ${report.summary.eligible_decided} eligible`));
  assert.equal(await page.locator('#panel-progress-bar').getAttribute('value'), '600');
  assert.equal(await page.locator('#panel-segments .segment-result').count(), 14);
  await page.waitForFunction(() => document.querySelectorAll('#panel-person-detail .panel-journey li').length === 6);
  assert.doesNotMatch(await page.locator('#panel-results').innerText(), /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/);
  await page.locator('#panel-next').click();
  assert.equal(await page.locator('#panel-page-label').textContent(), '21–40 of 100');
  await page.locator('#panel-decision-filter').selectOption('JOIN_PASS');
  assert.equal(await page.locator('#panel-people tr').count(), Math.min(20, report.summary.joined));
  const joined = report.results.filter(r => r.decision?.action === 'JOIN_PASS');
  assert.ok(joined.length);
  await page.locator('#panel-search').fill(joined[0].person.customer_id);
  assert.equal(await page.locator('#panel-people tr').count(), 1);
  await page.locator('#panel-people button').click();
  await page.waitForFunction(id => document.getElementById('panel-person-detail').textContent.includes(id), joined[0].person.customer_id);
  assert.equal(await page.locator('#panel-person-detail .panel-journey li').count(), 6);
  assert.match(await page.locator('#panel-person-detail').textContent(), /Budget left HK\$/);
  await page.locator('#panel-search').fill(''); await page.locator('#panel-decision-filter').selectOption('all');
  const scenario = page.locator('#agent-scenario');
  await scenario.locator('summary').focus(); await page.keyboard.press('Enter');
  assert.equal(await scenario.getAttribute('open'), '');
  assert.match(await scenario.innerText(), /4 \/ 0 \/ 1 member seats/);
  assert.match(await scenario.innerText(), /not purchases in this ledger/);
  await scenario.locator('summary').click();
  await page.locator('#view-customers h1').scrollIntoViewIfNeeded();
  await page.screenshot({ path: `${output}panel-admin-desktop.png`, fullPage: true });

  // Return a partial saved live panel only through fixtures. No model calls.
  let resumeCount = 0;
  const paused = structuredClone(report); paused.run_id = 'qa-panel-paused'; paused.mode = 'live'; paused.status = 'paused_at_budget';
  paused.progress = {completed_stages: 1,total_stages:600,completed_customers:0,total_customers:100};
  paused.summary = {...paused.summary, joined:1,eligible_decided:1,completed_customers:0};
  const detail = await (await page.request.get(`${origin}/api/agents/panels/${started.run_id}/people/${report.results[0].person.customer_id}`)).json();
  await page.route('**/api/agents/panels/qa-panel-paused/people/**', route => route.fulfill({json:detail}));
  await page.route('**/api/agents/panels/qa-panel-paused/resume', async route => {resumeCount++;assert.equal(route.request().postDataJSON().max_calls,60);await route.fulfill({json:{run_id:paused.run_id,status:'queued'}});});
  await page.route('**/api/agents/panels/qa-panel-paused', route => route.fulfill({json:resumeCount ? {...report,run_id:paused.run_id,mode:'live'} : paused}));
  await page.route('**/api/agents/panels', route => route.request().method() === 'POST' ? route.fulfill({json:{run_id:paused.run_id,status:'queued'}}) : route.fulfill({json:{runs:[{...paused,results:undefined}]}}));
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => !document.getElementById('panel-resume-controls').hidden);
  assert.equal(await page.locator('#panel-joined-detail').textContent(), 'Of 1 eligible travellers who have decided');
  assert.match(await page.locator('#agent-mode-message').textContent(), /partial/);
  await page.waitForTimeout(2200); assert.equal(resumeCount,0);
  await page.locator('#panel-resume').click();
  await page.waitForFunction(() => document.getElementById('panel-run-status').textContent.startsWith('Complete'));
  assert.equal(resumeCount,1);
  assert.equal(await page.locator('#panel-resume-controls').isVisible(),false);

  for (const width of [390, 768]) {
    await page.setViewportSize({width,height:900});
    await page.locator('#view-customers h1').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),false);
    await page.screenshot({path:`${output}panel-admin-${width}.png`,fullPage:true});
  }
  await page.locator('.primary-nav a[href="#members"]').click();
  // The view switches on hashchange, after the click resolves; wait for it instead of sampling once.
  await page.locator('#member-plan-form').waitFor({state:'visible'});
  assert.equal(await page.locator('#member-plan-form').isVisible(),true);
  assert.equal(await page.locator('#join-button').count(),0);assert.equal(await page.locator('#customer-id').count(),0);
  assert.equal(await page.locator('.portal-link').getAttribute('href'),'/members');
  let planFee = 399, planWrites = 0;
  await page.route('**/api/member-portal/plan', async route => {
    if (route.request().method() === 'POST') { planWrites++; planFee = route.request().postDataJSON().membership_fee; }
    await route.fulfill({json:{membership:{name:'UOption Fly Pass',fee:planFee,term_days:365},currency:'HKD',simulated:true}});
  });
  await page.locator('#member-fee').fill('599.75');
  await page.locator('.primary-nav a[href="#customers"]').click();
  await page.locator('.primary-nav a[href="#members"]').click();
  await page.waitForFunction(() => document.getElementById('membership-status').textContent.includes('HK$399'));
  assert.equal(await page.locator('#member-fee').inputValue(),'599.75','A proposed membership price must survive navigation without being silently overwritten.');
  assert.equal(planWrites,0,'A draft price must not publish automatically.');
  await page.locator('#save-plan-button').click();
  await page.waitForFunction(() => document.getElementById('membership-status').textContent.includes('HK$599.75'));
  assert.equal(planWrites,1);

  assert.deepEqual(errors,[]);
  console.log('PASS: 100-person / 600-stage rules panel; 20-row pagination, filters, 14-group comparisons, selected English/HKD journey, progress and manual resume, Admin/member separation, 390/768px layouts. No live calls.');
} finally { await browser.close(); }

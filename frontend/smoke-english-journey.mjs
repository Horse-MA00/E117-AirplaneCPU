/** Focused journey UI check. Generates current deterministic backend results;
 * intercepts the panel request, so this test never spends live-provider calls.
 * Run against the local app with: node frontend/smoke-english-journey.mjs
 */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
const fixture = JSON.parse(execFileSync(process.env.PYTHON || 'python3', ['-c', `
import json, tempfile
from pathlib import Path
from unittest.mock import patch
from llm_agent import audit
from llm_agent.journey_runner import run_journey
from llm_agent.population import coverage
with tempfile.TemporaryDirectory() as temporary, patch.object(audit, 'BASE', Path(temporary)/'runs'):
    result = run_journey(count=14)
    print(json.dumps({'result': result, 'coverage': coverage()}))
`], { cwd: root, encoding: 'utf8', maxBuffer: 4_000_000 }));
assert.equal(fixture.result.response_language, 'en');
assert.equal(fixture.result.currency, 'HKD');
assert.equal(fixture.result.summary.completed_stages, 84);

await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let panel = fixture.result;
let panelRequests = 0;
await page.route('**/api/personas', route => route.fulfill({ json: fixture.coverage }));
await page.route('**/api/agents/runs', route => route.fulfill({ json: { runs: [] } }));
await page.route('**/api/agents/run', route => {
  assert.equal(route.request().postDataJSON().mode, 'deterministic');
  panelRequests += 1;
  return route.fulfill({ json: panel });
});

try {
  await page.goto((process.env.APP_URL || 'http://127.0.0.1:8000') + '/#customers', { waitUntil: 'networkidle' });
  const scenario = page.locator('#agent-scenario');
  await scenario.locator('summary').focus();
  await page.keyboard.press('Enter');
  assert.equal(await scenario.getAttribute('open'), '');
  assert.equal(await scenario.locator('ol > li').count(), 6);
  assert.match(await scenario.innerText(), /not purchases in this journey's ledger/);
  assert.match(await scenario.innerText(), /4 \/ 0 \/ 1 seat counts are fixed test conditions/);
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.querySelectorAll('.customer-card').length === 14);
  assert.match(await page.locator('#agent-mode-message').innerText(), /English explanations · HKD amounts/);
  assert.match(await page.locator('#agent-mode-message').innerText(), /traveller-journey-v2.2-en/);
  const allCards = await page.locator('#agent-results').innerText();
  assert.doesNotMatch(allCards, /[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]/);
  assert.doesNotMatch(await page.locator('#coverage').innerText(), /[\u3040-\u30ff\u3400-\u9fff]/);
  const first = page.locator('.customer-card').first();
  assert.match(await first.innerText(), /Trip \+ new fee budget HK\$/);
  assert.match(await first.innerText(), /1 traveller(?:\s|$)/);
  await first.locator('summary').click();
  await page.locator('.customer-card').nth(1).locator('summary').click();
  assert.equal(await page.locator('.customer-card details[open]').count(), 2);
  assert.equal(await scenario.getAttribute('open'), '');
  assert.equal(await first.locator('.journey-events > li').count(), 6);
  assert.match(await first.locator('.journey-events').innerText(), /New membership fee paid: HK\$/);
  assert.match(await first.locator('.journey-events').innerText(), /Tickets paid: HK\$/);
  assert.match(await page.locator('.customer-card').nth(2).innerText(), /Existing member: no new subscription fee is charged/);
  await scenario.locator('summary').click();
  await page.screenshot({ path: `${output}english-journey-desktop.png`, fullPage: false });
  await first.screenshot({ path: `${output}english-journey-card.png` });

  // Historical raw text remains original, never translated and relabelled live.
  panel = structuredClone(fixture.result);
  delete panel.response_language;
  panel.prompt_version = 'traveller-journey-v2.1';
  panel.results[0].decision.reason = '歷史回覆保留原文。';
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.querySelector('#agent-mode-message').textContent.includes('Original response language preserved'));
  assert.match(await first.innerText(), /歷史回覆保留原文。/);

  panel = fixture.result;
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.querySelector('#agent-mode-message').textContent.includes('English explanations'));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#view-customers h1').scrollIntoViewIfNeeded();
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await page.screenshot({ path: `${output}english-journey-mobile.png`, fullPage: false });
  await first.locator('summary').click();
  await first.screenshot({ path: `${output}english-journey-card-mobile.png` });
  assert.equal(panelRequests, 3);
  assert.deepEqual(errors, []);
  console.log('English journey UI passed: 14 current personas / 84 stages, HKD budgets, keyboard disclosures, original historical text and 390px layout; zero live calls.');
} finally {
  await browser.close();
}

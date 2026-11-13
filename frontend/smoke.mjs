/** Run against an already-running backend. No production browser dependencies.
 * npm install && npx playwright install chromium && npm run test:smoke
 * Add -- --transactions to create explicit demo membership / booking records.
 */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const origin = process.env.APP_URL || 'http://127.0.0.1:8000';
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = [];
page.on('pageerror', (error) => errors.push(error.message));
const waitForecast = () => page.waitForFunction(() => document.querySelector('#flight-main').getAttribute('aria-busy') === 'false');
const navigate = (view) => page.locator(`.primary-nav a[href="#${view}"]`).click();

try {
  await page.goto(origin, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.getElementById('demand-value').textContent !== '—');
  assert.equal(await page.locator('#error').isVisible(), false);
  assert.ok((await page.locator('#dataset-label').textContent()).includes('synthetic'));
  await page.locator('[data-day="14"]').click();
  await waitForecast();
  assert.equal(await page.locator('#history-table tr').count(), 15);
  await page.locator('[data-day="28"]').click();
  await waitForecast();
  await page.screenshot({ path: `${output}desktop.png`, fullPage: true });

  await navigate('pricing');
  await page.locator('#passenger-cost').fill('80');
  const responsePromise = page.waitForResponse((response) => response.url().endsWith('/api/optimize'));
  await page.locator('#optimize-button').click();
  const result = await (await responsePromise).json();
  assert.equal(result.config.incremental_cost, 80, 'The cost input must reach the financial model.');
  assert.equal(result.candidates.length, 192);
  await page.waitForFunction(() => !document.getElementById('pricing-results').hidden);
  if (result.best.decision === 'OFFER' && result.best.open_day < 28) {
    assert.equal(await page.locator('#apply-policy').isDisabled(), true, 'Future policy must not publish early.');
  }
  const heatCells = page.locator('#heatmap button:not(:disabled)');
  if (await heatCells.count()) {
    await heatCells.first().click();
    assert.ok((await page.locator('#heatmap-detail').textContent()).includes('Fare'));
  }
  await page.screenshot({ path: `${output}pricing-desktop.png`, fullPage: true });
  if (!await page.locator('#send-market-candidate').isDisabled()) {
    await page.locator('#send-market-candidate').click();
    assert.equal(await page.locator('#market-fare').inputValue(), String(result.best.member_fare));
    assert.equal(await page.locator('#market-fee').inputValue(), String(result.best.membership_fee));
    assert.ok((await page.locator('#market-candidate-origin').textContent()).includes('hypothesis'));
  }

  await navigate('customers');
  await page.locator('#agent-count').fill('14');
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.querySelectorAll('.customer-card').length === 14);
  assert.ok((await page.locator('#agent-mode-message').textContent()).includes('not observed'));
  await page.screenshot({ path: `${output}customers-desktop.png`, fullPage: true });

  await navigate('market');
  const marketStartResponse = page.waitForResponse((response) => response.url().endsWith('/api/market/runs') && response.request().method() === 'POST');
  await page.locator('#market-mode').selectOption('deterministic');
  await page.locator('#market-start').click();
  const started = await (await marketStartResponse).json();
  assert.ok(started.run_id, JSON.stringify(started));
  await page.waitForFunction(() => document.getElementById('market-run-status').textContent.includes(' · completed · '), null, { timeout: 180000 });
  assert.equal(await page.locator('#market-policy-table tr').count(), 3);
  await page.waitForFunction(() => document.querySelectorAll('#market-flight-table tr').length === 9);
  assert.equal(await page.locator('#market-person-select option').count(), 14);
  const caseIds = await page.locator('#market-policy-select option').evaluateAll((options) => options.map((option) => option.value));
  await page.locator('#market-policy-select').selectOption(caseIds.at(-1));
  await page.waitForFunction(() => document.getElementById('market-detail-grid').getAttribute('aria-busy') === 'false');
  assert.ok(await page.locator('#market-journey-events li').count() >= 16, 'Full-term view must include multiple trips and renewal intention.');
  assert.ok((await page.locator('#market-source-counts').textContent()).includes('0 validated live'));
  assert.ok((await page.locator('#market-call-count').textContent()) === '0');
  assert.ok(await page.locator('#market-resume-controls').isHidden());
  await page.screenshot({ path: `${output}market-desktop.png`, fullPage: true });

  if (process.argv.includes('--transactions')) {
    await navigate('members');
    assert.equal(await page.locator('#publish-button').isDisabled(), false, 'Selected flight needs available member inventory for this optional test.');
    const beforeRelease = Number((await page.locator('#release-value').textContent()).replace(/[^0-9]/g, ''));
    await page.locator('#offer-quantity').fill('1');
    await page.locator('#offer-fare').fill('70');
    const publishedPromise = page.waitForResponse((response) => response.url().endsWith('/api/offers') && response.request().method() === 'POST');
    await page.locator('#publish-button').click();
    const published = await (await publishedPromise).json();
    assert.ok(published.offer, JSON.stringify(published));
    await page.waitForFunction((expected) => Number(document.getElementById('release-value').textContent.replace(/[^0-9]/g, '')) === expected, beforeRelease - 1);
    await page.waitForFunction(() => document.querySelectorAll('.offer-card').length > 0);
    await page.locator('#customer-id').fill(`frontend-qa-${Date.now()}`);
    await page.locator('#join-button').click();
    await page.waitForFunction(() => document.getElementById('membership-status').textContent.startsWith('Membership active'));
    const bookingPromise = page.waitForResponse((response) => response.url().endsWith('/api/bookings'));
    await page.locator('.offer-card button:not(:disabled)').first().click();
    const booking = await (await bookingPromise).json();
    assert.ok(booking.booking, JSON.stringify(booking));
    assert.equal(booking.booking.total, 70 + published.offer.fees);
    await page.waitForFunction(() => !document.getElementById('booking-result').hidden);
    await page.screenshot({ path: `${output}members-desktop.png`, fullPage: true });
  }

  for (const view of ['flights', 'pricing', 'customers', 'market', 'members']) {
    await page.setViewportSize({ width: 390, height: 844 });
    await navigate(view);
    await page.waitForTimeout(200);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${view} has mobile page overflow.`);
    await page.screenshot({ path: `${output}${view}-mobile.png`, fullPage: true });
  }
  // Exercise the pause/resume UI against intercepted responses: no provider
  // request is made by this fixture and merely reading a pause cannot resume it.
  await navigate('market');
  let resumes = 0;
  // A candidate wins one seed spectacularly but loses the other. The fixed
  // policy wins on the paired mean, which must drive the policy headline.
  const fixturePolicies = [{ name: 'NO_OFFER', enabled: false }, { name: 'FIXED', enabled: true }, { name: 'CANDIDATE', enabled: true }];
  const fixtureDeltas = [[0, 0], [100, 100], [1000, -900]];
  const fixtureCases = fixturePolicies.flatMap((policy, index) => [1, 2].map((seed) => ({ case_id: `qa-${index}-${seed}`, seed, mode: 'deterministic', split: 'validation', policy, completed: true, metrics: { contribution: 1000 + fixtureDeltas[index][seed - 1] } })));
  const rankingFixture = {
    run_id: 'qa-paused', cases: 6, completed_cases: 6, case_results: fixtureCases,
    aggregate: fixturePolicies.map((policy, index) => ({ policy: policy.name, mode: 'deterministic', split: 'validation', replicates: 2, mean_metrics: { contribution: 1000 + fixtureDeltas[index].reduce((a, b) => a + b) / 2 } })),
    paired_differences: fixtureCases.filter((row) => row.policy.enabled).map((row) => ({ case_id: row.case_id, metric_differences: { contribution: row.metrics.contribution - 1000 } })), runtime: {},
  };
  await page.route('**/api/market/runs/qa-paused/cases/**', async (route) => route.fulfill({ json: { inspection: { day: 365, metrics: { ledger: {} }, customers: [], flights: [], events: [] } } }));
  await page.route('**/api/market/runs/qa-paused/resume', async (route) => {
    resumes++; assert.equal(route.request().postDataJSON().max_calls, 60);
    await route.fulfill({ json: { run_id: 'qa-paused', status: 'queued' } });
  });
  await page.route('**/api/market/runs/qa-paused', async (route) => route.fulfill({ json: { run_id: 'qa-paused', status: resumes ? 'completed' : 'paused_at_budget', report: resumes ? rankingFixture : { cases: 6, completed_cases: 0, case_results: [], runtime: {} } } }));
  await page.route('**/api/market/runs', async (route) => {
    if (route.request().method() === 'POST') await route.fulfill({ json: { run_id: 'qa-paused', status: 'queued' } });
    else await route.continue();
  });
  await page.locator('#market-start').click();
  await page.waitForFunction(() => !document.getElementById('market-resume-controls').hidden);
  await page.waitForTimeout(2000);
  assert.equal(resumes, 0, 'Paused runs must not automatically consume another budget.');
  await page.locator('#market-call-budget').fill('60');
  await page.locator('#market-resume').click();
  await page.waitForFunction(() => document.getElementById('market-run-status').textContent.includes(' · completed · '));
  assert.equal(resumes, 1);
  assert.equal(await page.locator('#market-best-profit').textContent(), 'HK$100');
  assert.ok((await page.locator('#market-best-label').textContent()).startsWith('Fixed offer'));
  assert.equal(await page.locator('#market-policy-table tr').count(), 3);
  assert.deepEqual(errors, []);
  console.log('PASS: as-of forecast, cost propagation, 192 candidates, 14 synthetic customers, future-offer guard, three shared-market policies, manual bounded resume and five mobile layouts.');
  if (process.argv.includes('--transactions')) console.log('PASS: simulated offer, membership, itemised booking and inventory-backed reservation.');
} finally {
  await browser.close();
}

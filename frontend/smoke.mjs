/** Run against an already-running backend. No production browser dependencies.
 * npm install && npx playwright install chromium && npm run test:smoke
 * Add -- --transactions to publish an explicit demo offer. Member booking is tested separately in the member portal.
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
const navigate = async view => {
  if (view === 'pricing') { await page.locator('.primary-nav a[href="#optimization"]').click(); await page.locator('.advanced-link[href="#pricing"]').click(); }
  else if (['market', 'panel'].includes(view)) { await page.evaluate(name => { location.hash = name; }, view); await page.locator(`#view-${view}`).waitFor({state:'visible'}); }
  else await page.locator(`.primary-nav a[href="#${view}"]`).click();
};

try {
  await page.goto(origin + '/admin', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.getElementById('demand-value').textContent !== '—');
  assert.equal(await page.locator('#error').isVisible(), false);
  assert.ok((await page.locator('#dataset-label').textContent()).includes('synthetic'));
  await page.locator('[data-day="14"]').click();
  await waitForecast();
  assert.equal(await page.locator('#history-table').count(), 0);
  assert.equal(await page.locator('#forecast-notes').count(), 0);
  assert.equal(await page.locator('#risk-release-value, #member-sold-value, #prior-quota-value, #active-quota-value, #release-status, #demo-round-table, #beta-label, footer').count(), 0, 'Detailed release audit and model footer are removed from the simplified page.');
  assert.ok((await page.locator('#seat-composition').getAttribute('aria-label')).includes('seats'));
  assert.ok((await page.locator('#price-caption').textContent()).includes('D14'));
  assert.ok(await page.locator('#price-chart .chart-line').count());
  const d13Response = page.waitForResponse((r) => r.url().endsWith('/api/forecast') && r.request().postDataJSON()?.days_to_departure === 13);
  await page.locator('#day-slider').fill('15');
  await d13Response;
  await page.waitForFunction(() => document.getElementById('day-number').textContent === '13');
  await waitForecast();
  assert.equal(await page.locator('#release-value').textContent(), '0 seats');
  assert.equal(await page.locator('#publish-button').isDisabled(), true);
  assert.match(await page.locator('#nhpp-release-value').textContent(), /\d[\d,]* seats?/);
  await page.locator('[data-day="28"]').click();
  await waitForecast();
  await page.screenshot({ path: `${output}desktop.png`, fullPage: true });

  await navigate('pricing');
  await page.locator('#passenger-cost').fill('80');
  const responsePromise = page.waitForResponse((response) => response.url().endsWith('/api/optimize'));
  await page.locator('#optimize-button').click();
  const result = await (await responsePromise).json();
  assert.equal(result.config.incremental_cost, 80, 'The cost input must reach the financial model.');
  assert.equal(result.candidates.length, 64);
  assert.deepEqual(result.candidates[0].release_days, [28, 14, 7]);
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

  await navigate('panel');
  await page.locator('#agent-count').fill('14');
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.getElementById('panel-run-status').textContent.startsWith('Complete'), null, {timeout:120000});
  assert.equal(await page.locator('#panel-people tr').count(), 14);
  assert.equal(await page.locator('#panel-completed').textContent(), '14');
  assert.ok((await page.locator('#agent-mode-message').textContent()).includes('independent one-trip'));
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
  assert.equal(await page.locator('#market-round-table tr').count(), 27);
  assert.ok((await page.locator('#market-rule-note').textContent()).includes('Current rule'));
  assert.ok(await page.locator('#market-journey-events li').count() >= 16, 'Full-term view must include multiple trips and renewal intention.');
  assert.ok((await page.locator('#market-source-counts').textContent()).includes('0 validated live'));
  assert.ok((await page.locator('#market-call-count').textContent()) === '0');
  assert.ok(await page.locator('#market-resume-controls').isHidden());
  await page.screenshot({ path: `${output}market-desktop.png`, fullPage: true });

  if (process.argv.includes('--transactions')) {
    await navigate('flights');
    const availableFlight = await page.evaluate(async () => {
      const {flights} = await (await fetch('/api/flights')).json();
      for (const flight of flights.slice(0, 80)) {
        const {forecast} = await (await fetch('/api/forecast', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({flight_id:flight.flight_id,days_to_departure:28})})).json();
        if (forecast.releasable_seats >= 2 && !forecast.release_status?.blocked_reason) return flight.flight_id;
      }
    });
    assert.ok(availableFlight, 'Need an unused release round for transactional QA.');
    await page.locator('#flight-select').selectOption(availableFlight); await waitForecast();
    await navigate('members');
    assert.equal(await page.locator('#publish-button').isDisabled(), false, 'Selected flight needs available member inventory for this optional test.');
    await page.locator('#offer-quantity').fill('2');
    await page.locator('#offer-fare').fill('70');
    const publishedPromise = page.waitForResponse((response) => response.url().endsWith('/api/offers') && response.request().method() === 'POST');
    await page.locator('#publish-button').click();
    const published = await (await publishedPromise).json();
    assert.ok(published.offer, JSON.stringify(published));
    await page.waitForFunction(() => document.getElementById('release-value').textContent === '0 seats');
    assert.equal(await page.locator('#publish-button').isDisabled(), true, 'A published round cannot be issued twice.');
    await page.waitForFunction(() => document.querySelectorAll('.offer-card').length > 0);
    assert.equal(await page.locator('#customer-id').count(), 0, 'Consumer identity does not belong in Admin.');
    assert.equal(await page.locator('#join-button').count(), 0, 'Consumer joining is on the separate member site.');
    const publishedCard = page.locator(`[data-offer-id="${published.offer.id}"]`);
    assert.equal(await publishedCard.locator('a').getAttribute('href'), '/members');
    assert.equal(await publishedCard.locator('button').count(), 0, 'Admin must not contain a reserve-seat action.');
    await page.screenshot({ path: `${output}offers-desktop.png`, fullPage: true });
    await navigate('flights');
    const carryResponse = page.waitForResponse((response) => response.url().endsWith('/api/forecast') && response.request().postDataJSON()?.days_to_departure === 14);
    await page.locator('[data-day="14"]').click();
    const carried = (await (await carryResponse).json()).forecast;
    await waitForecast();
    assert.equal(carried.release_status.previous_valid_unsold, 2, 'Detailed carry accounting remains in the API.');
    assert.equal(carried.release_status.round_history.length, 1);
    assert.equal(await page.locator('#bookable-value').textContent(), `${carried.seat_inventory.published_bookable} seats`);

  }

  for (const view of ['flights', 'pricing', 'customers', 'panel', 'market', 'members']) {
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
  await page.route('**/api/market/runs/qa-paused/cases/**', async (route) => route.fulfill({ json: { inspection: { day: 365, metrics: { ledger: {}, version: 'shared-market-v2' }, customers: [], flights: [{flight_id:'QA-LEGACY',destination:'FUK',capacity:180,occupied:80,legacy_seats:60,member_seats:5,quota_history:[{days_to_departure:28,remaining_quota:12}]}], events: [] } } }));
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
  await page.waitForFunction(() => document.getElementById('market-round-note').textContent.includes('Historical experiment'));
  assert.ok((await page.locator('#market-rule-note').textContent()).includes('Historical or unversioned'));
  assert.equal(await page.locator('#market-round-table tr td').nth(1).textContent(), '—', 'Historical missing carry must not be invented.');
  assert.deepEqual(errors, []);
  console.log('PASS: as-of forecast, cost propagation, 64 three-round candidates, 14 synthetic customers, between-round issuance guard and round audit, three shared-market policies, manual bounded resume and five mobile layouts.');
  if (process.argv.includes('--transactions')) console.log('PASS: Admin publishes the offer once, carries its unsold quota and links to the separate member booking site.');
} finally {
  await browser.close();
}

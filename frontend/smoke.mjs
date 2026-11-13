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

  await navigate('customers');
  await page.locator('#agent-count').fill('14');
  await page.locator('#agent-button').click();
  await page.waitForFunction(() => document.querySelectorAll('.customer-card').length === 14);
  assert.ok((await page.locator('#agent-mode-message').textContent()).includes('not observed'));
  await page.screenshot({ path: `${output}customers-desktop.png`, fullPage: true });

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

  for (const view of ['flights', 'pricing', 'customers', 'members']) {
    await page.setViewportSize({ width: 390, height: 844 });
    await navigate(view);
    await page.waitForTimeout(200);
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, `${view} has mobile page overflow.`);
    await page.screenshot({ path: `${output}${view}-mobile.png`, fullPage: true });
  }
  assert.deepEqual(errors, []);
  console.log('PASS: as-of forecast, cost propagation, 192 candidates, 14 synthetic customers, future-offer guard and four mobile layouts.');
  if (process.argv.includes('--transactions')) console.log('PASS: simulated offer, membership, itemised booking and inventory-backed reservation.');
} finally {
  await browser.close();
}

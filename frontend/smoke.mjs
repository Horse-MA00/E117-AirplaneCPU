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
const waitForecast = () =>
  page.waitForFunction(() => document.querySelector('#flight-main').getAttribute('aria-busy') === 'false');
const navigate = async (view) => page.locator(`.primary-nav a[href="#${view}"]`).click();

try {
  await page.goto(origin + '/admin', { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.getElementById('demand-value').textContent !== '—');
  assert.equal(await page.locator('#error').isVisible(), false);
  assert.ok((await page.locator('#dataset-label').textContent()).includes('synthetic'));
  await page.locator('[data-day="14"]').click();
  await waitForecast();
  assert.equal(await page.locator('#history-table').count(), 0);
  assert.equal(await page.locator('#forecast-notes').count(), 0);
  assert.equal(
    await page
      .locator(
        '#risk-release-value, #member-sold-value, #prior-quota-value, #active-quota-value, #release-status, #demo-round-table, #beta-label, footer',
      )
      .count(),
    0,
    'Detailed release audit and model footer are removed from the simplified page.',
  );
  assert.ok((await page.locator('#seat-composition').getAttribute('aria-label')).includes('seats'));
  assert.ok((await page.locator('#price-caption').textContent()).includes('D14'));
  assert.ok(await page.locator('#price-chart .chart-line').count());
  const d13Response = page.waitForResponse(
    (r) => r.url().endsWith('/api/forecast') && r.request().postDataJSON()?.days_to_departure === 13,
  );
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

  if (process.argv.includes('--transactions')) {
    await navigate('flights');
    const availableFlight = await page.evaluate(async () => {
      const { flights } = await (await fetch('/api/flights')).json();
      for (const flight of flights.slice(0, 80)) {
        const { forecast } = await (
          await fetch('/api/forecast', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ flight_id: flight.flight_id, days_to_departure: 28 }),
          })
        ).json();
        if (forecast.releasable_seats >= 2 && !forecast.release_status?.blocked_reason)
          return { id: flight.flight_id, route: `${flight.origin} → ${flight.destination}` };
      }
    });
    assert.ok(availableFlight, 'Need an unused release round for transactional QA.');
    // The shared From / To fields filter the flight list.
    const [from, to] = availableFlight.route.split(' → ');
    await page.locator('#context-from').selectOption(from);
    await page.locator('#context-to').selectOption(to);
    await page.locator('#flight-select').selectOption(availableFlight.id);
    await waitForecast();
    await navigate('members');
    assert.equal(
      await page.locator('#publish-button').isDisabled(),
      false,
      'Selected flight needs available member inventory for this optional test.',
    );
    await page.locator('#offer-quantity').fill('2');
    await page.locator('#offer-fare').fill('70');
    const publishedPromise = page.waitForResponse(
      (response) => response.url().endsWith('/api/offers') && response.request().method() === 'POST',
    );
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
    const carryResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/forecast') && response.request().postDataJSON()?.days_to_departure === 14,
    );
    await page.locator('[data-day="14"]').click();
    const carried = (await (await carryResponse).json()).forecast;
    await waitForecast();
    assert.equal(carried.release_status.previous_valid_unsold, 2, 'Detailed carry accounting remains in the API.');
    assert.equal(carried.release_status.round_history.length, 1);
    assert.equal(
      await page.locator('#bookable-value').textContent(),
      `${carried.seat_inventory.published_bookable} seats`,
    );
  }

  for (const view of ['flights', 'customers', 'members']) {
    await page.setViewportSize({ width: 390, height: 844 });
    await navigate(view);
    await page.waitForTimeout(200);
    assert.equal(
      await page.evaluate(() => document.documentElement.scrollWidth > innerWidth),
      false,
      `${view} has mobile page overflow.`,
    );
    await page.screenshot({ path: `${output}${view}-mobile.png`, fullPage: true });
  }
  for (const hash of ['optimization', 'pricing', 'panel', 'market']) {
    await page.goto(`${origin}/admin#${hash}`);
    await page.locator('#view-unavailable:visible').waitFor();
    assert.equal(new URL(page.url()).hash, `#${hash}`, 'Retired routes must not redirect');
    assert.equal(await page.locator('#view-pricing,#view-panel,#view-market').count(), 0);
  }
  assert.deepEqual(errors, []);
  console.log(
    'PASS: as-of forecast, between-round issuance guard, current Admin views, three mobile layouts, retired pages unavailable without redirects.',
  );
  if (process.argv.includes('--transactions'))
    console.log(
      'PASS: Admin publishes the offer once, carries its unsold quota and links to the separate member booking site.',
    );
} finally {
  await browser.close();
}

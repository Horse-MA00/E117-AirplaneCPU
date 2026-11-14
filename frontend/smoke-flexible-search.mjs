/** Flexible member search against an already-running app, with all API reads
 * intercepted. Run: node smoke-flexible-search.mjs. No purchases or LLM calls. */
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
// A different browser timezone catches accidental reliance on local Date parts.
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  timezoneId: 'America/Los_Angeles',
});
if (process.env.FORCE_TEMPORAL_POLYFILL === '1')
  await context.addInitScript(() => {
    Object.defineProperty(globalThis, 'Temporal', { value: undefined, configurable: true });
  });
const page = await context.newPage();
const hasNativeTemporal = await page.evaluate(() => typeof globalThis.Temporal !== 'undefined');
await page.clock.setFixedTime(new Date('2027-04-15T04:00:00Z'));
const errors = [];
const unexpectedRequests = [];
page.on('pageerror', (error) => errors.push(error.message));
const fixtures = [
  ['FUK-FIRST', 'FUK', '2027-05-01'],
  ['KIX-LAST', 'KIX', '2027-05-31'],
  ['NRT-AFTER', 'NRT', '2027-06-01'],
  ['FUK-BEFORE', 'FUK', '2027-04-30'],
  ['ICN-MIDDLE', 'ICN', '2027-05-15'],
  ['DAD-MIDDLE', 'DAD', '2027-05-20'],
  ['UNKNOWN-MIDDLE', 'ZZZ', '2027-05-20'],
].map(([id, destination, departure_date], index) => ({
  offer_id: `fixture-${id.toLowerCase()}`,
  flight_id: `SYN-${id}`,
  origin: 'HKG',
  destination,
  departure_date,
  base_fare: 70 + index,
  mandatory_fees: 250,
  total: 320 + index,
  normal_total: 850,
  bookable_seats: 3,
  release_day: 28,
  days_to_departure: 28,
}));
let flightReads = 0;
let releasedFlights = fixtures;
await context.route('**/api/**', async (route) => {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const reply = (data) => route.fulfill({ json: data });
  if (request.method() === 'GET') {
    if (path === '/api/member-portal/session')
      return reply({
        authenticated: true,
        user: { customer_id: 'search-fixture', email: 'search@uoption.test', name: 'Search fixture' },
        account: { customer_id: 'search-fixture', membership: null, bookings: [], simulated: true },
        simulated: true,
      });
    if (path === '/api/member-portal/config')
      return reply({
        membership: {
          name: 'UOption Fly Pass',
          fee: 399,
          term_days: 181,
          term_months: 6,
          term_label: '6 months',
          personal_nontransferable: true,
        },
        currency: 'HKD',
        simulated: true,
      });
    if (path === '/api/member-portal/flights') {
      flightReads += 1;
      return reply({ flights: structuredClone(releasedFlights), simulated: true });
    }
    if (path.startsWith('/api/member-portal/accounts/'))
      return reply({ customer_id: path.split('/').at(-1), membership: null, bookings: [], simulated: true });
  }
  unexpectedRequests.push(`${request.method()} ${path}`);
  return route.fulfill({ status: 403, json: { error: 'This search test permits only fixture reads.' } });
});

const displayedIds = () =>
  page.locator('.flight-card').evaluateAll((cards) => cards.map((card) => card.dataset.flightId).sort());
const expectFlights = async (ids) => assert.deepEqual(await displayedIds(), ids.map((id) => `SYN-${id}`).sort());
const submit = () => page.locator('#search-button').click();
const summary = () => page.locator('#search-summary').innerText();
async function revealControl(id) {
  const details = page.locator('details').filter({ has: page.locator(`#${id}`) });
  if ((await details.count()) && !(await details.evaluate((element) => element.open)))
    await details.locator('summary').click();
}
async function dates(from, to) {
  await page.locator('#departure-from').fill(from);
  await page.locator('#departure-to').fill(to);
}
async function expectDates(from, to) {
  assert.equal(await page.locator('#departure-from').inputValue(), from);
  assert.equal(await page.locator('#departure-to').inputValue(), to);
}

try {
  await page.goto(`${origin}/members`, { waitUntil: 'networkidle' });
  assert.equal(await page.locator('.flight-card').count(), fixtures.length);

  // Draft filters leave the current result set and its summary unchanged.
  const initialSummary = await summary();
  await page.locator('#destination').selectOption('region:JP');
  await dates('2027-05-01', '2027-05-31');
  assert.equal(await page.locator('.flight-card').count(), fixtures.length);
  assert.equal(await summary(), initialSummary);
  await submit();
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);
  assert.match(await summary(), /Japan/);
  assert.match(await summary(), /May/);
  assert.match(await summary(), /2027/);
  assert.match(await summary(), /31/);
  const appliedSummary = await summary();

  // Availability refresh must preserve both the submitted criteria and inputs.
  const readsBeforeRefresh = flightReads;
  await page.locator('#refresh-flights').click();
  await page.waitForFunction(() => document.querySelector('#flight-results').getAttribute('aria-busy') === 'false');
  assert.ok(flightReads > readsBeforeRefresh);
  assert.equal(await page.locator('#destination').inputValue(), 'region:JP');
  await expectDates('2027-05-01', '2027-05-31');
  assert.equal(await summary(), appliedSummary);
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);

  // Either date bound may be omitted. The remaining boundary is inclusive.
  await dates('', '2027-05-31');
  await submit();
  await expectFlights(['FUK-BEFORE', 'FUK-FIRST', 'KIX-LAST']);
  await dates('2027-05-31', '');
  await submit();
  await expectFlights(['KIX-LAST', 'NRT-AFTER']);

  // All dates keeps the country filter and does not silently submit it.
  await page.locator('#any-dates').click();
  await expectDates('', '');
  await expectFlights(['KIX-LAST', 'NRT-AFTER']);
  await submit();
  await expectFlights(['FUK-BEFORE', 'FUK-FIRST', 'KIX-LAST', 'NRT-AFTER']);

  // The same picker offers each country's airports; one day is a same-date range.
  const japanAirports = await page.locator('#destination optgroup[label="Japan"] option').evaluateAll((options) =>
    options
      .map((option) => option.value)
      .filter((value) => !value.startsWith('region:'))
      .sort(),
  );
  assert.deepEqual(japanAirports, ['CTS', 'FUK', 'HIJ', 'HND', 'ISG', 'KIX', 'KMQ', 'NGO', 'NRT', 'OKA', 'SDJ', 'TAK']);
  await page.locator('#destination').selectOption('FUK');
  await dates('2027-05-01', '2027-05-01');
  await submit();
  await expectFlights(['FUK-FIRST']);
  // An offer disappearing cannot silently replace the applied airport/date.
  const exactSummary = await summary();
  releasedFlights = fixtures.filter((flight) => flight.destination !== 'FUK');
  await page.locator('#refresh-flights').click();
  await page.waitForFunction(() => document.querySelector('#flight-results').getAttribute('aria-busy') === 'false');
  assert.equal(await page.locator('#destination').inputValue(), 'FUK');
  await expectDates('2027-05-01', '2027-05-01');
  assert.equal(await summary(), exactSummary);
  await expectFlights([]);
  assert.match(await page.locator('#flight-results').innerText(), /No matching flights/);
  releasedFlights = fixtures;
  await page.locator('#refresh-flights').click();
  await page.waitForFunction(() => document.querySelector('#flight-results').getAttribute('aria-busy') === 'false');
  await expectFlights(['FUK-FIRST']);
  await page.locator('#any-dates').click();
  await expectDates('', '');
  await submit();
  await expectFlights(['FUK-BEFORE', 'FUK-FIRST']);

  // Choosing a whole country replaces the single airport in the same picker.
  await page.locator('#destination').selectOption('region:KR');
  assert.equal(await page.locator('#destination').inputValue(), 'region:KR');
  await submit();
  await expectFlights(['ICN-MIDDLE']);
  await page.locator('#destination').selectOption('region:VN');
  await submit();
  await expectFlights(['DAD-MIDDLE']);
  assert.match(await summary(), /Vietnam/);

  // A whole country also works as the origin.
  await page.locator('#clear-search').click();
  await page.locator('#origin').selectOption('region:JP');
  await submit();
  await expectFlights([]);
  assert.match(await summary(), /Japan \(all airports\) → Anywhere/);

  // Unknown airports are selectable without being assigned an invented country.
  await page.locator('#clear-search').click();
  assert.equal(await page.locator('.flight-card').count(), fixtures.length);
  await page.locator('#destination').selectOption('ZZZ');
  await submit();
  await expectFlights(['UNKNOWN-MIDDLE']);
  await page.locator('#clear-search').click();

  // Reversed ranges fail native validation and keep the last applied search.
  await page.locator('#destination').selectOption('region:JP');
  await dates('2027-05-01', '2027-05-31');
  await submit();
  const validSummary = await summary();
  // Browsers accept unsigned five-digit years; reject them before date parsing.
  await page.locator('#departure-from').fill('10000-01-01');
  await submit();
  assert.equal(await page.locator('#departure-from').inputValue(), '10000-01-01');
  assert.equal(await page.locator('#flight-search').evaluate((form) => form.checkValidity()), false);
  assert.equal(await summary(), validSummary);
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);
  assert.deepEqual(errors, []);
  await dates('2027-05-01', '2027-05-31');
  await submit();
  assert.equal(await page.locator('#flight-search').evaluate((form) => form.checkValidity()), true);
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);
  await dates('2027-05-31', '2027-05-01');
  await submit();
  assert.equal(await page.locator('#flight-search').evaluate((form) => form.checkValidity()), false);
  assert.equal(await summary(), validSummary);
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);

  // The preset repairs invalid ranges and uses complete calendar months.
  await page.locator('#next-month').click();
  await expectDates('2027-05-01', '2027-05-31');
  assert.equal(await page.locator('#flight-search').evaluate((form) => form.checkValidity()), true);
  await submit();
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);
  await page.clock.setFixedTime(new Date('2026-11-30T16:30:00Z')); // Already December in Hong Kong.
  await page.locator('#next-month').click();
  await expectDates('2027-01-01', '2027-01-31');
  await page.clock.setFixedTime(new Date('2028-01-15T04:00:00Z'));
  await page.locator('#next-month').click();
  await expectDates('2028-02-01', '2028-02-29');

  // Empty results retain the selected criteria and expose a complete reset.
  await page.locator('#origin').selectOption('HKG');
  await dates('2027-07-01', '2027-07-31');
  await submit();
  assert.equal(await page.locator('.flight-card').count(), 0);
  assert.match(await page.locator('#flight-results').innerText(), /No matching flights/);
  assert.match(await summary(), /Japan/);
  await page.locator('#clear-search').click();
  for (const id of ['origin', 'destination', 'departure-from', 'departure-to'])
    assert.equal(await page.locator(`#${id}`).inputValue(), '', `${id} must reset.`);
  assert.equal(await page.locator('.flight-card').count(), fixtures.length);
  assert.equal(await page.locator('#flight-search').evaluate((form) => form.checkValidity()), true);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#destination').selectOption('region:JP');
  await dates('2027-05-01', '2027-05-31');
  await submit();
  await expectFlights(['FUK-FIRST', 'KIX-LAST']);
  assert.equal(
    await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1),
    false,
    'The 390px member search must not overflow.',
  );
  await page.screenshot({ path: `${output}member-flexible-search-mobile.png`, fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.locator('.search-panel').evaluate((element) => element.scrollIntoView({ block: 'start' }));
  await page.locator('.search-panel').screenshot({ path: `${output}member-flexible-search-panel.png` });
  await page.screenshot({ path: `${output}member-flexible-search-desktop.png`, fullPage: false });

  assert.deepEqual(errors, []);
  assert.deepEqual(unexpectedRequests, []);
  console.log(
    `Browser ${browser.version()}; native Temporal: ${hasNativeTemporal}; calendar path: ${hasNativeTemporal ? 'native' : 'local fallback'}.`,
  );
  console.log(
    'Flexible member search passed: country and exact-airport filters, inclusive/open date ranges, explicit submit, invalid-range recovery, Hong Kong calendar presets, availability refresh, empty/reset states and 390px layout. Fixture reads only; zero purchases or LLM calls.',
  );
} finally {
  await browser.close();
}

/** Route/date regression against an already-running app. All API requests are
 * intercepted; no purchases or provider calls. Run: node smoke-route-catalog.mjs. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const appUrl = process.env.APP_URL || 'http://127.0.0.1:8000';
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
await mkdir(output, { recursive: true });
const catalog = ['HKG', 'HND', 'NRT', 'KIX', 'NGO', 'FUK', 'CTS', 'OKA', 'HIJ', 'TAK', 'SDJ', 'KMQ', 'ISG', 'ICN', 'PUS', 'TAE', 'CJU', 'TPE', 'KHH', 'RMQ', 'PKX', 'CZX', 'WUX', 'NGB', 'SYX', 'YIW', 'HFE', 'BKK', 'CNX', 'HKT', 'HAN', 'DAD', 'PQC', 'SZB', 'BKI', 'PEN', 'MNL', 'CRK'];
const japanCatalog = ['HND', 'NRT', 'KIX', 'NGO', 'FUK', 'CTS', 'OKA', 'HIJ', 'TAK', 'SDJ', 'KMQ', 'ISG'];
const fixtures = [
  ['BEFORE', 'HKG', 'FUK', '2027-05-14'],
  ['FIRST', 'HKG', 'FUK', '2027-05-15'],
  ['LAST', 'HKG', 'FUK', '2027-05-21'],
  ['AFTER', 'HKG', 'FUK', '2027-05-22'],
  ['REVERSE', 'FUK', 'HKG', '2027-05-18'],
  ['UNKNOWN-DESTINATION', 'HKG', 'ZZZ', '2027-05-18'],
  ['UNKNOWN-ORIGIN', 'YYY', 'HKG', '2027-05-18'],
].map(([id, origin, destination, departure_date], index) => ({
  offer_id: `fixture-${id.toLowerCase()}`,
  flight_id: `SYN-${id}`,
  origin,
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
let releasedFlights = fixtures;
const errors = [];
const unexpectedRequests = [];
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
});
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'America/Los_Angeles' });
const page = await context.newPage();
page.on('pageerror', error => errors.push(error.message));
await context.route('**/api/**', async route => {
  const request = route.request();
  const path = new URL(request.url()).pathname;
  const reply = data => route.fulfill({ json: data });
  if (request.method() === 'GET') {
    if (path === '/api/member-portal/config') return reply({ membership: { name: 'UOption Fly Pass', fee: 399, term_days: 365, personal_nontransferable: true }, currency: 'HKD', simulated: true });
    if (path === '/api/member-portal/flights') return reply({ flights: structuredClone(releasedFlights), simulated: true });
    if (path.startsWith('/api/member-portal/accounts/')) return reply({ customer_id: path.split('/').at(-1), membership: null, bookings: [], simulated: true });
  }
  unexpectedRequests.push(`${request.method()} ${path}`);
  return route.fulfill({ status: 403, json: { error: 'This regression permits only fixture reads.' } });
});

const optionValues = id => page.locator(`#${id} option`).evaluateAll(options => options.map(option => option.value).filter(Boolean));
const submit = () => page.locator('#search-button').click();
const clear = () => page.locator('#clear-search').click();
async function revealControl(id) {
  const details = page.locator('details').filter({ has: page.locator(`#${id}`) });
  if (await details.count() && !await details.evaluate(element => element.open)) await details.locator('summary').click();
}
async function expectFlights(ids) {
  const actual = await page.locator('.flight-card').evaluateAll(cards => cards.map(card => card.dataset.flightId).sort());
  assert.deepEqual(actual, ids.map(id => `SYN-${id}`).sort());
}
async function expectCatalog(id, required = catalog) {
  const values = await optionValues(id);
  assert.deepEqual(required.filter(code => !values.includes(code)), [], `${id} must include airports without released offers.`);
  assert.equal(new Set(values).size, values.length, `${id} must not contain duplicate airports.`);
}
async function refresh() {
  await page.locator('#refresh-flights').click();
  await page.waitForFunction(() => document.querySelector('#flight-results').getAttribute('aria-busy') === 'false');
}
async function expectReset() {
  for (const id of ['origin', 'destination', 'departure-from', 'departure-to']) {
    assert.equal(await page.locator(`#${id}`).inputValue(), '', `${id} must reset.`);
  }
  assert.equal(await page.locator('#flight-search').evaluate(form => form.checkValidity()), true);
}

try {
  await page.goto(`${appUrl}/members`, { waitUntil: 'networkidle' });
  await expectFlights(fixtures.map(flight => flight.flight_id.slice(4)));

  // Report both root regressions together before testing their interactions.
  const origins = await optionValues('origin');
  const destinations = await optionValues('destination');
  const exactControl = await page.locator('#departure-from').evaluate(element => ({ tag: element.tagName.toLowerCase(), type: element.type }));
  const regressions = [];
  const absentOrigins = catalog.filter(code => !origins.includes(code));
  const absentDestinations = catalog.filter(code => !destinations.includes(code));
  if (absentOrigins.length) regressions.push(`Origin catalog missing: ${absentOrigins.join(', ')}`);
  if (absentDestinations.length) regressions.push(`Destination catalog missing: ${absentDestinations.join(', ')}`);
  if (exactControl.tag !== 'input' || exactControl.type !== 'date') regressions.push(`Departure range start is ${exactControl.tag}[type=${exactControl.type}], expected input[type=date].`);
  assert.deepEqual(regressions, [], 'Route catalog and arbitrary exact-date regressions');
  await expectCatalog('origin');
  await expectCatalog('destination');
  assert.ok(origins.includes('YYY'), 'Observed origins outside the static catalog remain selectable.');
  assert.ok(destinations.includes('ZZZ'), 'Observed destinations outside the static catalog remain selectable.');

  // Each country group lists its full catalog even when most routes have no offers.
  const japanValues = await page.locator('#destination optgroup[label="Japan"] option').evaluateAll(options => options.map(option => option.value));
  assert.deepEqual(japanCatalog.filter(code => !japanValues.includes(code)), []);
  assert.ok(japanValues.includes('region:JP') && !japanValues.includes('HKG'));
  await page.locator('#destination').selectOption('HIJ');
  await submit();
  await expectFlights([]);
  assert.equal(await page.locator('#destination').inputValue(), 'HIJ');
  assert.match(await page.locator('#flight-results').innerText(), /No matching flights/);

  // A catalog route without inventory produces an honest empty result.
  await clear();
  await page.locator('#origin').selectOption('HND');
  await revealControl('destination');
  await page.locator('#destination').selectOption('HKG');
  await submit();
  await expectFlights([]);
  assert.equal(await page.locator('#origin').inputValue(), 'HND');
  assert.equal(await page.locator('#destination').inputValue(), 'HKG');

  // Direction matters: a released inbound offer can be selected independently.
  await page.locator('#origin').selectOption('FUK');
  await submit();
  await expectFlights(['REVERSE']);
  await clear();
  await page.locator('#origin').selectOption('HKG');
  await page.locator('#destination').selectOption('FUK');
  await page.locator('#departure-from').fill('2027-05-15');
  await page.locator('#departure-to').fill('2027-05-21');
  await submit();
  await expectFlights(['FIRST', 'LAST']);

  // Invalid ranges leave the submitted result set alone; a valid range repairs it.
  const validRangeSummary = await page.locator('#search-summary').innerText();
  await page.locator('#departure-from').fill('2027-05-21');
  await page.locator('#departure-to').fill('2027-05-15');
  await submit();
  assert.equal(await page.locator('#flight-search').evaluate(form => form.checkValidity()), false);
  assert.equal(await page.locator('#search-summary').innerText(), validRangeSummary);
  await expectFlights(['FIRST', 'LAST']);

  // An arbitrary exact date is retained even though no fixture exists for it.
  await page.locator('#departure-from').fill('2028-08-02');
  await page.locator('#departure-to').fill('2028-08-02');
  await page.locator('#departure-to').blur();
  await submit();
  await expectFlights([]);
  assert.equal(await page.locator('#flight-search').evaluate(form => form.checkValidity()), true, 'A same-day range repairs a reversed range.');
  for (const id of ['departure-from', 'departure-to']) assert.equal(await page.locator(`#${id}`).inputValue(), '2028-08-02');
  assert.match(await page.locator('#search-summary').innerText(), /2028/);
  await refresh();
  await expectFlights([]);
  assert.equal(await page.locator('#departure-from').inputValue(), '2028-08-02');

  // Native date fields accept five-digit years; reject them before parsing.
  const validExactSummary = await page.locator('#search-summary').innerText();
  await page.locator('#departure-to').fill('10000-01-01');
  await page.locator('#departure-to').blur();
  await submit();
  assert.equal(await page.locator('#departure-to').evaluate(element => document.activeElement === element), true, 'Native validation focuses the invalid date.');
  assert.equal(await page.locator('#departure-to').inputValue(), '10000-01-01');
  assert.equal(await page.locator('#flight-search').evaluate(form => form.checkValidity()), false);
  assert.equal(await page.locator('#search-summary').innerText(), validExactSummary);
  await expectFlights([]);
  assert.deepEqual(errors, []);
  await page.locator('#departure-from').fill('2027-05-21');
  await page.locator('#departure-to').fill('2027-05-21');
  await submit();
  assert.equal(await page.locator('#flight-search').evaluate(form => form.checkValidity()), true);
  await expectFlights(['LAST']);
  await clear();
  await expectReset();
  await expectFlights(fixtures.map(flight => flight.flight_id.slice(4)));

  // Observed unknown airports remain available and filter actual inventory.
  await page.locator('#origin').selectOption('YYY');
  await submit();
  await expectFlights(['UNKNOWN-ORIGIN']);
  await clear();
  await page.locator('#destination').selectOption('ZZZ');
  await submit();
  await expectFlights(['UNKNOWN-DESTINATION']);

  // A fresh empty response must not erase the route catalog.
  releasedFlights = [];
  await page.reload({ waitUntil: 'networkidle' });
  await expectCatalog('origin');
  await expectCatalog('destination');
  await expectFlights([]);
  await page.locator('#origin').selectOption('CTS');
  await page.locator('#destination').selectOption('HKG');
  await page.locator('#departure-from').fill('2028-08-02');
  await page.locator('#departure-to').fill('2028-08-02');
  await submit();
  await expectFlights([]);
  assert.equal(await page.locator('#origin').inputValue(), 'CTS');
  assert.equal(await page.locator('#destination').inputValue(), 'HKG');
  assert.equal(await page.locator('#departure-to').inputValue(), '2028-08-02');
  await clear();
  await expectReset();
  await expectCatalog('origin');
  await expectCatalog('destination');

  // Long real catalog labels fit at both desktop and mobile widths.
  await page.locator('#origin').selectOption('CTS');
  await page.locator('#destination').selectOption('HFE');
  assert.equal(await page.locator('#origin-note').isVisible(), true);
  assert.match(await page.locator('#origin-note').innerText(), /Schedule unconfirmed/i);
  assert.equal(await page.locator('#destination-note').isVisible(), true);
  assert.match(await page.locator('#destination-note').innerText(), /Announced/i);
  await page.locator('#departure-from').fill('2028-08-02');
  await page.locator('#departure-to').fill('2028-08-02');
  await submit();
  const browserMajor = browser.version().split('.')[0];
  await page.locator('.search-panel').screenshot({ path: `${output}member-route-catalog-${browserMajor}-desktop.png` });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, 'Long catalog labels must not overflow at 390px.');
  assert.equal(await page.locator('#origin-note').isVisible(), true);
  assert.equal(await page.locator('#destination-note').isVisible(), true);
  await page.locator('.search-panel').screenshot({ path: `${output}member-route-catalog-${browserMajor}-mobile.png` });
  assert.deepEqual(errors, []);
  assert.deepEqual(unexpectedRequests, []);
  console.log(`Browser ${browser.version()}. Route catalog regression passed: full catalogs with sparse/empty releases, unknown airports, country filtering, inbound routes, inclusive dates, arbitrary same-day ranges, collapsed invalid-date focus/range recovery, refresh preservation, clear, visible airport status notes, and 390px layout. Fixture reads only; zero purchases or provider calls.`);
} finally {
  await browser.close();
}

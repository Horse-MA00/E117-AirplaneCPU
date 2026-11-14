/** Member shopping UI: fixtures exercise price/availability changes; --real also
 * books one existing published synthetic offer through the live local backend. */
import assert from 'node:assert/strict';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const origin = process.env.APP_URL || 'http://127.0.0.1:8000';
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}) });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const errors = []; page.on('pageerror', error => errors.push(error.message));
let fee = 399; let feeChanged = false; let bookingUnavailable = false; let joinCalls = 0; let bookingCalls = 0; let failAccountReads = 0; let failAfterJoin = false; let failAfterBook = false; let existingFeeOnJoin = null;
const accounts = new Map();
const flights = [
  { offer_id: 'fixture-fuk', flight_id: 'SYN-UI-FUK', origin: 'HKG', destination: 'FUK', departure_date: '2027-05-30', base_fare: 70.25, mandatory_fees: 250.5, total: 320.75, normal_total: 850.5, bookable_seats: 4, release_day: 28, days_to_departure: 28 },
  { offer_id: 'fixture-kix', flight_id: 'SYN-UI-KIX', origin: 'HKG', destination: 'KIX', departure_date: '2027-05-31', base_fare: 30, mandatory_fees: 250, total: 280, normal_total: 750, bookable_seats: 2, release_day: 14, days_to_departure: 14 },
];
function account(id) { if (!accounts.has(id)) accounts.set(id, { customer_id: id, membership: null, bookings: [], simulated: true }); return accounts.get(id); }
await page.route('**/api/member-portal/**', async route => {
  const request = route.request(); const path = new URL(request.url()).pathname; const body = request.method() === 'POST' ? request.postDataJSON() : null;
  const reply = (data, status = 200) => route.fulfill({ status, json: data });
  if (path.endsWith('/config')) return reply({ membership: { name: 'UOption Fly Pass', fee, term_days: 365, personal_nontransferable: true }, currency: 'HKD', simulated: true });
  if (path.endsWith('/flights')) return reply({ flights: structuredClone(flights), simulated: true });
  if (path.includes('/accounts/')) { if (failAccountReads > 0) { failAccountReads -= 1; return reply({ error: 'Account refresh temporarily unavailable.' }, 503); } return reply(structuredClone(account(path.split('/').at(-1)))); }
  if (path.endsWith('/join')) {
    joinCalls += 1;
    if (feeChanged) { feeChanged = false; fee = 499; return reply({ error: 'Membership price changed. Please review the current fee.' }, 400); }
    assert.equal(body.expected_fee, fee); const a = account(body.customer_id);
    if (existingFeeOnJoin !== null) { a.membership = { fee: existingFeeOnJoin, created: 1794610000, expires: 1826146000, active: true }; existingFeeOnJoin = null; }
    a.membership ||= { fee, created: 1794610000, expires: 1826146000, active: true };
    if (failAfterJoin) { failAccountReads = 1; failAfterJoin = false; }
    return reply({ member: structuredClone(a.membership), simulated: true });
  }
  if (path.endsWith('/book')) {
    bookingCalls += 1;
    if (bookingUnavailable) { flights[0].bookable_seats = 0; return reply({ error: 'Offer unavailable or sold out.' }, 400); }
    const a = account(body.customer_id); const f = flights.find(x => x.offer_id === body.offer_id); assert.ok(a.membership?.active); assert.equal(body.expected_total, f.total);
    const booking = { ...f, id: `booking-${bookingCalls}`, customer_id: a.customer_id, created: 1794610000, status: 'confirmed_simulation' }; a.bookings.push(booking); f.bookable_seats -= 1;
    if (failAfterBook) { failAccountReads = 1; failAfterBook = false; }
    return reply({ booking, remaining: f.bookable_seats, simulated: true });
  }
  throw new Error(`Unexpected member API ${path}`);
});
try {
  await page.goto(`${origin}/members`, { waitUntil: 'networkidle' });
  assert.equal(await page.locator('.flight-card').count(), 2);
  assert.equal(await page.locator('#header-account').innerText(), 'Your demo account');
  assert.equal(await page.locator('a[href="/admin"]').count(), 1);
  assert.equal(await page.locator('#agent-form').count(), 0);
  await page.locator('#destination').selectOption('FUK');
  // Changing a filter does not auto-submit or change the result count.
  assert.equal(await page.locator('.flight-card').count(), 2);
  await page.locator('#search-button').click();
  assert.equal(await page.locator('.flight-card').count(), 1);
  assert.match(await page.locator('.flight-card').innerText(), /HKD 320\.75/);
  await page.locator('#departure-date').selectOption('2027-05-31'); await page.locator('#search-button').click();
  assert.match(await page.locator('#flight-results').innerText(), /No matching flights/);
  await page.locator('#departure-date').selectOption(''); await page.locator('#search-button').click();
  await page.screenshot({ path: `${output}member-portal-desktop.png`, fullPage: false });
  const select = page.locator('.choose-flight').first(); await select.click();
  assert.equal(await page.locator('#checkout').evaluate(el => el.matches(':modal')), true);
  assert.match(await page.locator('#checkout-content').innerText(), /HKD 719\.75/);
  await page.keyboard.press('Escape'); assert.equal(await page.locator('#checkout').isVisible(), false);
  assert.equal(await select.evaluate(el => el === document.activeElement), true);
  await select.click(); await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-submit').textContent.includes('Confirm booking'));
  assert.equal(joinCalls, 1); assert.equal(bookingCalls, 0);
  assert.match(await page.locator('#checkout-submit').innerText(), /HKD 320\.75/);
  await page.screenshot({ path: `${output}member-portal-checkout.png`, fullPage: false });
  await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-title').textContent === 'Your trip is saved');
  assert.equal(joinCalls, 1); assert.equal(bookingCalls, 1);
  await page.locator('#view-trips').click(); assert.equal(await page.locator('.trip-card').count(), 1);
  const savedId = await page.locator('#current-account').innerText();
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.locator('#current-account').innerText(), savedId);
  assert.equal(await page.locator('.trip-card').count(), 1);
  assert.match(await page.locator('#membership-state').innerText(), /Active until/);
  assert.equal(joinCalls, 1);

  // A changed membership fee requires a new explicit click; no automatic retry.
  await page.locator('#new-account').click();
  await page.waitForFunction(id => document.querySelector('#current-account').textContent !== id, savedId);
  await page.waitForFunction(() => !document.querySelector('#join-pass').disabled);
  feeChanged = true;
  await page.locator('#join-pass').click(); await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-error').textContent.includes('price changed'));
  assert.equal(joinCalls, 2); assert.match(await page.locator('#checkout-submit').innerText(), /HKD 499/);
  await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-title').textContent === 'Your pass is active');
  assert.equal(joinCalls, 3);
  await page.keyboard.press('Escape');

  // The same active member keeps the fee when another user consumes the seat.
  bookingUnavailable = true; await page.locator('.choose-flight').first().click(); await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-error').textContent.includes('sold out'));
  assert.equal(await page.locator('#checkout-submit').isDisabled(), true); assert.equal(joinCalls, 3);
  assert.match(await page.locator('#membership-state').innerText(), /Active until/);
  await page.keyboard.press('Escape');
  await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`${origin}/members`, { waitUntil: 'networkidle' });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await page.screenshot({ path: `${output}member-portal-mobile.png`, fullPage: true });
  await page.locator('.choose-flight').filter({ hasText: 'Select flight' }).first().click();
  assert.equal(await page.locator('#checkout').evaluate(el => el.scrollWidth > el.clientWidth + 1), false);
  await page.screenshot({ path: `${output}member-portal-checkout-mobile.png`, fullPage: false });
  await page.keyboard.press('Escape');
  const savedFlights = flights.splice(0);
  await page.locator('#refresh-flights').click();
  await page.waitForFunction(() => document.querySelector('#flight-results').textContent.includes('No member flights released yet'));
  assert.equal(await page.locator('.choose-flight').count(), 0);
  flights.push(...savedFlights);
  await page.locator('#refresh-flights').click(); await page.waitForFunction(() => document.querySelectorAll('.flight-card').length === 2);

  // Successful mutations remain confirmed if a subsequent account GET fails.
  bookingUnavailable = false; failAfterBook = true;
  await page.locator('.choose-flight').filter({ hasText: 'Select flight' }).first().click();
  const beforeBook = bookingCalls; await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-status').textContent.includes('Your booking is confirmed. Account'));
  assert.equal(bookingCalls, beforeBook + 1); assert.equal(await page.locator('#checkout-form').isVisible(), false);
  assert.equal(await page.locator('.trip-card').count(), 1);
  await page.locator('#checkout-refresh').click(); await page.waitForFunction(() => document.querySelector('#checkout-status').textContent.includes('Account refreshed.'));
  assert.equal(bookingCalls, beforeBook + 1); await page.keyboard.press('Escape');
  const priorId = await page.locator('#current-account').innerText(); await page.locator('#new-account').click();
  await page.waitForFunction(id => document.querySelector('#current-account').textContent !== id && !document.querySelector('#join-pass').disabled, priorId);
  failAfterJoin = true; await page.locator('#join-pass').click(); const beforeJoin = joinCalls; await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-status').textContent.includes('Membership is confirmed. Account'));
  assert.equal(joinCalls, beforeJoin + 1); assert.equal(await page.locator('#checkout-form').isVisible(), false);
  await page.locator('#checkout-refresh').click(); await page.waitForFunction(() => document.querySelector('#checkout-status').textContent.includes('Account refreshed.'));
  assert.equal(joinCalls, beforeJoin + 1); await page.keyboard.press('Escape');
  // Another tab already joined this identity at an older fee: display the
  // idempotent server receipt, never the currently requested plan price.
  const latestId = await page.locator('#current-account').innerText(); await page.locator('#new-account').click();
  await page.waitForFunction(id => document.querySelector('#current-account').textContent !== id && !document.querySelector('#join-pass').disabled, latestId);
  existingFeeOnJoin = 299; await page.locator('#join-pass').click(); await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-title').textContent === 'Your pass is active');
  assert.match(await page.locator('#checkout-content').innerText(), /HKD 299/);
  assert.match(await page.locator('#portal-notice').innerText(), /Recorded membership fee: HKD 299/);
  assert.doesNotMatch(await page.locator('#checkout-content').innerText(), /HKD 499/); await page.keyboard.press('Escape');
  assert.deepEqual(errors, []);

  if (process.argv.includes('--real')) {
    const real = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const response = await real.request.get(`${origin}/api/member-portal/flights`); const available = (await response.json()).flights.filter(f => f.bookable_seats > 0);
    assert.ok(available.length, 'Publish at least one eligible synthetic member offer before --real.');
    const selected = available[0];
    await real.goto(`${origin}/members`, { waitUntil: 'networkidle' });
    const id = await real.locator('#current-account').innerText();
    const chosen = real.locator(`.flight-card[data-flight-id="${selected.flight_id}"]`).getByRole('button'); await chosen.click();
    await real.locator('#checkout-submit').click();
    await real.waitForFunction(() => document.querySelector('#checkout-submit').textContent.includes('Confirm booking'));
    await real.locator('#checkout-submit').click();
    await real.waitForFunction(() => document.querySelector('#checkout-title').textContent === 'Your trip is saved');
    await real.keyboard.press('Escape'); await real.reload({ waitUntil: 'networkidle' });
    assert.equal(await real.locator('#current-account').innerText(), id); assert.equal(await real.locator('.trip-card').count(), 1);
    const after = await real.request.get(`${origin}/api/member-portal/accounts/${id}`); const a = await after.json();
    assert.equal(a.bookings.length, 1); assert.equal(a.bookings[0].total, selected.total); assert.equal(a.membership.active, true);
    console.log(`Real member portal passed: ${selected.flight_id}, one membership and one persisted booking for ${selected.total} HKD.`);
    await real.close();
  }
  console.log('Member portal UI passed: flight filters, exact cents, separate join/book confirmation, durable account, price-change re-review, sold-out handling, keyboard focus, 390px layout. Zero LLM calls.');
} finally { await browser.close(); }

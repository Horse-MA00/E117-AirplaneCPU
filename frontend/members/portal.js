const $ = (id) => document.getElementById(id);
const STORAGE_KEY = 'uoption-member-demo-account';
const airportNames = { HKG: 'Hong Kong', FUK: 'Fukuoka', KIX: 'Osaka Kansai', NRT: 'Tokyo Narita', HND: 'Tokyo Haneda', NGO: 'Nagoya', OKA: 'Okinawa', TPE: 'Taipei', KHH: 'Kaohsiung', ICN: 'Seoul Incheon', PUS: 'Busan', BKK: 'Bangkok', DMK: 'Bangkok Don Mueang', CNX: 'Chiang Mai', DAD: 'Da Nang', HAN: 'Hanoi', SGN: 'Ho Chi Minh City', MNL: 'Manila', CEB: 'Cebu', SIN: 'Singapore' };
const state = { config: null, flights: [], account: null, customerId: '', filters: {}, checkout: null, busy: false, loadVersion: 0, refreshRequired: false };
const money = (value) => `HKD ${new Intl.NumberFormat('en-HK', { maximumFractionDigits: 2 }).format(Number(value || 0))}`;
const airport = (code) => airportNames[code] ? `${airportNames[code]} (${code})` : code;
const node = (tag, text, className) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (className) el.className = className; return el; };
function calendarDate(value) { return new Date(`${value}T00:00:00Z`); }
function dateLabel(value) { return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(calendarDate(value)); }
function timestampLabel(value) { return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Hong_Kong' }).format(new Date(Number(value) * 1000)); }
function activeMember() { return Boolean(state.account?.membership?.active); }
function membershipExpired() { return Boolean(state.account?.membership && !state.account.membership.active); }
function alreadyBooked(flightId) { return (state.account?.bookings || []).some((booking) => booking.flight_id === flightId); }
function newCustomerId() { return `traveller-${crypto.randomUUID().slice(0, 12)}`; }
function remember(id) { try { localStorage.setItem(STORAGE_KEY, id); } catch { /* The account still works for this tab. */ } }
function initialCustomerId() {
  try { const id = localStorage.getItem(STORAGE_KEY); if (/^[A-Za-z0-9_-]{1,60}$/.test(id || '')) return id; } catch { /* Use a temporary local identity. */ }
  const id = newCustomerId(); remember(id); return id;
}
function notice(text, error = false) { const target = $(error ? 'portal-error' : 'portal-notice'); target.textContent = text; target.hidden = !text; }
function clearNotices() { notice(''); notice('', true); }
async function api(path, body) {
  let response;
  try { response = await fetch(path, body === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  catch { throw new Error('The connection could not be confirmed. Refresh your account and trips before retrying a purchase.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Refresh your trips before retrying a purchase.'); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function setBusy(value) {
  state.busy = value;
  for (const id of ['switch-account', 'new-account', 'refresh-account']) $(id).disabled = value;
  renderMembership();
  for (const button of document.querySelectorAll('.choose-flight')) button.disabled = value || button.dataset.available !== 'true';
  $('checkout-submit').disabled = value;
}
function populateSelect(id, values, firstLabel, format = String) {
  const select = $(id); const previous = select.value;
  const options = [new Option(firstLabel, ''), ...values.map((value) => new Option(format(value), value))];
  select.replaceChildren(...options);
  if (values.includes(previous)) select.value = previous;
}
function populateSearch() {
  populateSelect('origin', [...new Set(state.flights.map((f) => f.origin))].sort(), 'Any airport', airport);
  populateSelect('destination', [...new Set(state.flights.map((f) => f.destination))].sort(), 'Any destination', airport);
  populateSelect('departure-date', [...new Set(state.flights.map((f) => f.departure_date))].sort(), 'Any available date', dateLabel);
}
function emptyState(title, description, link) {
  const container = node('div', undefined, 'empty-state'); container.append(node('h3', title), node('p', description));
  if (link) { const anchor = node('a', link.text, 'text-link'); anchor.href = link.href; container.append(anchor); }
  return container;
}
function routeHeading(flight) {
  const heading = node('h3', undefined, 'flight-route');
  const route = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  route.setAttribute('viewBox', '0 0 40 16'); route.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M1 8h36m-6-5 6 5-6 5'); route.append(path);
  heading.setAttribute('aria-label', `${flight.origin} to ${flight.destination}`);
  heading.append(node('span', flight.origin), route, node('span', flight.destination));
  return heading;
}
function renderFlights() {
  const list = $('flight-results');
  const availableOnly = $('available-only').checked;
  const flights = state.flights.filter((f) => (!state.filters.origin || f.origin === state.filters.origin) && (!state.filters.destination || f.destination === state.filters.destination) && (!state.filters.date || f.departure_date === state.filters.date) && (!availableOnly || Number(f.bookable_seats) > 0 && !alreadyBooked(f.flight_id))).sort((a, b) => $('flight-sort').value === 'price' ? a.total - b.total || a.departure_date.localeCompare(b.departure_date) : a.departure_date.localeCompare(b.departure_date) || a.total - b.total);
  $('result-count').textContent = `${flights.length} ${flights.length === 1 ? 'flight' : 'flights'} · Prices include mandatory fees`;
  if (!state.flights.length) {
    list.replaceChildren(emptyState('No member flights released yet', 'There are no released member seats to browse right now. Check again later; joining a pass does not guarantee a flight.', { href: '#membership', text: 'How the pass works' }));
    return;
  }
  if (!flights.length) {
    const empty = emptyState('No matching flights', 'Try another destination or date to see the released offers.');
    const reset = node('button', 'Show all available flights', 'text-button'); reset.type = 'button'; reset.addEventListener('click', () => { state.filters = {}; $('flight-search').reset(); $('available-only').checked = false; renderFlights(); }); empty.append(reset); list.replaceChildren(empty); return;
  }
  list.replaceChildren(...flights.map((flight) => {
    const booked = alreadyBooked(flight.flight_id); const available = Number(flight.bookable_seats) > 0 && !booked;
    const card = node('article', undefined, `flight-card${available ? '' : ' is-unavailable'}`); card.dataset.flightId = flight.flight_id;
    const date = node('div', undefined, 'flight-date'); const d = calendarDate(flight.departure_date);
    date.append(node('span', d.getUTCDate(), 'day'), node('span', new Intl.DateTimeFormat('en-GB', { month: 'short', weekday: 'short', timeZone: 'UTC' }).format(d), 'month'), node('span', d.getUTCFullYear(), 'year'));
    const route = node('div'); route.append(routeHeading(flight), node('p', `${airportNames[flight.origin] || flight.origin} to ${airportNames[flight.destination] || flight.destination}`, 'flight-name'));
    route.append(node('p', `One way · 1 traveller`, 'flight-detail'), node('p', flight.flight_id, 'flight-detail'));
    if (flight.normal_total != null) {
      route.append(node('p', `Current normal fare ${money(flight.normal_total)}`, 'flight-detail'));
      const saving = Math.round((Number(flight.normal_total) - Number(flight.total)) * 100) / 100;
      if (saving > 0) route.append(node('p', `Ticket saving ${money(saving)} before membership fee`, 'flight-savings'));
    }
    route.append(node('p', booked ? 'Already in your trips' : available ? `${flight.bookable_seats} member ${Number(flight.bookable_seats) === 1 ? 'seat' : 'seats'} available` : 'Currently unavailable', 'availability'));
    const price = node('div', undefined, 'flight-price'); price.append(node('span', 'Member ticket · total', 'price-label'), node('strong', money(flight.total), 'total'), node('span', `Base ${money(flight.base_fare)} + fees ${money(flight.mandatory_fees)}`, 'breakdown'));
    const choose = node('button', booked ? 'Booked' : available ? 'Select flight' : 'Unavailable', 'button primary choose-flight'); choose.type = 'button'; choose.dataset.purchase = ''; choose.dataset.available = String(available); choose.disabled = !available || state.busy;
    choose.setAttribute('aria-label', `${choose.textContent}: ${flight.origin} to ${flight.destination}, ${dateLabel(flight.departure_date)}, ${money(flight.total)}`);
    choose.addEventListener('click', () => openCheckout('flight', flight)); price.append(choose); card.append(date, route, price); return card;
  }));
}
function renderMembership() {
  if (!state.config) return;
  const membership = state.config.membership;
  $('hero-fee').textContent = money(membership.fee);
  $('hero-term').textContent = membership.term_days;
  $('pass-price').textContent = money(membership.fee);
  $('pass-term').textContent = `${membership.term_days} days · One personal membership`;
  $('header-account').textContent = activeMember() ? 'Your membership is active' : 'Your demo account';
  $('join-pass').disabled = state.busy || !state.account || activeMember() || membershipExpired();
  $('join-pass').textContent = activeMember() ? 'Membership active' : membershipExpired() ? 'Membership expired' : 'Review membership';
  $('membership-state').textContent = activeMember() ? `Active until ${timestampLabel(state.account.membership.expires)}. You will not be charged another membership fee when booking.` : membershipExpired() ? 'This membership has expired. Renewal is not available in this prototype.' : 'Find a suitable flight first. Join when you are ready to book.';
}
function renderAccount() {
  $('current-account').textContent = state.customerId; $('customer-id').value = state.customerId;
  renderMembership(); const bookings = state.account?.bookings || [];
  $('trip-count').textContent = bookings.length;
  if (!bookings.length) { $('trip-results').replaceChildren(emptyState('Your next trip starts here', 'Choose a member flight to start planning. Your confirmed bookings will appear here.', { href: '#flights', text: 'Find a member flight' })); return; }
  $('trip-results').replaceChildren(...bookings.map((booking) => {
    const card = node('article', undefined, 'trip-card'); card.dataset.bookingId = booking.id;
    card.append(node('p', 'Simulated booking confirmed', 'confirmed'), node('h3', `${booking.origin} → ${booking.destination}`), node('p', `${dateLabel(booking.departure_date)} · One way · 1 traveller`), node('p', money(booking.total), 'trip-total'), node('p', `Base ${money(booking.base_fare)} + mandatory fees ${money(booking.mandatory_fees)}`), node('p', `Reference ${booking.id}`, 'booking-id'));
    return card;
  }));
}
async function loadData() {
  const version = ++state.loadVersion; const customer = state.customerId;
  $('flight-results').setAttribute('aria-busy', 'true');
  try {
    const [config, flights, account] = await Promise.all([api('/api/member-portal/config'), api('/api/member-portal/flights'), api(`/api/member-portal/accounts/${encodeURIComponent(customer)}`)]);
    if (version !== state.loadVersion || customer !== state.customerId) return;
    state.config = config; state.flights = flights.flights || []; state.account = account; state.refreshRequired = false;
    populateSearch(); renderAccount(); renderFlights();
  } catch (error) {
    if (version === state.loadVersion) { notice(error.message, true); if (!state.config) $('flight-results').replaceChildren(emptyState('Flights could not be loaded', 'Use Refresh availability to try again.')); }
    throw error;
  } finally { if (version === state.loadVersion) $('flight-results').setAttribute('aria-busy', 'false'); }
}
function addPriceLine(dl, label, value, total = false) { dl.append(node('dt', label, total ? 'total-line' : ''), node('dd', money(value), total ? 'total-line' : '')); }
function renderCheckout() {
  if (!state.checkout || !state.config) return;
  const { type, flight } = state.checkout; const fee = activeMember() ? 0 : Number(state.config.membership.fee);
  $('checkout-error').hidden = true; $('checkout-status').hidden = true; $('checkout-form').hidden = false; $('view-trips').hidden = true; $('checkout-refresh').hidden = !state.refreshRequired;
  $('checkout-step').textContent = activeMember() ? 'Confirm your flight' : type === 'flight' ? 'Membership, then your flight' : 'Review membership';
  $('checkout-title').textContent = type === 'flight' ? 'Your trip, at a glance' : 'Join UOption Fly Pass';
  const content = $('checkout-content'); content.replaceChildren();
  if (type === 'flight') {
    content.append(node('h3', `${flight.origin} → ${flight.destination}`), node('p', `${dateLabel(flight.departure_date)} · 1 member traveller · One way`, 'checkout-date'));
    const prices = node('dl', undefined, 'price-lines'); addPriceLine(prices, 'Member base fare', flight.base_fare); addPriceLine(prices, 'Mandatory fees', flight.mandatory_fees); addPriceLine(prices, 'New membership fee', fee); addPriceLine(prices, activeMember() ? 'Ticket total to confirm' : 'Membership + ticket total', Number(flight.total) + fee, true); content.append(prices);
    if (!activeMember()) {
      const steps = node('ol', undefined, 'checkout-steps'); steps.append(node('li', `First, join the ${state.config.membership.term_days}-day pass for ${money(fee)}.`), node('li', `Then confirm this ticket separately for ${money(flight.total)}. Seats are checked again at booking and are not reserved by joining.`)); content.append(steps);
    } else content.append(node('p', 'Your membership is active. No new membership fee is due.', 'fine-print'));
    content.append(node('p', 'Personal member fare. Baggage is not sold in this prototype. This screen does not promise a free checked bag.', 'fine-print'));
    $('checkout-submit').textContent = activeMember() ? `Confirm booking · ${money(flight.total)}` : `Join pass · ${money(fee)}`;
  } else {
    content.append(node('h3', `${state.config.membership.term_days} days of member access`), node('p', 'A personal membership for published member fares. Each ticket is paid separately, including its mandatory fees.', 'checkout-date'));
    const prices = node('dl', undefined, 'price-lines'); addPriceLine(prices, 'Membership fee', fee, true); content.append(prices, node('p', 'Seats and suitable dates are not guaranteed. No automatic renewal. Joining does not reserve a flight.', 'fine-print'));
    $('checkout-submit').textContent = `Join pass · ${money(fee)}`;
  }
  $('checkout-submit').disabled = state.busy || state.refreshRequired || membershipExpired() || (type === 'flight' && (Number(flight.bookable_seats) < 1 || alreadyBooked(flight.flight_id)));
}
async function openCheckout(type, flight = null) {
  if (state.busy) return;
  clearNotices(); state.checkout = { type, flight }; renderCheckout(); $('checkout').showModal();
}
function checkoutMessage(text, error = false) { const element = $(error ? 'checkout-error' : 'checkout-status'); element.textContent = text; element.hidden = !text; }
async function submitCheckout(event) {
  event.preventDefault(); if (state.busy || state.refreshRequired || !state.checkout || !state.account) return;
  const selected = { ...state.checkout }; const customer = state.customerId; const joining = !activeMember(); const fee = Number(state.config.membership.fee);
  setBusy(true); checkoutMessage(''); checkoutMessage('', true);
  try {
    if (joining) {
      const result = await api('/api/member-portal/join', { customer_id: customer, expected_fee: fee });
      const recordedFee = Number(result.member.fee);
      state.account.membership = { ...result.member, active: true }; renderAccount();
      let refreshed = true;
      try { await loadData(); } catch { refreshed = false; state.refreshRequired = true; }
      notice(`Your simulated membership is active. Recorded membership fee: ${money(recordedFee)}.`);
      if (selected.type === 'flight') {
        const current = state.flights.find((flight) => flight.offer_id === selected.flight.offer_id);
        state.checkout = { ...selected, flight: current || { ...selected.flight, bookable_seats: 0 } }; renderCheckout();
        checkoutMessage(!refreshed ? 'Membership is confirmed. Account and availability refresh failed; no flight has been booked. Refresh below before continuing. Do not join again.' : current && current.bookable_seats > 0 ? 'Membership is active. Review the ticket price, then confirm your booking.' : 'Membership is active, but this offer is no longer available. No flight has been booked. Close this window and choose another flight.', !refreshed || !current || current.bookable_seats < 1);
      } else {
        $('checkout-title').textContent = 'Your pass is active'; $('checkout-step').textContent = 'Membership confirmed';
        $('checkout-content').replaceChildren(node('p', money(recordedFee), 'booking-complete'), node('p', `Recorded membership fee. Your personal pass is valid until ${timestampLabel(state.account.membership.expires)}. Find a released flight when you are ready.`, 'checkout-date'));
        $('checkout-form').hidden = true; $('checkout-refresh').hidden = refreshed; checkoutMessage(refreshed ? 'No real payment was collected.' : 'Membership is confirmed. Account refresh failed; refresh before continuing. No real payment was collected.');
      }
    } else if (selected.type === 'flight') {
      const result = await api('/api/member-portal/book', { customer_id: customer, offer_id: selected.flight.offer_id, expected_total: Number(selected.flight.total) });
      if (!state.account.bookings.some((booking) => booking.id === result.booking.id)) state.account.bookings.push({ ...selected.flight, ...result.booking });
      renderAccount(); renderFlights();
      let refreshed = true;
      try { await loadData(); } catch { refreshed = false; state.refreshRequired = true; }
      $('checkout-step').textContent = 'Booking complete'; $('checkout-title').textContent = 'Your trip is saved';
      $('checkout-content').replaceChildren(node('p', `${selected.flight.origin} → ${selected.flight.destination}`, 'booking-complete'), node('p', `${dateLabel(selected.flight.departure_date)} · ${money(result.booking.total)}`, 'checkout-date'), node('p', `Booking reference ${result.booking.id}`, 'fine-print'));
      $('checkout-form').hidden = true; $('view-trips').hidden = false; $('checkout-refresh').hidden = refreshed; checkoutMessage(refreshed ? 'This is a simulated booking. No airline ticket has been issued.' : 'Your booking is confirmed. Account and availability refresh failed; refresh My trips to verify the saved record. Do not submit this booking again.');
      notice(`Your ${selected.flight.origin} to ${selected.flight.destination} trip is saved in My trips.`);
    }
  } catch (error) {
    // Refresh displayed server prices, but never automatically retry a charge.
    try { await loadData(); } catch { /* Preserve the original mutation error. */ }
    if (selected.type === 'flight') { const current = state.flights.find((flight) => flight.offer_id === selected.flight.offer_id); state.checkout = { ...selected, flight: current || { ...selected.flight, bookable_seats: 0 } }; }
    renderCheckout(); checkoutMessage(`${error.message} Review the current information before trying again.`, true); notice(error.message, true);
  } finally {
    setBusy(false);
    if (state.refreshRequired) $('checkout-submit').disabled = true;
    if (state.checkout?.type === 'flight' && (Number(state.checkout.flight.bookable_seats) < 1 || alreadyBooked(state.checkout.flight.flight_id))) $('checkout-submit').disabled = true;
    if (membershipExpired()) $('checkout-submit').disabled = true;
  }
}
async function switchAccount(id) {
  if (state.busy) return; clearNotices(); state.customerId = id; state.account = null; remember(id); $('checkout').close(); state.checkout = null;
  $('current-account').textContent = id; $('customer-id').value = id;
  renderMembership(); $('trip-count').textContent = '0'; $('trip-results').replaceChildren(emptyState('Loading this account', 'Checking membership and saved trips for the selected test ID.'));
  try { await loadData(); notice('Demo account changed. Membership and trips below belong to this test ID.'); } catch { /* loadData announces its error. */ }
}
$('flight-search').addEventListener('submit', (event) => { event.preventDefault(); state.filters = { origin: $('origin').value, destination: $('destination').value, date: $('departure-date').value }; renderFlights(); $('results-title').focus(); });
$('available-only').addEventListener('change', renderFlights);
$('flight-sort').addEventListener('change', renderFlights);
$('refresh-flights').addEventListener('click', async () => { clearNotices(); try { await loadData(); notice('Flight availability refreshed.'); } catch { /* Error is visible. */ } });
$('refresh-account').addEventListener('click', async () => { clearNotices(); try { await loadData(); notice('Membership and trips refreshed.'); } catch { /* Error is visible. */ } });
$('join-pass').addEventListener('click', () => openCheckout('membership'));
$('checkout-form').addEventListener('submit', submitCheckout);
$('checkout-refresh').addEventListener('click', async () => {
  if (state.busy) return;
  const button = $('checkout-refresh'); button.disabled = true;
  try {
    await loadData();
    if (state.checkout?.type === 'flight') {
      const current = state.flights.find((flight) => flight.offer_id === state.checkout.flight.offer_id);
      state.checkout.flight = current || { ...state.checkout.flight, bookable_seats: 0 };
    }
    if (state.checkout?.type === 'flight' && alreadyBooked(state.checkout.flight.flight_id)) { button.hidden = true; checkoutMessage('Account refreshed. Your confirmed booking is in My trips.'); }
    else if (state.checkout?.type === 'membership' && activeMember()) { button.hidden = true; checkoutMessage('Account refreshed. Your membership is active.'); }
    else { renderCheckout(); checkoutMessage('Account and availability refreshed. Review the current ticket before confirming.'); }
  } catch (error) { checkoutMessage(error.message, true); }
  finally { button.disabled = false; }
});
$('checkout').addEventListener('close', () => { $('checkout').returnValue = ''; });
$('view-trips').addEventListener('click', () => { $('checkout').close(); location.hash = 'trips'; });
$('account-form').addEventListener('submit', (event) => { event.preventDefault(); if ($('account-form').reportValidity()) switchAccount($('customer-id').value.trim()); });
$('new-account').addEventListener('click', () => switchAccount(newCustomerId()));
function renderNavigation() { const current = ['membership', 'trips'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'flights'; for (const link of document.querySelectorAll('.header nav a')) { if (link.hash === `#${current}`) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); } }
window.addEventListener('hashchange', renderNavigation);
state.customerId = initialCustomerId(); renderNavigation(); loadData().catch(() => {});

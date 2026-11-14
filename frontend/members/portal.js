import { regions, nextMonthRange, dateLabel, dateParts, reversedRange, matchesSearch, placeRegion, REGION_PREFIX } from './search.js';
import { airports, catalogAirportCodes, airportNames, airportLabel } from './airports.js';

const $ = (id) => document.getElementById(id);

// Post-purchase returns use published, currently available offers only.
function availableFlight(f) { return Number(f.bookable_seats) > 0 && !alreadyBooked(f.flight_id); }
function returnOptions(outbound) {
  return state.flights.filter(f => availableFlight(f) && f.origin === outbound.destination
    && f.destination === outbound.origin && f.departure_date > outbound.departure_date)
    .sort((a,b) => a.departure_date.localeCompare(b.departure_date) || a.total-b.total);
}
function suggestReturn(outbound) {
  const choices=returnOptions(outbound);if(!choices.length)return;
  const box=node('div',undefined,'return-suggestion');box.append(node('h3','Complete your trip with a return flight'));
  const back=choices[0];box.append(node('p',`${back.origin} → ${back.destination} · ${dateLabel(back.departure_date)} · ${money(back.total)} incl. fees`));
  const button=node('button','Review return flight','button primary');button.type='button';
  button.onclick=()=>{openCheckout('flight',back);};box.append(button);$('checkout-content').append(box);
}
$('available-dates').addEventListener('click',()=>{
  const dates=state.flights.filter(f=>availableFlight(f)&&matchesSearch(f,{origin:$('origin').value,destination:$('destination').value})).map(f=>f.departure_date).sort();
  if(!dates.length){notice('No available offers for these airports. Try another destination.');return;}
  setDates(dates[0],dates.at(-1));$('available-only').checked=true;$('flight-search').requestSubmit();
});

const state = { config: null, flights: [], account: null, user: null, customerId: '', filters: {}, checkout: null, busy: false, loadVersion: 0, refreshRequired: false };
const money = (value) => `HKD ${new Intl.NumberFormat('en-HK', { maximumFractionDigits: 2 }).format(Number(value || 0))}`;
const airport = (code) => airportNames[code] ? `${airportNames[code]} (${code})` : code;
const node = (tag, text, className) => { const el = document.createElement(tag); if (text != null) el.textContent = text; if (className) el.className = className; return el; };
function timestampLabel(value) { return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'Asia/Hong_Kong' }).format(new Date(Number(value) * 1000)); }
function activeMember() { return Boolean(state.account?.membership?.active); }
function membershipExpired() { return Boolean(state.account?.membership && !state.account.membership.active); }
function alreadyBooked(flightId) { return (state.account?.bookings || []).some((booking) => booking.flight_id === flightId); }
function membershipTerm() { return state.config?.membership?.term_label || `${state.config?.membership?.term_months || 6} months`; }
function signInRequired() {
  ++state.loadVersion;
  state.account = null; state.user = null; state.customerId = ''; state.checkout = null;
  $('checkout').close(); $('main-content').hidden = true;
  $('session-status').textContent = 'Sign in to continue.'; $('session-status').hidden = false;
  location.replace('/members/login');
}
function notice(text, error = false) { const target = $(error ? 'portal-error' : 'portal-notice'); target.textContent = text; target.hidden = !text; }
function clearNotices() { notice(''); notice('', true); }
async function api(path, body) {
  let response;
  try { response = await fetch(path, body === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  catch { throw new Error('The connection could not be confirmed. Refresh your account and trips before retrying a purchase.'); }
  let data;
  try { data = await response.json(); } catch { throw new Error('The server returned an unreadable response. Refresh your trips before retrying a purchase.'); }
  if (!response.ok) {
    if (response.status === 401 || response.status === 403) signInRequired();
    throw new Error(data.error || `Request failed (${response.status}).`);
  }
  return data;
}
function setBusy(value) {
  state.busy = value;
  for (const id of ['sign-out', 'refresh-account']) $(id).disabled = value;
  renderMembership();
  for (const button of document.querySelectorAll('.choose-flight')) button.disabled = value || button.dataset.available !== 'true';
  $('checkout-submit').disabled = value;
}
function placeLabel(place) {
  const region = placeRegion(place);
  return region ? `${regions[region]?.name || region} (all airports)` : airport(place);
}
function populateSearch() { populatePlaces('origin', 'origin'); populatePlaces('destination', 'destination'); }
// One picker per side: each country group starts with an "all airports"
// option (when it has more than one airport), then its airports. Unknown
// observed airports stay selectable under "Other published airports".
function populatePlaces(id, field) {
  const select = $(id); const previous = select.value;
  const codes = [...new Set([...catalogAirportCodes, ...state.flights.map((f) => f[field]), ...(previous && !placeRegion(previous) ? [previous] : [])])];
  const groups = new Map();
  for (const code of codes.sort((a, b) => airport(a).localeCompare(airport(b)))) {
    const region = airports[code]?.region || '';
    if (!groups.has(region)) groups.set(region, []);
    groups.get(region).push(code);
  }
  const name = (region) => regions[region]?.name || 'Other published airports';
  const ordered = [...groups.keys()].sort((a, b) => a === 'HK' ? -1 : b === 'HK' ? 1 : !a ? 1 : !b ? -1 : name(a).localeCompare(name(b)));
  const children = ordered.map((region) => {
    const group = document.createElement('optgroup'); group.label = name(region);
    const members = groups.get(region);
    if (region && members.length > 1) group.append(new Option(`All ${name(region)} airports`, `${REGION_PREFIX}${region}`));
    group.append(...members.map((code) => new Option(airportLabel(code), code)));
    return group;
  });
  select.replaceChildren(new Option('Anywhere', ''), ...children);
  if ([...select.options].some((option) => option.value === previous)) select.value = previous;
  renderAirportNote(id);
}
function renderAirportNote(id) {
  const value = $(id).value; const note = placeRegion(value) ? '' : airports[value]?.note || '';
  $(id).title = value ? placeLabel(value) : '';
  $(`${id}-note`).textContent = note; $(`${id}-note`).hidden = !note;
}
function setPlace(id, value) {
  const select = $(id);
  if (value && ![...select.options].some((option) => option.value === value)) select.append(new Option(placeLabel(value), value));
  select.value = value || ''; renderAirportNote(id);
}
function searchDescription() {
  const { origin, destination, from, to } = state.filters;
  const place = origin || destination ? `${origin ? placeLabel(origin) : 'Anywhere'} → ${destination ? placeLabel(destination) : 'Anywhere'}` : 'Anywhere';
  const dates = from && to ? from === to ? dateLabel(from) : `${dateLabel(from)} – ${dateLabel(to)}` : from ? `From ${dateLabel(from)}` : to ? `Until ${dateLabel(to)}` : 'Any dates';
  return `${place} · ${dates}`;
}
function validateDates() {
  const fields = [$('departure-from'), $('departure-to')];
  for (const field of fields) { field.setCustomValidity(''); field.removeAttribute('aria-invalid'); }
  // Check the native date domain first: browsers can accept unsigned five-digit
  // years, but our API uses four-digit ISO dates. Never pass those to Temporal.
  const malformed = fields.find((field) => field.validity.badInput || field.validity.rangeOverflow || field.validity.rangeUnderflow);
  const invalid = malformed || (reversedRange(fields[0].value, fields[1].value) ? fields[1] : null);
  const message = malformed ? 'Enter a complete date with a year from 0001 to 9999.' : invalid ? 'Latest departure must be on or after earliest departure.' : '';
  if (invalid) { invalid.setCustomValidity(message); invalid.setAttribute('aria-invalid', 'true'); }
  $('search-date-error').textContent = message;
  $('search-date-error').hidden = !invalid;
  return !invalid;
}
function setDates(from, to) {
  $('departure-from').value = from; $('departure-to').value = to;
  validateDates();
}
function clearSearch() {
  state.filters = {}; $('flight-search').reset(); $('available-only').checked = true;
  validateDates(); populateSearch(); renderFlights();
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
function renderDateFares() {
  const strip=$('date-options'); strip.replaceChildren();
  const {origin,destination}=state.filters;
  const lowest=new Map();
  for(const flight of state.flights) {
    if(!availableFlight(flight) || !matchesSearch(flight,{origin,destination})) continue;
    const previous=lowest.get(flight.departure_date);
    if(previous===undefined || Number(flight.total)<previous) lowest.set(flight.departure_date,Number(flight.total));
  }
  $('date-fares').hidden=lowest.size===0;
  for(const [date,total] of [...lowest].sort(([a],[b])=>a.localeCompare(b))) {
    const b=node('button',undefined,'date-fare');b.type='button';b.dataset.date=date;
    b.setAttribute('aria-pressed',String(state.filters.from===date && state.filters.to===date));
    b.append(node('span',dateLabel(date)),node('strong',`From ${money(total)}`));
    b.addEventListener('click',()=>{
      // Restore the applied route, rather than silently apply unfinished draft filters.
      setPlace('origin',origin);setPlace('destination',destination);
      setDates(date,date);$('flight-search').requestSubmit();
    });strip.append(b);
  }
}
function checkoutProgress(stage) {
  for(const item of document.querySelectorAll('.checkout-progress li')) {
    item.classList.toggle('is-current',item.dataset.stage===stage);
    if(item.dataset.stage===stage)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');
  }
  $('checkout').dataset.stage=stage;
}
function renderFlights() {
  renderDateFares();
  const list = $('flight-results');
  const availableOnly = $('available-only').checked;
  const flights = state.flights.filter((f) => matchesSearch(f, state.filters) && (!availableOnly || Number(f.bookable_seats) > 0 && !alreadyBooked(f.flight_id))).sort((a, b) => $('flight-sort').value === 'total' ? a.total - b.total || a.departure_date.localeCompare(b.departure_date) : $('flight-sort').value === 'price' ? a.base_fare - b.base_fare || a.departure_date.localeCompare(b.departure_date) : a.departure_date.localeCompare(b.departure_date) || a.base_fare - b.base_fare);
  $('search-summary').textContent = searchDescription();
  $('result-count').textContent = `${flights.length} ${flights.length === 1 ? 'flight' : 'flights'} · One way · Ticket totals include fees`;
  if (!state.flights.length) {
    list.replaceChildren(emptyState('No member flights released yet', 'There are no released member seats to browse right now. Check again later; joining a pass does not guarantee a flight.', { href: '#membership', text: 'How the pass works' }));
    return;
  }
  if (!flights.length) {
    const empty = emptyState('No matching flights', 'No released offers match this search. Try a wider date range or another destination; more member seats may be released later.');
    const reset = node('button', 'Show all released flights', 'text-button'); reset.type = 'button'; reset.addEventListener('click', clearSearch); empty.append(reset); list.replaceChildren(empty); return;
  }
  list.replaceChildren(...flights.map((flight) => {
    const booked = alreadyBooked(flight.flight_id); const available = Number(flight.bookable_seats) > 0 && !booked;
    const card = node('article', undefined, `flight-card${available ? '' : ' is-unavailable'}`); card.dataset.flightId = flight.flight_id;
    const date = node('div', undefined, 'flight-date'); const d = dateParts(flight.departure_date);
    date.append(node('span', d.day, 'day'), node('span', dateLabel(flight.departure_date, { month: 'short', weekday: 'short' }), 'month'), node('span', d.year, 'year'));
    const route = node('div'); route.append(routeHeading(flight), node('p', `${airportNames[flight.origin] || flight.origin} to ${airportNames[flight.destination] || flight.destination}`, 'flight-name'));
    route.append(node('p', `One way · 1 member traveller`, 'flight-detail'));
    if(flight.departure_at) route.append(node('p',`Departure ${flight.departure_at.slice(11,16)} · scheduled time, UTC${flight.departure_at.slice(19)} (simulated)`,'flight-detail'));
    const details=node('details');details.append(node('summary','Flight reference'),node('span',flight.flight_id));route.append(details);
    route.append(node('p', booked ? 'Already in your trips' : available ? `${flight.bookable_seats} member ${Number(flight.bookable_seats) === 1 ? 'seat' : 'seats'} available` : 'Currently unavailable', 'availability'));
    const price = node('div', undefined, 'flight-price'); price.append(node('span', 'Member base fare', 'price-label'), fareCompare(flight), ...fareSaving(flight), node('span', flight.fee_breakdown ? 'Reference fee estimate' : `+ fees ${money(flight.mandatory_fees)} · total payable ${money(flight.total)}`, 'breakdown'));
    if(flight.fee_breakdown) { const costs=node('div',undefined,'fee-summary'); for(const item of feeLines(flight)) costs.append(node('span',`${item.label}: ${money(item.amount)}`)); costs.append(node('strong',`Ticket total: ${money(flight.total)}`,'ticket-total')); price.append(costs); }
    else price.append(node('strong',`Ticket total: ${money(flight.total)}`,'ticket-total')); 
    const choose = node('button', booked ? 'Booked' : available ? 'Select flight' : 'Unavailable', 'button primary choose-flight'); choose.type = 'button'; choose.dataset.purchase = ''; choose.dataset.available = String(available); choose.disabled = !available || state.busy;
    choose.setAttribute('aria-label', `${choose.textContent}: ${flight.origin} to ${flight.destination}, ${dateLabel(flight.departure_date)}, base fare ${money(flight.base_fare)}, total payable ${money(flight.total)}`);
    if(!activeMember()) price.append(node('span',`First purchase incl. pass: ${money(Number(flight.total)+Number(state.config?.membership.fee||0))}`,'first-purchase'));
    choose.addEventListener('click', () => openCheckout('flight', flight)); price.append(choose); card.append(date, route, price); return card;
  }));
}
function renderMembership() {
  if (!state.config) return;
  const membership = state.config.membership;
  $('hero-fee').textContent = money(membership.fee);
  $('hero-term').textContent = membershipTerm();
  $('pass-price').textContent = money(membership.fee);
  $('pass-term').textContent = `${membershipTerm()} · One personal membership`;
  $('header-account').textContent = activeMember() ? 'Member account' : 'Guest account';
  $('join-pass').disabled = state.busy || !state.account || activeMember() || membershipExpired();
  $('join-pass').textContent = activeMember() ? 'Membership active' : membershipExpired() ? 'Membership expired' : 'Review membership';
  $('membership-state').textContent = activeMember() ? `Active until ${timestampLabel(state.account.membership.expires)}. You will not be charged another membership fee when booking.` : membershipExpired() ? 'This membership has expired. Renewal is not available in this prototype.' : 'Find a suitable flight first. Join when you are ready to book.';
}
function renderAccount() {
  $('current-account').textContent = state.user?.email || state.customerId;
  $('account-status').textContent = activeMember() ? `Member · Active until ${timestampLabel(state.account.membership.expires)}` : membershipExpired() ? 'Membership expired' : 'Guest · No membership purchased';
  renderMembership(); const bookings = state.account?.bookings || [];
  $('trip-count').textContent = bookings.length;
  if (!bookings.length) { $('trip-results').replaceChildren(emptyState('Your next trip starts here', 'Choose a member flight to start planning. Your confirmed bookings will appear here.', { href: '#flights', text: 'Find a member flight' })); return; }
  $('trip-results').replaceChildren(...bookings.map((booking) => {
    const card = node('article', undefined, 'trip-card'); card.dataset.bookingId = booking.id;
    card.append(node('p', 'Simulated booking confirmed', 'confirmed'), node('h3', `${booking.origin} → ${booking.destination}`), node('p', `${dateLabel(booking.departure_date)} · One way · 1 traveller`), node('p', `${money(booking.base_fare)} base fare`, 'trip-total'), node('p', `+ fees ${money(booking.mandatory_fees)} · total paid ${money(booking.total)}`, 'fine-print'), node('p', `Reference ${booking.id}`, 'booking-id'));
    if(booking.fee_breakdown) {const fees=node('dl',undefined,'price-lines');for(const item of feeLines(booking)) addPriceLine(fees,item.label,item.amount);card.append(fees,feeDetails(booking));}
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
// The normal (non-member) base fare for the same flight, when it is higher.
function normalBaseFare(flight) {
  const normal = flight.normal_base_fare ?? (flight.normal_total != null ? Number(flight.normal_total) - Number(flight.mandatory_fees) : null);
  return normal != null && Number(normal) > Number(flight.base_fare) ? Number(normal) : null;
}
// Struck-through normal fare beside the member fare. Screen readers hear
// "Normal base fare" because a strikethrough alone is not announced.
function wasPrice(flight) {
  const normal = normalBaseFare(flight); if (normal == null) return null;
  const was = node('s', undefined, 'was-price'); was.append(node('span', 'Normal base fare ', 'sr-only'), document.createTextNode(money(normal)));
  return was;
}
function fareCompare(flight) {
  const row = node('div', undefined, 'fare-compare'); const was = wasPrice(flight);
  if (was) row.append(was);
  row.append(node('strong', money(flight.base_fare), 'total'));
  return row;
}
function fareSaving(flight) {
  const normal = normalBaseFare(flight); if (normal == null) return [];
  const saving = Math.round((normal - Number(flight.base_fare)) * 100) / 100;
  return [node('span', `Save ${money(saving)} · ${Math.round(saving / normal * 100)}% off normal base fare`, 'fare-saving')];
}
function addPriceLine(dl, label, value, total = false) { dl.append(node('dt', label, total ? 'total-line' : ''), node('dd', money(value), total ? 'total-line' : '')); }
function feeLines(flight) {
  const lines = flight.fee_breakdown?.lines;
  if (Array.isArray(lines) && lines.length && lines.every(l => Number.isFinite(l.amount) && l.amount >= 0)
      && Math.abs(lines.reduce((sum,l) => sum+l.amount,0)-Number(flight.mandatory_fees)) < 0.005) return lines;
  return [{label:'Published demo fees (unitemized)',amount:Number(flight.mandatory_fees)}];
}
function feeDetails(flight) {
  const detail=flight.fee_breakdown;
  if(!detail) return node('p','Fee components are not available for this older demo offer.','fine-print');
  const box=node('details',undefined,'fee-reference');box.append(node('summary','Fee details & sources'));
  box.append(node('p',`Reference checked ${detail.checked_on} · ${detail.terminal_assumption}. ${detail.note}`));
  for(const part of detail.components || []) {
    const row=node('p',`${part.code ? part.code+' · ' : ''}${part.label}: ${part.native_currency} ${part.native_amount} → ${money(part.amount)} `);
    if(part.source?.startsWith('https://')) {const link=node('a','Source');link.href=part.source;link.target='_blank';link.rel='noopener noreferrer';row.append(link);}
    box.append(row);
  }
  if(detail.fx_date) box.append(node('p',`ECB reference ${detail.fx_date}: JPY 1 ≈ HKD ${Number(detail.fx_rate).toFixed(6)}. HKD estimates round each component to cents; airline conversion may differ.`));
  box.append(node('p','HK Express lists fuel under YR. No separate YQ or insurance amount is published in this reference.'));
  return box;
}
function renderCheckout() {
  if (!state.checkout || !state.config) return;
  checkoutProgress(activeMember()?'confirm':'membership');
  const { type, flight } = state.checkout; $('checkout').dataset.kind=type; const fee = activeMember() ? 0 : Number(state.config.membership.fee);
  $('checkout-error').hidden = true; $('checkout-status').hidden = true; $('checkout-form').hidden = false; $('view-trips').hidden = true; $('checkout-refresh').hidden = !state.refreshRequired;
  $('checkout-step').textContent = activeMember() ? 'Confirm your flight' : type === 'flight' ? 'Membership, then your flight' : 'Review membership';
  $('checkout-title').textContent = type === 'flight' ? 'Your trip, at a glance' : 'Join UOption Fly Pass';
  const content = $('checkout-content'); content.replaceChildren();
  if (type === 'flight') {
    content.append(node('h3', `${flight.origin} → ${flight.destination}`), node('p', `${dateLabel(flight.departure_date)} · 1 member traveller · One way`, 'checkout-date'));
    const prices = node('dl', undefined, 'price-lines'); addPriceLine(prices, 'Member base fare', flight.base_fare); { const was = wasPrice(flight); if (was) prices.lastElementChild.prepend(was, ' '); } for(const item of feeLines(flight)) addPriceLine(prices,item.label,item.amount); addPriceLine(prices,'Ticket total',flight.total,true); addPriceLine(prices, 'New membership fee', fee); addPriceLine(prices, activeMember() ? 'Ticket total to confirm' : 'Membership + ticket total', Number(flight.total) + fee, true); content.append(prices,feeDetails(flight));
    if (!activeMember()) {
      const steps = node('ol', undefined, 'checkout-steps'); steps.append(node('li', `First, join the ${state.config.membership.term_months || 6}-month pass for ${money(fee)}.`), node('li', `Then confirm this ticket separately for ${money(flight.total)}. Seats are checked again at booking and are not reserved by joining.`)); content.append(steps);
    } else content.append(node('p', 'Your membership is active. No new membership fee is due.', 'fine-print'));
    content.append(node('p', 'Personal member fare. Baggage is not sold in this prototype. This screen does not promise a free checked bag.', 'fine-print'));
    if (activeMember()) $('checkout-submit').textContent = `Confirm booking · ${money(flight.total)}`;
    else {
      // Show the whole trip cost; the small line says what this click charges.
      $('checkout-submit').replaceChildren(node('span', `Membership + ticket total · ${money(Number(flight.total) + fee)}`, 'submit-main'), node('small', `Step 1 of 2: join the pass for ${money(fee)}, then confirm the ticket for ${money(flight.total)}`, 'submit-note'));
    }
  } else {
    content.append(node('h3', `${membershipTerm()} of member access`), node('p', 'A personal membership for published member fares. Each ticket is paid separately, including its mandatory fees.', 'checkout-date'));
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
      if (selected.type === 'flight') {
        const fresh = await api('/api/member-portal/flights');
        const current = fresh.flights.find(f => f.offer_id === selected.flight.offer_id);
        if (!current || Number(current.bookable_seats) < 1) throw new Error('This flight is no longer available. No new membership was purchased.');
        if (Number(current.total) !== Number(selected.flight.total)) throw new Error('The ticket price changed. Review the new total before joining.');
      }
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
        checkoutProgress('complete'); $('checkout-title').textContent = 'Your pass is active'; $('checkout-step').textContent = 'Membership confirmed';
        $('checkout-content').replaceChildren(node('p', money(recordedFee), 'booking-complete'), node('p', `Recorded membership fee. Your personal pass is valid until ${timestampLabel(state.account.membership.expires)}. Find a released flight when you are ready.`, 'checkout-date'));
        $('checkout-form').hidden = true; $('checkout-refresh').hidden = refreshed; checkoutMessage(refreshed ? 'No real payment was collected.' : 'Membership is confirmed. Account refresh failed; refresh before continuing. No real payment was collected.');
      }
    } else if (selected.type === 'flight') {
      const result = await api('/api/member-portal/book', { customer_id: customer, offer_id: selected.flight.offer_id, expected_total: Number(selected.flight.total) });
      if (!state.account.bookings.some((booking) => booking.id === result.booking.id)) state.account.bookings.push({ ...selected.flight, ...result.booking });
      renderAccount(); renderFlights();
      let refreshed = true;
      try { await loadData(); } catch { refreshed = false; state.refreshRequired = true; }
      checkoutProgress('complete'); $('checkout-step').textContent = 'Booking complete'; $('checkout-title').textContent = 'Your trip is saved';
      $('checkout-content').replaceChildren(node('p', `${selected.flight.origin} → ${selected.flight.destination}`, 'booking-complete'), node('p', `${dateLabel(selected.flight.departure_date)} · ${money(result.booking.total)}`, 'checkout-date'), node('p', `Booking reference ${result.booking.id}`, 'fine-print'));
      $('checkout-form').hidden = true; $('view-trips').hidden = false; $('checkout-refresh').hidden = refreshed; checkoutMessage(refreshed ? 'This is a simulated booking. No airline ticket has been issued.' : 'Your booking is confirmed. Account and availability refresh failed; refresh My trips to verify the saved record. Do not submit this booking again.');
      notice(`Your ${selected.flight.origin} to ${selected.flight.destination} trip is saved in My trips.`);
      if(refreshed) suggestReturn(selected.flight);
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
async function signOut() {
  if (state.busy) return;
  setBusy(true); clearNotices();
  try { await api('/api/member-portal/logout', {}); signInRequired(); }
  catch (error) { notice(error.message, true); setBusy(false); }
}
async function initializeAccount() {
  try {
    const session = await api('/api/member-portal/session');
    if (!session.authenticated || !session.user?.customer_id) { signInRequired(); return; }
    state.user = session.user; state.customerId = session.user.customer_id; state.account = session.account;
    await loadData();
    $('session-status').hidden = true; $('main-content').hidden = false;
  } catch (error) {
    if (state.user) {
      // Keep refresh and sign-out available if initial flight loading fails.
      $('session-status').hidden = true; $('main-content').hidden = false;
      return; // loadData already announces its own error.
    }
    $('session-status').replaceChildren(document.createTextNode('We could not check your account. '));
    const retry = node('button', 'Try again', 'text-button'); retry.type = 'button';
    retry.addEventListener('click', () => { $('session-status').textContent = 'Checking your account…'; initializeAccount(); });
    $('session-status').append(retry);
  }
}
$('flight-search').addEventListener('submit', (event) => {
  event.preventDefault();
  if (!validateDates()) { $('flight-search').reportValidity(); return; }
  state.filters = { origin: $('origin').value, destination: $('destination').value, from: $('departure-from').value, to: $('departure-to').value };
  renderFlights(); $('results-title').focus();
});
$('swap-airports').addEventListener('click',()=>{
  const origin=$('origin').value,destination=$('destination').value;
  setPlace('origin',destination);setPlace('destination',origin);
});
$('edit-search').addEventListener('click',()=>$('origin').focus());
for (const id of ['origin', 'destination']) $(id).addEventListener('change', () => renderAirportNote(id));
for (const id of ['departure-from', 'departure-to']) {
  $(id).addEventListener('input', () => {
    // Clear existing errors during editing; announce new errors only on exit/submit.
    for (const field of [$('departure-from'), $('departure-to')]) { field.setCustomValidity(''); field.removeAttribute('aria-invalid'); }
    $('search-date-error').hidden = true;
  });
  $(id).addEventListener('change', validateDates);
  $(id).addEventListener('blur', validateDates);
}
$('next-month').addEventListener('click', () => { const dates = nextMonthRange(); setDates(dates.from, dates.to); });
$('any-dates').addEventListener('click', () => setDates('', ''));
$('clear-search').addEventListener('click', clearSearch);
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
$('sign-out').addEventListener('click', signOut);
function renderNavigation() { const current = ['membership', 'trips'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'flights'; for (const link of document.querySelectorAll('.header nav a')) { if (link.hash === `#${current}`) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current'); } }
window.addEventListener('hashchange', renderNavigation);
// A page restored by Back must verify the current cookie rather than display
// another demo account's previously cached trips.
window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  $('main-content').hidden = true; $('session-status').hidden = false;
  $('session-status').textContent = 'Checking your account…';
  location.reload();
});
renderNavigation(); initializeAccount();

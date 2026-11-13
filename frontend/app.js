const $ = (id) => document.getElementById(id);
const state = { flights: [], flight: null, history: [], forecast: null, day: 28, candidates: [], best: null, loadedFlightId: null, request: 0, forecastRequest: 0, summary: null, offers: [] };
const number = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-HK', { maximumFractionDigits: digits });
const money = (value) => value === null || value === undefined ? '—' : `HK$${number(value)}`;
const percent = (value) => value === null || value === undefined ? '—' : `${number(Number(value) * 100, 1)}%`;
const value = (id) => Number($(id).value);
function text(id, content) { $(id).textContent = content; }
function clearError() { $('error').hidden = true; }
function error(message) { text('error', message); $('error').hidden = false; }
function notify(message) { text('notice', message); $('notice').hidden = false; }
function element(tag, content, className) { const el = document.createElement(tag); if (content !== undefined) el.textContent = content; if (className) el.className = className; return el; }
function list(id, rows) { $(id).replaceChildren(...rows.map((row) => element('li', typeof row === 'string' ? row : JSON.stringify(row)))); }
async function api(path, body, options = {}) {
  const response = await fetch(path, { ...options, method: body === undefined ? 'GET' : 'POST', headers: { 'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  let data; try { data = await response.json(); } catch { throw new Error(`The server returned an unreadable response (${response.status}).`); }
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : data.message || `Request failed (${response.status}).`);
  return data;
}
async function busy(button, callback) {
  clearError(); button.disabled = true; const previous = button.textContent; button.textContent = 'Working…';
  try { await callback(); } catch (e) { error(e.message); } finally { button.disabled = false; button.textContent = previous; }
}
function setView() {
  const name = ['flights', 'pricing', 'customers', 'members'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'flights';
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== `view-${name}`;
  for (const anchor of document.querySelectorAll('.primary-nav a')) { if (anchor.hash === `#${name}`) anchor.setAttribute('aria-current', 'page'); else anchor.removeAttribute('aria-current'); }
  document.title = `${({ flights: 'Flight decisions', pricing: 'Pricing lab', customers: 'Customer lab', members: 'Member experience' })[name]} — UOption Fly Pass`;
  const selected = document.querySelector('.primary-nav [aria-current=page]');
  if (selected) { const nav = selected.parentElement; if (selected.offsetLeft < nav.scrollLeft || selected.offsetLeft + selected.offsetWidth > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = Math.max(0, selected.offsetLeft - nav.offsetLeft - 20); }
  if (name === 'members') loadOffers();
}
window.addEventListener('hashchange', setView);
let resizeTimer; window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.forecast) renderForecast(); }, 120); });
$('go-pricing').addEventListener('click', () => { location.hash = 'pricing'; });

function svgNode(tag, attrs, content) { const el = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attrs || {}).forEach(([key, val]) => el.setAttribute(key, val)); if (content !== undefined) el.textContent = content; return el; }
function linePath(points, x, y) { return points.map((p, i) => `${i ? 'L' : 'M'}${x(p.day).toFixed(2)},${y(p.value).toFixed(2)}`).join(' '); }
function drawChart(id, observed, future, { maxY, yLabel, width = 720, height = 260, minDay = 28 } = {}) {
  const svg = $(id); width = Math.max(280, Math.round(svg.getBoundingClientRect().width) || width); svg.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const left = 44, right = 14, top = 24, bottom = 32;
  const upper = Math.max(1, maxY || 0, ...observed.map((p) => p.value), ...future.map((p) => p.high || p.value));
  const maxDay = Math.max(minDay, ...observed.map((p) => p.day));
  const x = (day) => left + (maxDay - day) / Math.max(1, maxDay) * (width - left - right);
  const y = (v) => top + (1 - v / upper) * (height - top - bottom);
  svg.append(svgNode('title', {}, `${yLabel}. Observations through day ${state.day}, with subsequent forecasts when available.`));
  for (let j = 0; j <= 4; j++) { const yy = upper * j / 4; svg.append(svgNode('line', { x1: left, x2: width - right, y1: y(yy), y2: y(yy), class: 'chart-grid' })); svg.append(svgNode('text', { x: left - 9, y: y(yy) + 4, 'text-anchor': 'end', class: 'chart-tick' }, number(yy))); }
  for (const day of [maxDay, maxDay / 2, 0]) svg.append(svgNode('text', { x: x(day), y: height - 8, 'text-anchor': day === 0 ? 'end' : day === maxDay ? 'start' : 'middle', class: 'chart-tick' }, day === 0 ? 'Sales cutoff' : `D${number(day)}`));
  if (future.length) { const band = [...future.map((p) => ({ day: p.day, value: p.high ?? p.value })), ...[...future].reverse().map((p) => ({ day: p.day, value: p.low ?? p.value }))]; svg.append(svgNode('path', { d: linePath(band, x, y) + ' Z', class: 'chart-band' })); svg.append(svgNode('path', { d: linePath(future, x, y), class: 'chart-forecast' })); }
  if (observed.length) svg.append(svgNode('path', { d: linePath(observed, x, y), class: 'chart-line' }));
  const last = observed.at(-1); if (last) svg.append(svgNode('circle', { cx: x(last.day), cy: y(last.value), r: 3.5, fill: '#002FA7' }));
  svg.append(svgNode('text', { x: left, y: 12, class: 'chart-tick' }, yLabel));
}

function invalidatePricing() { state.best = null; state.candidates = []; $('apply-policy').disabled = true; $('pricing-results').hidden = true; $('pricing-empty').hidden = false; }
async function loadFlight() {
  invalidatePricing();
  clearError(); const id = $('flight-select').value; if (!id) return;
  const request = ++state.request; state.forecastRequest++; state.forecast = null; state.loadedFlightId = null;
  $('flight-main').classList.add('loading'); $('publish-button').disabled = true;
  try {
    const data = await api(`/api/flights/${encodeURIComponent(id)}`);
    if (request !== state.request) return;
    state.flight = data.flight || state.flights.find((flight) => flight.flight_id === id);
    state.history = data.history || data.snapshots || []; state.loadedFlightId = id;
    const flight = state.flight;
    text('flight-date', (flight.departure_at || flight.departure_date || '').slice(0, 10));
    text('flight-capacity', `${number(flight.capacity || flight.sellable_capacity)} seats`);
    await loadForecast();
  } catch (e) { if (request === state.request) error(e.message); }
  finally { if (request === state.request) $('flight-main').classList.remove('loading'); }
}
async function loadForecast() {
  if (!state.loadedFlightId) return;
  const request = ++state.forecastRequest; const flightId = state.loadedFlightId; const day = state.day;
  $('flight-main').setAttribute('aria-busy', 'true'); $('flight-main').classList.add('loading'); $('publish-button').disabled = true;
  try {
    const data = await api('/api/forecast', { flight_id: flightId, days_to_departure: day });
    if (request !== state.forecastRequest || flightId !== state.loadedFlightId) return;
    state.forecast = data.forecast || data;
    renderForecast();
  } catch (e) { if (request === state.forecastRequest) { state.forecast = null; error(e.message); } }
  finally { if (request === state.forecastRequest) { $('flight-main').setAttribute('aria-busy', 'false'); $('flight-main').classList.remove('loading'); } }
}
function renderForecast() {
  const f = state.forecast; const history = state.history.filter((row) => Number(row.days_to_departure) >= state.day).sort((a, b) => b.days_to_departure - a.days_to_departure);
  const latest = history.at(-1) || {}; const capacity = Number(state.flight.capacity || latest.capacity || latest.sellable_capacity);
  const booked = Number(latest.booked_seats ?? latest.net_booked_seats ?? 0);
  text('booked-value', number(booked)); text('booked-detail', `${percent(booked / capacity)} of ${number(capacity)} seats`);
  text('demand-value', number(f.expected_remaining_demand, 1)); text('empty-value', number(f.expected_empty_seats, 1));
  text('empty-detail', `${percent(f.expected_empty_rate)} expected unsold`);
  text('protection-value', `${number(f.protection_p90)} seats`);
  text('chart-caption', `Predictive model bands; not a validated airline interval. Protection uses ${number(f.raw_protection_p90 ?? f.protection_p90)} model-percentile seats plus ${number(f.protection_allowance ?? 0)} allowance seats.`); text('release-value', `${number(f.releasable_seats)} seats`);
  text('beta-label', `β ${number(f.beta, 4)} / day · ${number(f.rate_now, 2)} requests / day`);
  const context = `${state.flight.origin || '—'} → ${state.flight.destination || '—'} · ${(state.flight.departure_at || '').slice(0, 10)} · D${state.day}`;
  text('pricing-context', `${context} · ${number(f.releasable_seats)} seats available for a new member allocation under this forecast.`);
  text('offer-flight-context', context);
  const qty = Math.max(0, Math.floor(Number(f.releasable_seats) || 0)); $('offer-quantity').max = qty; $('offer-quantity').value = Math.min(Math.max(1, value('offer-quantity')), qty) || 1;
  $('publish-button').disabled = qty < 1 || state.day === 0;
  list('forecast-notes', f.assumptions || ['Synthetic booking histories; normal demand forecasts depend on the selected intensity model.']);
  const past = history.filter((r) => r.days_to_departure <= 28).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.booked_seats ?? r.net_booked_seats) }));
  const future = (f.forecast_curve || []).map((r) => ({ day: Number(r.day ?? r.days_to_departure), value: Number(r.expected_booked), low: Number(r.p10), high: Number(r.p90) })).filter((r) => Number.isFinite(r.value) && r.day <= state.day).sort((a, b) => b.day - a.day);
  drawChart('booking-chart', past, future, { maxY: capacity, yLabel: 'Booked seats' });
  const prices = history.filter((r) => r.days_to_departure <= 180 && (r.normal_total_fare ?? r.total_payable) !== null && (r.normal_total_fare ?? r.total_payable) !== undefined).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.normal_total_fare ?? r.total_payable) }));
  drawChart('price-chart', prices, [], { yLabel: 'HKD', width: 620, height: 210, minDay: 180 });
  $('history-table').replaceChildren(...history.filter((r) => r.days_to_departure <= 28).reverse().map((r) => { const tr = element('tr'); [`D${r.days_to_departure}`, number(r.booked_seats ?? r.net_booked_seats), percent(r.empty_rate ?? r.empty_seat_rate), money(r.normal_total_fare ?? r.total_payable)].forEach((v) => tr.append(element('td', v))); return tr; }));
}
function chooseDay(day) {
  invalidatePricing();
  state.day = day; $('day-slider').value = 28 - day; $('day-slider').setAttribute('aria-valuetext', day ? `${day} days before departure` : 'Sales cutoff'); text('day-number', day); text('day-description', day ? 'Days before departure' : 'Sales cutoff · no new offers');
  document.querySelectorAll('[data-day]').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.day) === day)));
  state.best = null; $('apply-policy').disabled = true; loadForecast();
}
let dayTimer;
$('day-slider').addEventListener('input', () => { clearTimeout(dayTimer); const day = 28 - value('day-slider'); text('day-number', day); dayTimer = setTimeout(() => chooseDay(day), 150); });
document.querySelectorAll('[data-day]').forEach((button) => button.addEventListener('click', () => { clearTimeout(dayTimer); chooseDay(Number(button.dataset.day)); }));
$('flight-select').addEventListener('change', () => { state.best = null; $('apply-policy').disabled = true; loadFlight(); });

const candidateProfit = (c) => c.incremental_profit ?? c.incremental_contribution ?? c.mean_incremental_profit;
const fare = (c) => c.member_fare ?? c.base_fare ?? c.P;
const fee = (c) => c.membership_fee ?? c.V;
function renderPolicy(candidate) {
  const noOffer = candidate.decision === 'NO_OFFER';
  text('best-fare', noOffer ? 'No offer' : money(fare(candidate))); text('best-fee', noOffer ? '—' : money(fee(candidate))); text('best-profit', money(candidateProfit(candidate)));
  const details = [ ['Decision', noOffer ? 'Do not launch this offer' : 'Offer subject to inventory'], ['Earliest opening', candidate.open_day == null ? '—' : `D${candidate.open_day}`], ['Release share', percent(candidate.release_fraction)], ['Simulated members', number(candidate.members)], ['Member bookings', number(candidate.member_bookings)], ['Request fulfilment', percent(candidate.service_rate)], ['Feasible', candidate.feasible === false ? 'No' : 'Yes'] ];
  $('policy-detail').replaceChildren(...details.flatMap(([label, val]) => [element('dt', label), element('dd', val)]));
  $('apply-policy').textContent = candidate.open_day != null && candidate.open_day < state.day ? `Offer opens at D${candidate.open_day} — select that day first` : 'Prepare this member offer';
  $('apply-policy').disabled = (candidate.open_day != null && candidate.open_day < state.day) || value('term-days') !== 365 || noOffer || candidate.feasible === false || !state.forecast || state.day === 0 || state.forecast.releasable_seats < 1;
}
function renderPricing(data) {
  state.candidates = data.candidates || []; state.best = data.best || null;
  $('pricing-empty').hidden = true; $('pricing-results').hidden = false;
  text('term-label', `For ${number(data.config?.term_days ?? data.config?.membership_days ?? value('term-days'))} days; charged once`);
  if (state.best) renderPolicy(state.best);
  list('pricing-notes', data.assumptions || []);
  const h = data.holdout;
  text('holdout-detail', h ? `Independent seeds: ${money(h.incremental_profit)} incremental contribution; fulfilment ${percent(h.service_rate)}; ${h.feasible ? 'service constraints met' : 'service constraints not met'}. This result did not select the candidate.` : 'No independent validation result returned.');
  const ledger = state.best?.ledger || {};
  const labels = {membership_revenue:'Membership fees',member_ticket_revenue:'Member base fares',normal_ticket_revenue:'Normal base fares',ancillary_margin:'Ancillary margin',incremental_passenger_cost:'Passenger costs',membership_service_cost:'Member service costs',program_cost:'Programme costs',pass_through_fees_excluded:'Pass-through fees (excluded)'};
  $('ledger-detail').replaceChildren(...Object.entries(labels).filter(([key]) => ledger[key] != null).flatMap(([key,label]) => [element('dt',label),element('dd',money(ledger[key]))]));
  const comparisons = [['No membership',data.baseline],['Fixed offer',data.fixed_offer],['Selected policy',data.best],...(data.stress || []).map((r) => [r.scenario,r])].filter(([,r]) => r);
  $('stress-table').replaceChildren(...comparisons.map(([name,r]) => {const tr=element('tr');[name,money(r.incremental_profit),percent(r.service_rate),r.feasible ? 'Yes' : 'No'].forEach((v)=>tr.append(element('td',v)));return tr;}));
  const ranked = [...state.candidates].sort((a, b) => Number(candidateProfit(b)) - Number(candidateProfit(a)));
  $('candidate-table').replaceChildren(...ranked.slice(0, 40).map((c) => { const tr = element('tr'); [money(fare(c)), money(fee(c)), c.open_day == null ? '—' : `D${c.open_day}`, percent(c.release_fraction), money(candidateProfit(c)), c.feasible === false ? 'No' : 'Yes'].forEach((v) => tr.append(element('td', v))); return tr; }));
  const fares = [...new Set(state.candidates.map(fare).filter((v) => v != null))].sort((a, b) => a - b);
  const fees = [...new Set(state.candidates.map(fee).filter((v) => v != null))].sort((a, b) => a - b);
  const map = $('heatmap'); map.replaceChildren(); map.style.gridTemplateColumns = `70px repeat(${Math.max(1, fees.length)}, minmax(0, 1fr))`;
  map.append(element('span', 'P / V', 'label')); fees.forEach((v) => map.append(element('span', `$${v}`, 'label')));
  const maxAbs = Math.max(1, ...state.candidates.map((c) => Math.abs(Number(candidateProfit(c)) || 0)));
  fares.forEach((p) => { map.append(element('span', `$${p}`, 'label')); fees.forEach((v) => {
    const matching = ranked.filter((c) => fare(c) === p && fee(c) === v && c.feasible !== false); const c = matching[0];
    const button = element('button', c ? number(candidateProfit(c)) : 'Infeasible', 'cell'); button.type = 'button'; button.disabled = !c; button.setAttribute('aria-pressed', 'false');
    if (c) { const contribution = Number(candidateProfit(c)); const intensity = .06 + Math.min(1, Math.abs(contribution) / maxAbs) * .15; button.style.background = contribution >= 0 ? `rgba(0,47,167,${intensity})` : `rgba(23,25,30,${intensity})`; button.setAttribute('aria-label', `Base fare HK$${p}, membership HK$${v}, incremental contribution HK$${number(contribution)}`); button.addEventListener('click', () => { map.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', 'false')); button.setAttribute('aria-pressed', 'true'); text('heatmap-detail', `Fare ${money(p)} · membership ${money(v)} · opens D${c.open_day} · releases ${percent(c.release_fraction)} · contribution ${money(contribution)}.`); }); }
    map.append(button);
  }); });
}
$('optimize-form').addEventListener('input', () => { $('apply-policy').disabled = true; if (state.best) notify('Experiment settings changed. Run a new comparison before adopting a policy.'); });
$('optimize-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('optimize-button'), async () => {
  if (!state.loadedFlightId) throw new Error('Select a flight first.');
  const flightId = state.loadedFlightId, day = state.day;
  const settings = [value('term-days'),value('customer-count'),value('passenger-cost'),value('ancillary-margin')].join('|');
  const data = await api('/api/optimize', { flight_id: flightId, days_to_departure: day, config: { membership_days: value('term-days'), customers: value('customer-count'), incremental_cost: value('passenger-cost'), ancillary_margin: value('ancillary-margin'), seed: 117 } });
  if (settings !== [value('term-days'),value('customer-count'),value('passenger-cost'),value('ancillary-margin')].join('|')) throw new Error('Experiment settings changed while calculating. Run a new comparison.');
  if (flightId !== state.loadedFlightId || day !== state.day) throw new Error('The selected flight or date changed. Run a new comparison for the current selection.');
  renderPricing(data); notify(`Compared ${number(state.candidates.length)} candidate policies. Results are conditional on the simulation assumptions.`);
}); });
$('apply-policy').addEventListener('click', () => { if (!state.best || !state.forecast) return; $('offer-fare').value = fare(state.best); $('member-fee').value = fee(state.best); const max = Number(state.forecast.releasable_seats); $('offer-quantity').value = Math.max(1, Math.floor(max * Number(state.best.release_fraction || 1))); location.hash = 'members'; notify('The policy has been copied into the offer form. Review its quantity and price before publishing.'); });
$('export-candidates').addEventListener('click', () => {
  const keys = ['member_fare','membership_fee','open_day','release_fraction','incremental_profit','members','member_bookings','service_rate','feasible'];
  const escape = (v) => `"${String(v ?? '').replace(/^[=+@-]/, "'$&").replaceAll('"', '""')}"`;
  const csv = [keys.join(','), ...state.candidates.map((c) => keys.map((key) => escape(c[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = element('a'); a.href = url; a.download = 'uoption-candidate-policies.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

function renderAgents(data) {
  const results = data.results || []; const mode = data.mode || 'deterministic';
  text('agent-mode-message', `${mode === 'live' ? 'Live LLM' : 'Reproducible scenario model'} · ${number(results.length)} synthetic travellers. These decisions are not observed HK Express customer purchases.`);
  $('agent-results').replaceChildren(...results.map((row, index) => {
    const person = row.person || row.persona || row; const decision = row.decision || row; const booking = row.booking_decision;
    const card = element('article', undefined, 'customer-card');
    card.append(element('div', person.customer_id || `Synthetic customer ${index + 1}`, 'persona-number'));
    card.append(element('h2', person.segment_label || person.segment || person.purpose || 'Synthetic traveller'));
    const traits = [person.expected_trips && `${person.expected_trips} expected trips / term`, person.total_budget && `Budget ${money(person.total_budget)}`, person.budget_hkd && `Budget ${money(person.budget_hkd)}`, person.party_size && `${person.party_size} travellers`, person.flexibility && `Flexibility: ${person.flexibility}`].filter(Boolean);
    card.append(element('p', traits.join(' · '), 'traits'));
    card.append(element('p', String(decision.action || decision.choice || 'No action').replaceAll('_', ' '), 'action'));
    card.append(element('p', decision.reason || decision.explanation || 'No reason returned.'));
    if (booking) card.append(element('p', `Booking: ${String(booking.action || '').replaceAll('_',' ')}. ${booking.reason || ''}`, 'small'));
    card.append(element('p', `Source: ${row.source || data.source || mode}`, 'traits'));
    return card;
  }));
  if (!results.length) $('agent-results').append(element('p', 'No customer results returned.', 'empty-state'));
}
$('agent-mode').addEventListener('change', () => { const live = $('agent-mode').value === 'live'; $('agent-count').max = live ? 5 : 100; $('agent-count').value = Math.min(value('agent-count'), live ? 5 : 100); });
$('agent-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('agent-button'), async () => {
  const data = await api('/api/agents/run', { mode: $('agent-mode').value, count: value('agent-count'), member_fare: value('agent-fare'), membership_fee: value('agent-fee'), seed: 117 }); renderAgents(data);
}); });
async function loadPersonas() {
  try { const data = await api('/api/personas'); const segments = data.segments || []; $('coverage').replaceChildren(...segments.map((s) => element('span', `${s.name || s.label || s.id}${s.assumed_weight != null ? ` · ${percent(s.assumed_weight)} assumed` : ''}`))); }
  catch (e) { text('coverage', `Customer coverage could not be loaded: ${e.message}`); }
}

async function loadOffers() {
  try { const data = await api('/api/offers'); state.offers = data.offers || (Array.isArray(data) ? data : []); renderOffers(); } catch (e) { error(e.message); }
}
function renderOffers() {
  $('offers-list').replaceChildren(...state.offers.map((offer) => {
    const card = element('article', undefined, 'offer-card'); const knownFlight = state.flights.find((f) => f.flight_id === offer.flight_id) || {};
    const intro = element('div'); intro.append(element('h3', `${offer.origin || knownFlight.origin || '—'} → ${offer.destination || knownFlight.destination || '—'}`)); intro.append(element('p', (offer.departure_at || knownFlight.departure_at || '').slice(0, 10))); intro.append(element('p', offer.flight_id));
    const price = element('div'); price.append(element('div', money(offer.total_payable ?? (Number(offer.base_fare) + Number(offer.mandatory_fees ?? offer.fees ?? 0))), 'offer-price'));
    price.append(element('p', `${money(offer.base_fare)} base fare + ${money(offer.mandatory_fees ?? offer.fees ?? 0)} mandatory fees`));
    const inventory = element('div'); const remaining = offer.remaining ?? offer.remaining_seats ?? offer.available ?? offer.quantity;
    inventory.append(element('h3', `${number(remaining)} seats`)); inventory.append(element('p', 'Limited member inventory'));
    const button = element('button', Number(remaining) > 0 ? 'Reserve a seat' : 'Sold out', 'button primary'); button.type = 'button'; button.disabled = !(Number(remaining) > 0);
    button.addEventListener('click', () => busy(button, async () => { const result = await api('/api/bookings', { offer_id: offer.offer_id || offer.id, customer_id: $('customer-id').value }); const booking = result.booking || result; text('booking-result', `Simulated booking confirmed: ${booking.booking_id || booking.id || 'record saved'}. ${money(booking.total_payable ?? booking.total ?? offer.total_payable)} due for this flight. No payment was taken and no real ticket was issued.`); $('booking-result').hidden = false; await loadOffers(); }));
    card.append(intro, price, inventory, button); return card;
  }));
  if (!state.offers.length) $('offers-list').append(element('p', 'No member offers yet. Publish an offer from the selected flight above.', 'empty-state'));
}
$('offer-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('publish-button'), async () => {
  if (!state.loadedFlightId || !state.forecast) throw new Error('Load a valid flight forecast first.');
  if (value('offer-quantity') > Number(state.forecast.releasable_seats)) throw new Error('Requested seats exceed the current forecast release limit.');
  const data = await api('/api/offers', { flight_id: state.loadedFlightId, days_to_departure: state.day, quantity: value('offer-quantity'), base_fare: value('offer-fare') }); notify(`Member offer published: ${(data.offer || data).offer_id || (data.offer || data).id || 'saved'}.`); await loadOffers(); await loadForecast();
}); });
$('member-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('join-button'), async () => { const data = await api('/api/members', { customer_id: $('customer-id').value, membership_fee: value('member-fee') }); const member = data.member || data; text('membership-status', `Membership active for ${member.customer_id || $('customer-id').value}. ${money(member.membership_fee ?? member.fee ?? value('member-fee'))} recorded once in the simulation.`); notify('Simulated membership is ready. Choose an available flight below.'); }); });
$('refresh-offers').addEventListener('click', loadOffers);

async function init() {
  setView();
  try {
    const [summary, flightData] = await Promise.all([api('/api/summary'), api('/api/flights')]); state.summary = summary; state.flights = flightData.flights || flightData;
    text('dataset-label', `${number(summary.dataset?.rows ?? summary.rows)} daily snapshots · synthetic`);
    const configured = summary.llm?.live_configured || summary.llm?.configured || summary.llm?.live_available;
    if (configured) { $('live-mode-option').disabled = false; $('live-mode-option').textContent = 'Live LLM'; }
    $('flight-select').replaceChildren(...state.flights.map((flight) => { const option = element('option', `${flight.origin} → ${flight.destination} · ${(flight.departure_at || flight.departure_date || '').slice(0, 10)} · ${flight.flight_id}`); option.value = flight.flight_id; return option; }));
    $('flight-select').disabled = !state.flights.length;
    if (state.flights.length) await loadFlight(); else throw new Error('No flights available. Generate the simulation dataset and restart the backend.');
    loadPersonas();
    api('/api/evaluation').then((report) => { const result = report.overall || {}; text('validation-summary', `${number(result.flights)} synthetic evaluation flights. Demand MAE: ${number(result.demand_mae, 1)} requests; unsold-seat MAE: ${number(result.empty_seats_mae, 1)} seats. Raw model P90 coverage: ${percent(result.raw_p90_empirical_coverage ?? result.p90_empirical_coverage)}. Coverage after the ${number(report.protection_allowance)}-seat protection allowance: ${percent(result.p90_empirical_coverage)}. The allowance was calibrated for D28 only; neither figure guarantees future airline coverage.`); }).catch(() => text('validation-summary', 'Evaluation report is unavailable. No empirical coverage claim is shown.'));
  } catch (e) { error(`Unable to load the workspace. ${e.message}`); text('dataset-label', 'Dataset unavailable'); }
}
init();

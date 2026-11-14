const $ = (id) => document.getElementById(id);
const RELEASE_DAYS = [28, 14, 7];
const roundLabel = (days) => days?.length ? days.map((day) => `D${day}`).join(' / ') : 'No future rounds';
const state = { flights: [], flight: null, history: [], forecast: null, day: 28, candidates: [], best: null, loadedFlightId: null, request: 0, forecastRequest: 0, summary: null, offers: [], marketRun: null, marketReport: null, marketCases: [], marketRequest: 0, marketTimer: null, marketLoading: false, panelRun: null, panelData: null, panelTimer: null, panelRequest: 0, panelLoading: false, panelPage: 0, panelPerson: null, panelPersonRequest: 0, panelDetailStage: null, planDraft: false };
const number = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-HK', { maximumFractionDigits: digits });
const money = (value) => value === null || value === undefined ? '—' : `HK$${number(value, Number.isInteger(Number(value)) ? 0 : 2)}`;
const percent = (value) => value === null || value === undefined ? '—' : `${number(Number(value) * 100, 1)}%`;
const value = (id) => Number($(id).value);
function text(id, content) { $(id).textContent = content; }
function clearError() { $('error').hidden = true; }
function error(message) { text('error', message); $('error').hidden = false; }
function notify(message) { text('notice', message); $('notice').hidden = false; state.noticeView = location.hash.slice(1) || 'flights'; }
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
  try { await callback(); } catch (e) { error(e.message); } finally { button.disabled = button.id === 'publish-button' ? !canPublish() : false; button.textContent = previous; }
}
function setView() {
  const name = ['flights', 'pricing', 'customers', 'market', 'members'].includes(location.hash.slice(1)) ? location.hash.slice(1) : 'flights';
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== `view-${name}`;
  for (const anchor of document.querySelectorAll('.primary-nav a')) { if (anchor.hash === `#${name}`) anchor.setAttribute('aria-current', 'page'); else anchor.removeAttribute('aria-current'); }
  if (state.noticeView !== name) $('notice').hidden = true;
  document.title = `${({ flights: 'Flight decisions', pricing: 'Fast screening', customers: 'Customer panel', market: 'Test the market', members: 'Manage offers' })[name]} — UOption Fly Pass`;
  const selected = document.querySelector('.primary-nav [aria-current=page]');
  if (selected) { const nav = selected.parentElement; if (selected.offsetLeft < nav.scrollLeft || selected.offsetLeft + selected.offsetWidth > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = Math.max(0, selected.offsetLeft - nav.offsetLeft - 20); }
  if (name === 'members') { loadOffers(); loadMemberPlan(); }
  if (name === 'customers') { loadPanelRuns(); if (state.panelRun) pollPanel(); }
  if (name === 'market') loadMarketRuns();
}
window.addEventListener('hashchange', setView);
document.querySelector('.skip').addEventListener('click', (event) => { event.preventDefault(); document.querySelector('.view:not([hidden]) h1')?.focus(); });
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

function invalidatePricing() { state.best = null; state.candidates = []; $('apply-policy').disabled = true; $('send-market-candidate').disabled = true; $('pricing-results').hidden = true; $('pricing-empty').hidden = false; }
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
  renderReleaseStatus(f);
  text('beta-label', `β ${number(f.beta, 4)} / day · ${number(f.rate_now, 2)} requests / day`);
  const context = `${state.flight.origin || '—'} → ${state.flight.destination || '—'} · ${(state.flight.departure_at || '').slice(0, 10)} · D${state.day}`;
  text('pricing-context', `${context} · ${number(f.risk_release_ceiling ?? f.releasable_seats)} forecast risk ceiling · future release rounds: ${roundLabel(RELEASE_DAYS.filter((d) => d <= state.day))}.`);
  text('offer-flight-context', context);
  const qty = Math.max(0, Math.floor(Number(f.releasable_seats) || 0)); $('offer-quantity').max = qty; $('offer-quantity').value = Math.min(Math.max(1, value('offer-quantity')), qty) || 1;
  $('publish-button').disabled = !canPublish();
  list('forecast-notes', f.assumptions || ['Synthetic booking histories; normal demand forecasts depend on the selected intensity model.']);
  const past = history.filter((r) => r.days_to_departure <= 28).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.booked_seats ?? r.net_booked_seats) }));
  const future = (f.forecast_curve || []).map((r) => ({ day: Number(r.day ?? r.days_to_departure), value: Number(r.expected_booked), low: Number(r.p10), high: Number(r.p90) })).filter((r) => Number.isFinite(r.value) && r.day <= state.day).sort((a, b) => b.day - a.day);
  drawChart('booking-chart', past, future, { maxY: capacity, yLabel: 'Booked seats' });
  const prices = history.filter((r) => r.days_to_departure <= 180 && (r.normal_total_fare ?? r.total_payable) !== null && (r.normal_total_fare ?? r.total_payable) !== undefined).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.normal_total_fare ?? r.total_payable) }));
  drawChart('price-chart', prices, [], { yLabel: 'HKD', width: 620, height: 210, minDay: 180 });
  $('history-table').replaceChildren(...history.filter((r) => r.days_to_departure <= 28).reverse().map((r) => { const tr = element('tr'); [`D${r.days_to_departure}`, number(r.booked_seats ?? r.net_booked_seats), percent(r.empty_rate ?? r.empty_seat_rate), money(r.normal_total_fare ?? r.total_payable)].forEach((v) => tr.append(element('td', v))); return tr; }));
  if (state.offers.length) renderOffers();
}
function canPublish() {
  const f = state.forecast;
  return Boolean(f && state.loadedFlightId && RELEASE_DAYS.includes(state.day) && f.releasable_seats > 0 && !f.release_status?.round_already_issued && !f.release_status?.blocked_reason);
}
function releaseExplanation(f) {
  const r = f.release_status || {};
  if (r.blocked_reason) return String(r.blocked_reason).replaceAll('_', ' ');
  if (r.round_already_issued) return `D${state.day} has already been published. Each release round can be issued once.`;
  if (!RELEASE_DAYS.includes(state.day)) return r.next_release_day ? `Observation only at D${state.day}. Next release round: D${r.next_release_day}. Existing valid offers remain available.` : 'No future release rounds. Existing valid offers can sell until cutoff; no new seats are issued.';
  return `D${state.day} release round: subtract all earlier valid unsold quota before issuing additional seats. Publication closes this round.`;
}
function renderReleaseStatus(f) {
  const r = f.release_status || {};
  text('risk-release-value', `${number(r.safe_capacity ?? Math.max(0, Number(f.risk_release_ceiling ?? f.releasable_seats) - Number(r.member_sold || 0)))} seats`);
  text('member-sold-value', `${number(r.member_sold ?? 0)} seats`);
  text('prior-quota-value', `${number(r.previous_valid_unsold ?? r.prior_valid_unsold ?? 0)} seats`);
  text('active-quota-value', `${number(r.total_active_unsold ?? 0)} seats`);
  const explanation = releaseExplanation(f) + (r.currently_bookable == null ? '' : ` Currently bookable member seats: ${number(r.currently_bookable)}. Valid quota above the current safety capacity: ${number(r.protection_shortfall ?? 0)}.`);
  text('release-status', explanation); text('offer-release-status', explanation);
  const rows = r.round_history || [];
  $('demo-round-table').replaceChildren(...rows.map((row) => {
    const tr = element('tr'), th = element('th', `D${row.day}`); th.scope = 'row'; tr.append(th);
    for (const item of [number(row.quantity), number(row.sold), number(row.remaining), `${row.valid ? 'Valid' : 'Not active at this date'}${row.release_version && row.release_version !== 'three-round-release-v1' ? ' · historical rule' : ''}`]) tr.append(element('td', item));
    return tr;
  }));
  if (!rows.length) { const tr = element('tr'), td = element('td', 'No member quota has been published for this flight.'); td.colSpan = 5; tr.append(td); $('demo-round-table').append(tr); }
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
  $('send-market-candidate').disabled = noOffer || candidate.feasible === false || value('term-days') !== 365;
  text('best-fare', noOffer ? 'No offer' : money(fare(candidate))); text('best-fee', noOffer ? '—' : money(fee(candidate))); text('best-profit', money(candidateProfit(candidate)));
  const details = [ ['Decision', noOffer ? 'Do not launch this offer' : 'Offer subject to inventory'], ['Future release rounds', roundLabel(candidate.release_days || (candidate.open_day == null ? [] : [candidate.open_day]))], ['Release share', percent(candidate.release_fraction)], ['Simulated members', number(candidate.members)], ['Member bookings', number(candidate.member_bookings)], ['Request fulfilment', percent(candidate.service_rate)], ['Feasible', candidate.feasible === false ? 'No' : 'Yes'] ];
  $('policy-detail').replaceChildren(...details.flatMap(([label, val]) => [element('dt', label), element('dd', val)]));
  $('apply-policy').textContent = !RELEASE_DAYS.includes(state.day) ? 'Select a release day to prepare an offer' : 'Prepare this member offer';
  $('apply-policy').disabled = !RELEASE_DAYS.includes(state.day) || state.forecast?.release_status?.round_already_issued || Boolean(state.forecast?.release_status?.blocked_reason) || value('term-days') !== 365 || noOffer || candidate.feasible === false || !state.forecast || state.day === 0 || state.forecast.releasable_seats < 1;
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
  $('candidate-table').replaceChildren(...ranked.slice(0, 40).map((c) => { const tr = element('tr'); [money(fare(c)), money(fee(c)), roundLabel(c.release_days || (c.open_day == null ? [] : [c.open_day])), percent(c.release_fraction), money(candidateProfit(c)), c.feasible === false ? 'No' : 'Yes'].forEach((v) => tr.append(element('td', v))); return tr; }));
  const fares = [...new Set(state.candidates.map(fare).filter((v) => v != null))].sort((a, b) => a - b);
  const fees = [...new Set(state.candidates.map(fee).filter((v) => v != null))].sort((a, b) => a - b);
  const map = $('heatmap'); map.replaceChildren(); map.style.gridTemplateColumns = `70px repeat(${Math.max(1, fees.length)}, minmax(0, 1fr))`;
  map.append(element('span', 'P / V', 'label')); fees.forEach((v) => map.append(element('span', `$${v}`, 'label')));
  const maxAbs = Math.max(1, ...state.candidates.map((c) => Math.abs(Number(candidateProfit(c)) || 0)));
  fares.forEach((p) => { map.append(element('span', `$${p}`, 'label')); fees.forEach((v) => {
    const matching = ranked.filter((c) => fare(c) === p && fee(c) === v && c.feasible !== false); const c = matching[0];
    const button = element('button', c ? number(candidateProfit(c)) : 'Infeasible', 'cell'); button.type = 'button'; button.disabled = !c; button.setAttribute('aria-pressed', 'false');
    if (c) { const contribution = Number(candidateProfit(c)); const intensity = .06 + Math.min(1, Math.abs(contribution) / maxAbs) * .15; button.style.background = contribution >= 0 ? `rgba(0,47,167,${intensity})` : `rgba(23,25,30,${intensity})`; button.setAttribute('aria-label', `Base fare HK$${p}, membership HK$${v}, incremental contribution HK$${number(contribution)}`); button.addEventListener('click', () => { map.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', 'false')); button.setAttribute('aria-pressed', 'true'); text('heatmap-detail', `Fare ${money(p)} · membership ${money(v)} · rounds ${roundLabel(c.release_days)} · target share ${percent(c.release_fraction)} · contribution ${money(contribution)}.`); }); }
    map.append(button);
  }); });
}
$('optimize-form').addEventListener('input', () => { $('apply-policy').disabled = true; $('send-market-candidate').disabled = true; if (state.best) notify('Experiment settings changed. Run a new comparison before adopting a policy.'); });
$('optimize-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('optimize-button'), async () => {
  if (!state.loadedFlightId) throw new Error('Select a flight first.');
  const flightId = state.loadedFlightId, day = state.day;
  const settings = [value('term-days'),value('customer-count'),value('passenger-cost'),value('ancillary-margin')].join('|');
  const data = await api('/api/optimize', { flight_id: flightId, days_to_departure: day, config: { membership_days: value('term-days'), customers: value('customer-count'), incremental_cost: value('passenger-cost'), ancillary_margin: value('ancillary-margin'), seed: 117 } });
  if (settings !== [value('term-days'),value('customer-count'),value('passenger-cost'),value('ancillary-margin')].join('|')) throw new Error('Experiment settings changed while calculating. Run a new comparison.');
  if (flightId !== state.loadedFlightId || day !== state.day) throw new Error('The selected flight or date changed. Run a new comparison for the current selection.');
  renderPricing(data); notify(`Compared ${number(state.candidates.length)} candidate policies. Results are conditional on the simulation assumptions.`);
}); });
$('apply-policy').addEventListener('click', () => {
  if (!state.best || !state.forecast) return;
  const f = state.forecast, r = f.release_status || {};
  const safe = r.safe_capacity ?? Math.max(0, Number(f.risk_release_ceiling ?? f.releasable_seats) - Number(r.member_sold || 0));
  const target = Math.floor(safe * Number(state.best.release_fraction ?? 1));
  const quantity = Math.min(Number(f.releasable_seats), Math.max(0, target - Number(r.total_active_unsold || 0)));
  if (quantity < 1) { notify('Earlier valid quota already meets this policy target. No additional seats can be prepared.'); return; }
  $('offer-fare').value = fare(state.best); $('member-fee').value = fee(state.best); state.planDraft = true; $('offer-quantity').value = quantity;
  location.hash = 'members'; notify('New allocation and candidate prices copied. Publish seats and save the membership price separately when ready.');
});
$('export-candidates').addEventListener('click', () => {
  const keys = ['member_fare','membership_fee','release_days','release_fraction','incremental_profit','members','member_bookings','service_rate','feasible'];
  const escape = (v) => `"${String(v ?? '').replace(/^[=+@-]/, "'$&").replaceAll('"', '""')}"`;
  const csv = [keys.join(','), ...state.candidates.map((c) => keys.map((key) => escape(c[key])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' })); const a = element('a'); a.href = url; a.download = 'uoption-candidate-policies.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

// Large panels render a summary and one selected journey, never hundreds of
// full transcripts. Polling reads progress only; paid continuation is explicit.
const panelRunning = (status) => ['queued', 'running'].includes(status);
const panelCanResume = (status) => ['paused_at_budget', 'paused_after_errors', 'interrupted'].includes(status);
const panelAction = (action) => ({ JOIN_PASS: 'Joined', DECLINE: 'Declined', KEEP_MEMBERSHIP: 'Existing member', BUY_MEMBER: 'Member ticket', BUY_REGULAR: 'Regular ticket', WAIT: 'Waiting', KEEP_BOOKING: 'Booking kept', CANCEL_BOOKING: 'Cancelled', RENEW_INTENT: 'Would renew', DO_NOT_RENEW: 'Would not renew', CONSIDER_LATER: 'Consider later' })[action] || (action ? action.replaceAll('_', ' ').toLowerCase() : 'Pending');
const panelStatusLabel = (status) => ({ queued: 'Queued', running: 'Running', completed: 'Complete', paused_at_budget: 'Batch limit reached', paused_after_errors: 'Paused after an error', interrupted: 'Interrupted', failed: 'Unable to continue' })[status] || status || 'Not started';
function panelControls() {
  const live = $('agent-mode').value === 'live';
  $('agent-count').max = live ? 100 : 1000;
  $('agent-count').value = Math.min(value('agent-count'), live ? 100 : 1000);
  text('agent-count-hint', live ? 'Up to 100 synthetic travellers.' : 'Up to 1,000 synthetic travellers.');
  $('agent-budget-field').hidden = !live && state.panelData?.mode !== 'live';
  $('agent-call-budget').disabled = $('agent-budget-field').hidden;
  const running = panelRunning(state.panelData?.status);
  $('agent-button').disabled = running || state.panelLoading;
  $('agent-button').textContent = running ? 'Panel is running…' : state.panelLoading ? 'Starting…' : 'Run customer panel';
  $('panel-resume').disabled = running || state.panelLoading;
}
function renderPanel(data) {
  state.panelData = data;
  const rows = data.results || [], summary = data.summary || {}, progress = data.progress || {}, runtime = data.runtime || {};
  const total = Number(progress.total_customers ?? data.count ?? rows.length);
  const completed = Number(progress.completed_customers ?? summary.completed_customers ?? 0);
  const stages = Number(progress.completed_stages ?? 0), totalStages = Number(progress.total_stages ?? total * 6);
  $('panel-progress').hidden = false;
  $('panel-progress-bar').max = Math.max(1, totalStages); $('panel-progress-bar').value = stages;
  text('panel-progress-count', `${number(stages)} / ${number(totalStages)} stages`);
  text('panel-run-status', `${panelStatusLabel(data.status)} · ${number(completed)} of ${number(total)} travellers finished.${data.error ? ` ${data.error}` : ''}`);
  text('panel-call-counts', `${number(runtime.provider_calls || 0)} new provider requests · ${number(runtime.cache_hits || 0)} cached responses · ${number(runtime.forced_actions || 0)} forced actions · ${number(runtime.rule_decisions || 0)} rule decisions · ${number(runtime.failures || 0)} failed attempts`);
  $('panel-resume-controls').hidden = !panelCanResume(data.status);
  text('panel-pause-message', data.status === 'paused_at_budget' ? 'This batch used its decision allowance. Completed choices are saved. Continue only when you want to run the next batch.' : 'Saved choices are preserved. Review the error or interruption before continuing this panel.');
  $('panel-audit-link').hidden = !data.audit_run_id;
  if (data.audit_run_id) $('panel-audit-link').href = `/api/agents/runs/${encodeURIComponent(data.audit_run_id)}/export`;
  text('agent-mode-message', `${data.mode === 'live' ? 'Live LLM' : 'Rules'} · ${number(total)} synthetic travellers · ${money(data.member_fare)} member base fare + HK$250 mandatory fees · ${money(data.membership_fee)} pass fee. English explanations; independent one-trip scenarios.${panelRunning(data.status) || panelCanResume(data.status) ? ' Results below are partial.' : ''}`);
  $('panel-empty').hidden = rows.length > 0; $('panel-results').hidden = !rows.length; $('panel-overview').hidden = !rows.length;
  text('panel-overview-status', `${panelStatusLabel(data.status)} · ${number(total)} travellers · ${money(data.member_fare)} member base fare · ${money(data.membership_fee)} pass fee${data.status !== 'completed' ? ' · Results are still partial' : ''}`);
  const currentOption = [...$('panel-run-select').options].find((o) => o.value === data.run_id);
  if (currentOption) currentOption.textContent = `${data.mode === 'live' ? 'Live LLM' : 'Rules'} · ${number(total)} travellers · ${panelStatusLabel(data.status)} · ${data.run_id}`;
  text('panel-joined', number(summary.joined || 0));
  text('panel-joined-detail', `Of ${number(summary.eligible_decided || 0)} eligible travellers who have decided`);
  text('panel-booked', number(summary.booked || 0)); text('panel-cancelled', number(summary.cancelled || 0));
  text('panel-completed', number(completed)); text('panel-completed-detail', `Of ${number(total)} configured travellers`);
  renderPanelSegments(data.segments || []);
  renderPanelTable(); panelControls();
  if (!state.panelPerson && rows.length) selectPanelPerson(rows[0].person.customer_id, false);
  else if (state.panelPerson) {
    const row = rows.find((r) => r.person.customer_id === state.panelPerson);
    if (row && row.completed_stages !== state.panelDetailStage) selectPanelPerson(state.panelPerson, false);
  }
}
function renderPanelSegments(segments) {
  $('panel-segments').replaceChildren(...segments.map((segment) => {
    const card = element('div', undefined, 'segment-result');
    const label = element('div', undefined, 'segment-label');
    const outcome = segment.eligible_decided ? `${number(segment.joined || 0)} / ${number(segment.eligible_decided)}` : segment.eligible_new_members === 0 ? 'Existing members only' : 'Waiting for decisions';
    label.append(element('span', segment.segment_label || segment.segment), element('strong', outcome));
    const track = element('div', undefined, 'segment-track'); track.setAttribute('aria-hidden', 'true');
    const fill = element('div'); fill.style.width = `${Math.min(100, (segment.joined || 0) / Math.max(1, segment.eligible_decided || 0) * 100)}%`; track.append(fill);
    card.append(label, track, element('small', `${number(segment.booked || 0)} booked · ${number(segment.completed_customers || 0)} / ${number(segment.customers || 0)} finished`));
    return card;
  }));
}
function panelRows() {
  const query = $('panel-search').value.trim().toLowerCase(), filter = $('panel-decision-filter').value;
  return (state.panelData?.results || []).filter((r) => {
    const person = r.person || {}, action = r.decision?.action;
    return (!query || `${person.customer_id} ${person.segment_label} ${person.segment}`.toLowerCase().includes(query)) && (filter === 'all' || filter === 'pending' && !action || action === filter);
  });
}
function renderPanelTable() {
  const rows = panelRows(), pageSize = 20;
  state.panelPage = Math.min(state.panelPage, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
  const start = state.panelPage * pageSize, visible = rows.slice(start, start + pageSize);
  const focused = document.activeElement?.dataset?.panelPerson;
  $('panel-people').replaceChildren(...visible.map((row) => {
    const person = row.person, tr = element('tr');
    tr.classList.toggle('selected', person.customer_id === state.panelPerson);
    const name = element('th'); name.scope = 'row';
    const button = element('button', person.segment_label, 'person-row-button'); button.type = 'button'; button.dataset.panelPerson = person.customer_id;
    button.setAttribute('aria-label', `View journey for ${person.customer_id}, ${person.segment_label}`);
    button.setAttribute('aria-pressed', String(person.customer_id === state.panelPerson));
    button.addEventListener('click', () => selectPanelPerson(person.customer_id, true));
    name.append(button, element('small', person.customer_id)); tr.append(name);
    const stateAfter = row.final_state || {};
    for (const v of [money(person.total_budget), panelAction(row.decision?.action), stateAfter.booking_cancelled ? 'Cancelled after booking' : panelAction(row.booking_decision?.action), `${row.completed_stages || 0} / 6`]) tr.append(element('td', v));
    return tr;
  }));
  if (!visible.length) { const row = element('tr'); const cell = element('td', 'No travellers match these filters.'); cell.colSpan = 5; row.append(cell); $('panel-people').append(row); }
  if (focused) $('panel-people').querySelector(`[data-panel-person="${CSS.escape(focused)}"]`)?.focus({ preventScroll: true });
  text('panel-page-label', rows.length ? `${number(start + 1)}–${number(Math.min(start + pageSize, rows.length))} of ${number(rows.length)}` : '0 travellers');
  text('panel-result-note', `${number(rows.length)} matching travellers · select a row for details`);
  $('panel-prev').disabled = state.panelPage === 0; $('panel-next').disabled = start + pageSize >= rows.length;
}
async function selectPanelPerson(customerId, requested) {
  const runId = state.panelRun; if (!runId) return;
  state.panelPerson = customerId; renderPanelTable(); const request = ++state.panelPersonRequest;
  const region = $('panel-person-detail');
  if (requested) { region.replaceChildren(element('h2', 'Loading journey…')); }
  try {
    const data = await api(`/api/agents/panels/${encodeURIComponent(runId)}/people/${encodeURIComponent(customerId)}`);
    if (request !== state.panelPersonRequest || runId !== state.panelRun) return;
    state.panelDetailStage = data.completed_stages;
    const person = data.person || {}, title = element('h2', person.segment_label || 'Traveller journey'); title.id = 'panel-person-title'; title.tabIndex = -1;
    const info = element('p', `${person.customer_id} · ${person.party_size} ${person.party_size === 1 ? 'traveller' : 'travellers'} · ${person.expected_trips} expected trips / term`, 'small muted');
    const budget = element('div', undefined, 'person-budget'); budget.append(element('span', 'Trip + new fee budget'), element('strong', money(person.total_budget)));
    const steps = element('ol', undefined, 'panel-journey');
    const stages = ['subscription', 'quote_d28', 'quote_d14', 'quote_d7', 'plan_change', 'term_end'];
    const labels = ['Subscription', 'D28 quote', 'D14 quote', 'D7 quote', 'D3 plan change', 'Renewal intention'];
    for (let index = 0; index < stages.length; index++) {
      const event = (data.events || []).find((e) => (e.packet?.context?.stage || e.stage) === stages[index]);
      const item = element('li'); item.classList.toggle('pending', !event);
      item.append(element('span', String(index + 1).padStart(2, '0'), 'journey-step-number'));
      const content = element('div'); content.append(element('h3', labels[index]));
      if (event) {
        content.append(element('strong', panelAction(event.decision?.action), 'decision-label'), element('p', event.decision?.reason || 'No explanation returned.'));
        content.append(element('p', `Budget left ${money(event.state_after?.remaining_budget)} · Tickets paid ${money(event.state_after?.ticket_spend)} · Refunds ${money(event.state_after?.refund_received)}`, 'small muted'));
        content.append(element('p', `Source: ${event.source || data.source || state.panelData?.mode || 'unknown'}`, 'event-source'));
      } else content.append(element('p', 'Not reached yet.', 'small muted'));
      item.append(content); steps.append(item);
    }
    region.replaceChildren(title, info, budget);
    if (person.membership_active) region.append(element('p', 'Existing member: no new subscription fee is charged.', 'small'));
    region.append(steps);
    if (requested && matchMedia('(max-width: 900px)').matches) { region.scrollIntoView({ block: 'start' }); title.focus({ preventScroll: true }); }
  } catch (e) { if (request === state.panelPersonRequest) region.replaceChildren(element('h2', 'Journey unavailable'), element('p', e.message, 'small')); }
}
async function pollPanel() {
  const runId = state.panelRun; if (!runId) return;
  clearTimeout(state.panelTimer); const request = ++state.panelRequest;
  try {
    const data = await api(`/api/agents/panels/${encodeURIComponent(runId)}`);
    if (request !== state.panelRequest || runId !== state.panelRun) return;
    renderPanel(data);
    if (panelRunning(data.status)) state.panelTimer = setTimeout(() => { if (!document.hidden) pollPanel(); }, 2000);
  } catch (e) { if (request === state.panelRequest) { text('panel-run-status', `Progress could not be loaded: ${e.message}. Refresh to reconnect; saved work is not discarded.`); state.panelTimer = null; } }
}
function selectPanelRun(runId) {
  clearTimeout(state.panelTimer); state.panelRequest++; state.panelPersonRequest++;
  state.panelRun = runId || null; state.panelPerson = null; state.panelDetailStage = null; state.panelPage = 0; state.panelData = null;
  $('panel-search').value = ''; $('panel-decision-filter').value = 'all';
  $('panel-person-detail').replaceChildren(element('h2', 'Select a traveller'), element('p', 'Their journey will appear here.', 'small muted'));
  if (runId) pollPanel(); else { $('panel-progress').hidden = true; $('panel-results').hidden = true; $('panel-overview').hidden = true; $('panel-empty').hidden = false; panelControls(); }
}
async function loadPanelRuns() {
  try {
    const data = await api('/api/agents/panels'); const runs = data.runs || [];
    const select = $('panel-run-select'); const current = state.panelRun;
    select.replaceChildren(element('option', 'Start a panel or select a saved run'));
    select.firstElementChild.value = '';
    for (const run of runs) { const option = element('option', `${run.mode === 'live' ? 'Live LLM' : 'Rules'} · ${number(run.count)} travellers · ${panelStatusLabel(run.status)} · ${run.run_id}`); option.value = run.run_id; select.append(option); }
    if (current && runs.some((r) => r.run_id === current)) select.value = current;
  } catch (e) { text('panel-run-status', `Saved panels could not be loaded: ${e.message}`); }
}
async function loadAgentRuns() {
  try {
    const data = await api('/api/agents/runs');
    $('agent-runs').replaceChildren(...data.runs.slice(0, 20).map((run) => {
      const item = element('li'); const link = element('a', `${run.run_id} · ${run.source} · ${run.status} · ${number(run.event_records)} records`, 'text-link');
      link.href = `/api/agents/runs/${encodeURIComponent(run.run_id)}/export`; item.append(link); return item;
    }));
    if (!data.runs.length) $('agent-runs').append(element('li', 'No saved runs yet.'));
  } catch (e) { text('agent-runs', `Saved records unavailable: ${e.message}`); }
}
$('refresh-agent-runs').addEventListener('click', loadAgentRuns);
$('agent-mode').addEventListener('change', panelControls);
$('agent-form').addEventListener('submit', async (event) => {
  event.preventDefault(); clearError(); state.panelLoading = true; panelControls();
  try {
    const data = await api('/api/agents/panels', { mode: $('agent-mode').value, count: value('agent-count'), member_fare: value('agent-fare'), membership_fee: value('agent-fee'), seed: 117, max_calls: $('agent-mode').value === 'live' ? value('agent-call-budget') : 0 });
    selectPanelRun(data.run_id); await loadPanelRuns();
  } catch (e) { error(e.message); }
  finally { state.panelLoading = false; panelControls(); }
});
$('panel-resume').addEventListener('click', async () => {
  if (!state.panelRun || !panelCanResume(state.panelData?.status) || !$('agent-call-budget').reportValidity()) return;
  const runId = state.panelRun; state.panelLoading = true; panelControls(); clearError();
  try { await api(`/api/agents/panels/${encodeURIComponent(runId)}/resume`, { max_calls: state.panelData?.mode === 'live' ? value('agent-call-budget') : 0 }); await pollPanel(); }
  catch (e) { error(e.message); }
  finally { state.panelLoading = false; panelControls(); }
});
$('panel-refresh').addEventListener('click', () => { loadPanelRuns(); if (state.panelRun) pollPanel(); });
$('panel-run-select').addEventListener('change', () => selectPanelRun($('panel-run-select').value));
for (const id of ['panel-search', 'panel-decision-filter']) $(id).addEventListener(id === 'panel-search' ? 'input' : 'change', () => { state.panelPage = 0; renderPanelTable(); });
$('panel-prev').addEventListener('click', () => { state.panelPage--; renderPanelTable(); });
$('panel-next').addEventListener('click', () => { state.panelPage++; renderPanelTable(); });
document.addEventListener('visibilitychange', () => { if (!document.hidden && state.panelRun && panelRunning(state.panelData?.status)) pollPanel(); });
panelControls();
async function loadPersonas() {
  try { const data = await api('/api/personas'); const segments = data.segments || []; $('coverage').replaceChildren(...segments.map((s) => element('span', `${s.name || s.label || s.id}${s.assumed_weight != null ? ` · ${percent(s.assumed_weight)} assumed` : ''}`))); }
  catch (e) { text('coverage', `Customer coverage could not be loaded: ${e.message}`); }
}

// A run is a bounded background batch. Polling only reads saved progress;
// further provider calls require an explicit start/resume submission.
const marketIsRunning = (status) => ['queued', 'running'].includes(status);
const marketLabel = (policy) => policy?.name === 'NO_OFFER' ? 'No membership offer' : policy?.name === 'FIXED' ? 'Fixed offer' : policy?.name === 'CANDIDATE' ? 'Candidate' : policy?.name || 'Policy';
const marketFields = { membership_revenue: 'Membership fees', member_base_revenue: 'Member base fares', normal_base_revenue: 'Normal base fares', ancillary_revenue: 'Ancillary revenue', cancellation_revenue: 'Cancellation service revenue', passenger_cost: 'Passenger costs', ancillary_cost: 'Ancillary costs', membership_service_cost: 'Member service costs', program_cost: 'Programme costs', refunds_paid: 'Refunds paid', mandatory_liability: 'Mandatory fees awaiting remittance', mandatory_remitted: 'Mandatory fees remitted', revenue_excluding_mandatory_fees: 'Revenue excluding mandatory fees', total_variable_cost: 'Variable costs', total_cost: 'Total costs in this comparison', contribution: 'Contribution' };
function marketControlState() {
  const running = marketIsRunning(state.marketStatus);
  $('market-start').disabled = running || state.marketLoading;
  $('market-resume').disabled = running || state.marketLoading;
  $('market-start').textContent = running ? 'Batch is running…' : state.marketLoading ? 'Starting…' : 'Start shared-market run';
  $('market-call-budget').disabled = $('market-mode').value !== 'live' && !state.marketRun;
}
function marketOptions(id, rows, preferred) {
  const select = $(id); select.replaceChildren(...rows.map(([key, label]) => { const option = element('option', label); option.value = key; return option; }));
  if (rows.some(([key]) => key === preferred)) select.value = preferred;
  select.disabled = !rows.length;
}
async function loadMarketRuns() {
  try {
    const data = await api('/api/market/runs');
    const rows = (data.runs || []).map((run) => [run.run_id, `${run.run_id} · ${String(run.status).replaceAll('_', ' ')} · ${number(run.completed_cases)}/${number(run.cases)} policies complete`]);
    marketOptions('market-run-select', [['', 'Select a saved market run'], ...rows], state.marketRun || '');
  } catch (e) { if (!state.marketRun) text('market-run-status', `Saved market runs unavailable: ${e.message}`); }
}
function selectMarketRun(runId) {
  clearTimeout(state.marketTimer); state.marketRequest++; state.marketRun = runId || null; state.marketReport = null; state.marketCases = []; state.marketStatus = null; state.marketCase = null;
  $('market-report').hidden = true; $('market-resume-controls').hidden = true;
  if (!runId) { text('market-run-status', 'Start a new run or select a saved experiment.'); marketControlState(); return; }
  text('market-run-status', `Loading ${runId}…`);
  loadMarketRun(runId, state.marketRequest);
}
async function loadMarketRun(runId, request) {
  try {
    const result = await api(`/api/market/runs/${encodeURIComponent(runId)}`);
    if (request !== state.marketRequest || runId !== state.marketRun) return;
    state.marketStatus = result.status;
    const report = result.report;
    text('market-run-status', `${runId} · ${String(result.status || 'recorded').replaceAll('_', ' ')}${report ? ` · ${number(report.completed_cases)}/${number(report.cases)} policy worlds complete` : ''}${result.error ? ` · ${result.error}` : ''}`);
    const paused = ['paused_at_budget', 'paused_after_errors', 'interrupted'].includes(result.status);
    $('market-resume-controls').hidden = !paused;
    text('market-pause-reason', result.status === 'paused_after_errors' ? 'A provider or validation error paused this run. Accepted events are saved; no fallback decisions were inserted. Resume explicitly to retry.' : 'This run has stopped at its checkpoint. Accepted events are saved. Resume explicitly to allow the next bounded batch.');
    if (report) renderMarketReport(report, runId);
    marketControlState();
    if (marketIsRunning(result.status)) state.marketTimer = setTimeout(() => loadMarketRun(runId, request), 1800);
    else loadMarketRuns();
  } catch (e) {
    if (request !== state.marketRequest) return;
    text('market-run-status', `Unable to read this run: ${e.message} Select the saved run again to retry; no further calls were requested.`);
    state.marketStatus = 'read_failed'; marketControlState();
  }
}
function renderMarketReport(report, runId) {
  state.marketReport = report; $('market-report').hidden = false;
  $('market-report-link').href = `/api/market/runs/${encodeURIComponent(runId)}`;
  $('market-audit-link').href = report.run_id ? `/api/agents/runs/${encodeURIComponent(report.run_id)}/export` : '/api/agents/runs';
  const runtime = report.runtime || {};
  const decisions = [runtime.environment_forced, runtime.deterministic_choices, runtime.validated_live_choices];
  const recorded = decisions.every((x) => Number.isFinite(x)) ? decisions.reduce((a, b) => a + b, 0) : (report.case_results || []).reduce((n, row) => n + (row.metrics?.decision_count || 0), 0);
  text('market-event-count', number(recorded));
  text('market-event-detail', `${number(report.completed_cases)}/${number(report.cases)} policy worlds completed`);
  text('market-call-count', number(runtime.provider_calls));
  text('market-call-detail', `${number(runtime.cache_hits)} cache hits · ${number(runtime.failures)} failures`);
  text('market-source-counts', `Run-wide provenance: ${number(runtime.deterministic_choices)} deterministic choices · ${number(runtime.validated_live_choices)} validated live choices (including ${number(runtime.cache_hits)} cached responses) · ${number(runtime.environment_forced)} environment-forced actions. Forced actions are not model choices.`);
  const cases = report.case_results || [];
  const currentRule = cases.length && cases.every((row) => row.policy?.release_days?.join(',') === RELEASE_DAYS.join(','));
  text('market-rule-note', currentRule ? 'Current rule: D28 / D14 / D7. Each round adds only the shortfall after all prior valid unsold quota.' : 'Historical or unversioned experiment: its original release rules are preserved. These results are not evidence for the current three-round rule.');
  state.marketCases = cases;
  const pairs = new Map((report.paired_differences || []).map((pair) => [pair.case_id, pair]));
  const groupKey = (row) => JSON.stringify([row.mode, row.split || 'development', typeof row.policy === 'string' ? row.policy : row.policy?.name]);
  const aggregates = new Map((report.aggregate || []).map((group) => [groupKey(group), group]));
  const groups = new Map();
  for (const row of cases) { const key = groupKey(row); if (!groups.has(key)) groups.set(key, []); groups.get(key).push(row); }
  const comparisons = [...groups.entries()].map(([key, rows]) => {
    const first = rows[0], completeRows = rows.filter((row) => row.completed), metrics = aggregates.get(key)?.mean_metrics || (rows.length === 1 ? first.metrics || {} : {});
    const deltas = rows.filter((row) => row.completed).map((row) => row.policy?.enabled === false ? 0 : pairs.get(row.case_id)?.metric_differences?.contribution).filter((delta) => Number.isFinite(delta));
    return { first, rows, metrics, completed: completeRows.length, delta: deltas.length === rows.length ? deltas.reduce((a, b) => a + b, 0) / deltas.length : null };
  });
  const completed = report.cases > 0 && report.completed_cases === report.cases;
  const contexts = new Set(comparisons.map((group) => JSON.stringify([group.first.mode, group.first.split || 'development'])));
  const ranked = comparisons.filter((group) => Number.isFinite(group.delta)).sort((a, b) => b.delta - a.delta);
  const singleContext = contexts.size === 1;
  text('market-best-profit', completed && ranked.length ? singleContext ? money(ranked[0].delta) : 'By cohort' : 'Pending');
  const leaders = ranked.length ? [...new Set(ranked.filter((item) => Math.abs(item.delta - ranked[0].delta) < .005).map((item) => marketLabel(item.first.policy)))] : [];
  text('market-best-label', completed && ranked.length ? singleContext ? `${leaders.join(' / ')}${leaders.length > 1 ? ' (tied)' : ''} · mean across matched seeds` : 'Compare policies within each mode and split below' : 'All policies must finish before ranking');
  text('market-comparison-note', completed ? 'Each policy is paired with the no-offer world at the same seed and decision mode. Values are means across completed seeds; different modes and development/validation splits remain separate. These simulator results do not establish an optimal real-market price.' : 'This run is incomplete. Partial ledger values are progress only; ranking is withheld until all compared worlds finish. The table groups policies by decision mode and development/validation split.');
  $('market-policy-table').replaceChildren(...comparisons.map((group) => {
    const { first: row, metrics: m, delta } = group;
    const tr = element('tr'), digits = group.rows.length > 1 ? 1 : 0;
    const nameCell = element('td'); nameCell.append(element('strong', marketLabel(row.policy)));
    nameCell.append(element('div', row.policy?.enabled === false ? 'Normal sales only' : `${money(row.policy?.member_fare)} + ${money(row.policy?.membership_fee)} membership · ${row.policy?.release_days ? roundLabel(row.policy.release_days) : `historical opening D${row.policy?.open_day}`} · ${percent(row.policy?.release_fraction)} target share`, 'market-policy-status'));
    nameCell.append(element('div', `${number(group.rows.length)} seed${group.rows.length > 1 ? 's' : ''} · ${row.mode} · ${row.split || 'development'}`, 'market-policy-status')); tr.append(nameCell);
    for (const item of [`${number(group.completed)}/${number(group.rows.length)} complete`, number(m.members, digits), number(m.member_flown, digits), number(m.normal_seats_flown, digits), money(m.contribution), money(delta)]) tr.append(element('td', item));
    return tr;
  }));
  if (!cases.length) { const tr = element('tr'), td = element('td', 'The first checkpoint is being prepared.'); td.colSpan = 7; tr.append(td); $('market-policy-table').append(tr); }
  const selected = $('market-policy-select').value;
  marketOptions('market-policy-select', cases.map((row) => [row.case_id, `${marketLabel(row.policy)} · seed ${number(row.seed)} · ${row.mode}`]), selected);
  list('market-assumptions', report.limitations || []);
  // Keep the inspected traveller stable while periodic progress reads complete.
  if (cases.length && (state.marketCaseId !== $('market-policy-select').value || !state.marketCase || !marketIsRunning(state.marketStatus))) loadMarketCase();
}
async function loadMarketCase() {
  const runId = state.marketRun, caseId = $('market-policy-select').value;
  if (!runId || !caseId) return;
  const request = (state.marketCaseRequest || 0) + 1; state.marketCaseRequest = request; state.marketCaseId = caseId;
  $('market-detail-grid')?.setAttribute('aria-busy', 'true');
  try {
    const data = await api(`/api/market/runs/${encodeURIComponent(runId)}/cases/${encodeURIComponent(caseId)}`);
    if (request !== state.marketCaseRequest || runId !== state.marketRun || caseId !== $('market-policy-select').value) return;
    const inspection = data.inspection;
    const world = inspection ? { day: inspection.day, records: inspection.events || [], customers: Object.fromEntries((inspection.customers || []).map((customer) => [customer.customer_id, { ...customer, budget_cents: customer.remaining_budget * 100, membership_expires: customer.membership_expires_day }])) } : data.state;
    if (!world) throw new Error('This saved policy has no inspection state.');
    state.marketCase = world;
    const current = state.marketCases.find((row) => row.case_id === caseId);
    const metrics = inspection?.metrics || current?.metrics;
    const ledger = metrics?.ledger || Object.fromEntries(Object.entries(world.ledger_cents || {}).map(([key, cents]) => [key, cents / 100]));
    list('market-assumptions', [...new Set([...(state.marketReport?.limitations || []), ...(metrics?.assumptions || [])])]);
    $('market-ledger').replaceChildren(...Object.entries(marketFields).filter(([key]) => ledger[key] != null).flatMap(([key, label]) => [element('dt', label), element('dd', money(ledger[key]))]));
    const flights = inspection?.flights || Object.values(world.flights || {}), bookings = Object.values(world.bookings || {});
    $('market-flight-table').replaceChildren(...flights.map((flight) => {
      const matching = bookings.filter((booking) => booking.flight_id === flight.flight_id && booking.status !== 'cancelled');
      const member = inspection ? flight.member_seats : matching.reduce((n, booking) => n + (booking.member_seats || 0), 0);
      const normal = inspection ? flight.occupied - flight.legacy_seats - member : matching.reduce((n, booking) => n + (booking.normal_seats || 0), 0);
      const tr = element('tr');
      for (const item of [`${flight.flight_id} · ${flight.destination}`, number(flight.legacy_seats), number(normal), number(member), number(flight.capacity - flight.occupied)]) tr.append(element('td', item));
      return tr;
    }));
    renderMarketRounds(flights, metrics?.version);
    const selectedPerson = $('market-person-select').value;
    marketOptions('market-person-select', Object.entries(world.customers || {}).map(([id, customer]) => [id, `${id} · ${customer.person?.segment_label || customer.person?.segment || 'Synthetic traveller'}`]), selectedPerson);
    renderMarketJourney();
  } catch (e) { if (request === state.marketCaseRequest) { state.marketCase = null; text('market-ledger', `Unable to load this policy: ${e.message}`); $('market-flight-table').replaceChildren(); $('market-round-table').replaceChildren(); $('market-journey-events').replaceChildren(); } }
  finally { if (request === state.marketCaseRequest) $('market-detail-grid')?.setAttribute('aria-busy', 'false'); }
}
function renderMarketRounds(flights, version) {
  const rows = flights.flatMap((flight) => (flight.quota_history || []).map((round) => ({ ...round, flight_id: flight.flight_id })));
  const currentRule = version === 'shared-market-v3' || (rows.length && rows.every((row) => row.policy_rule_version === 'three-round-release-v1'));
  text('market-round-note', currentRule ? 'Target = floor(unprotected physical seats × share). New seats = max(0, target − earlier valid unsold quota). Prior quota remains recorded; actual sales still respect protection and capacity.' : 'Historical experiment: earlier versions did not record additive round cohorts. Missing carry and new-allocation values are shown as unavailable, not reconstructed.');
  $('market-round-table').replaceChildren(...rows.map((row) => {
    const tr = element('tr'), th = element('th', `${row.flight_id} · D${row.days_to_departure}`); th.scope = 'row'; tr.append(th);
    for (const val of [row.target_quota, row.prior_valid_unsold, row.new_allocation, row.remaining_quota, row.protection_shortfall]) tr.append(element('td', number(val)));
    return tr;
  }));
  if (!rows.length) { const tr = element('tr'), td = element('td', 'No release-round records are available at this checkpoint.'); td.colSpan = 6; tr.append(td); $('market-round-table').append(tr); }
}
function renderMarketJourney() {
  const world = state.marketCase, personId = $('market-person-select').value, customer = world?.customers?.[personId];
  if (!customer) { text('market-person-state', 'No traveller selected'); return; }
  const membership = customer.membership_expires == null ? 'No membership' : customer.membership_expires >= world.day ? 'Membership active' : 'Membership expired';
  text('market-person-state', `${membership} · ${money(customer.budget_cents / 100)} budget left · ${money(customer.membership_fee_paid ?? (customer.membership_fee_cents == null ? null : customer.membership_fee_cents / 100))} membership paid${customer.renewal_intention ? ` · ${String(customer.renewal_intention).replaceAll('_', ' ')} (not charged)` : ''}`);
  const records = (world.records || []).filter((record) => record.customer_id === personId);
  $('market-journey-events').replaceChildren(...records.map((record) => {
    const item = element('li');
    const provenance = record.source ? record : (state.marketReport?.decision_sources || {})[record.packet_id];
    item.append(element('p', provenance ? `${provenance.source}${provenance.cache_hit ? ' · cached response' : ''}` : 'Accepted environment record', 'event-source'));
    item.append(element('strong', `Day ${number(record.day, 1)} · ${String(record.stage || '').replaceAll('_', ' ')}`));
    item.append(element('p', String(record.action || '').replaceAll('_', ' ')));
    if (record.reason) item.append(element('p', record.reason));
    const deltas = Object.entries(record.financial_delta || {}).filter(([, amount]) => Number(amount) !== 0).map(([key, amount]) => `${marketFields[key] || key.replaceAll('_', ' ')} ${money(amount)}`);
    item.append(element('p', `${money(record.remaining_budget)} budget left${deltas.length ? ` · ${deltas.join(' · ')}` : ' · No financial posting'}`, 'event-state'));
    return item;
  }));
  if (!records.length) $('market-journey-events').append(element('li', 'No decisions recorded for this traveller at the current checkpoint.'));
}
$('market-form').addEventListener('submit', async (event) => {
  event.preventDefault(); clearError(); state.marketLoading = true; marketControlState();
  try {
    const data = await api('/api/market/runs', { mode: $('market-mode').value, seed: value('market-seed'), member_fare: value('market-fare'), membership_fee: value('market-fee'), release_fraction: value('market-release'), max_calls: $('market-mode').value === 'live' ? value('market-call-budget') : 0 });
    selectMarketRun(data.run_id); state.marketStatus = data.status; await loadMarketRuns();
  } catch (e) { error(e.message); }
  finally { state.marketLoading = false; marketControlState(); }
});
$('market-resume').addEventListener('click', async () => {
  if (!state.marketRun || !['paused_at_budget', 'paused_after_errors', 'interrupted'].includes(state.marketStatus)) return;
  if (!$('market-call-budget').reportValidity()) return;
  clearError(); const id = state.marketRun; state.marketLoading = true; marketControlState();
  try { const data = await api(`/api/market/runs/${encodeURIComponent(id)}/resume`, { max_calls: value('market-call-budget') }); if (id === state.marketRun) { selectMarketRun(id); state.marketStatus = data.status; } }
  catch (e) { error(e.message); }
  finally { state.marketLoading = false; marketControlState(); }
});
$('market-refresh').addEventListener('click', () => { loadMarketRuns(); if (state.marketRun) selectMarketRun(state.marketRun); });
$('market-run-select').addEventListener('change', () => selectMarketRun($('market-run-select').value));
$('market-policy-select').addEventListener('change', loadMarketCase);
$('market-person-select').addEventListener('change', renderMarketJourney);
$('market-mode').addEventListener('change', marketControlState);
$('send-market-candidate').addEventListener('click', () => {
  const best = state.best; if (!best || best.decision === 'NO_OFFER') return;
  $('market-fare').value = fare(best); $('market-fee').value = fee(best);
  $('market-release').value = best.release_fraction;
  text('market-candidate-origin', `Candidate copied from fast screening: ${money(fare(best))} base fare, ${money(fee(best))} membership, target share ${percent(best.release_fraction)}. This transfers a price/share hypothesis into a new full-term world with all D28 / D14 / D7 rounds; it does not copy this flight's previous allocations.`);
  location.hash = 'market';
});
marketControlState();

async function loadOffers() {
  try { const data = await api('/api/offers'); state.offers = data.offers || (Array.isArray(data) ? data : []); renderOffers(); } catch (e) { error(e.message); }
}
function renderOffers() {
  $('offers-list').replaceChildren(...state.offers.map((offer) => {
    const card = element('article', undefined, 'offer-card'); card.dataset.offerId = offer.offer_id || offer.id; const knownFlight = state.flights.find((f) => f.flight_id === offer.flight_id) || {};
    const intro = element('div'); intro.append(element('h3', `${offer.origin || knownFlight.origin || '—'} → ${offer.destination || knownFlight.destination || '—'}`)); intro.append(element('p', (offer.departure_at || knownFlight.departure_at || '').slice(0, 10))); intro.append(element('p', offer.flight_id));
    const price = element('div'); price.append(element('div', money(offer.total_payable ?? (Number(offer.base_fare) + Number(offer.mandatory_fees ?? offer.fees ?? 0))), 'offer-price'));
    price.append(element('p', `${money(offer.base_fare)} base fare + ${money(offer.mandatory_fees ?? offer.fees ?? 0)} mandatory fees`));
    const inventory = element('div'); const remaining = offer.remaining ?? offer.remaining_seats ?? offer.available ?? offer.quantity;
    inventory.append(element('h3', `${number(remaining)} unspent quota`)); inventory.append(element('p', `D${offer.day} allocation · ${offer.release_version === 'three-round-release-v1' ? 'valid until cutoff' : 'historical expiry rule'}`));
    inventory.append(element('p', 'Subject to current protection and physical seats; checked on booking.'));
    const link = element('a', Number(remaining) > 0 ? 'View member site' : 'Sold out', 'text-link'); link.href = '/members';
    card.append(intro, price, inventory, link); return card;
  }));
  if (!state.offers.length) $('offers-list').append(element('p', 'No member offers yet. Publish an offer from the selected flight above.', 'empty-state'));
}
$('offer-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('publish-button'), async () => {
  if (!state.loadedFlightId || !state.forecast) throw new Error('Load a valid flight forecast first.');
  if (!RELEASE_DAYS.includes(state.day) || state.forecast.release_status?.round_already_issued || state.forecast.release_status?.blocked_reason) throw new Error(releaseExplanation(state.forecast));
  if (value('offer-quantity') > Number(state.forecast.releasable_seats)) throw new Error('Requested seats exceed the current forecast release limit.');
  const data = await api('/api/offers', { flight_id: state.loadedFlightId, days_to_departure: state.day, quantity: value('offer-quantity'), base_fare: value('offer-fare') }); notify(`Member offer published: ${(data.offer || data).offer_id || (data.offer || data).id || 'saved'}.`); await loadOffers(); await loadForecast();
}); });
async function loadMemberPlan() {
  try { const data = await api('/api/member-portal/plan'); const plan = data.membership;
    if (!state.planDraft && document.activeElement !== $('member-fee')) $('member-fee').value = plan.fee;
    text('membership-status', `Published membership: ${money(plan.fee)} for ${number(plan.term_days)} days. This is the price shown on the member site.`);
  } catch (e) { text('membership-status', `Membership plan unavailable: ${e.message}`); }
}
$('member-fee').addEventListener('input', () => { state.planDraft = true; });
$('member-plan-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('save-plan-button'), async () => {
  const data = await api('/api/member-portal/plan', { membership_fee: value('member-fee') });
  state.planDraft = false;
  text('membership-status', `Published membership: ${money(data.membership.fee)} for ${number(data.membership.term_days)} days. Existing members are not charged again.`);
  notify('Membership price saved. New members see this price on the member site.');
}); });
$('refresh-offers').addEventListener('click', loadOffers);

async function init() {
  setView();
  try {
    const [summary, flightData] = await Promise.all([api('/api/summary'), api('/api/flights')]); state.summary = summary; state.flights = flightData.flights || flightData;
    text('dataset-label', `${number(summary.dataset?.rows ?? summary.rows)} daily snapshots · synthetic`);
    const configured = summary.llm?.live_configured || summary.llm?.configured || summary.llm?.live_available;
    if (configured) { $('live-mode-option').disabled = false; $('live-mode-option').textContent = 'Live LLM'; $('market-live-option').disabled = false; $('market-live-option').textContent = 'Live LLM · bounded calls'; }
    $('flight-select').replaceChildren(...state.flights.map((flight) => { const option = element('option', `${flight.origin} → ${flight.destination} · ${(flight.departure_at || flight.departure_date || '').slice(0, 10)} · ${flight.flight_id}`); option.value = flight.flight_id; return option; }));
    $('flight-select').disabled = !state.flights.length;
    if (state.flights.length) await loadFlight(); else throw new Error('No flights available. Generate the simulation dataset and restart the backend.');
    loadPersonas(); loadAgentRuns(); loadPanelRuns(); loadMemberPlan();
    api('/api/evaluation').then((report) => {
      if (!report.summary) throw new Error('Evaluation pending');
      text('validation-summary', `${number(report.flights)} fresh synthetic flights, evaluated at D28, D14 and D7 after model freeze. Protection includes a separate calibrated safety margin; it is not a posterior P90 or a real-airline guarantee. The comparison below uses the same flights for both models.`);
      const table = element('table');
      table.append(element('caption', 'Held-out surge coverage and all-flight trade-offs'));
      const header = element('thead'); const heading = element('tr');
      for (const label of ['Day', 'Surge v1', 'Surge v2', 'Demand MAE v2', 'Released v2']) { const th = element('th', label); th.scope = 'col'; heading.append(th); }
      header.append(heading); table.append(header);
      const body = element('tbody');
      for (const day of [28, 14, 7]) {
        const all = report.summary[`v2/D${day}/all`], old = report.summary[`v1/D${day}/surge`], surge = report.summary[`v2/D${day}/surge`];
        if (!all || !old || !surge) continue;
        const row = element('tr');
        for (const item of [`D${day}`, percent(old.coverage), percent(surge.coverage), number(all.demand_mae, 1), `${number(all.mean_release, 1)} seats`]) row.append(element('td', item));
        body.append(row);
      }
      table.append(body); $('validation-table').replaceChildren(table);
    }).catch(() => text('validation-summary', 'Evaluation report is unavailable. No empirical coverage claim is shown.'));
    api('/api/evaluation/extended').then((report) => {
      const v2 = report.summary?.['v2/D28/surge'], v1 = report.summary?.['v1/D28/surge'], unseen = report.summary?.['v2/D7/surge_future'];
      if (!v2 || !v1) throw new Error('Extended evaluation pending');
      text('extended-validation-summary', `Additional frozen-model check: ${number(report.evaluated_flights)} synthetic flights, including ${number(v2.n)} surge flights. D28 surge protection coverage: ${percent(v2.coverage)} for v2 versus ${percent(v1.coverage)} for recalibrated v1. ${unseen ? `For ${number(unseen.n)} flights with a surge still unobserved at D7, v2 coverage is ${number(unseen.coverage * 100, 2)}%. ` : ''}This larger, separate cohort complements the first holdout; it does not establish real-airline coverage.`);
    }).catch(() => text('extended-validation-summary', 'Extended evaluation is unavailable. The first holdout remains visible above.'));
  } catch (e) { error(`Unable to load the workspace. ${e.message}`); text('dataset-label', 'Dataset unavailable'); }
}
init();

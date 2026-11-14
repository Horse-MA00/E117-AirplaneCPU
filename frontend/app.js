import { thompsonUrl } from './thompson-navigation.js';
import { seatStatus } from './seat-status.js';
import { demandDescription, matchesDemand, populateDemandFilter } from './demand-filter.js';
import { populatePlaces, matchesFlightPlaces, setFlightPlaces, flightOptionLabel } from './flight-picker.js';
import { attachPlaceSearch } from './place-search.js';
const $ = (id) => document.getElementById(id);
const RELEASE_DAYS = [28, 14, 7];
const state = { flights: [], flight: null, history: [], forecast: null, day: 28, loadedFlightId: null, request: 0, forecastRequest: 0, summary: null, offers: [], offersLoaded: false, planDraft: false, planFee: null, offerFlightId: null, offerDay: 28, offerForecast: null, offerRequest: 0, offerManual: false, thompsonRuns: null };
const VIEWS = ['flights', 'members', 'results', 'customers'];
const BAR_VIEWS = ['flights', 'members', 'results'];
const number = (value, digits = 0) => value === null || value === undefined || !Number.isFinite(Number(value)) ? '—' : Number(value).toLocaleString('en-HK', { maximumFractionDigits: digits });
const money = (value) => value === null || value === undefined ? '—' : `HK$${number(value, Number.isInteger(Number(value)) ? 0 : 2)}`;
const percent = (value) => value === null || value === undefined ? '—' : `${number(Number(value) * 100, 1)}%`;
const value = (id) => Number($(id).value);
function text(id, content) { $(id).textContent = content; }
function clearError() { $('error').hidden = true; }
function error(message) { text('error', message); $('error').hidden = false; }
function notify(message) { text('notice', message); $('notice').hidden = false; state.noticeView = location.hash.slice(1) || 'flights'; }
function element(tag, content, className) { const el = document.createElement(tag); if (content !== undefined) el.textContent = content; if (className) el.className = className; return el; }
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
  const requested = location.hash.slice(1) || 'flights';
  const name = VIEWS.includes(requested) ? requested : 'unavailable';
  $('context-bar').hidden = !BAR_VIEWS.includes(name);
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== `view-${name}`;
  for (const anchor of document.querySelectorAll('.primary-nav a')) {
    if (anchor.hash === `#${name}`) anchor.setAttribute('aria-current', 'page');
    else anchor.removeAttribute('aria-current');
  }
  if (state.noticeView !== name) $('notice').hidden = true;
  document.title = `${({flights:'Forecast seats',customers:'Member feedback',members:'Publish offers',results:'Results',unavailable:'Page unavailable'})[name]} — UOption Fly Pass`;
  if (name === 'unavailable') { text('dataset-label','No data loaded'); return true; }
  if (name === 'members') { loadOffers(); loadMemberPlan(); if(state.loadedFlightId)selectOffer(state.loadedFlightId,state.day,false); }
  if (name === 'results') loadOffers();
  if (name === 'flights' && state.forecast) requestAnimationFrame(renderForecast);
  if (name === 'flights' && state.flights.length && !state.loadedFlightId && $('flight-select').value) loadFlight();
  document.dispatchEvent(new CustomEvent('uoption:view', { detail: { name } }));
  return false;
}
window.addEventListener('hashchange', () => { if(state.summary)setView(); else init(); });
// Returning with the browser Back button (often from the member site) restores this page from cache; reload sales and seats.
window.addEventListener('pageshow', (event) => { if (!event.persisted || !state.summary) return; loadOffers(); if (state.loadedFlightId) loadForecast(); });
document.querySelector('.skip').addEventListener('click', (event) => { event.preventDefault(); document.querySelector('.view:not([hidden]) h1')?.focus(); });
let resizeTimer; window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.forecast) renderForecast(); }, 120); });
$('go-pricing').addEventListener('click', () => {
  if ($('go-pricing').disabled || !state.loadedFlightId) return;
  location.assign(thompsonUrl({flightId:state.loadedFlightId, day:state.day}));
});

function updateNavLinks() { $('nav-optimize').href = thompsonUrl({flightId: state.loadedFlightId, day: state.day}); }
const flightDay = (flight) => (flight.departure_at || flight.departure_date || '').slice(0, 10);
function longDate(iso) {
  const [y, m, d] = String(iso).split('-').map(Number);
  if (!y || !m || !d) return iso || '—';
  const date = new Date(Date.UTC(y, m - 1, d)), part = (o) => date.toLocaleDateString('en-GB', { ...o, timeZone: 'UTC' });
  return `${part({ weekday: 'short' })} ${d} ${part({ month: 'short' })} ${y}`;
}
const routeKey = (flight) => `${flight.origin} → ${flight.destination}`;
function svgNode(tag, attrs, content) { const el = document.createElementNS('http://www.w3.org/2000/svg', tag); Object.entries(attrs || {}).forEach(([key, val]) => el.setAttribute(key, val)); if (content !== undefined) el.textContent = content; return el; }
function linePath(points, x, y) { return points.map((p, i) => `${i ? 'L' : 'M'}${x(p.day).toFixed(2)},${y(p.value).toFixed(2)}`).join(' '); }
function drawChart(id, observed, future, { maxY, yLabel, width = 720, height = 260, minDay = 28 } = {}) {
  const svg = $(id); width = Math.max(280, Math.round(svg.clientWidth || svg.getBoundingClientRect().width) || width); svg.replaceChildren(); svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
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
  const last = observed.at(-1); if (last) svg.append(svgNode('circle', { cx: x(last.day), cy: y(last.value), r: 3.5, fill: '#6F2C91' }));
  svg.append(svgNode('text', { x: left, y: 12, class: 'chart-tick' }, yLabel));
}

function clearFlightSelection() {
  state.request++; state.forecastRequest++; state.forecast=null; state.loadedFlightId=null; state.flight=null; state.history=[];
  $('flight-main').hidden=true; $('flight-main').setAttribute('aria-busy','false');
  $('flight-filter-empty').hidden=false; $('go-pricing').disabled=true; $('publish-button').disabled=true;
  text('flight-date','—'); text('flight-capacity','—'); text('flight-scenario-note','Choose another departure, destination or demand level to find a flight.');
  selectOffer(null, state.day, false); updateNavLinks(); renderResults(); clearResultsSeatBar();
}
// Airport/country choices stay complete; only departures respond to the filters.
function fillForecastFlights(preferred=$('flight-select').value) {
  const from=$('context-from').value, to=$('context-to').value;
  const matches=state.flights.filter(f=>matchesDemand(f,$('forecast-demand').value) && matchesFlightPlaces(f,from,to))
    .sort((a,b)=>`${flightDay(a)}${a.flight_id}`.localeCompare(`${flightDay(b)}${b.flight_id}`));
  text('forecast-demand-status',`${number(matches.length)} of ${number(state.flights.length)} flights match these filters. Demand groups use the fixed D28 forecast.`);
  for (const id of ['context-from','context-to']) $(id).title=$(id).selectedOptions[0]?.textContent || '';
  if(!matches.length){
    $('flight-select').replaceChildren(new Option('No matching flights','')); $('flight-select').disabled=true;
    $('flight-select').title=''; clearFlightSelection(); return false;
  }
  const includeRoute=!from || !to || from.startsWith('region:') || to.startsWith('region:');
  $('flight-select').replaceChildren(...matches.map(f=>new Option(flightOptionLabel(f,{includeRoute}),f.flight_id)));
  $('flight-select').disabled=false;
  const demo=matches.find(f=>f.demo_priority===0&&Number(f.demo_d28_releasable)>0);
  $('flight-select').value=(matches.find(f=>f.flight_id===preferred)||demo||matches[0]).flight_id;
  $('flight-select').title=$('flight-select').selectedOptions[0]?.textContent || '';
  $('flight-filter-empty').hidden=true;
  return true;
}
async function loadFlight() {
  clearError(); $('flight-select').title=$('flight-select').selectedOptions[0]?.textContent || ''; const id = $('flight-select').value; if (!id) {clearFlightSelection();return;}
  const request = ++state.request; state.forecastRequest++; state.forecast = null; state.loadedFlightId = null; state.flight = null; state.history = [];
  selectOffer(null, state.day, false); updateNavLinks(); renderResults(); clearResultsSeatBar();
  $('flight-main').hidden=false; $('flight-filter-empty').hidden=true;
  $('flight-main').classList.add('loading'); $('publish-button').disabled = true; $('go-pricing').disabled=true;
  try {
    const data = await api(`/api/flights/${encodeURIComponent(id)}`);
    if (request !== state.request) return;
    state.flight = data.flight || state.flights.find((flight) => flight.flight_id === id);
    state.history = data.history || data.snapshots || []; state.loadedFlightId = id;
    state.asOf = Number(state.flight?.observed_through_day) || 0; applyDataHorizon();
    selectOffer(id, state.day, false);
    const flight = state.flight;
    text('flight-date', `${routeKey(flight)} · ${longDate(flightDay(flight))}`);
    text('flight-capacity', `${number(flight.capacity || flight.sellable_capacity)} seats`);
    text('flight-scenario-note',demandDescription(flight)); $('flight-scenario-note').title = id;
    updateNavLinks();
    await loadForecast();
  } catch (e) { if (request === state.request) error(e.message); }
  finally { if (request === state.request) $('flight-main').classList.remove('loading'); }
}
async function loadForecast() {
  if (!state.loadedFlightId) return;
  const request = ++state.forecastRequest; const flightId = state.loadedFlightId; const day = state.day;
  state.forecast = null; clearResultsSeatBar();
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
  const seats=seatStatus(f,capacity,booked,state.day);
  text('booked-value', number(seats.reportedOccupied)); text('booked-detail', `${number(seats.normal)} normal + ${number(seats.confirmedMembers)} member · ${seats.overage?`${number(seats.overage)} over capacity`:`${percent(seats.occupied / capacity)} occupied`}`);
  $('seat-inventory-warning').hidden=seats.overage<1;
  text('seat-inventory-warning',seats.overage?`Snapshot conflict: ${number(seats.normal)} normal bookings + ${number(seats.confirmedMembers)} confirmed member bookings = ${number(seats.reportedOccupied)} bookings for ${number(capacity)} seats (${number(seats.overage)} over capacity). The bar is capped at physical capacity. Review inventory before publishing.`:'');
  text('demand-value', number(f.expected_remaining_demand, 1)); text('empty-value', number(f.expected_empty_seats, 1));
  text('empty-detail', `${percent(f.expected_empty_rate)} expected unsold in the normal-sales baseline; member bookings excluded`);
  text('protection-value', `${number(f.protection_p90)} seats`);
  text('chart-caption', `Normal-demand baseline only. Solid: observed normal bookings; dashed: expected normal bookings to departure. Member demo bookings are excluded. Shading: model forecast range.`); text('release-value', `${number(seats.newSeats)} seats`);
  text('headroom-value', `${number(seats.headroom)} seats`);
  // The NHPP model's own recommendation: empty seats minus P90 normal demand and its safety allowance.
  const nhppSeats=Math.max(0,Math.floor(Number(f.risk_release_ceiling??f.releasable_seats)||0));
  text('nhpp-release-value',`${number(nhppSeats)} seat${nhppSeats===1?'':'s'}`);
  text('nhpp-release-detail',Number.isFinite(Number(f.protection_p90))&&Number.isFinite(Number(f.available_seats))
    ?`${number(f.available_seats)} empty − ${number(f.protection_p90)} protected for normal demand (P90 ${number(f.raw_protection_p90??f.protection_p90)}${Number(f.protection_allowance)?` + ${number(f.protection_allowance)} safety allowance`:''}) at D${state.day}. Total for this flight, before earlier rounds and sold member seats are deducted.`
    :'Empty seats minus seats protected for normal demand at this date.');text('bookable-value', `${number(seats.published)} seats`);
  text('member-allocation-detail', seats.reason);text('headroom-detail', `${number(seats.unpublished)} unpublished + ${number(seats.published)} published and bookable${seats.heldPublished?` + ${number(seats.heldPublished)} published on hold`:''}`);
  text('bookable-detail',seats.published?'Existing usable quota; checked again when booking':'No published seats can be booked now.');
  const noRelease=nhppNoRelease(f,seats,state.day);
  $('release-decision').hidden=!noRelease;$('release-decision').replaceChildren(...(noRelease?[element('strong',noRelease.title),document.createTextNode(noRelease.detail)]:[]));
  if(noRelease)text('release-value','Do not release');
  $('publish-button').disabled = !canPublish();
  const past = history.filter((r) => r.days_to_departure <= 28).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.booked_seats ?? r.net_booked_seats) }));
  const future = (f.forecast_curve || []).map((r) => ({ day: Number(r.day ?? r.days_to_departure), value: Number(r.expected_booked), low: Number(r.p10), high: Number(r.p90) })).filter((r) => Number.isFinite(r.value) && r.day <= state.day).sort((a, b) => b.day - a.day);
  drawChart('booking-chart', past, future, { maxY: capacity, yLabel: 'Normal bookings' });
  const prices = history.filter((r) => r.days_to_departure <= 180 && r.normal_base_fare != null).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.normal_base_fare) }));
  drawChart('price-chart', prices, [], { yLabel: 'HKD', width: 620, height: 260, minDay: 180 });
  const lastQuote=history.findLast(r=>r.normal_base_fare!=null);
  text('price-caption', `Base fares through D${state.day}.${lastQuote?` Last quote D${lastQuote.days_to_departure}: fees ${money(lastQuote.mandatory_fees)} · total payable ${money(lastQuote.normal_total_fare)}.`:' No observed quote is available.'} Future quotes are not shown.`);
  renderSeatComposition(seats);
  const nextValid=RELEASE_DAYS.includes(seats.nextRound)&&seats.nextRound<state.day&&reachedDay(seats.nextRound);
  const nextNotReached=!RELEASE_DAYS.includes(state.day)&&RELEASE_DAYS.includes(seats.nextRound)&&!reachedDay(seats.nextRound);
  const blockedRelease=seats.overage>0||seats.historical||seats.salesClosed||seats.releaseState==='round_already_issued';
  $('go-pricing').disabled=blockedRelease||Boolean(noRelease)||(!RELEASE_DAYS.includes(state.day)&&!nextValid);
  $('go-pricing').textContent=noRelease?'No member seats to price':seats.overage>0?'Resolve inventory conflict first':seats.historical?'Historical view · release unavailable':seats.salesClosed?'Sales are closed':seats.releaseState==='round_already_issued'?'This release round is already published':RELEASE_DAYS.includes(state.day)?'Optimize this release round →':nextValid?`Optimize next release D${seats.nextRound} →`:nextNotReached?`Next release D${seats.nextRound} not reached yet`:'No release rounds remain';

  if (state.offers.length) renderOffers();
  renderResults();
}
// On a release round, NHPP leaving no member headroom means nothing should be released or priced.
function nhppNoRelease(f,seats,day){
  if(!RELEASE_DAYS.includes(day)||seats.historical||seats.salesClosed||seats.overage>0||seats.headroom>=1)return null;
  const ceiling=Math.max(0,Math.floor(Number(f.risk_release_ceiling??f.releasable_seats)||0));
  return {title:`Forecast decision: do not release member seats at D${day}`,
    detail:ceiling<1
      ?`The forecast expects ${number(f.expected_remaining_demand,1)} more normal bookings and protects ${number(seats.protection)} of ${number(seats.physicalRemaining)} empty seats, so 0 member seats are safe to release. There is no member fare to optimize for this round.`
      :`The forecast allows ${number(ceiling)} member seat${ceiling===1?'':'s'}, and existing member bookings already use all of them. No further member seats should be released this round.`};
}
function renderSeatComposition(seats) {
  text('protection-value', `${number(seats.protection)} seats`);
  const bar=$('seat-composition');
  bar.setAttribute('aria-label', `${number(seats.capacity)} total seats. `+seats.parts.map(p=>`${p.label}: ${number(p.value)} seats`).join('. '));
  bar.replaceChildren(...seats.parts.map(p=>{
    const share=p.value/Math.max(1,seats.capacity)*100;
    const segment=element('span',p.value&&share>=3.5?number(p.value):'',`seat-part ${p.key}`);if(p.value)segment.title=`${p.label}: ${number(p.value)} seats`;
    segment.dataset.seats=p.value;segment.dataset.part=p.key;
    segment.style.setProperty('--seat-share',String(p.value/Math.max(1,seats.capacity)*100));
    if(!p.value)segment.hidden=true;return segment;
  }));
  $('seat-composition-legend').replaceChildren(...seats.parts.filter(p=>p.value>0||p.key==='published'||p.key==='available').map(p=>{
    const label=element('div',undefined,`seat-legend-item ${p.key}`),dot=element('i');dot.setAttribute('aria-hidden','true');
    label.append(dot,element('span',p.label),element('strong',`${number(p.value)} seats`));return label;
  }));
}
function canPublish() {
  const f = state.offerForecast;
  return Boolean(f && state.offerFlightId && state.offerFlightId === state.loadedFlightId && state.offerFlightId === $('flight-select').value && state.offerDay === state.day && RELEASE_DAYS.includes(state.offerDay) && f.releasable_seats > 0 && !f.release_status?.round_already_issued && !f.release_status?.blocked_reason);
}
// Near-term feeds stop at today: observed_through_day is the flight's days to departure
// today (0 for full simulated histories). Later rounds have no booking data yet.
function reachedDay(day) { return day >= (state.asOf || 0); }
function notReachedMessage(day) {
  const gap = state.asOf - day;
  return `D${day} has not been reached yet for this flight. Booking data runs to D${state.asOf} (today); D${day} is ${gap} day${gap === 1 ? '' : 's'} away.`;
}
function setDayView(day) {
  state.day = day; $('day-slider').value = 28 - day; $('day-slider').setAttribute('aria-valuetext', day ? `${day} days before departure` : 'Sales cutoff'); text('day-number', day);
  text('day-description', !day ? 'Sales cutoff · no new offers' : state.asOf && day === state.asOf ? 'Today · days before departure' : 'Days before departure');
  document.querySelectorAll('[data-day]').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.day) === day)));
}
function applyDataHorizon() {
  const live = state.asOf > 0;
  // Data that stops at today has no later days to scrub through.
  document.querySelector('.day-controller').hidden = live;
  document.querySelectorAll('[data-day]').forEach((button) => {
    const future = !reachedDay(Number(button.dataset.day));
    button.classList.toggle('not-reached', future);
    if (future) { button.setAttribute('aria-disabled', 'true'); button.title = `Not reached yet · booking data runs to D${state.asOf} (today)`; }
    else { button.removeAttribute('aria-disabled'); button.removeAttribute('title'); }
  });
  if (reachedDay(state.day)) { setDayView(state.day); return; }
  const wanted = state.day, rounds = RELEASE_DAYS.filter(reachedDay);
  const day = rounds.length ? Math.min(...rounds) : state.asOf;
  setDayView(day);
  notify(`${notReachedMessage(wanted)} Showing D${day}${rounds.length ? '' : ' (today); no release round has been reached yet'}.`);
}
function chooseDay(day) {
  setDayView(day);
  updateNavLinks();
  if (state.loadedFlightId) selectOffer(state.loadedFlightId, day, false);
  loadForecast();
}
let dayTimer;
$('day-slider').addEventListener('input', () => { clearTimeout(dayTimer); const day = 28 - value('day-slider'); text('day-number', day); dayTimer = setTimeout(() => chooseDay(day), 150); });
document.querySelectorAll('[data-day]').forEach((button) => button.addEventListener('click', () => {
  clearTimeout(dayTimer); const day = Number(button.dataset.day);
  if (state.loadedFlightId && !reachedDay(day)) { notify(notReachedMessage(day)); return; }
  $('notice').hidden = true; chooseDay(day);
}));
$('flight-select').addEventListener('change', loadFlight);
$('forecast-demand').addEventListener('change',()=>{if(fillForecastFlights())loadFlight();});
for (const id of ['context-from','context-to']) $(id).addEventListener('change',()=>{if(fillForecastFlights())loadFlight();});
attachPlaceSearch($('context-from'),{label:'Search departure places'});attachPlaceSearch($('context-to'),{label:'Search destination places'});

async function loadOffers() {
  try { const data = await api('/api/offers'); state.offers = data.offers || (Array.isArray(data) ? data : []); state.offersLoaded = true; renderOffers(); renderResults(); } catch (e) { error(e.message); }
}
// ---- ⓘ tips built in script (same markup as the static ones in index.html) ----
let tipCount = 0;
function infoTip(label, title, nodes) {
  const id = `tip-js-${++tipCount}`, wrap = element('span', undefined, 'info');
  const button = element('button', 'i', 'info-btn'); button.type = 'button'; button.setAttribute('aria-label', label); button.setAttribute('aria-describedby', id);
  const tip = element('span', undefined, 'info-tip'); tip.id = id; tip.setAttribute('role', 'tooltip');
  tip.append(element('strong', title, 'info-title'), ...nodes); wrap.append(button, tip); return wrap;
}
// Sourced fee estimates written by scripts/apply_member_fee_reference.py (offers.fee_breakdown).
function feeBreakdown(offer) {
  try { const b = typeof offer.fee_breakdown === 'string' ? JSON.parse(offer.fee_breakdown) : offer.fee_breakdown; return b && Array.isArray(b.lines) && b.lines.length ? b : null; } catch { return null; }
}
function feeTip(breakdown) {
  const nodes = breakdown.lines.map((line) => { const row = element('span', undefined, 'info-row'); row.append(element('span', line.label), element('strong', money(line.amount))); return row; });
  nodes.push(element('small', `${breakdown.kind === 'reference_estimate' ? 'Reference estimate, not a quoted fare' : 'Fee breakdown'}${breakdown.checked_on ? ` · checked ${breakdown.checked_on}` : ''}`));
  const bySite = new Map(); for (const c of breakdown.components || []) if (/^https:\/\//.test(c.source || '')) { const host = new URL(c.source).hostname; if (!bySite.has(host)) bySite.set(host, c.source); }
  const sources = [...bySite.values()];
  if (sources.length) {
    const list = element('span', undefined, 'info-sources'); list.append(element('span', 'Sources: '));
    sources.forEach((url, i) => { const a = element('a', new URL(url).hostname.replace(/^www\./, '')); a.href = url; a.target = '_blank'; a.rel = 'noopener'; list.append(...(i ? [document.createTextNode(' · ')] : []), a); });
    nodes.push(list);
  }
  return infoTip('Fee breakdown', 'Mandatory fees per ticket', nodes);
}
function renderOffers() {
  $('offers-list').replaceChildren(...state.offers.map((offer) => {
    const card = element('article', undefined, 'offer-card'); card.dataset.offerId = offer.offer_id || offer.id; const knownFlight = state.flights.find((f) => f.flight_id === offer.flight_id) || {};
    const intro = element('div'); intro.append(element('h3', `${offer.origin || knownFlight.origin || '—'} → ${offer.destination || knownFlight.destination || '—'}`)); intro.append(element('p', (offer.departure_at || knownFlight.departure_at || '').slice(0, 10))); intro.append(element('p', offer.flight_id));
    const price = element('div'); price.append(element('div', money(offer.base_fare), 'offer-price'));
    const feeLine = element('p', `Base fare · fees ${money(offer.mandatory_fees ?? offer.fees ?? 0)} · total payable ${money(offer.total_payable ?? (Number(offer.base_fare)+Number(offer.mandatory_fees??offer.fees??0)))}`, 'small muted');
    const breakdown = feeBreakdown(offer); if (breakdown) feeLine.append(feeTip(breakdown));
    price.append(feeLine);
    const inventory = element('div'); const remaining = offer.remaining ?? offer.remaining_seats ?? offer.available ?? offer.quantity;
    inventory.append(element('h3', `${number(remaining)} unspent quota`)); inventory.append(element('p', `D${offer.day} allocation · ${offer.release_version === 'three-round-release-v1' ? 'valid until cutoff' : 'historical expiry rule'}`));
    inventory.append(element('p', 'Subject to current protection and physical seats; checked on booking.'));
    const link = element('a', Number(remaining) > 0 ? 'View member site' : 'Sold out', 'text-link'); link.href = '/members';
    card.append(intro, price, inventory, link); return card;
  }));
  if (!state.offers.length) $('offers-list').append(element('p', 'No member offers yet. Publish an offer from the selected flight above.', 'empty-state'));
}
function offerOptimizeLink(flightId,day){
  const link=element('a','Optimize this flight','button secondary');link.href=thompsonUrl({flightId,day});
  return link;
}
async function selectOffer(flightId,day,manual=true){
  const changed=flightId!==state.offerFlightId||day!==state.offerDay;
  if(changed){$('offer-fare').value='';$('offer-quantity').value='';$('publish-next').hidden=true;}
  const token=++state.offerRequest;state.offerManual=manual;state.offerFlightId=flightId;state.offerDay=day;state.offerForecast=null;$('publish-button').disabled=true;
  const flight=state.flights.find(f=>f.flight_id===flightId), box=$('offer-guidance');
  box.setAttribute('aria-busy','true');box.replaceChildren(element('p','Calculating the current release limit…'));renderPreview();
  if(!flight){text('offer-flight-context','Choose a flight in the bar above.');text('offer-release-status','Select a flight to calculate its current safe release limit.');$('offer-quantity').max=0;box.replaceChildren(element('p','Choose a route, departure and release round in the bar above.'));box.setAttribute('aria-busy','false');return;}
  text('offer-flight-context',`${routeKey(flight)} · ${longDate(flightDay(flight))} · ${flightId} · D${day}`);
  try{
    const result=await api('/api/forecast',{flight_id:flightId,days_to_departure:day});if(token!==state.offerRequest)return;
    state.offerForecast=result.forecast;
    const qty=Math.max(0,Math.floor(state.offerForecast.releasable_seats));$('offer-quantity').max=qty;
    // Default to the full safe limit; a value already typed for this flight and round is kept.
    $('offer-quantity').value=$('offer-quantity').value===''?(qty||1):Math.min(Math.max(1,value('offer-quantity')),qty)||1;
    const blocked=state.offerForecast.release_status?.blocked_reason;
    text('offer-release-status',`${qty} new seat${qty===1?'':'s'} can be released now${blocked?`. ${blocked}`:''}`);
    box.replaceChildren();
    if(RELEASE_DAYS.includes(day)){const ref=await thompsonReference(flightId,day);if(token!==state.offerRequest)return;box.append(ref||element('p','No completed Thompson experiment for this flight and round yet.','muted'),offerOptimizeLink(flightId,day));}
    else box.replaceChildren(element('p','Select D28, D14 or D7 to publish a new allocation.'));
  }catch(e){if(token===state.offerRequest)box.replaceChildren(element('p',`Release limit unavailable: ${e.message}`));}
  finally{if(token===state.offerRequest){box.setAttribute('aria-busy','false');$('publish-button').disabled=!canPublish();renderPreview();}}
}
for(const id of ['offer-fare','offer-quantity'])$(id).addEventListener('input',()=>{$('publish-button').disabled=!canPublish();renderPreview();});
$('offer-form').addEventListener('submit',(event)=>{event.preventDefault();busy($('publish-button'),async()=>{
  if(!canPublish())throw new Error('Choose a valid flight and release round with new safe seats.');
  if(value('offer-quantity')>Number(state.offerForecast.releasable_seats))throw new Error('Requested seats exceed the current forecast release limit.');
  const data=await api('/api/offers',{flight_id:state.offerFlightId,days_to_departure:state.offerDay,quantity:value('offer-quantity'),base_fare:value('offer-fare')});
  notify(`Member offer published: ${(data.offer||data).offer_id||(data.offer||data).id||'saved'}.`);state.thompsonRuns=null;await loadOffers();await selectOffer(state.offerFlightId,state.offerDay,state.offerManual);$('publish-next').hidden=false;if(state.loadedFlightId===state.offerFlightId)await loadForecast();
});});
async function loadMemberPlan() {
  try { const data = await api('/api/member-portal/plan'); const plan = data.membership;
    if (!state.planDraft && document.activeElement !== $('member-fee')) $('member-fee').value = plan.fee;
    state.planFee = Number(plan.fee); renderPreview();
    text('membership-status', `Published membership: ${money(plan.fee)} for ${plan.term_label || '6 months'}. This is the price shown on the member site.`);
  } catch (e) { text('membership-status', `Membership plan unavailable: ${e.message}`); }
}
$('member-fee').addEventListener('input', () => { state.planDraft = true; });
$('member-plan-form').addEventListener('submit', (event) => { event.preventDefault(); busy($('save-plan-button'), async () => {
  const data = await api('/api/member-portal/plan', { membership_fee: value('member-fee') });
  state.planDraft = false; state.planFee = Number(data.membership.fee); renderPreview();
  text('membership-status', `Published membership: ${money(data.membership.fee)} for ${data.membership.term_label || '6 months'}. Existing members are not charged again.`);
  notify('Membership price saved. New members see this price on the member site.');
}); });
$('refresh-offers').addEventListener('click', loadOffers);
$('refresh-results').addEventListener('click', () => { loadOffers(); if (state.loadedFlightId) loadForecast(); });

// ---- Publish: Thompson reference and member preview (display only; publication stays manual) ----
const DECISIONS = { ADOPT_CANDIDATE: 'Adopt the tested fare', KEEP_INITIAL: 'Keep the initial fare', NO_OFFER: 'No member offer', INCONCLUSIVE: 'Inconclusive' };
async function thompsonReference(flightId, day) {
  try {
    if (!state.thompsonRuns) state.thompsonRuns = (await api('/api/adaptive-pricing/runs')).runs || [];
  } catch { return null; }
  const runs = state.thompsonRuns.filter((r) => !r.scenario && !r.scope?.scenario && !r.config?.demo_scenario && r.status === 'completed' && (r.scope?.flight_id ?? r.config?.flight_id) === flightId && Number(r.scope?.as_of_day ?? r.config?.forecast_day) === day);
  const latest = runs.sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))[0];
  if (!latest) return null;
  const decision = latest.validation?.adoption_result || latest.validation?.decision;
  const fare = latest.validation?.retained_price ?? latest.recommendation?.price;
  const ref = element('p', undefined, 'thompson-ref');
  ref.append(element('span', 'Latest Thompson result'), element('strong', decision === 'NO_OFFER' ? 'No offer' : money(fare)), element('span', DECISIONS[decision] || 'Completed experiment', 'muted'));
  return ref;
}
const hkd = (value) => `HKD ${number(value, Number.isInteger(Number(value)) ? 0 : 2)}`;
// Mirrors the member site's flight card (members/portal.js): struck normal fare, saving, ticket total, first purchase with pass.
function renderPreview() {
  const box = $('offer-preview'); if (!box) return;
  const flight = state.flights.find((f) => f.flight_id === state.offerFlightId);
  if (!flight) { box.replaceChildren(element('p', 'Choose a flight to preview the member offer.', 'preview-empty')); return; }
  const quote = state.history.filter((r) => r.normal_base_fare != null && Number(r.days_to_departure) >= state.offerDay).sort((a, b) => b.days_to_departure - a.days_to_departure).at(-1) || {};
  const fare = Number($('offer-fare').value), seats = Number($('offer-quantity').value);
  const fees = Number(quote.mandatory_fees ?? 0), normal = Number(quote.normal_base_fare);
  const hasFare = $('offer-fare').value !== '' && Number.isFinite(fare);
  const d = Number(flightDay(flight).split('-')[2]);
  const card = element('div', undefined, 'preview-card');
  const date = element('div', String(d || '—'), 'preview-date'); date.append(element('small', longDate(flightDay(flight)).replace(/ \d+ /, ' · ')));
  const middle = element('div'); const route = element('div', undefined, 'preview-route'); route.append(document.createTextNode(flight.origin), element('span', '→'), document.createTextNode(flight.destination));
  const time = String(flight.departure_at || '').slice(11, 16);
  middle.append(route, element('div', 'One way · 1 member traveller', 'preview-meta'));
  if (time) middle.append(element('div', `Departure ${time}`, 'preview-meta'));
  if (Number.isFinite(seats) && seats > 0) middle.append(element('div', `${number(seats)} member seat${seats === 1 ? '' : 's'} available`, 'preview-seats'));
  const price = element('div', undefined, 'preview-price'); price.append(element('small', 'Member base fare'));
  const line = element('div', undefined, 'preview-fare');
  if (Number.isFinite(normal) && hasFare && normal > fare) line.append(element('s', hkd(normal), 'preview-was'));
  line.append(element('strong', hasFare ? hkd(fare) : '—')); price.append(line);
  if (Number.isFinite(normal) && hasFare && normal > fare) price.append(element('div', `Save ${hkd(normal - fare)} · ${Math.round((1 - fare / normal) * 100)}% off normal base fare`, 'preview-save-badge'));
  price.append(element('small', hasFare ? `+ fees ${hkd(fees)} · total payable ${hkd(fare + fees)}` : 'Enter a member fare'));
  if (hasFare) price.append(element('div', `Ticket total: ${hkd(fare + fees)}`, 'preview-total'));
  if (hasFare && state.planFee !== null) price.append(element('div', `First purchase incl. pass: ${hkd(fare + fees + state.planFee)}`, 'preview-pass'));
  card.append(date, middle, price);
  box.replaceChildren(card, element('p', `Membership ${state.planFee !== null ? hkd(state.planFee) : '—'} for 6 months, paid once on first purchase. Every booking is checked again on the member site.`, 'hint'));
}

// ---- Results: member sales from /api/offers (sold = released − remaining) ----
function offerNumbers(offer) {
  const released = Number(offer.quantity ?? 0), remaining = Number(offer.remaining ?? offer.remaining_seats ?? released);
  const sold = Math.max(0, released - remaining), fare = Number(offer.base_fare ?? 0), fees = Number(offer.mandatory_fees ?? offer.fees ?? 0);
  return { released, remaining, sold, fare, fees, revenue: sold * fare, feeTotal: sold * fees };
}
function clearResultsSeatBar() {
  $('results-composition').replaceChildren(); $('results-legend').replaceChildren();
  $('results-composition').setAttribute('aria-label', 'Choose a flight and wait for its current seat forecast.');
  text('results-protected', '—');
}
function renderResults() {
  if (!$('view-results') || !state.offersLoaded) return;
  const flight = state.flights.find((f) => f.flight_id === state.loadedFlightId);
  const mine = state.offers.filter((o) => o.flight_id === state.loadedFlightId).map((o) => ({ offer: o, ...offerNumbers(o) }));
  const sum = (key) => mine.reduce((t, o) => t + o[key], 0);
  const released = sum('released');
  text('results-context', flight ? `${routeKey(flight)} · ${longDate(flightDay(flight))} · bookings from the member site, read from the shared offer inventory.` : 'Choose a flight in the bar above.');
  text('results-sold', flight ? number(sum('sold')) : '—'); text('results-sold-detail', released ? `of ${number(released)} member seats released` : 'No member seats released yet');
  text('results-remaining', flight ? number(sum('remaining')) : '—');
  text('results-revenue', flight ? money(sum('revenue')) : '—'); text('results-fees', flight ? money(sum('feeTotal')) : '—');
  const sourced = mine.map((o) => feeBreakdown(o.offer)).find(Boolean);
  $('results-fees-label').querySelector('.info')?.remove();
  if (sourced) $('results-fees-label').append(feeTip(sourced));
  text('results-fees-detail', sourced ? `${money(sourced.lines.reduce((t, l) => t + Number(l.amount || 0), 0))} per ticket · reference estimate` : 'Shown separately');
  text('results-updated', `Updated ${new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`);
  $('results-empty').hidden = !flight || mine.length > 0;
  $('results-flight-offers').replaceChildren(...mine.map((o) => { const tr = element('tr'); tr.append(element('td', `D${o.offer.day}`), element('td', number(o.released)), element('td', number(o.sold)), element('td', number(o.remaining)), element('td', money(o.fare))); return tr; }));
  $('results-all-offers').replaceChildren(...state.offers.map((offer) => {
    const o = offerNumbers(offer), known = state.flights.find((f) => f.flight_id === offer.flight_id), tr = element('tr');
    tr.append(element('td', known ? `${routeKey(known)} · ${longDate(flightDay(known))}` : offer.flight_id), element('td', `D${offer.day}`), element('td', number(o.released)), element('td', number(o.sold)), element('td', number(o.remaining)), element('td', money(o.fare)), element('td', money(o.revenue)));
    return tr;
  }));
  if (!state.offers.length) { const tr = element('tr'), td = element('td', 'No member offers yet.'); td.colSpan = 7; tr.append(td); $('results-all-offers').append(tr); }
  // Seat bar: split bookings into normal and member seats.
  const f = state.forecast; if (!f || !state.flight || state.flight.flight_id !== state.loadedFlightId) { clearResultsSeatBar(); return; }
  const latest = state.history.filter((r) => Number(r.days_to_departure) >= state.day).sort((a, b) => b.days_to_departure - a.days_to_departure).at(-1) || {};
  const capacity = Number(state.flight.capacity || latest.capacity || latest.sellable_capacity);
  const seats = seatStatus(f, capacity, Number(latest.booked_seats ?? latest.net_booked_seats ?? 0), state.day);
  const memberSold = Math.min(Number(seats.sold) || 0, seats.occupied);
  const parts = [
    { key: 'occupied', label: 'Normal booked', value: Math.max(0, seats.occupied - memberSold) },
    { key: 'member-sold', label: 'Member sold', value: memberSold },
    ...seats.parts.filter((part) => part.key !== 'occupied'),
  ];
  text('results-protected', `${number(seats.protection)} protected seats untouched`);
  const bar = $('results-composition');
  bar.setAttribute('aria-label', `${number(seats.capacity)} total seats. ` + parts.map((p) => `${p.label}: ${number(p.value)} seats`).join('. '));
  bar.replaceChildren(...parts.map((p) => { const share = p.value / Math.max(1, seats.capacity) * 100; const seg = element('span', p.value && share >= 3.5 ? number(p.value) : '', `seat-part ${p.key}`); if (p.value) seg.title = `${p.label}: ${number(p.value)}`; seg.dataset.seats = p.value; seg.dataset.part = p.key; seg.style.setProperty('--seat-share', String(p.value / Math.max(1, seats.capacity) * 100)); if (!p.value) seg.hidden = true; return seg; }));
  // Like the Forecast legend: hide empty categories, but always show member sales and bookable member quota.
  $('results-legend').replaceChildren(...parts.filter((p) => p.value > 0 || ['member-sold', 'published'].includes(p.key)).map((p) => { const item = element('div', undefined, `seat-legend-item ${p.key}`), dot = element('i'); dot.setAttribute('aria-hidden', 'true'); item.append(dot, element('span', p.label), element('strong', number(p.value))); return item; }));
}

async function init() {
  if (setView()) return;
  try {
    const [summary, flightData] = await Promise.all([api('/api/summary'), api('/api/flights')]); state.summary = summary; state.flights = flightData.flights || flightData;
    text('dataset-label', `${number(summary.dataset?.catalog_rows ?? summary.dataset?.rows ?? summary.rows)} daily snapshots · synthetic`);
    const llm = summary.llm || {};
    const llmOn = Boolean(llm.live_configured || llm.configured || llm.live_available);
    text('llm-status', llmOn ? 'LLM configured' : 'LLM not configured'); $('llm-status').dataset.state = llmOn ? 'on' : 'off';
    populateDemandFilter($('forecast-demand'),state.flights);
    populatePlaces($('context-from'),state.flights,'HKG');
    populatePlaces($('context-to'),state.flights,'');
    $('context-from').disabled=false; $('context-to').disabled=false;
    // Optimize and the sidebar pass the current selection back as ?flight_id=&forecast_day=.
    const params = new URL(location.href).searchParams, wanted = state.flights.find(f => f.flight_id === params.get('flight_id'));
    if(wanted)setFlightPlaces($('context-from'),$('context-to'),wanted);
    const wantedDay = Number(params.get('forecast_day'));
    if (RELEASE_DAYS.includes(wantedDay)) { state.day = wantedDay; $('day-slider').value = 28 - wantedDay; text('day-number', wantedDay); document.querySelectorAll('[data-day]').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.day) === wantedDay))); }
    if(fillForecastFlights(wanted?.flight_id) && location.hash !== '#customers')await loadFlight();
    loadMemberPlan();

  } catch (e) { error(`Unable to load the workspace. ${e.message}`); text('dataset-label', 'Dataset unavailable'); }
}
init();

import { thompsonUrl } from './thompson-navigation.js';
import { seatStatus } from './seat-status.js';
import { demandDescription, matchesDemand, populateDemandFilter } from './demand-filter.js';
const $ = (id) => document.getElementById(id);
const RELEASE_DAYS = [28, 14, 7];
const state = { flights: [], flight: null, history: [], forecast: null, day: 28, loadedFlightId: null, request: 0, forecastRequest: 0, summary: null, offers: [], planDraft: false, offerFlightId: null, offerDay: 28, offerForecast: null, offerRequest: 0, offerManual: false };
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
  const name = ['flights', 'customers', 'members'].includes(requested) ? requested : 'unavailable';
  for (const section of document.querySelectorAll('.view')) section.hidden = section.id !== `view-${name}`;
  for (const anchor of document.querySelectorAll('.primary-nav a')) {
    if (anchor.hash === `#${name}`) anchor.setAttribute('aria-current', 'page');
    else anchor.removeAttribute('aria-current');
  }
  if (state.noticeView !== name) $('notice').hidden = true;
  document.title = `${({flights:'Forecast seats',customers:'What members said',members:'Manage offers',unavailable:'Page unavailable'})[name]} — UOption Fly Pass`;
  if (name === 'unavailable') { text('dataset-label','No data loaded'); return true; }
  if (name === 'members') { loadOffers(); loadMemberPlan(); if(state.offerFlightId)selectOffer(state.offerFlightId,state.offerDay,state.offerManual); }
  if (name === 'flights' && state.forecast) requestAnimationFrame(renderForecast);
  if (name === 'flights' && state.flights.length && !state.loadedFlightId && $('flight-select').value) loadFlight();
  document.dispatchEvent(new CustomEvent('uoption:view', { detail: { name } }));
  return false;
}
window.addEventListener('hashchange', () => { if(state.summary)setView(); else init(); });
document.querySelector('.skip').addEventListener('click', (event) => { event.preventDefault(); document.querySelector('.view:not([hidden]) h1')?.focus(); });
let resizeTimer; window.addEventListener('resize', () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(() => { if (state.forecast) renderForecast(); }, 120); });
$('go-pricing').addEventListener('click', () => {
  if ($('go-pricing').disabled || !state.loadedFlightId) return;
  location.assign(thompsonUrl({flightId:state.loadedFlightId, day:state.day}));
});

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
  const last = observed.at(-1); if (last) svg.append(svgNode('circle', { cx: x(last.day), cy: y(last.value), r: 3.5, fill: '#6F2C91' }));
  svg.append(svgNode('text', { x: left, y: 12, class: 'chart-tick' }, yLabel));
}

function clearFlightSelection() {
  state.request++; state.forecastRequest++; state.forecast=null; state.loadedFlightId=null; state.flight=null; state.history=[];
  $('flight-main').hidden=true; $('flight-main').setAttribute('aria-busy','false');
  $('flight-filter-empty').hidden=false; $('go-pricing').disabled=true; $('publish-button').disabled=true;
  text('flight-date','—'); text('flight-capacity','—'); text('flight-scenario-note','Choose another demand level to find a flight.');
}
function fillForecastFlights(preferred=$('flight-select').value) {
  const matches=state.flights.filter(f=>matchesDemand(f,$('forecast-demand').value));
  $('flight-select').replaceChildren(...matches.map(f=>new Option(`${f.origin} → ${f.destination} · ${(f.departure_at||f.departure_date||'').slice(0,10)} · ${f.flight_id} · ${demandDescription(f)}`,f.flight_id)));
  $('flight-select').disabled=!matches.length;
  text('forecast-demand-status',`${number(matches.length)} of ${number(state.flights.length)} flights match. Demand groups use the fixed D28 forecast.`);
  if(!matches.length){$('flight-select').append(new Option('No flights match this demand level',''));clearFlightSelection();return false;}
  const retained=matches.find(f=>f.flight_id===preferred);
  const demo=matches.find(f=>f.demo_priority===0&&Number(f.demo_d28_releasable)>0);
  $('flight-select').value=(retained||demo||matches[0]).flight_id;
  $('flight-filter-empty').hidden=true;
  return true;
}
async function loadFlight() {
  clearError(); const id = $('flight-select').value; if (!id) {clearFlightSelection();return;}
  const request = ++state.request; state.forecastRequest++; state.forecast = null; state.loadedFlightId = null;
  $('flight-main').hidden=false; $('flight-filter-empty').hidden=true;
  $('flight-main').classList.add('loading'); $('publish-button').disabled = true; $('go-pricing').disabled=true;
  try {
    const data = await api(`/api/flights/${encodeURIComponent(id)}`);
    if (request !== state.request) return;
    state.flight = data.flight || state.flights.find((flight) => flight.flight_id === id);
    state.history = data.history || data.snapshots || []; state.loadedFlightId = id;
    const flight = state.flight;
    text('flight-date', (flight.departure_at || flight.departure_date || '').slice(0, 10));
    text('flight-capacity', `${number(flight.capacity || flight.sellable_capacity)} seats`);
    text('flight-scenario-note',`${demandDescription(flight)}. Synthetic flight; each release round recalculates safe capacity.`);
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
  if(!state.offerManual) selectOffer(state.loadedFlightId,state.day,false);
  $('publish-button').disabled = !canPublish();
  const past = history.filter((r) => r.days_to_departure <= 28).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.booked_seats ?? r.net_booked_seats) }));
  const future = (f.forecast_curve || []).map((r) => ({ day: Number(r.day ?? r.days_to_departure), value: Number(r.expected_booked), low: Number(r.p10), high: Number(r.p90) })).filter((r) => Number.isFinite(r.value) && r.day <= state.day).sort((a, b) => b.day - a.day);
  drawChart('booking-chart', past, future, { maxY: capacity, yLabel: 'Normal bookings' });
  const prices = history.filter((r) => r.days_to_departure <= 180 && r.normal_base_fare != null).map((r) => ({ day: Number(r.days_to_departure), value: Number(r.normal_base_fare) }));
  drawChart('price-chart', prices, [], { yLabel: 'HKD', width: 620, height: 260, minDay: 180 });
  const lastQuote=history.findLast(r=>r.normal_base_fare!=null);
  text('price-caption', `Base fares through D${state.day}.${lastQuote?` Last quote D${lastQuote.days_to_departure}: fees ${money(lastQuote.mandatory_fees)} · total payable ${money(lastQuote.normal_total_fare)}.`:' No observed quote is available.'} Future quotes are not shown.`);
  renderSeatComposition(seats);
  const nextValid=RELEASE_DAYS.includes(seats.nextRound)&&seats.nextRound<state.day;
  const blockedRelease=seats.overage>0||seats.historical||seats.salesClosed||seats.releaseState==='round_already_issued';
  $('go-pricing').disabled=blockedRelease||Boolean(noRelease)||(!RELEASE_DAYS.includes(state.day)&&!nextValid);
  $('go-pricing').textContent=noRelease?'NHPP: no member seats to price':seats.overage>0?'Resolve inventory conflict first':seats.historical?'Historical view · release unavailable':seats.salesClosed?'Sales are closed':seats.releaseState==='round_already_issued'?'This release round is already published':RELEASE_DAYS.includes(state.day)?'Optimize this release round →':nextValid?`Optimize next release D${seats.nextRound} →`:'No release rounds remain';

  if (state.offers.length) renderOffers();
}
// On a release round, NHPP leaving no member headroom means nothing should be released or priced.
function nhppNoRelease(f,seats,day){
  if(!RELEASE_DAYS.includes(day)||seats.historical||seats.salesClosed||seats.overage>0||seats.headroom>=1)return null;
  const ceiling=Math.max(0,Math.floor(Number(f.risk_release_ceiling??f.releasable_seats)||0));
  return {title:`NHPP decision: do not release member seats at D${day}`,
    detail:ceiling<1
      ?`The forecast expects ${number(f.expected_remaining_demand,1)} more normal bookings and protects ${number(seats.protection)} of ${number(seats.physicalRemaining)} empty seats, so 0 member seats are safe to release. There is no member fare to optimize for this round.`
      :`The forecast allows ${number(ceiling)} member seat${ceiling===1?'':'s'}, and existing member bookings already use all of them. No further member seats should be released this round.`};
}
function renderSeatComposition(seats) {
  text('protection-value', `${number(seats.protection)} seats`);
  const bar=$('seat-composition');
  bar.setAttribute('aria-label', `${number(seats.capacity)} total seats. `+seats.parts.map(p=>`${p.label}: ${number(p.value)} seats`).join('. '));
  bar.replaceChildren(...seats.parts.map(p=>{
    const segment=element('span',p.value?number(p.value):'',`seat-part ${p.key}`);
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
  return Boolean(f && state.offerFlightId && RELEASE_DAYS.includes(state.offerDay) && f.releasable_seats > 0 && !f.release_status?.round_already_issued && !f.release_status?.blocked_reason);
}
function chooseDay(day) {
  state.day = day; $('day-slider').value = 28 - day; $('day-slider').setAttribute('aria-valuetext', day ? `${day} days before departure` : 'Sales cutoff'); text('day-number', day); text('day-description', day ? 'Days before departure' : 'Sales cutoff · no new offers');
  document.querySelectorAll('[data-day]').forEach((button) => button.setAttribute('aria-pressed', String(Number(button.dataset.day) === day)));
  loadForecast();
}
let dayTimer;
$('day-slider').addEventListener('input', () => { clearTimeout(dayTimer); const day = 28 - value('day-slider'); text('day-number', day); dayTimer = setTimeout(() => chooseDay(day), 150); });
document.querySelectorAll('[data-day]').forEach((button) => button.addEventListener('click', () => { clearTimeout(dayTimer); chooseDay(Number(button.dataset.day)); }));
$('flight-select').addEventListener('change', loadFlight);
$('forecast-demand').addEventListener('change',()=>{if(fillForecastFlights())loadFlight();});

async function loadOffers() {
  try { const data = await api('/api/offers'); state.offers = data.offers || (Array.isArray(data) ? data : []); renderOffers(); } catch (e) { error(e.message); }
}
function renderOffers() {
  $('offers-list').replaceChildren(...state.offers.map((offer) => {
    const card = element('article', undefined, 'offer-card'); card.dataset.offerId = offer.offer_id || offer.id; const knownFlight = state.flights.find((f) => f.flight_id === offer.flight_id) || {};
    const intro = element('div'); intro.append(element('h3', `${offer.origin || knownFlight.origin || '—'} → ${offer.destination || knownFlight.destination || '—'}`)); intro.append(element('p', (offer.departure_at || knownFlight.departure_at || '').slice(0, 10))); intro.append(element('p', offer.flight_id));
    const price = element('div'); price.append(element('div', money(offer.base_fare), 'offer-price'));
    price.append(element('p', `Base fare · fees ${money(offer.mandatory_fees ?? offer.fees ?? 0)} · total payable ${money(offer.total_payable ?? (Number(offer.base_fare)+Number(offer.mandatory_fees??offer.fees??0)))}`, 'small muted'));
    const inventory = element('div'); const remaining = offer.remaining ?? offer.remaining_seats ?? offer.available ?? offer.quantity;
    inventory.append(element('h3', `${number(remaining)} unspent quota`)); inventory.append(element('p', `D${offer.day} allocation · ${offer.release_version === 'three-round-release-v1' ? 'valid until cutoff' : 'historical expiry rule'}`));
    inventory.append(element('p', 'Subject to current protection and physical seats; checked on booking.'));
    const link = element('a', Number(remaining) > 0 ? 'View member site' : 'Sold out', 'text-link'); link.href = '/members';
    card.append(intro, price, inventory, link); return card;
  }));
  if (!state.offers.length) $('offers-list').append(element('p', 'No member offers yet. Publish an offer from the selected flight above.', 'empty-state'));
}
function offerRouteKey(flight){return `${flight.origin}-${flight.destination}`;}
function populateOfferFlights(selected=''){
  const matches=state.flights.filter(f=>offerRouteKey(f)===$('offer-route').value).sort((a,b)=>(a.departure_at||a.departure_date).localeCompare(b.departure_at||b.departure_date));
  $('offer-flight').replaceChildren(new Option('Choose a departure / flight',''),...matches.map(f=>new Option(`${(f.departure_at||f.departure_date).slice(0,10)} · ${f.flight_id}`,f.flight_id)));
  if(selected)$('offer-flight').value=selected;
}
function initializeOfferSelectors(){
  $('offer-route').replaceChildren(new Option('Choose a route',''),...[...new Set(state.flights.map(offerRouteKey))].sort().map(route=>new Option(route.replace('-', ' → '),route)));
}
function offerOptimizeLink(flightId,day){
  const link=element('a','Optimize this flight','button primary');link.href=thompsonUrl({flightId,day});
  return link;
}
async function selectOffer(flightId,day,manual=true){
  const changed=flightId!==state.offerFlightId||day!==state.offerDay;
  if(changed){$('offer-fare').value='';$('offer-quantity').value=1;}
  const token=++state.offerRequest;state.offerManual=manual;state.offerFlightId=flightId;state.offerDay=day;state.offerForecast=null;$('publish-button').disabled=true;
  const flight=state.flights.find(f=>f.flight_id===flightId), box=$('offer-guidance');
  box.setAttribute('aria-busy','true');box.replaceChildren(element('p','Calculating the current NHPP release limit…'));
  if(!flight){text('offer-flight-context','Choose a departure / flight.');text('offer-release-status','Select a flight to calculate its current safe release limit.');$('offer-quantity').max=0;box.replaceChildren(element('p','Choose a route, departure and release round.'));box.setAttribute('aria-busy','false');return;}
  $('offer-route').value=offerRouteKey(flight);populateOfferFlights(flightId);$('offer-day').value=String(day);
  text('offer-flight-context',`${flight.origin} → ${flight.destination} · ${(flight.departure_at||flight.departure_date).slice(0,10)} · ${flightId} · D${day}`);
  try{
    const result=await api('/api/forecast',{flight_id:flightId,days_to_departure:day});if(token!==state.offerRequest)return;
    state.offerForecast=result.forecast;
    const qty=Math.max(0,Math.floor(state.offerForecast.releasable_seats));$('offer-quantity').max=qty;$('offer-quantity').value=Math.min(Math.max(1,value('offer-quantity')),qty)||1;
    text('offer-release-status',`${qty} new seats can currently be released. ${state.offerForecast.release_status?.blocked_reason||'Existing valid quotas are deducted before new seats are issued.'}`);
    box.replaceChildren(element('p','Review the Thompson result for this flight, then enter the base fare and seat quantity below. Publication is a separate manual action.'));
    if(RELEASE_DAYS.includes(day))box.append(offerOptimizeLink(flightId,day));
    else box.replaceChildren(element('p','Select D28, D14 or D7 to publish a new allocation.'));
  }catch(e){if(token===state.offerRequest)box.replaceChildren(element('p',`Release limit unavailable: ${e.message}`));}
  finally{if(token===state.offerRequest){box.setAttribute('aria-busy','false');$('publish-button').disabled=!canPublish();}}
}
$('offer-route').addEventListener('change',()=>{populateOfferFlights();selectOffer('',Number($('offer-day').value)||28,true);});
$('offer-flight').addEventListener('change',()=>selectOffer($('offer-flight').value,Number($('offer-day').value)||28,true));
$('offer-day').addEventListener('change',()=>selectOffer($('offer-flight').value,Number($('offer-day').value),true));
for(const id of ['offer-fare','offer-quantity'])$(id).addEventListener('input',()=>{$('publish-button').disabled=!canPublish();});
$('offer-form').addEventListener('submit',(event)=>{event.preventDefault();busy($('publish-button'),async()=>{
  if(!canPublish())throw new Error('Choose a valid flight and release round with new safe seats.');
  if(value('offer-quantity')>Number(state.offerForecast.releasable_seats))throw new Error('Requested seats exceed the current forecast release limit.');
  const data=await api('/api/offers',{flight_id:state.offerFlightId,days_to_departure:state.offerDay,quantity:value('offer-quantity'),base_fare:value('offer-fare')});
  notify(`Member offer published: ${(data.offer||data).offer_id||(data.offer||data).id||'saved'}.`);await loadOffers();await selectOffer(state.offerFlightId,state.offerDay,state.offerManual);if(state.loadedFlightId===state.offerFlightId)await loadForecast();
});});
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
  if (setView()) return;
  try {
    const [summary, flightData] = await Promise.all([api('/api/summary'), api('/api/flights')]); state.summary = summary; state.flights = flightData.flights || flightData;
    text('dataset-label', `${number(summary.dataset?.catalog_rows ?? summary.dataset?.rows ?? summary.rows)} daily snapshots · synthetic`);
    populateDemandFilter($('forecast-demand'),state.flights); initializeOfferSelectors();
    if(fillForecastFlights() && location.hash !== '#customers')await loadFlight();
    loadMemberPlan();

  } catch (e) { error(`Unable to load the workspace. ${e.message}`); text('dataset-label', 'Dataset unavailable'); }
}
init();

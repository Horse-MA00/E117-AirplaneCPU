const $ = id => document.getElementById(id);
const state = {flights: [], scope: null, provider: false, busy: false, scopeToken: 0, runToken: 0, runId: null, report: null, timer: null};
const numeric = value => value !== null && value !== undefined && Number.isFinite(Number(value));
const number = value => numeric(value) ? new Intl.NumberFormat('en-HK', {maximumFractionDigits: 2}).format(Number(value)) : '—';
const money = value => numeric(value) ? `HK$${number(value)}` : '—';
const signedMoney = value => numeric(value) ? `${Number(value) > 0 ? '+' : ''}${money(value)}` : '—';
const text = (id, value) => {if ($(id).textContent !== String(value)) $(id).textContent = value;};
const value = id => Number($(id).value);
const active = status => ['queued', 'running'].includes(status);
const resumable = status => ['paused', 'interrupted', 'failed'].includes(status);
const routeName = flight => `${flight.origin} → ${flight.destination}`;
const routeKey = flight => `${flight.origin}-${flight.destination}`;

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || data.message || `Request failed (${response.status})`);
  return data;
}
function error(message = '') {text('feedback-error', message); $('feedback-error').hidden = !message;}
function canStart() {
  return state.provider && state.scope && state.scope.optimization_eligible !== false &&
    Math.floor(Number(state.scope.member_supply_exposure ?? state.scope.releasable_seats) * value('feedback-share')) > 0;
}
function controls() {
  const running = active(state.report?.status);
  $('feedback-start').disabled = state.busy || running || !canStart();
  text('feedback-start', state.busy ? 'Starting…' : running ? 'Experiment is running…' : 'Start LLM pricing experiment');
  $('feedback-resume').disabled = state.busy || running;
  $('feedback-resume-controls').hidden = !resumable(state.report?.status);
}
function fillFlights() {
  const flights = state.flights.filter(flight => routeKey(flight) === $('feedback-route').value);
  $('feedback-flight').replaceChildren(new Option(flights.length ? 'Choose a departure / flight' : 'Choose a route first', ''), ...flights.map(flight => new Option(`${(flight.departure_at || flight.departure_date).slice(0, 10)} · ${flight.flight_id}${flight.demand_band ? ` · ${flight.demand_band} demand` : ''}`, flight.flight_id)));
  $('feedback-flight').disabled = !flights.length;
}
async function loadScope() {
  const token = ++state.scopeToken;
  state.scope = null; $('feedback-initial').value = ''; controls();
  if (!$('feedback-flight').value) {text('feedback-scope', 'Choose a flight to load its fare and available member quota.'); return;}
  text('feedback-scope', 'Loading the observed flight snapshot…');
  try {
    const result = await api('/api/optimization/initial-policy', {flight_id: $('feedback-flight').value, forecast_day: value('feedback-day'), customers: value('feedback-customers'), program_cost: 0});
    if (token !== state.scopeToken) return;
    state.scope = result.scope;
    if (!state.scope) throw new Error('This server did not return a flight snapshot.');
    $('feedback-initial').value = result.initial_member_fare;
    if (Number(result.initial_member_fare) > value('feedback-max')) $('feedback-max').value = result.initial_member_fare;
    const scope = state.scope;
    text('feedback-scope', `${scope.origin} → ${scope.destination} · ${scope.departure_date} · D${scope.as_of_day}. ${number(scope.available_seats)} physical empty seats; ${number(scope.releasable_seats)} forecast member seats.${scope.optimization_eligible === false ? ` ${scope.optimization_unavailable_reason || 'No member offer can be tested at this snapshot.'}` : ''}`);
  } catch (cause) {if (token === state.scopeToken) {state.scope = null; error(cause.message);}}
  finally {if (token === state.scopeToken) controls();}
}
function cell(row, content, heading = false) {const node = document.createElement(heading ? 'th' : 'td'); if (heading) node.scope = 'row'; node.textContent = content; row.append(node); return node;}
function svgNode(tag, attributes = {}, content) {const node = document.createElementNS('http://www.w3.org/2000/svg', tag); for (const [key, val] of Object.entries(attributes)) node.setAttribute(key, val); if (content !== undefined) node.textContent = content; return node;}
function comparisonRows(report) {
  const validation = report.validation;
  if (!validation || ![validation.initial, validation.selected, validation.no_offer].every(item => item && numeric(item.ticket_revenue))) return [];
  return [
    {label: 'Before · initial P₀', fare: report.initial_fare, result: validation.initial, color: '#6a6270'},
    {label: 'After · selected fare', fare: report.selected?.fare, result: validation.selected, color: '#6F2C91'},
    {label: 'Reference · no offer', fare: null, result: validation.no_offer, color: '#24BCDC'},
  ];
}
function drawComparison(rows) {
  const svg = $('feedback-comparison-chart'); svg.replaceChildren();
  const width = Math.max(290, Math.round(svg.getBoundingClientRect().width) || 760), height = 300;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const left = 8, right = width - 12, span = right - left;
  const max = Math.max(1, ...rows.map(row => Number(row.result.ticket_revenue))) * 1.08;
  const axis = 277;
  for (let tick = 0; tick <= 4; tick++) {
    const x = left + span * tick / 4;
    svg.append(svgNode('line', {x1:x, x2:x, y1:33, y2:axis, stroke:'#e8e2ec', 'stroke-width':1}));
    svg.append(svgNode('text', {x, y:296, 'text-anchor':tick === 0 ? 'start' : tick === 4 ? 'end' : 'middle', class:'chart-note'}, `HK$${new Intl.NumberFormat('en-HK', {notation:'compact', maximumFractionDigits:1}).format(max * tick / 4)}`));
  }
  rows.forEach((row, index) => {
    const y = 23 + index * 83;
    svg.append(svgNode('text', {x:left, y, class:'chart-label'}, row.label));
    svg.append(svgNode('text', {x:right, y, 'text-anchor':'end', class:'chart-value'}, money(row.result.ticket_revenue)));
    svg.append(svgNode('rect', {x:left, y:y+12, width:Math.max(0, Number(row.result.ticket_revenue)) / max * span, height:28, fill:row.color, 'data-policy':index, 'data-revenue':row.result.ticket_revenue}));
    svg.append(svgNode('text', {x:left, y:y+56, class:'chart-note'}, `${number(row.result.tickets_sold)} tickets sold${numeric(row.fare) ? ` · base fare ${money(row.fare)}` : ' · normal fares only'}`));
  });
  svg.setAttribute('aria-label', rows.map(row => `${row.label}: ${money(row.result.ticket_revenue)} ticket revenue, ${number(row.result.tickets_sold)} tickets sold`).join('. '));
}
function render(report) {
  state.report = report;
  $('feedback-empty').hidden = true; $('feedback-progress').hidden = false;
  const rounds = report.rounds || [], cfg = report.config || {}, counts = report.counts || {}, scope = report.scope || cfg.scope || {};
  text('feedback-status', ({completed:'Experiment complete', paused:'Paused at call limit', failed:'Experiment stopped', interrupted:'Experiment interrupted', queued:'Experiment queued', running:'Experiment running'})[report.status] || report.status);
  text('feedback-round-count', `${rounds.length} / ${cfg.rounds || '—'} evaluations`);
  $('feedback-progress-bar').max = cfg.rounds || 1; $('feedback-progress-bar').value = rounds.length;
  text('feedback-phase', report.error || `Phase: ${String(report.progress?.phase || report.status).replaceAll('_', ' ')}${report.progress?.round ? ` · round ${report.progress.round}` : ''}`);
  text('feedback-counts', `${number(counts.proposer_calls)} proposal attempts · ${number(counts.customer_calls)} traveller attempts · ${number(counts.provider_calls)} provider calls · ${number(counts.cache_hits)} cache replays · ${number(counts.forced)} forced actions · ${number(counts.failures)} failures`);
  text('feedback-run-scope', `${scope.origin || ''} → ${scope.destination || ''} · ${scope.departure_date || cfg.flight_id || ''} · D${scope.as_of_day ?? cfg.forecast_day ?? '—'} · ${number(cfg.customers)} customer agents per market · no membership fee`);
  $('feedback-export').href = `/api/feedback-pricing/runs/${encodeURIComponent(report.run_id)}/export`;
  $('feedback-events').href = `/api/feedback-pricing/runs/${encodeURIComponent(report.run_id)}/events`;
  const body = $('feedback-round-table'); body.replaceChildren();
  rounds.forEach(round => {const row = document.createElement('tr'); if (round.round === report.selected?.round) row.className = 'selected-row'; cell(row, number(round.round), true); cell(row, money(round.fare)); cell(row, money(round.ticket_revenue)); cell(row, number(round.tickets_sold)); cell(row, round.reason || round.proposal?.reason || (round.round === 1 ? 'Observed normal base fare from the selected flight.' : 'See saved proposal record.')); body.append(row);});
  $('feedback-search').hidden = !rounds.length;
  text('feedback-selected-round', report.selected ? `Best search result: round ${report.selected.round}` : '');
  const rows = comparisonRows(report);
  $('feedback-comparison').hidden = !rows.length; $('feedback-validation-pending').hidden = Boolean(rows.length);
  if (rows.length) {
    const validation = report.validation;
    text('feedback-selected-fare', money(report.selected?.fare)); text('feedback-delta', signedMoney(validation.delta_vs_initial));
    const decisions = {KEEP_INITIAL:'Keep initial fare', REJECT_OFFER:'Offer not supported', RECOMMEND_TESTED_FARE:'Tested fare supported'};
    text('feedback-decision', decisions[validation.decision] || validation.decision || 'Comparison complete');
    text('feedback-comparison-summary', `The selected fare earned ${money(validation.selected.ticket_revenue)} per validation market, compared with ${money(validation.initial.ticket_revenue)} at P₀. Change against no offer: ${signedMoney(validation.delta_vs_no_offer ?? validation.incremental_revenue)}.`);
    const table = $('feedback-comparison-table'); table.replaceChildren(); rows.forEach(item => {const row = document.createElement('tr'); cell(row, item.label, true); cell(row, numeric(item.fare) ? money(item.fare) : 'Normal fares'); cell(row, money(item.result.ticket_revenue)); cell(row, number(item.result.tickets_sold)); table.append(row);});
    text('feedback-validation-detail', `Fresh market seeds: ${(validation.seeds || []).join(', ') || 'See experiment export'}. Standard error of the paired revenue change vs P₀: ${money(validation.standard_error_vs_initial)}. Tickets sold include later cancellations; revenue follows the experiment’s retained base-fare rules. Small synthetic panels do not establish real demand or a global optimum.`);
    drawComparison(rows);
  }
  controls();
}
async function readRun(id, token = ++state.runToken) {
  clearTimeout(state.timer); state.runId = id;
  try {
    const report = await api(`/api/feedback-pricing/runs/${encodeURIComponent(id)}`);
    if (token !== state.runToken || id !== state.runId) return;
    render(report);
    const url = new URL(location.href); url.searchParams.set('run', id); history.replaceState(null, '', url);
    if (active(report.status)) state.timer = setTimeout(() => readRun(id, token), 1600);
  } catch (cause) {if (token === state.runToken) error(cause.message);}
}
async function listRuns() {
  const result = await api('/api/feedback-pricing/runs');
  const runs = Array.isArray(result) ? result : result.runs || [];
  $('feedback-runs').replaceChildren(new Option('Choose an experiment', ''), ...runs.map(run => new Option(`${run.run_id} · ${run.status} · ${run.config?.flight_id || ''}`, run.run_id)));
  if (runs.some(run => run.run_id === state.runId)) $('feedback-runs').value = state.runId;
}
$('feedback-route').addEventListener('change', () => {fillFlights(); loadScope();});
$('feedback-flight').addEventListener('change', loadScope);
$('feedback-day').addEventListener('change', loadScope);
$('feedback-share').addEventListener('change', controls);
$('feedback-form').addEventListener('invalid', event => {const details = event.target.closest('details'); if (details) details.open = true;}, true);
$('feedback-form').addEventListener('submit', async event => {
  event.preventDefault(); if (state.busy || !canStart()) return;
  const config = {flight_id:$('feedback-flight').value, forecast_day:value('feedback-day'), rounds:value('feedback-rounds'), customers:value('feedback-customers'), replicates:value('feedback-replicates'), seed:value('feedback-seed'), release_fraction:value('feedback-share'), fare_min:value('feedback-min'), fare_max:value('feedback-max'), total_call_budget:value('feedback-budget')};
  if (config.fare_min >= config.fare_max || value('feedback-initial') < config.fare_min || value('feedback-initial') > config.fare_max) {error('Price limits must contain P₀, and the minimum must be lower than the maximum.'); return;}
  error(); state.busy = true; controls();
  try {const run = await api('/api/feedback-pricing/runs', config); state.runId = run.run_id; await listRuns(); await readRun(run.run_id);}
  catch (cause) {error(cause.message);}
  finally {state.busy = false; controls();}
});
$('feedback-resume').addEventListener('click', async () => {
  if (!state.runId || state.busy || !$('feedback-additional-budget').reportValidity()) return;
  error(); state.busy = true; controls();
  try {await api(`/api/feedback-pricing/runs/${encodeURIComponent(state.runId)}/resume`, {additional_call_budget:value('feedback-additional-budget')}); await readRun(state.runId); await listRuns();}
  catch (cause) {error(cause.message);}
  finally {state.busy = false; controls();}
});
$('feedback-runs').addEventListener('change', () => {const id = $('feedback-runs').value; if (id) {error(); readRun(id);}});
$('feedback-refresh').addEventListener('click', async () => {try {error(); await listRuns(); if (state.runId) await readRun(state.runId);} catch (cause) {error(cause.message);}});
let resizeTimer;
window.addEventListener('resize', () => {clearTimeout(resizeTimer); resizeTimer = setTimeout(() => {const rows = state.report ? comparisonRows(state.report) : []; if (rows.length) drawComparison(rows);}, 100);});

async function initialize() {
  const results = await Promise.allSettled([api('/api/flights'), api('/api/summary'), listRuns()]);
  if (results[0].status === 'fulfilled') {
    state.flights = results[0].value.flights || results[0].value;
    const routes = [...new Set(state.flights.map(routeKey))].sort();
    $('feedback-route').replaceChildren(new Option('Choose a route', ''), ...routes.map(route => new Option(routeName(state.flights.find(flight => routeKey(flight) === route)), route)));
    $('feedback-route').disabled = !routes.length;
  } else error(results[0].reason.message);
  if (results[1].status === 'fulfilled') {
    const llm = results[1].value.llm || {};
    state.provider = Boolean(llm.live_configured || llm.configured || llm.live_available);
    text('feedback-provider', state.provider ? 'Live LLM calls will be made within the selected budget.' : 'Configure an LLM provider on the server before starting. Saved experiments remain available.');
  } else text('feedback-provider', 'Unable to check the LLM provider. Refresh to retry.');
  if (results[2].status === 'rejected') error(results[2].reason.message);
  controls();
  const saved = new URL(location.href).searchParams.get('run');
  if (saved) {await readRun(saved); $('feedback-runs').value = saved;}
}
initialize().catch(cause => error(cause.message));

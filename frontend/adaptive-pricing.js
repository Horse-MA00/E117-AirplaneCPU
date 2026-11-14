import { analysisDiagnostics, analysisUnavailable, analysisLabel } from './analysis-diagnostics.js';
import { releaseRound } from './thompson-navigation.js';
import { matchesDemand, populateDemandFilter } from './demand-filter.js';
import { populatePlaces, matchesFlightPlaces, setFlightPlaces, flightOptionLabel } from './flight-picker.js';
import { attachPlaceSearch } from './place-search.js';
const $ = id => document.getElementById(id);
const analystDiagnostics = analysisDiagnostics($('run-analysis-diagnostics'));
const money = value => Number.isFinite(Number(value)) && value !== null && value !== undefined ? `HK$${Number(value).toLocaleString('en-HK', {minimumFractionDigits: Number(value) % 1 ? 2 : 0, maximumFractionDigits: 2})}` : '—';
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const count = value => numeric(value) ? value.toLocaleString('en-HK', {maximumFractionDigits: 2}) : '—';
const percentage = value => numeric(value) ? `${(value * 100).toFixed(1)}%` : '—';
const signedMoney = value => numeric(value) ? `${value > 0 ? '+' : value < 0 ? '−' : ''}${money(Math.abs(value))}` : '—';
const retainedRevenue = value => `${Number(((value?.revenue_fraction ?? run?.config?.revenue_fraction ?? .95) * 100).toFixed(2))}%`;
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const active = run => ['queued', 'running'].includes(run?.status);
const CURRENT_VERSION = 'member-thompson-v5-marketing';
const currentRun = value => value?.version === CURRENT_VERSION && value?.config?.profile === 'flexible_deal_seekers';
const scenarioRun = value => Boolean(value?.scenario || value?.scope?.scenario || value?.config?.demo_scenario);
function scenarioDescription(scenario) {
  if (!scenario) return '';
  return `${scenario.label || 'Low-fare stress test'} · Assumed normal base fare ${money(scenario.normal_base_fare)} · Ticket budgets ${count(Number(scenario.budget_multiplier)*100)}% of the standard scenario · Source NHPP quota ${count(scenario.source_scope?.releasable_seats)} seats held fixed from the ${money(scenario.source_scope?.normal_base_fare)} snapshot. These hypothetical inputs are not a new flight forecast.`;
}
const budgetUpper = (rounds,members,panels) => rounds*(2*members+3)+3*panels*members;
const hypothesisLabel = status => ({supported:'Above initial revenue',not_supported:'Below initial revenue'}[status] || String(status||'not_tested').replaceAll('_',' '));
let flights = [], segments = [], defaultWeights = {}, scope = null, run = null, liveConfigured = false;
const TARGET_PROFILE = 'flexible_deal_seekers';
let targetPopulation = null;
let scopeSequence = 0, runSequence = 0, pollTimer = null, submitting = false, savedRuns = [], setupOpen = false, shownRunId = null;

async function api(path, body) {
  const options = body === undefined ? {} : {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  let data;
  try { data = await response.json(); } catch { throw new Error(`The server returned an unreadable response (${response.status}).`); }
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status}).`);
  return data;
}
function error(message = '') { $('page-error').textContent = message; $('page-error').hidden = !message; }
function node(tag, text, className) { const el = document.createElement(tag); if (text !== undefined) el.textContent = text; if (className) el.className = className; return el; }
function renderScenarioNotice(scenario) {
  let notice = $('scenario-notice');
  if (!notice) {
    notice = node('p', '', 'hint'); notice.id = 'scenario-notice';
    $('flight-description').after(notice);
  }
  notice.hidden = !scenario;
  notice.replaceChildren();
  if (scenario) notice.append(
    node('strong', 'Hypothetical low-fare scenario. '),
    document.createTextNode(`Assumed normal base fare ${money(scenario.normal_base_fare)}. Ticket budgets ${count(Number(scenario.budget_multiplier)*100)}% of standard. Source NHPP quota ${count(scenario.source_scope?.releasable_seats)} seats held fixed; no new demand forecast.`));
}
function option(value, text) { const el = node('option', text); el.value = value; return el; }
function flightDate(flight) { return flight.departure_date || String(flight.departure_at || '').slice(0, 10); }
const inDemand = f => matchesDemand(f, $('opt-demand').value || 'all');
function fillFlights(selected = $('flight').value) {
  const from = $('opt-from').value, to = $('opt-to').value;
  const includeRoute = [from, to].some(place => !place || place.startsWith('region:'));
  const matching = flights.filter(f => inDemand(f) && matchesFlightPlaces(f, from, to)).sort((a,b) => `${flightDate(a)}${a.flight_id}`.localeCompare(`${flightDate(b)}${b.flight_id}`));
  $('flight').replaceChildren(option('', matching.length ? 'Choose a departure' : 'No matching flights'), ...matching.map(f => option(f.flight_id, flightOptionLabel(f, {includeRoute}))));
  $('flight').disabled = !matching.length;
  if (matching.some(f => f.flight_id === selected)) $('flight').value = selected;
}
function renderTargetPopulation() {
  if (!targetPopulation) return;
  segments = targetPopulation.segments;
  defaultWeights = Object.fromEntries(segments.map(s => [s.id, Number(s.assumed_weight ?? s.weight ?? 0)]));
  $('weights').replaceChildren(...segments.map((s, index) => {
    const row = node('div', undefined, 'weight-row');
    const label = node('label', `${s.name || s.label || s.id} (%)`); label.htmlFor = `weight-${index}`;
    const input = node('input'); Object.assign(input, {type:'number', min:'0', max:'100', step:'0.01', value:String(Math.round(defaultWeights[s.id]*10000)/100), id:`weight-${index}`}); input.dataset.segment = s.id; input.required = true;
    input.addEventListener('input', updateWeightTotal); row.append(label,input); return row;
  }));
  updateWeightTotal();
}
function restoreNewExperimentWeights(savedRun) {
  // Restore editable weights from a current-method experiment only.
  renderTargetPopulation();
  if (targetPopulation && currentRun(savedRun)) {
    const weights = savedRun.config?.weights || Object.fromEntries((savedRun.population?.segments || []).map(s => [s.id, Number(s.weight ?? s.assumed_weight ?? 0)]));
    setWeights(weights);
  }
}
function readWeights() { return Object.fromEntries([...$('weights').querySelectorAll('input')].map(input => [input.dataset.segment, Number(input.value)/100])); }
function updateWeightTotal() {
  const values = Object.values(readWeights()), sum = values.reduce((a,b) => a+b,0);
  $('weight-total').textContent = `Total: ${(sum*100).toFixed(2)}%`;
  $('weight-total').classList.toggle('error', values.length > 0 && Math.abs(sum-1) > 0.00001);
  updateControls();
}
function setWeights(weights) {
  for (const input of $('weights').querySelectorAll('input')) if (numeric(weights?.[input.dataset.segment])) input.value = String(Math.round(weights[input.dataset.segment]*10000)/100);
  updateWeightTotal();
}
function renderScope(value) {
  scope = value;
  $('normal-fare').textContent = value ? money(value.normal_base_fare) : '—';
  $('starting-fare').textContent = value ? money(value.member_fare_cap ?? value.initial_member_fare) : '—';
  $('member-quota').textContent = value ? count(value.releasable_seats) : '—';
  $('scope-day').textContent = value ? `D${value.as_of_day}` : 'Choose a flight';
  $('flight-title').textContent = value ? `${value.origin} → ${value.destination}` : 'Your Selected Flight';
  $('flight-description').textContent = value ? `${value.departure_date} · ${value.flight_id} · ${value.departure_time || ''}` : 'A separate experiment is created for each flight and release round.';
  renderScenarioNotice(value?.scenario);
  syncRound();
  $('scope-message').textContent = value?.scenario ? scenarioDescription(value.scenario) : value ? value.releasable_seats > 0 ? 'The starting price is the 80% member-fare cap, rounded down to whole HKD. The member seat quota is held fixed during price trials.' : 'No member quota is available at this release round. Choose another flight or round.' : 'Choose a flight to load its normal fare quote and member seat quota.';
  updateControls();
}
// Settings stay folded while a result is on screen; "New experiment" opens them. With no result they are the page.
function updateSetup() {
  const state = run ? (run.recommendation ? 'result' : 'running') : 'setup';
  document.body.dataset.optState = state;
  const folded = Boolean(run) && !setupOpen;
  $('setup-panel').hidden = folded;
  $('new-experiment').hidden = !run;
  $('new-experiment').setAttribute('aria-expanded', String(!folded));
  $('new-experiment').textContent = folded ? 'New experiment' : 'Hide settings';
}
function syncRound() {
  for (const b of document.querySelectorAll('[data-round]')) b.setAttribute('aria-pressed', String(b.dataset.round === $('release-day').value));
}
// The sidebar carries the current flight and round back to Admin (read there from ?flight_id=&forecast_day=).
function updateNavLinks() {
  const fid = $('flight').value, query = fid ? `?${new URLSearchParams({ flight_id: fid, forecast_day: $('release-day').value })}` : '';
  for (const a of document.querySelectorAll('[data-admin-view]')) a.href = `/admin${query}#${a.dataset.adminView}`;
}
function updatePublishLink(value) {
  const link = $('publish-link'), decision = value?.validation?.adoption_result || value?.validation?.decision;
  const fare = value?.validation?.retained_price ?? null, fid = value?.scope?.flight_id ?? value?.config?.flight_id;
  const show = !scenarioRun(value) && value?.status === 'completed' && numeric(fare) && decision !== 'NO_OFFER' && safeId(fid);
  link.hidden = !show; if (!show) { link.removeAttribute('href'); return; }
  link.href = `/admin?${new URLSearchParams({ flight_id: fid, forecast_day: String(value.scope?.as_of_day ?? value.config?.forecast_day ?? $('release-day').value) })}#members`;
  link.firstChild.textContent = `Publish at ${money(fare)} `;
}
// With no experiment in the URL, open the latest completed experiment for this flight and round.
function latestSavedFor(flightId, day) {
  return savedRuns.filter(r => !scenarioRun(r) && r.status === 'completed' && (r.scope?.flight_id ?? r.config?.flight_id) === flightId && String(r.scope?.as_of_day ?? r.config?.forecast_day) === String(day))
    .sort((a, b) => Number(b.updated_at || b.created_at || 0) - Number(a.updated_at || a.created_at || 0))[0] || null;
}
async function loadScope() {
  const sequence = ++scopeSequence;
  renderScope(null); error();
  const flightId = $('flight').value;
  const url = new URL(location.href);
  url.searchParams.delete('day');
  if (flightId) { url.searchParams.set('flight_id',flightId); url.searchParams.set('forecast_day',$('release-day').value); }
  else { url.searchParams.delete('flight_id'); url.searchParams.delete('forecast_day'); }
  history.replaceState(null,'',url);
  updateNavLinks();
  if (!flightId) return;
  $('scope-message').textContent = 'Calculating this flight’s member quota…';
  try {
    const result = await api('/api/adaptive-pricing/scope', {flight_id:flightId, forecast_day:Number($('release-day').value),profile:TARGET_PROFILE});
    if (sequence !== scopeSequence) return;
    // Open the latest saved result before enabling anything, so the page settles in one step.
    const latest = !run && !submitting ? latestSavedFor(flightId, $('release-day').value) : null;
    if (latest) { try { await showRun(latest.run_id, {restorePlaces:false}); return; } catch { /* fall back to the live scope below */ } }
    if (sequence !== scopeSequence) return;
    renderScope(result.scope || result);
  } catch (e) { if (sequence === scopeSequence) { $('scope-message').textContent = 'Flight details could not be loaded.'; error(e.message); } }
}
function updateControls() {
  const isLive = $('mode').value === 'live', busy = submitting || active(run);
  const weights = Object.values(readWeights());
  const weightsValid = targetPopulation && weights.length === 8 && weights.every(n => Number.isFinite(n) && n>=0) && Math.abs(weights.reduce((a,b)=>a+b,0)-1)<0.00001;
  $('setup-fields').disabled = busy;
  updateSetup();
  $('scope-fields').disabled = busy;
  $('start').disabled = busy || scenarioRun(run) || !scope || !(scope.releasable_seats > 0) || !weightsValid || (isLive && !liveConfigured);
  $('start').textContent = submitting ? 'Starting experiment…' : isLive ? 'Start Thompson with live customers' : 'Start Thompson simulation';
  const n=Number($('rounds').value), m=Number($('customers').value), v=Number($('validation-repeats').value);
  const calls=budgetUpper(n,m,v);
  $('customers').min=String(Math.max(1,weights.filter(w=>w>0).length));
  $('call-estimate').textContent = isLive ? `Up to ${calls.toLocaleString()} calls for fresh paired cohorts, up to 3 analyst attempts per round and independent confirmation, before forced choices or identical-policy reuse. The configured call limit applies to the whole experiment.` : 'Uses simulated customer choices. No paid LLM calls are made in this mode.';
}
function clearRun() {
  analystDiagnostics.clear();
  runSequence++; clearTimeout(pollTimer); run = null;
  for (const id of ['run-progress','recommendation','round-section','curve-section','validation-section']) $(id).hidden=true;
  $('empty-state').hidden=false;
  $('member-feedback-link').hidden=true;
  $('publish-link').hidden=true;
  setupOpen=false;shownRunId=null;
  const url=new URL(location.href);url.searchParams.delete('run');url.searchParams.delete('round');history.replaceState(null,'',url);
  $('experiments-nav-link').href='/admin#customers';
  updateControls();
}
function tableRow(values, rowHeader=true) {
  const tr=node('tr'); values.forEach((value,index) => {const cell=node(index===0&&rowHeader?'th':'td',value);if(index===0&&rowHeader)cell.scope='row';tr.append(cell);});return tr;
}
const svgNS='http://www.w3.org/2000/svg';
function svgNode(tag, attrs, text) {const e=document.createElementNS(svgNS,tag);for(const[k,v]of Object.entries(attrs||{}))e.setAttribute(k,String(v));if(text!==undefined)e.textContent=text;return e;}
function plot(svg, rows, {xKey,yKey,xLabel,yLabel,lineClass='model-line',priceX=false,selected=null}) {
  svg.replaceChildren();
  const data=rows.filter(r=>numeric(r[xKey])&&numeric(r[yKey])).sort((a,b)=>a[xKey]-b[xKey]);
  if(!data.length)return;
  const width=Math.max(300,svg.clientWidth||760),height=280,left=70,right=24,top=24,bottom=55;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  const maxX=Math.max(...data.map(r=>r[xKey]),1),minX=priceX?0:Math.min(...data.map(r=>r[xKey]),1),maxY=Math.max(...data.map(r=>r[yKey]),1)*1.12;
  const x=value=>left+(value-minX)/(maxX-minX||1)*(width-left-right), y=value=>height-bottom-value/maxY*(height-top-bottom);
  for(let i=0;i<=3;i++) {const value=maxY*i/3;svg.append(svgNode('line',{x1:left,y1:y(value),x2:width-right,y2:y(value),class:'grid'}),svgNode('text',{x:left-10,y:y(value)+4,'text-anchor':'end'},Math.round(value).toLocaleString()));}
  const ticks=priceX?[0,maxX/2,maxX]:[minX,...(maxX>2?[Math.round((minX+maxX)/2)]:[]),maxX];
  for(const value of [...new Set(ticks)])svg.append(svgNode('text',{x:x(value),y:height-bottom+23,'text-anchor':'middle'},priceX?Math.round(value).toLocaleString():String(value)));
  svg.append(svgNode('text',{x:left,y:12,class:'axis-title'},yLabel),svgNode('text',{x:(left+width-right)/2,y:height-4,'text-anchor':'middle',class:'axis-title'},xLabel));
  svg.append(svgNode('path',{d:data.map((r,i)=>`${i?'L':'M'} ${x(r[xKey])} ${y(r[yKey])}`).join(' '),class:lineClass}));
  if(numeric(selected)&&selected>=minX&&selected<=maxX)svg.append(svgNode('line',{x1:x(selected),x2:x(selected),y1:top,y2:height-bottom,class:'selected-line'}));
}
function renderRounds(rounds) {
  $('round-section').hidden=!rounds.length;
  const rows=rounds.map((r,i)=>({...r,round:r.round??i+1}));
  $('round-table').replaceChildren(...rows.map(r=>{
    const observations=numeric(r.learning_updates)?String(r.learning_updates):'Not recorded';
    const fresh=numeric(r.unique_customers)?`${r.unique_customers} / ${observations}`:observations;
    const test=r.hypothesis_test;
    const feedback=analysisUnavailable(r)||r.analysis_attempts?.length>1 ? analysisLabel(r) : test ? hypothesisLabel(test.status) : r.reused_analysis?'Cached summary':r.analysis_source==='provider_live'?'Fresh LLM summary':r.analysis_source==='synthetic_analysis'?'Rule summary':'Recorded summary';
    const row=tableRow([r.round,money(r.price),count(r.member_buyers),percentage(r.weighted_conversion),money(r.member_revenue),fresh,signedMoney(r.paired_delta_vs_initial),feedback]);
    if(r.analysis_error)row.lastElementChild.append(node('small',r.analysis_error,'analysis-cell'));
    else if(r.analysis_attempts?.some(a=>a.status==='failed'))row.lastElementChild.append(node('small',r.analysis_attempts.filter(a=>a.status==='failed').map(a=>`Attempt ${a.attempt}: ${a.error}`).join(' '),'analysis-cell'));
    if(run?.recommendation?.raw_price===r.price)row.className='selected';return row;
  }));
  $('round-caption').textContent=`${rounds.length} rounds · ${new Set(rows.map(r=>r.price)).size} different prices`;
}
function renderCurve(value) {
  const rounds=value.rounds||[];
  const curve=value.recommendation?.model_curve||value.model_curve||value.recommendation?.curve||value.curve||rounds.at(-1)?.curve||[];
  const points=curve.map(r=>({...r,expected_revenue:r.expected_revenue??r.expected_member_revenue,expected_buyers:r.expected_buyers??r.expected_member_buyers})).filter(r=>numeric(r.price)&&numeric(r.expected_revenue)).sort((a,b)=>a.price-b.price);
  $('curve-section').hidden=!points.length;
  plot($('curve-chart'),points,{xKey:'price',yKey:'expected_revenue',xLabel:'Member base fare · HKD',yLabel:'Expected member revenue · HKD',priceX:true,selected:value.recommendation?.price});
  $('curve-table').replaceChildren(...points.map(r=>tableRow([money(r.price),count(r.expected_buyers),money(r.expected_revenue)])));
  $('curve-table-caption').textContent=value.recommendation ? 'Final fitted model estimates, not observed sales' : 'Pre-round Thompson hypothesis before these choices';
  $('curve-caption').textContent=value.recommendation ? `Final fitted posterior after all search choices. Search selection retains at least ${retainedRevenue(value.recommendation)} of the best estimated member revenue among tested fares. The dashed line marks the adjusted promotional fare, which may not have been tested during search. Curve values are model estimates; the final quoted fare is checked separately on independent panels.` : 'Pre-round Thompson hypothesis before these choices. This is the sampled curve used to propose the latest round’s fare, before that round’s customer decisions were observed; it is not the updated posterior after those choices.';

}
const policyNames={initial:'Formatted initial fare',selected:'Promotional candidate',no_offer:'No member offer'};
function renderValidation(validation) {
  const comparisons=validation?.comparisons||[];
  $('validation-section').hidden=!comparisons.length;
  if(!comparisons.length)return;
  const names=policyNames;
  const weighted=validation.decision_basis==='poststratified_target_mix';
  $('delta-label-initial').textContent=weighted?'Target-weighted revenue vs formatted initial':'Panel revenue change vs formatted initial';
  $('validation-intro').textContent='Independent validation panels compare the formatted initial fare, the promotional candidate and no member offer.';
  $('delta-label-no-offer').textContent=weighted?'Target-weighted revenue vs no offer':'Panel revenue change vs no offer';
  $('delta-initial').textContent=signedMoney(weighted?validation.weighted_delta_vs_initial:validation.delta_vs_initial);
  $('delta-no-offer').textContent=signedMoney(weighted?validation.weighted_delta_vs_no_offer:validation.delta_vs_no_offer);
  $('validation-basis').textContent=weighted?'The comparison uses the target customer weights. Actual panel transactions are also shown in the table.':'The comparison uses actual panel transactions. When inventory binds, weighted extrapolations do not determine the verdict.';
  const revenue=c=>weighted?c.mean_weighted_revenue:c.mean_revenue;
  const maximum=Math.max(1,...comparisons.map(c=>numeric(revenue(c))?revenue(c):0));
  $('comparison-bars').replaceChildren(...comparisons.map(c=>{
    const row=node('div',undefined,`comparison-row ${c.policy==='no_offer'?'no-offer':c.policy}`);
    const track=node('div',undefined,'comparison-track');track.setAttribute('aria-hidden','true');const fill=node('div',undefined,'comparison-fill');fill.style.width=`${Math.max(0,(revenue(c)||0)/maximum*100)}%`;track.append(fill);
    const val=node('div',money(revenue(c)),'comparison-value');
    const buyers=weighted&&numeric(c.mean_weighted_buyers)?`${count(c.mean_weighted_buyers)} weighted buyers`:`${count(c.mean_buyers)} panel buyers`;
    val.append(node('small',buyers));row.append(node('span',names[c.policy]||c.policy,'comparison-label'),track,val);return row;
  }));
  $('validation-table').replaceChildren(...comparisons.map(c=>tableRow([names[c.policy]||c.policy,c.policy==='no_offer'?'Normal fare only':money(c.price),count(c.mean_buyers),money(c.mean_revenue),money(c.mean_weighted_revenue)])));
  const required=validation.break_even_conversion, observed=validation.observed_conversion;
  const hasBreakEven=Object.hasOwn(validation,'break_even_conversion');
  $('break-even-panel').hidden=!hasBreakEven;
  if(hasBreakEven){
    $('break-even-rate').textContent=numeric(required)?percentage(required):'Not attainable at HK$0';
    $('observed-rate').textContent=percentage(observed);
    const quotaLimit=numeric(validation.max_fulfilled_conversion)?validation.max_fulfilled_conversion:null;
    $('break-even-note').textContent=!numeric(required) ? 'A zero member fare cannot recover positive initial revenue through more member ticket sales.' : required===0 ? 'Normal-ticket receipts under the candidate already match the initial ticket revenue; no additional member purchases are required to match it.' : quotaLimit!==null&&required>quotaLimit+1e-8 ? `The member quota allows at most ${percentage(quotaLimit)} fulfilled member purchases, below the required rate. This fare cannot match initial ticket revenue with this quota.` : required>1 ? 'The required rate exceeds 100%; this fare cannot match initial ticket revenue with the available audience.' : validation.break_even_attainable===false ? 'The required purchase rate cannot be fulfilled with the available member quota.' : 'The required rate matches initial basic-ticket revenue after allowing for normal-ticket receipts under the candidate. It is a revenue threshold, not a demand forecast.';
  }
  const parts=[];
  parts.push(`Confirmation uses the actual promotional quotes: initial ${money(validation.initial_price_before_marketing)} → ${money(validation.initial_price)}, selected ${money(validation.selected_price_before_marketing)} → ${money(validation.selected_price)}. Search-price revenue is not reused as the adjusted fare’s result.`);
  const interval=weighted?validation.weighted_initial_delta_interval:validation.initial_delta_interval;
  if(interval&&numeric(interval.low)&&numeric(interval.high))parts.push(`Descriptive paired-world interval vs initial: ${signedMoney(interval.low)} to ${signedMoney(interval.high)} (${count(interval.worlds)} synthetic worlds).`);
  if(validation.caveat)parts.push(validation.caveat);
  if(validation.note)parts.push(validation.note);
  parts.push('These totals include member and normal base-fare sales. Membership fees and operating costs are excluded.');
  $('validation-detail').textContent=parts.join(' ');
}
function renderRun(value) {
  if(!currentRun(value))throw new Error('This experiment is no longer available. Choose a current Thompson Sampling experiment.');
  run=value;
  if(value.run_id!==shownRunId){shownRunId=value.run_id;setupOpen=false;}
  $('run-progress').hidden=false;$('empty-state').hidden=true;
  const completed=value.progress?.completed_rounds??value.rounds?.length??0,total=value.progress?.total_rounds??value.config?.rounds??1;
  $('round-progress').textContent=`${completed} / ${total} price rounds`;
  $('progress-bar').max=Math.max(1,total);$('progress-bar').value=completed;
  const seconds=value.elapsed_seconds??(value.updated_at&&value.created_at?value.updated_at-value.created_at:null);
  $('elapsed').textContent=numeric(seconds)?`${Math.floor(seconds/60)}m ${Math.floor(seconds%60)}s elapsed`:'Elapsed time pending';
  $('run-source').textContent=value.config?.mode==='live'?'Thompson Sampling · live LLM':'Thompson Sampling · offline customers';
  const scenario=value.scenario||value.scope?.scenario;
  renderScenarioNotice(scenario);
  $('run-cohort').textContent=scenario ? scenarioDescription(scenario) : `Flexible bargain travellers · ${value.population?.segments?.length||0} assumed customer groups · This result uses the experiment’s saved population.`;
  const phase=String(['failed','interrupted','paused_at_budget'].includes(value.status)?value.status:value.progress?.phase||value.status||'').replaceAll('_',' ');
  $('run-status').textContent=value.error?`${phase}: ${value.error}`:value.status==='completed'?'Complete. Selection and independent validation are saved.':`${phase.charAt(0).toUpperCase()+phase.slice(1)}. Progress is saved; this page can be reopened.`;
  const counts=value.counts||{};
  analystDiagnostics.update(value);
  const unique=value.progress?.cumulative_unique_customers??value.cumulative_unique_customers;
  $('run-people').textContent=numeric(unique)?`${count(unique)} unique search members · New people in every round; paired quotes share the same people.`:'Fresh paired search cohorts; exact budgets are private to customers.';
  $('run-counts').textContent=`${counts.provider_calls??0} provider calls · ${counts.cache_hits??0} cache hits · ${counts.forced??0} forced decisions · ${counts.failures??0} failures · ${counts.peak_parallel??0} peak parallel calls · ${counts.analyst_retries??0} analyst retries · ${counts.analyst_unavailable??0} unavailable analyses`;
  $('member-feedback-link').hidden=!safeId(value.run_id);
  if(safeId(value.run_id)){
    const params=new URLSearchParams({run:value.run_id});
    const selectedRound=new URL(location.href).searchParams.get('round');
    if(/^[1-9]\d*$/.test(selectedRound||''))params.set('round',selectedRound);
    $('member-feedback-link').href=`/admin?${params}#customers`;
    $('experiments-nav-link').href=$('member-feedback-link').href;
  }
  if(safeId(value.run_id)){$('export-run').href=`/api/adaptive-pricing/runs/${value.run_id}/export`;$('export-run').hidden=false;}
  renderRounds(value.rounds||[]);renderCurve(value);renderValidation(value.validation);
  const recommendation=value.recommendation;
  $('recommendation').hidden=!recommendation;
  if(recommendation){
    const adjustment=recommendation.marketing_adjustment;
    $('recommended-price').textContent=money(recommendation.price);
    $('recommendation-title').textContent='Promotional Base Fare';
    $('recommendation-stage').textContent=value.validation?'Candidate checked on independent panels':'Promotional candidate for validation';
    $('marketing-fare-note').hidden=false;
    $('marketing-fare-note').textContent=`Search selection ${money(recommendation.raw_price)} → promotional quote ${money(recommendation.price)}. Round down to an amount ending in 9; a resulting fare below HK$30 becomes HK$0. The adjusted quote is validated before it can be retained.${adjustment?` Initial comparison: ${money(adjustment.initial_price_before_marketing)} → ${money(adjustment.initial_price)}.`:''}`;
    $('recommendation-reason').textContent=recommendation.reason||`Prefer more member buyers among tested fares with at least ${retainedRevenue(recommendation)} of the best estimated member revenue.`;
    const candidates=[];
    if(numeric(recommendation.revenue_max_price))candidates.push(`Highest predicted revenue: ${money(recommendation.revenue_max_price)}`);
    if(numeric(recommendation.volume_max_price))candidates.push(`Most predicted buyers: ${money(recommendation.volume_max_price)}`);
    $('candidate-tradeoff').textContent=(candidates.length?'Search-price estimates: ':'')+candidates.join(' · ');
    const retained=value.validation?.retained_price, adoption=value.validation?.adoption_result;
    $('retained-price-note').textContent=adoption==='NO_OFFER'?'No member offer retained.':numeric(retained)?`Retained promotional fare after confirmation: ${money(retained)}. No offer is published automatically.`:'';
    const adoptions={ADOPT_CANDIDATE:'Candidate passed the confirmation rule.',KEEP_INITIAL:'Keep the formatted initial fare.',INCONCLUSIVE:'Insufficient evidence to change the formatted initial fare.',NO_OFFER:'Keep normal sales; neither member offer passed confirmation.'};
    $('validation-verdict').textContent=adoption?adoptions[adoption]||adoption:'Waiting for independent validation.';
  }
  updatePublishLink(value);
  updateSetup();
  updateControls();
}
async function fetchRun(id, sequence=runSequence) {
  const value=await api(`/api/adaptive-pricing/runs/${id}`);
  if(sequence!==runSequence)return;
  renderRun(value);
  if(active(value))pollTimer=setTimeout(()=>fetchRun(id,sequence).catch(e=>{if(sequence===runSequence){error(`Progress polling stopped: ${e.message} Use “Refresh saved progress” to retry.`);}}),1500);
}
async function showRun(id, {restorePlaces=true} = {}) {
  if(!safeId(id))throw new Error('Choose a valid saved experiment.');
  // An explicit saved-run selection supersedes any pending flight request.
  // Otherwise its late scope response could start an automatic saved-run load.
  if(restorePlaces)scopeSequence++;
  clearTimeout(pollTimer);const sequence=++runSequence;
  const value=await api(`/api/adaptive-pricing/runs/${id}`);
  if(sequence!==runSequence)return;
  if(!currentRun(value))throw new Error('This experiment is no longer available. Choose a current Thompson Sampling experiment.');
  const url=new URL(location.href);if(url.searchParams.get('run')!==id)url.searchParams.delete('round');url.searchParams.set('run',id);history.replaceState(null,'',url);if([...$('saved-run').options].some(o=>o.value===id)){$('saved-run').value=id;$('load-run').disabled=false;}
  if(value.scope){
    scopeSequence++;
    const savedFlight=flights.find(f=>f.flight_id===value.scope.flight_id);
    // Opening a saved result must restore its actual flight, even when the
    // current demand filter excludes it. A matching filter remains intact.
    if(savedFlight&&!inDemand(savedFlight))$('opt-demand').value='all';
    if(restorePlaces)setFlightPlaces($('opt-from'),$('opt-to'),savedFlight || value.scope);
    $('release-day').value=String(value.scope.as_of_day);
    fillFlights(value.scope.flight_id);renderScope($('flight').value ? value.scope : null);
    syncRound();updateNavLinks();
  }
  restoreNewExperimentWeights(value);
  for(const[id,key]of [['rounds','rounds'],['customers','customers'],['concurrency','concurrency'],['max-calls','max_calls'],['seed','seed'],['validation-repeats','validation_repeats']])if(value.config?.[key]!==undefined)$(id).value=String(value.config[key]);
  if(['synthetic','live'].includes(value.config?.mode))$('mode').value=value.config.mode;
  renderRun(value);error();
  if(active(value))pollTimer=setTimeout(()=>fetchRun(id,sequence).catch(e=>error(e.message)),1500);
}
async function loadSaved() {
  const data=await api('/api/adaptive-pricing/runs');
  savedRuns=(data.runs||[]).filter(r=>safeId(r.run_id));
  const selected=$('saved-run').value;
  $('saved-run').replaceChildren(option('','Choose a saved experiment'),...(data.runs||[]).filter(r=>safeId(r.run_id)).map(r=>option(r.run_id,`${r.config?.name ? `${r.config.name} · ` : ''}${r.config?.flight_id||r.scope?.flight_id||r.run_id} · ${r.status} · ${r.config?.mode==='live'?'Live LLM customers':'Offline customers'}`)));
  if([...$('saved-run').options].some(o=>o.value===selected))$('saved-run').value=selected;
  $('load-run').disabled=!$('saved-run').value;
}
for(const id of ['opt-from','opt-to','opt-demand'])$(id).addEventListener('change',()=>{const selected=$('flight').value;clearRun();fillFlights(selected);loadScope();});
attachPlaceSearch($('opt-from'),{label:'Search departure places'});attachPlaceSearch($('opt-to'),{label:'Search destination places'});
for(const b of document.querySelectorAll('[data-round]'))b.addEventListener('click',()=>{if($('release-day').value===b.dataset.round)return;$('release-day').value=b.dataset.round;$('release-day').dispatchEvent(new Event('change'));});
$('flight').addEventListener('change',()=>{clearRun();loadScope();});
$('release-day').addEventListener('change',()=>{syncRound();clearRun();loadScope();});
for(const id of ['mode','rounds','customers','validation-repeats'])$(id).addEventListener('input',updateControls);
$('max-calls').addEventListener('input',()=>{$('max-calls').removeAttribute('aria-invalid');error();});
$('reset-weights').addEventListener('click',()=>setWeights(defaultWeights));
$('new-experiment').addEventListener('click',async()=>{
  if(scenarioRun(run)){clearRun();await loadScope();setupOpen=true;}else setupOpen=!setupOpen;
  updateSetup();if(setupOpen){$('setup-panel').scrollIntoView({block:'start',behavior:'smooth'});$('mode').focus({preventScroll:true});}
});
$('saved-run').addEventListener('change',()=>{$('load-run').disabled=!$('saved-run').value;});
$('load-run').addEventListener('click',()=>showRun($('saved-run').value).catch(e=>error(e.message)));
$('refresh-run').addEventListener('click',()=>{if(!safeId(run?.run_id))return;clearTimeout(pollTimer);const sequence=++runSequence;error();fetchRun(run.run_id,sequence).catch(e=>error(e.message));});
$('experiment-form').addEventListener('submit',async event=>{
  event.preventDefault();if(submitting||active(run)||scenarioRun(run)||!scope||!targetPopulation)return;
  if(!$('experiment-form').reportValidity())return;
  const weights=readWeights();if(Math.abs(Object.values(weights).reduce((a,b)=>a+b,0)-1)>0.00001){error('Customer weights must total 100%.');return;}
  const body={flight_id:scope.flight_id,forecast_day:Number($('release-day').value),mode:$('mode').value,profile:TARGET_PROFILE,weights};
  for(const[id,key]of [['rounds','rounds'],['customers','customers'],['concurrency','concurrency'],['max-calls','max_calls'],['seed','seed'],['validation-repeats','validation_repeats']])body[key]=Number($(id).value);
  const needed=budgetUpper(body.rounds,body.customers,body.validation_repeats);
  if(body.mode==='live'&&body.max_calls<needed){const field=$('max-calls');field.setAttribute('aria-invalid','true');error(`The call limit must be at least ${needed} for this configuration. Reduce the panel or rounds, or increase the explicit call limit.`);field.focus();return;}
  submitting=true;updateControls();error();
  try{
    const value=await api('/api/adaptive-pricing/runs',body);
    clearTimeout(pollTimer);runSequence++;
    if(safeId(value.run_id)){const url=new URL(location.href);url.searchParams.delete('round');url.searchParams.set('run',value.run_id);history.replaceState(null,'',url);}
    renderRun(value);
    if(safeId(value.run_id)&&active(value))pollTimer=setTimeout(()=>fetchRun(value.run_id).catch(e=>error(e.message)),1500);
    loadSaved().catch(()=>{});
  }catch(e){error(e.message);}finally{submitting=false;updateControls();}
});
async function init(){
  const results=await Promise.allSettled([api('/api/flights'),api('/api/adaptive-pricing/status'),loadSaved()]);
  if(results[0].status==='fulfilled'){
    flights=results[0].value.flights||[];
    populateDemandFilter($('opt-demand'),flights);
    populatePlaces($('opt-from'),flights,'HKG');populatePlaces($('opt-to'),flights,'');
    $('opt-from').disabled=false;$('opt-to').disabled=false;
    fillFlights();
  }else error(results[0].reason.message);
  if(results[1].status==='fulfilled'){
    const value=results[1].value;liveConfigured=Boolean(value.live_configured);
    const opt=$('mode').querySelector('option[value="live"]');opt.disabled=!liveConfigured;opt.textContent=liveConfigured?'Live LLM':'Live LLM · not configured';
    $('provider-note').textContent=liveConfigured?'A provider is configured. Only starting a live experiment makes paid calls.':'Live LLM is unavailable. Thompson Sampling with offline customer choices remains available.';
    const p=value.population;
    targetPopulation=p?.profile===TARGET_PROFILE&&Array.isArray(p.segments)&&p.segments.length===8&&p.segments.every(s=>safeId(s?.id))&&new Set(p.segments.map(s=>s.id)).size===8?p:null;
    renderTargetPopulation();
    if(!targetPopulation)$('provider-note').textContent='Customer configuration is unavailable. Reload before starting a new experiment.';
  }else{$('provider-note').textContent='Experiment setup is unavailable. Saved results can still be viewed; reload before starting a new experiment.';}
  updateControls();
  const params=new URL(location.href).searchParams;
  const id=params.get('run');
  if(id)await showRun(id);
  else {
    const day=releaseRound(params.get('forecast_day')??params.get('day'));
    if(day!==null){$('release-day').value=String(day);syncRound();}
    const fid=params.get('flight_id'), f=flights.find(f=>f.flight_id===fid);
    if(f){if(!inDemand(f))$('opt-demand').value='all';setFlightPlaces($('opt-from'),$('opt-to'),f);fillFlights(fid);await loadScope();}
  }
}
let lastChartWidth=0;
new ResizeObserver(entries=>{
  const width=entries[0]?.contentRect.width;
  if(run&&width&&Math.abs(width-lastChartWidth)>1){lastChartWidth=width;renderRounds(run.rounds||[]);renderCurve(run);}
}).observe(document.querySelector('.results'));
init().catch(e=>error(e.message));

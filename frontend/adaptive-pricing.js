const $ = id => document.getElementById(id);
const money = value => Number.isFinite(Number(value)) && value !== null && value !== undefined ? `HK$${Number(value).toLocaleString('en-HK', {minimumFractionDigits: Number(value) % 1 ? 2 : 0, maximumFractionDigits: 2})}` : '—';
const numeric = value => typeof value === 'number' && Number.isFinite(value);
const count = value => numeric(value) ? value.toLocaleString('en-HK', {maximumFractionDigits: 2}) : '—';
const percentage = value => numeric(value) ? `${(value * 100).toFixed(1)}%` : '—';
const signedMoney = value => numeric(value) ? `${value > 0 ? '+' : value < 0 ? '−' : ''}${money(Math.abs(value))}` : '—';
const retainedRevenue = value => `${Number(((value?.revenue_fraction ?? run?.config?.revenue_fraction ?? .95) * 100).toFixed(2))}%`;
const safeId = value => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);
const active = run => ['queued', 'running'].includes(run?.status);
const paired = value => value?.version === 'member-thompson-v4-paired' || value?.config?.experiment_protocol === 'fresh_paired_cohorts';
const budgetUpper = (rounds,members,panels) => rounds*(2*members+1)+3*panels*members;
const hypothesisLabel = status => ({supported:'Above initial revenue',not_supported:'Below initial revenue'}[status] || String(status||'not_tested').replaceAll('_',' '));
let flights = [], segments = [], defaultWeights = {}, scope = null, run = null, liveConfigured = false;
let populations = new Map(), renderedProfile = null;
const profileNames = {flexible_deal_seekers:'Flexible bargain travellers', broad_coverage:'Broad customer coverage (legacy)'};
const profileOf = value => value?.config?.profile || value?.population?.profile || 'broad_coverage';
let scopeSequence = 0, runSequence = 0, pollTimer = null, submitting = false, auditLoaded = [];

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
function option(value, text) { const el = node('option', text); el.value = value; return el; }
function routeKey(flight) { return `${flight.origin} → ${flight.destination}`; }
function flightDate(flight) { return flight.departure_date || String(flight.departure_at || '').slice(0, 10); }
function fillRoutes() {
  const keys = [...new Set(flights.map(routeKey))].sort();
  $('route').replaceChildren(option('', 'Choose a route'), ...keys.map(key => option(key, key)));
  $('route').disabled = false;
}
function fillFlights(selected = '') {
  const matching = flights.filter(f => routeKey(f) === $('route').value).sort((a,b) => `${flightDate(a)}${a.flight_id}`.localeCompare(`${flightDate(b)}${b.flight_id}`));
  $('flight').replaceChildren(option('', matching.length ? 'Choose a departure' : 'Choose a route first'), ...matching.map(f => option(f.flight_id, `${flightDate(f)} · ${f.flight_id}`)));
  $('flight').disabled = !matching.length;
  if (matching.some(f => f.flight_id === selected)) $('flight').value = selected;
}
function renderPopulation(population, {reset=false}={}) {
  if (!Array.isArray(population?.segments) || !population.segments.length) return;
  const profile=population.profile || 'broad_coverage';
  if (!reset && renderedProfile===profile && segments.map(s=>s.id).join('|')===population.segments.map(s=>s.id).join('|')) return;
  if (![...$('profile').options].some(o=>o.value===profile)) $('profile').append(option(profile,profileNames[profile]||profile));
  $('profile').value=profile;
  renderedProfile=profile;
  $('profile-note').textContent=profile==='flexible_deal_seekers'
    ? 'Students, spontaneous trips and destination-flexible bargain seekers. Assumed target audience, not measured HK Express customer shares.'
    : 'Earlier broad coverage, including fixed-date and essential travel scenarios. Assumed test mix, not measured HK Express customer shares.';
  segments = population.segments;
  const defaultSegments=populations.get(profile)?.segments||segments;
  defaultWeights = Object.fromEntries(defaultSegments.map(s => [s.id, Number(s.assumed_weight ?? s.weight ?? 0)]));
  $('weights').replaceChildren(...segments.map((s, index) => {
    const row = node('div', undefined, 'weight-row');
    const label = node('label', `${s.name || s.label || s.id} (%)`); label.htmlFor = `weight-${index}`;
    const input = node('input'); Object.assign(input, {type:'number', min:'0', max:'100', step:'0.01', value:String(Math.round(Number(s.weight??s.assumed_weight??0)*10000)/100), id:`weight-${index}`}); input.dataset.segment = s.id; input.required = true;
    input.addEventListener('input', updateWeightTotal); row.append(label,input); return row;
  }));
  updateWeightTotal();
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
  $('flight-title').textContent = value ? `${value.origin} → ${value.destination}` : 'Your selected flight';
  $('flight-description').textContent = value ? `${value.departure_date} · ${value.flight_id} · ${value.departure_time || ''}` : 'A separate experiment is created for each flight and release round.';
  $('scope-message').textContent = value ? value.releasable_seats > 0 ? 'The starting price is the 80% member-fare cap, rounded down to whole HKD. The NHPP quota is held fixed during price trials.' : 'No member quota is available at this release round. Choose another flight or round.' : 'Choose a flight to load its normal fare quote and NHPP member quota.';
  updateControls();
}
async function loadScope() {
  const sequence = ++scopeSequence;
  renderScope(null); error();
  const flightId = $('flight').value;
  if (!flightId) return;
  $('scope-message').textContent = 'Calculating this flight’s member quota…';
  try {
    const result = await api('/api/adaptive-pricing/scope', {flight_id:flightId, forecast_day:Number($('release-day').value),profile:$('profile').value});
    if (sequence !== scopeSequence) return;
    renderPopulation(result.population); renderScope(result.scope || result);
  } catch (e) { if (sequence === scopeSequence) { $('scope-message').textContent = 'Flight details could not be loaded.'; error(e.message); } }
}
function updateControls() {
  const isLive = $('mode').value === 'live', busy = submitting || active(run);
  const weights = Object.values(readWeights());
  const weightsValid = weights.length && weights.every(n => Number.isFinite(n) && n>=0) && Math.abs(weights.reduce((a,b)=>a+b,0)-1)<0.00001;
  $('setup-fields').disabled = busy;
  $('start').disabled = busy || !scope || !(scope.releasable_seats > 0) || !weightsValid || (isLive && !liveConfigured);
  $('start').textContent = submitting ? 'Starting experiment…' : isLive ? 'Start live LLM experiment' : 'Start mathematical simulation';
  const n=Number($('rounds').value), m=Number($('customers').value), v=Number($('validation-repeats').value);
  const calls=budgetUpper(n,m,v);
  $('customers').min=String(Math.max(1,weights.filter(w=>w>0).length));
  $('call-estimate').textContent = isLive ? `Up to ${calls.toLocaleString()} calls for fresh paired cohorts and independent confirmation, before forced choices or identical-policy reuse. The configured call limit applies to the whole experiment.` : 'Uses simulated customer choices. No paid LLM calls are made in this mode.';
}
function clearRun() {
  runSequence++; clearTimeout(pollTimer); run = null; auditLoaded=[];
  for (const id of ['run-progress','recommendation','round-section','curve-section','validation-section','feedback-section']) $(id).hidden=true;
  $('empty-state').hidden=false;
  const url=new URL(location.href);url.searchParams.delete('run');history.replaceState(null,'',url);
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
  const width=Math.max(300,svg.clientWidth||760),height=svg.id==='round-chart'?240:280,left=70,right=24,top=24,bottom=55;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  const maxX=Math.max(...data.map(r=>r[xKey]),1),minX=priceX?0:Math.min(...data.map(r=>r[xKey]),1),maxY=Math.max(...data.map(r=>r[yKey]),1)*1.12;
  const x=value=>left+(value-minX)/(maxX-minX||1)*(width-left-right), y=value=>height-bottom-value/maxY*(height-top-bottom);
  for(let i=0;i<=3;i++) {const value=maxY*i/3;svg.append(svgNode('line',{x1:left,y1:y(value),x2:width-right,y2:y(value),class:'grid'}),svgNode('text',{x:left-10,y:y(value)+4,'text-anchor':'end'},Math.round(value).toLocaleString()));}
  const ticks=priceX?[0,maxX/2,maxX]:[minX,...(maxX>2?[Math.round((minX+maxX)/2)]:[]),maxX];
  for(const value of [...new Set(ticks)])svg.append(svgNode('text',{x:x(value),y:height-bottom+23,'text-anchor':'middle'},priceX?Math.round(value).toLocaleString():String(value)));
  svg.append(svgNode('text',{x:left,y:12,class:'axis-title'},yLabel),svgNode('text',{x:(left+width-right)/2,y:height-4,'text-anchor':'middle',class:'axis-title'},xLabel));
  svg.append(svgNode('path',{d:data.map((r,i)=>`${i?'L':'M'} ${x(r[xKey])} ${y(r[yKey])}`).join(' '),class:lineClass}));
  if(svg.id==='round-chart')for(const r of data){const c=svgNode('circle',{cx:x(r[xKey]),cy:y(r[yKey]),r:5,class:'point'});c.append(svgNode('title',{},`Round ${r[xKey]}: ${money(r[yKey])}`));svg.append(c);}
  if(numeric(selected)&&selected>=minX&&selected<=maxX)svg.append(svgNode('line',{x1:x(selected),x2:x(selected),y1:top,y2:height-bottom,class:'selected-line'}));
}
function renderRounds(rounds) {
  $('round-section').hidden=!rounds.length;
  const rows=rounds.map((r,i)=>({...r,round:r.round??r.round_number??i+1}));
  plot($('round-chart'),rows,{xKey:'round',yKey:'price',xLabel:'Price round',yLabel:'Member base fare · HKD',lineClass:'round-line'});
  $('round-table').replaceChildren(...rows.map(r=>{
    const observations=numeric(r.learning_updates)?String(r.learning_updates):'Not recorded';
    const fresh=numeric(r.unique_customers)?`${r.unique_customers} / ${observations}`:observations;
    const test=r.hypothesis_test;
    const feedback=test ? hypothesisLabel(test.status) : r.reused_analysis?'Cached summary':r.analysis_source==='provider_live'?'Fresh LLM summary':r.analysis_source==='synthetic_analysis'?'Rule summary':'Recorded summary';
    const row=tableRow([r.round,money(r.price),count(r.member_buyers),percentage(r.weighted_conversion),money(r.member_revenue),fresh,signedMoney(r.paired_delta_vs_initial),feedback]);
    if(run?.recommendation?.price===r.price)row.className='selected';return row;
  }));
  $('round-caption').textContent=`${rounds.length} rounds · ${new Set(rows.map(r=>r.price)).size} different prices`;
  const previous=$('feedback-round').value;
  $('feedback-round').replaceChildren(...rows.map(r=>option(String(r.round),`Round ${r.round}`)));
  if(rows.some(r=>String(r.round)===previous))$('feedback-round').value=previous;else if(rows.length)$('feedback-round').value=String(rows.at(-1).round);
}
function renderCurve(value) {
  const rounds=value.rounds||[];
  const curve=value.recommendation?.model_curve||value.model_curve||value.recommendation?.curve||value.curve||rounds.at(-1)?.curve||[];
  const points=curve.map(r=>({...r,expected_revenue:r.expected_revenue??r.expected_member_revenue,expected_buyers:r.expected_buyers??r.expected_member_buyers})).filter(r=>numeric(r.price)&&numeric(r.expected_revenue)).sort((a,b)=>a.price-b.price);
  $('curve-section').hidden=!points.length;
  plot($('curve-chart'),points,{xKey:'price',yKey:'expected_revenue',xLabel:'Member base fare · HKD',yLabel:'Expected member revenue · HKD',priceX:true,selected:value.recommendation?.price});
  $('curve-table').replaceChildren(...points.map(r=>tableRow([money(r.price),count(r.expected_buyers),money(r.expected_revenue)])));
  const currentProtocol=paired(value);
  $('curve-table-caption').textContent=currentProtocol ? value.recommendation ? 'Final fitted model estimates, not observed sales' : 'Pre-round Thompson hypothesis before these choices' : 'Model estimates, not observed sales';
  $('curve-caption').textContent=value.recommendation ? `${currentProtocol?'Final fitted posterior after all search choices. ':''}The dashed line marks the selected tested fare. Selection favours more member buyers while retaining at least ${retainedRevenue(value.recommendation)} of the best estimated member revenue among tested fares. The full curve shows model estimates, including untested prices.` : currentProtocol ? 'Pre-round Thompson hypothesis before these choices. This is the sampled curve used to propose the latest round’s fare, before that round’s customer decisions were observed; it is not the updated posterior after those choices.' : 'The model updates after each round. These are estimates for the assumed customer mix, not validated airline demand.';
}
const policyNames={initial:'Initial fare',selected:'Selected fare',no_offer:'No member offer'};
function renderValidation(validation) {
  const comparisons=validation?.comparisons||[];
  $('validation-section').hidden=!comparisons.length;
  if(!comparisons.length)return;
  const weighted=validation.decision_basis==='poststratified_target_mix';
  $('delta-label-initial').textContent=weighted?'Target-weighted revenue vs initial':'Panel revenue change vs initial';
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
    val.append(node('small',buyers));row.append(node('span',policyNames[c.policy]||c.policy,'comparison-label'),track,val);return row;
  }));
  $('validation-table').replaceChildren(...comparisons.map(c=>tableRow([policyNames[c.policy]||c.policy,c.policy==='no_offer'?'Normal fare only':money(c.price),count(c.mean_buyers),money(c.mean_revenue),money(c.mean_weighted_revenue)])));
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
  const interval=weighted?validation.weighted_initial_delta_interval:validation.initial_delta_interval;
  if(interval&&numeric(interval.low)&&numeric(interval.high))parts.push(`Descriptive paired-world interval vs initial: ${signedMoney(interval.low)} to ${signedMoney(interval.high)} (${count(interval.worlds)} synthetic worlds).`);
  if(validation.caveat)parts.push(validation.caveat);
  if(validation.note)parts.push(validation.note);
  parts.push('These totals include member and normal base-fare sales. Membership fees and operating costs are excluded.');
  $('validation-detail').textContent=parts.join(' ');
}
function renderFeedback() {
  const rounds=run?.rounds||[], index=Number($('feedback-round').value);
  const r=rounds.find((row,i)=>(row.round??row.round_number??i+1)===index)||rounds.at(-1);
  $('feedback-section').hidden=!r;
  if(!r)return;
  const analysis=r.analysis||{};
  $('analysis-summary').textContent=typeof analysis==='string'?analysis:analysis.summary||analysis.interpretation||'This round’s decision records are available below or in the experiment export.';
  $('analysis-source-note').textContent=r.reused_analysis?'Cached summary: the analysis from the earlier identical price is reused. No new analysis call or independent observation is implied.':r.analysis_source==='provider_live'?'Fresh LLM analysis of this round’s recorded decisions.':r.analysis_source==='synthetic_analysis'?'Rule-based summary of mathematical customer choices.':'Analysis provenance is available in the experiment export.';
  const hypothesis=r.hypothesis_test;
  $('hypothesis-note').hidden=!hypothesis;
  if(hypothesis){const origin=numeric(hypothesis.source_round)?`From round ${hypothesis.source_round}: `:'';const direction=String(hypothesis.direction||'none').replaceAll('_',' ');$('hypothesis-note').textContent=`${origin}${direction} · ${hypothesisLabel(hypothesis.status)}. ${hypothesis.summary||''}`;}
  let decisions=r.decisions||[];
  if(!decisions.length)decisions=auditLoaded.filter(e=>!e.round||e.round===index).map(e=>e.record||e).filter(e=>e.decision);
  $('feedback-list').replaceChildren(...decisions.slice(0,28).map(item=>{
    const p=item.person||item.observation?.person||{},d=item.decision||item;
    const card=node('article',undefined,'feedback-card');card.append(node('strong',p.segment_label||p.segment||item.segment||'Simulated member'));
    card.append(node('p',String(d.action||'Decision recorded').replaceAll('_',' '),'decision'),node('p',d.reason||'No written reason recorded.'));
    const info=[p.customer_id,item.source,item.settlement?.status].filter(Boolean).join(' · ');if(info)card.append(node('small',info));return card;
  }));
  $('load-audit').hidden=Boolean(decisions.length)||!safeId(run?.run_id);
  $('feedback-note').textContent=`${decisions.length>28?`Showing 28 of ${decisions.length} decisions; the export includes all records. `:''}Reasons explain simulated choices. They are not additional independent purchase observations.`;
}
function renderRun(value) {
  run=value;
  $('run-progress').hidden=false;$('empty-state').hidden=true;
  const completed=value.progress?.completed_rounds??value.rounds?.length??0,total=value.progress?.total_rounds??value.config?.rounds??1;
  $('round-progress').textContent=`${completed} / ${total} price rounds`;
  $('progress-bar').max=Math.max(1,total);$('progress-bar').value=completed;
  const seconds=value.elapsed_seconds??(value.updated_at&&value.created_at?value.updated_at-value.created_at:null);
  $('elapsed').textContent=numeric(seconds)?`${Math.floor(seconds/60)}m ${Math.floor(seconds%60)}s elapsed`:'Elapsed time pending';
  $('run-source').textContent=value.config?.mode==='live'?'Live LLM · simulated members':'Mathematical simulation';
  $('run-cohort').textContent=`${profileNames[profileOf(value)]||profileOf(value)} · ${value.population?.segments?.length||0} assumed customer groups · This result uses the experiment’s saved population.`;
  const phase=String(['failed','interrupted','paused_at_budget'].includes(value.status)?value.status:value.progress?.phase||value.status||'').replaceAll('_',' ');
  $('run-status').textContent=value.error?`${phase}: ${value.error}`:value.status==='completed'?'Complete. Selection and independent validation are saved.':`${phase.charAt(0).toUpperCase()+phase.slice(1)}. Progress is saved; this page can be reopened.`;
  const counts=value.counts||{};
  const unique=value.progress?.cumulative_unique_customers??value.cumulative_unique_customers;
  $('run-people').textContent=numeric(unique)?`${count(unique)} unique search members · New people in every round; paired quotes share the same people.`:paired(value)?'Fresh paired search cohorts; exact budgets are private to customers.':'';
  $('run-counts').textContent=`${counts.provider_calls??0} provider calls · ${counts.cache_hits??0} cache hits · ${counts.forced??0} forced decisions · ${counts.failures??0} failures · ${counts.peak_parallel??0} peak parallel calls`;
  if(safeId(value.run_id)){$('export-run').href=`/api/adaptive-pricing/runs/${value.run_id}/export`;$('export-run').hidden=false;}
  renderRounds(value.rounds||[]);renderCurve(value);renderValidation(value.validation);renderFeedback();
  const recommendation=value.recommendation;
  $('recommendation').hidden=!recommendation;
  if(recommendation){
    $('recommended-price').textContent=money(recommendation.price);
    $('recommendation-stage').textContent=value.validation?'Candidate checked on independent panels':'Selected for validation';
    $('recommendation-reason').textContent=recommendation.reason||`Prefer more member buyers among tested fares with at least ${retainedRevenue(recommendation)} of the best estimated member revenue.`;
    const candidates=[];
    if(numeric(recommendation.revenue_max_price))candidates.push(`Highest predicted revenue: ${money(recommendation.revenue_max_price)}`);
    if(numeric(recommendation.volume_max_price))candidates.push(`Most predicted buyers: ${money(recommendation.volume_max_price)}`);
    $('candidate-tradeoff').textContent=candidates.join(' · ');
    const retained=value.validation?.retained_price, adoption=value.validation?.adoption_result;
    $('retained-price-note').textContent=adoption==='NO_OFFER'?'No member offer retained.':numeric(retained)?`Retained fare after confirmation: ${money(retained)}. No offer is published automatically.`:'';
    const decision=value.validation?.decision;
    const verdicts={REJECT_OFFER:'Keep normal sales: this offer did not add revenue.',IMPROVED_IN_TEST:'Improved in this simulation.',KEEP_INITIAL:'Keep the initial fare.',DID_NOT_IMPROVE:'No improvement over the initial fare.'};
    const adoptions={ADOPT_CANDIDATE:'Candidate passed the confirmation rule.',KEEP_INITIAL:'Keep the initial fare.',INCONCLUSIVE:'Insufficient evidence to change the initial fare.',NO_OFFER:'Keep normal sales; neither member offer passed confirmation.'};
    $('validation-verdict').textContent=adoption?adoptions[adoption]||adoption:decision?verdicts[decision]||String(decision).replaceAll('_',' '):'Waiting for independent validation.';
  }
  updateControls();
}
async function fetchRun(id, sequence=runSequence) {
  const value=await api(`/api/adaptive-pricing/runs/${id}`);
  if(sequence!==runSequence)return;
  renderRun(value);
  if(active(value))pollTimer=setTimeout(()=>fetchRun(id,sequence).catch(e=>{if(sequence===runSequence){error(`Progress polling stopped: ${e.message} Use “Refresh saved progress” to retry.`);}}),1500);
}
async function showRun(id) {
  if(!safeId(id))throw new Error('Choose a valid saved experiment.');
  clearTimeout(pollTimer);const sequence=++runSequence;auditLoaded=[];
  const value=await api(`/api/adaptive-pricing/runs/${id}`);
  if(sequence!==runSequence)return;
  const url=new URL(location.href);url.searchParams.set('run',id);history.replaceState(null,'',url);
  if(value.scope){scopeSequence++;renderScope(value.scope);$('route').value=routeKey(value.scope);fillFlights(value.scope.flight_id);$('release-day').value=String(value.scope.as_of_day);}
  renderPopulation({...value.population,profile:profileOf(value)},{reset:true});
  for(const[id,key]of [['rounds','rounds'],['customers','customers'],['concurrency','concurrency'],['max-calls','max_calls'],['seed','seed'],['validation-repeats','validation_repeats']])if(value.config?.[key]!==undefined)$(id).value=String(value.config[key]);
  if(['synthetic','live'].includes(value.config?.mode))$('mode').value=value.config.mode;
  if(value.config?.weights)setWeights(value.config.weights);
  renderRun(value);error();
  if(active(value))pollTimer=setTimeout(()=>fetchRun(id,sequence).catch(e=>error(e.message)),1500);
}
async function loadSaved() {
  const data=await api('/api/adaptive-pricing/runs');
  const selected=$('saved-run').value;
  $('saved-run').replaceChildren(option('','Choose a saved experiment'),...(data.runs||[]).filter(r=>safeId(r.run_id)).map(r=>option(r.run_id,`${r.config?.flight_id||r.scope?.flight_id||r.run_id} · ${r.status} · ${r.config?.mode||''}`)));
  if([...$('saved-run').options].some(o=>o.value===selected))$('saved-run').value=selected;
  $('load-run').disabled=!$('saved-run').value;
}
$('route').addEventListener('change',()=>{clearRun();fillFlights();loadScope();});
$('flight').addEventListener('change',()=>{clearRun();loadScope();});
$('release-day').addEventListener('change',()=>{clearRun();loadScope();});
$('profile').addEventListener('change',()=>{clearRun();const population=populations.get($('profile').value);if(population)renderPopulation(population,{reset:true});loadScope();});
for(const id of ['mode','rounds','customers','validation-repeats'])$(id).addEventListener('input',updateControls);
$('max-calls').addEventListener('input',()=>{$('max-calls').removeAttribute('aria-invalid');error();});
$('reset-weights').addEventListener('click',()=>setWeights(defaultWeights));
$('saved-run').addEventListener('change',()=>{$('load-run').disabled=!$('saved-run').value;});
$('load-run').addEventListener('click',()=>showRun($('saved-run').value).catch(e=>error(e.message)));
$('feedback-round').addEventListener('change',renderFeedback);
$('refresh-run').addEventListener('click',()=>{if(!safeId(run?.run_id))return;clearTimeout(pollTimer);const sequence=++runSequence;error();fetchRun(run.run_id,sequence).catch(e=>error(e.message));});
$('load-audit').addEventListener('click',async()=>{
  if(!safeId(run?.run_id))return;const id=run.run_id; const sequence=runSequence;$('load-audit').disabled=true;
  try{const result=await api(`/api/adaptive-pricing/runs/${id}/events?limit=100&offset=0`);if(sequence!==runSequence)return;auditLoaded=result.events||result.records||[];renderFeedback();$('audit-message').textContent='Showing available original decisions. Download the experiment for the complete audit.';}catch(e){error(e.message);}finally{$('load-audit').disabled=false;}
});
$('experiment-form').addEventListener('submit',async event=>{
  event.preventDefault();if(submitting||active(run)||!scope)return;
  if(!$('experiment-form').reportValidity())return;
  const weights=readWeights();if(Math.abs(Object.values(weights).reduce((a,b)=>a+b,0)-1)>0.00001){error('Customer weights must total 100%.');return;}
  const body={flight_id:scope.flight_id,forecast_day:Number($('release-day').value),mode:$('mode').value,profile:$('profile').value,weights};
  for(const[id,key]of [['rounds','rounds'],['customers','customers'],['concurrency','concurrency'],['max-calls','max_calls'],['seed','seed'],['validation-repeats','validation_repeats']])body[key]=Number($(id).value);
  const needed=budgetUpper(body.rounds,body.customers,body.validation_repeats);
  if(body.mode==='live'&&body.max_calls<needed){const field=$('max-calls');field.setAttribute('aria-invalid','true');error(`The call limit must be at least ${needed} for this configuration. Reduce the panel or rounds, or increase the explicit call limit.`);field.focus();return;}
  submitting=true;updateControls();error();
  try{
    const value=await api('/api/adaptive-pricing/runs',body);
    clearTimeout(pollTimer);runSequence++;auditLoaded=[];renderRun(value);
    if(safeId(value.run_id)){const url=new URL(location.href);url.searchParams.set('run',value.run_id);history.replaceState(null,'',url);if(active(value))pollTimer=setTimeout(()=>fetchRun(value.run_id).catch(e=>error(e.message)),1500);}
    loadSaved().catch(()=>{});
  }catch(e){error(e.message);}finally{submitting=false;updateControls();}
});
async function init(){
  const results=await Promise.allSettled([api('/api/flights'),api('/api/adaptive-pricing/status'),loadSaved()]);
  if(results[0].status==='fulfilled'){flights=results[0].value.flights||[];fillRoutes();}else error(results[0].reason.message);
  if(results[1].status==='fulfilled'){
    const value=results[1].value;liveConfigured=Boolean(value.live_configured??value.configured??value.provider?.live_configured);
    const opt=$('mode').querySelector('option[value="live"]');opt.disabled=!liveConfigured;opt.textContent=liveConfigured?'Live LLM':'Live LLM · not configured';
    $('provider-note').textContent=liveConfigured?'A provider is configured. Only starting a live experiment makes paid calls.':'Live LLM is unavailable. Mathematical simulations remain available.';
    const known=value.populations||[value.population||value];
    populations=new Map(known.filter(p=>Array.isArray(p.segments)).map(p=>[p.profile||'broad_coverage',p]));
    $('profile').replaceChildren(...[...populations].map(([id])=>option(id,profileNames[id]||id)));
    $('profile').disabled=populations.size<1;
    renderPopulation(value.population||value);
  }else{$('provider-note').textContent='Provider status is unavailable. Live experiments are disabled.';}
  updateControls();
  const id=new URL(location.href).searchParams.get('run');if(id)await showRun(id);
  else {const fid=new URL(location.href).searchParams.get('flight_id');const f=flights.find(f=>f.flight_id===fid);if(f){$('route').value=routeKey(f);fillFlights(fid);await loadScope();}}
}
let lastChartWidth=0;
new ResizeObserver(entries=>{
  const width=entries[0]?.contentRect.width;
  if(run&&width&&Math.abs(width-lastChartWidth)>1){lastChartWidth=width;renderRounds(run.rounds||[]);renderCurve(run);}
}).observe(document.querySelector('.results'));
init().catch(e=>error(e.message));

import { renderContributionExplanation } from './contribution-explanation.js';
import { demandDescription, matchesDemand, populateDemandFilter } from './demand-filter.js';
const $ = id => document.getElementById(id);
const state = { runId:null, data:null, timer:null, request:0, loading:false, configured:false, listed:false, flights:[], scope:null, scopeRequest:0 };
const num = (v, digits=0) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-HK',{maximumFractionDigits:digits});
const money = v => v == null ? '—' : `HK$${num(v,2)}`;
const signed = v => v == null || !Number.isFinite(Number(v)) ? '—' : `${Number(v)>=0?'+':'−'}HK$${num(Math.abs(Number(v)),2)}`;
// Contribution of the matched no-offer market; older runs only stored total and incremental.
const baselineOf = r => Number.isFinite(r?.baseline_contribution) ? r.baseline_contribution : Number.isFinite(r?.total_contribution) && Number.isFinite(r?.incremental_contribution) ? Math.round((r.total_contribution-r.incremental_contribution)*100)/100 : null;
const pct = v => v == null ? '—' : `${num(Number(v)*100,1)}%`;
const name = mode => mode === 'live' ? 'Live LLM' : 'Mathematical';
const running = status => ['queued','running'].includes(status);
const scopeEligible = scope => Boolean(scope && scope.optimization_eligible!==false && Number(scope.member_supply_exposure??scope.releasable_seats)>0);
// The NHPP release rule decides supply before any price is tested. Mirrors optimization.start().
function releaseDecision(scope, share) {
  if(!scope)return null;
  const day=`D${scope.as_of_day}`;
  if(!scopeEligible(scope))return {title:`NHPP decision: do not release member seats at ${day}`,
    detail:`The forecast expects ${num(scope.expected_remaining_demand,1)} more normal bookings for ${num(scope.available_seats)} empty seats. After protecting normal demand, 0 member seats can be released, so there is no member fare to test. Choose another flight or release round.`};
  const seats=Number(scope.releasable_seats)||0;
  if(Math.floor(seats*share)<1)return {title:`Do not release member seats at ${day} with a ${num(share*100)}% release share`,
    detail:`NHPP allows ${num(seats)} member seat${seats===1?'':'s'}, but ${num(share*100)}% of that rounds down to 0. Raise the release share to test prices.`};
  return null;
}
const evidenceLabel = row => ({uninformative_no_supply:'No member supply',uninformative_no_member_exposure:'No traveller saw a member offer',no_member_sales:'Offers seen; no member sales',observed_member_sales:'Member purchases observed'})[row.price_evidence_status]||'Historical exposure not recorded';
const canResume = status => ['paused','paused_at_budget','interrupted','failed'].includes(status);
const node = (tag, text, className) => { const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el; };
const text = (id, content) => { $(id).textContent=content; };
const val = id => Number($(id).value);
async function api(path, body) {
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  let data;try{data=await response.json();}catch{throw new Error(`Unreadable server response (${response.status}).`);}
  if(!response.ok)throw new Error(typeof data.error==='string'?data.error:`Request failed (${response.status}).`);
  return data;
}
function showError(message) {text('optimization-error',message);$('optimization-error').hidden=!message;}
function showDecision(){
  const decision=releaseDecision(state.scope,val('optimization-share')),box=$('optimization-no-release');
  box.hidden=!decision;box.replaceChildren(...(decision?[node('strong',decision.title),document.createTextNode(decision.detail)]:[]));
  return decision;
}
function controls() {
  const live=$('optimization-mode').value!=='math';
  $('optimization-budget-field').hidden=!live && !['both','live'].includes(state.data?.config?.mode);
  $('optimization-budget').disabled=$('optimization-budget-field').hidden; $('optimization-total-budget').disabled=$('optimization-budget-field').hidden;
  const blocked=showDecision();
  $('optimization-start').disabled=state.loading || running(state.data?.status) || !state.scope || Boolean(blocked);
  text('optimization-start',state.loading?'Starting…':running(state.data?.status)?'Optimization is running…':'Start optimization');
  $('optimization-resume').disabled=state.loading || running(state.data?.status);
  document.querySelector('label[for=optimization-total-budget]').textContent=canResume(state.data?.status)?'Additional LLM decisions':'Total LLM decision budget';
}
function provider(configured) {
  state.configured=configured;
  for(const mode of ['both','live']) {
    const option=$('optimization-mode').querySelector(`option[value="${mode}"]`);
    option.disabled=!configured;option.textContent=mode==='both'?(configured?'Math + Live LLM':'Math + Live LLM · provider unavailable'):(configured?'Live LLM':'Live LLM · provider unavailable');
  }
}
document.addEventListener('uoption:provider',event=>provider(event.detail.configured));
$('optimization-mode').addEventListener('change',controls);
$('optimization-form').addEventListener('invalid',event=>{const details=event.target.closest('details');if(details)details.open=true;requestAnimationFrame(()=>$('optimization-form').querySelector(':invalid')?.focus());},true);
const statusLabel = status => ({queued:'Queued',running:'Running',completed:'Completed',paused:'Total decision limit reached',paused_at_budget:'Total decision limit reached',interrupted:'Interrupted',failed:'Run needs attention'})[status] || status;
function svgNode(tag,attrs={},content) {const el=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))el.setAttribute(k,v);if(content!==undefined)el.textContent=content;return el;}
function chart(id,tracks,key,{initialKey,caption}={}) {
  const svg=$(id);const width=Math.max(290,Math.round(svg.getBoundingClientRect().width)||440),height=id==='optimization-profit-chart'?240:215;
  svg.replaceChildren();svg.setAttribute('viewBox',`0 0 ${width} ${height}`);svg.append(svgNode('title',{},caption));
  const series=tracks.map(track=>({mode:track.mode,points:[...(initialKey?[{round:0,value:state.data.config[initialKey]}]:[]),...track.rounds.filter(r=>Number.isFinite(Number(r[key]))).map(r=>({round:r.round,value:Number(r[key])}))]}));
  const values=series.flatMap(s=>s.points.map(p=>p.value));
  if(!values.length){svg.append(svgNode('text',{x:width/2,y:100,'text-anchor':'middle',class:'chart-tick'},'Appears after the first completed round'));return;}
  const min=Math.min(0,...values),max=Math.max(1,...values),span=max-min||1,low=min<0?min-span*.08:0,high=max+span*.1;
  const left=64,right=18,top=16,bottom=29;const rounds=Math.max(1,...series.flatMap(s=>s.points.map(p=>p.round)));
  const x=round=>left+round/rounds*(width-left-right),y=v=>top+(high-v)/(high-low)*(height-top-bottom);
  for(let n=0;n<=3;n++){const v=low+(high-low)*n/3;svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(v),y2:y(v),class:'chart-grid'}));svg.append(svgNode('text',{x:left-8,y:y(v)+4,'text-anchor':'end',class:'chart-tick'},num(v)));}
  if(min<0)svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(0),y2:y(0),stroke:'#9F93A7','stroke-dasharray':'3 3'}));
  const tickRounds=rounds<=6?Array.from({length:rounds+1},(_,i)=>i):[0,Math.floor(rounds/2),rounds];
  for(const round of tickRounds)svg.append(svgNode('text',{x:x(round),y:height-6,'text-anchor':round===0?'start':round===rounds?'end':'middle',class:'chart-tick'},round===0?'Initial':`R${round}`));
  for(const s of series) {
    const color=s.mode==='live'?'#087D96':'#6F2C91';
    svg.append(svgNode('path',{d:s.points.map((p,i)=>`${i?'L':'M'}${x(p.round)},${y(p.value)}`).join(' '),stroke:color,'stroke-width':2.5,fill:'none',...(s.mode==='live'?{'stroke-dasharray':'6 3'}:{})}));
    for(const p of s.points) {
      const point=svgNode('circle',{cx:x(p.round),cy:y(p.value),r:3.5,fill:color});point.append(svgNode('title',{},`${name(s.mode)}, ${p.round===0?'initial price':`round ${p.round}`}: ${money(p.value)}`));svg.append(point);
    }
  }
}
function priceProfit(tracks){
  const svg=$('optimization-price-profit'),cards=$('optimization-tradeoffs');svg.replaceChildren();cards.replaceChildren();
  const allRows=tracks.flatMap(t=>t.rounds.filter(r=>Number.isFinite(r.total_contribution)).map(r=>({...r,mode:t.mode})));
  const rows=allRows.filter(row=>row.price_evidence_qualified===true);
  text('optimization-price-evidence',!allRows.length?'Waiting for evaluated customer decisions.':!rows.length?'No member-price evidence: no usable member offer exposure was recorded. Financial audit rows below are not a price-response curve.':`${rows.length} tested prices had customer exposure to a member offer. ${allRows.length-rows.length} uninformative evaluations excluded. These are tested candidates; only independent validation can recommend an offer.`);
  text('optimization-curve-protocol',state.data.config.price_comparison_protocol==='fixed-seat-profile-local-fare-v1'?'Pass fee, seat-protection profile and matched markets stay fixed across tested prices. Proposed forecast updates are recorded separately.':'Historical run: seat protection may differ by round; price effects are not isolated.');
  const width=Math.max(290,Math.round(svg.getBoundingClientRect().width)||700),height=320;
  svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
  svg.append(svgNode('title',{},'Member base price versus simulated flight contribution; point size represents member buyers'));
  if(!rows.length){svg.append(svgNode('text',{x:15,y:80,class:'chart-tick'},allRows.length?'No informative member-price curve to display.':'Available after a scoped flight evaluation completes.'));text('optimization-price-detail',allRows.length?'Inspect supply, member buyers and normal buyers in the audit table.':'No evaluated price points yet.');return;}
  const highest=rows.reduce((a,b)=>b.total_contribution>a.total_contribution?b:a);
  const buyers=rows.reduce((a,b)=>(b.mean_member_buyers??0)>(a.mean_member_buyers??0)?b:a);
  const margins=rows.filter(r=>Number.isFinite(r.profit_margin));
  const margin=margins.length?margins.reduce((a,b)=>b.profit_margin>a.profit_margin?b:a):null;
  for(const [label,row,metric] of [['Highest tested contribution',highest,money(highest.total_contribution)],['Most member buyers',buyers,`${num(buyers.mean_member_buyers,1)} member buyers`],['Highest tested margin',margin,margin?pct(margin.profit_margin):'—']]){
    const card=node('div');card.append(node('span',label),node('strong',row?money(row.member_fare):'—'),node('small',row?`${name(row.mode)} · ${metric}${label==='Highest tested contribution'?` · ${signed(row.incremental_contribution)} vs no offer`:''}${row.feasible?'':' · service unmet'}`:'No revenue to calculate a margin'));cards.append(card);
  }
  const left=66,right=20,top=28,bottom=52;
  const xmin=Math.min(...rows.map(r=>r.member_fare)),xmax=Math.max(...rows.map(r=>r.member_fare)),xspan=Math.max(1,xmax-xmin);
  const baselines=tracks.map(t=>({mode:t.mode,value:baselineOf(rows.find(r=>r.mode===t.mode))})).filter(b=>Number.isFinite(b.value));
  const levels=[...rows.map(r=>r.total_contribution),...baselines.map(b=>b.value)];
  const low=Math.min(...levels),high=Math.max(...levels);
  const span=Math.max(1,high-low,Math.abs(high)*.005),ymin=low-span*.15,ymax=high+span*.15;
  const x=p=>left+(p-xmin)/xspan*(width-left-right),y=v=>top+(ymax-v)/(ymax-ymin)*(height-top-bottom);
  for(let i=0;i<=4;i++){const v=ymin+(ymax-ymin)*i/4;svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(v),y2:y(v),class:'chart-grid'}),svgNode('text',{x:left-8,y:y(v)+4,'text-anchor':'end',class:'chart-tick'},num(v)));}
  for(let i=0;i<=(width<500?2:4);i++){const value=xmin+xspan*i/(width<500?2:4);svg.append(svgNode('text',{x:x(value),y:height-25,'text-anchor':'middle',class:'chart-tick'},num(value,2)));}
  svg.append(svgNode('text',{x:left,y:14,class:'chart-tick'},'Flight contribution · HK$'),svgNode('text',{x:width/2,y:height-5,'text-anchor':'middle',class:'chart-tick'},'Member base fare · HK$'));
  // Dashed line: the same flight without the membership offer. Each stem shows the gain or loss against it.
  for(const b of baselines){const color=b.mode==='live'?'#087D96':'#6F2C91';
    svg.append(svgNode('line',{x1:left,x2:width-right,y1:y(b.value),y2:y(b.value),stroke:color,'stroke-width':1.5,'stroke-dasharray':'7 5',opacity:.75,class:'baseline-line','data-baseline':b.value}));
    svg.append(svgNode('text',{x:width-right,y:y(b.value)-6,'text-anchor':'end',class:'chart-tick baseline-label',fill:color},`Without member offer${baselines.length>1?` · ${name(b.mode)}`:''} · ${money(b.value)}`));
    for(const r of rows.filter(r=>r.mode===b.mode))svg.append(svgNode('line',{x1:x(r.member_fare),x2:x(r.member_fare),y1:y(b.value),y2:y(r.total_contribution),stroke:r.total_contribution>=b.value?'#1C8A5A':'#B22946','stroke-width':2,opacity:.55,class:'gain-stem'}));
  }
  const describe=r=>text('optimization-price-detail',`${name(r.mode)} · fare ${money(r.member_fare)} · contribution ${money(r.total_contribution)} · without member offer ${money(baselineOf(r))} · difference ${signed(r.incremental_contribution)} · contribution margin ${pct(r.profit_margin)} · ${num(r.mean_member_buyers,1)} member buyers / ${num(r.mean_regular_buyers,1)} regular buyers · ${num(r.mean_new_members,1)} joins · ${num(r.member_supply_exposure,1)} seats issued / ${num(r.mean_member_offer_customers,1)} travellers saw offers · ${num(r.mean_member_tickets,1)} member / ${num(r.mean_regular_tickets,1)} regular tickets · ${r.feasible?'service target met':'service target unmet'}.`);
  for(const track of tracks){
    const color=track.mode==='live'?'#087D96':'#6F2C91',points=rows.filter(r=>r.mode===track.mode).sort((a,b)=>a.member_fare-b.member_fare);
    // A true price curve only joins evaluations with the same membership fee.
    for(const fee of new Set(points.map(r=>r.membership_fee))){const fixed=points.filter(r=>r.membership_fee===fee);svg.append(svgNode('polyline',{points:fixed.map(r=>`${x(r.member_fare)},${y(r.total_contribution)}`).join(' '),fill:'none',stroke:color,'stroke-width':2,...(track.mode==='live'?{'stroke-dasharray':'5 4'}:{})}));}
    for(const row of points){const point=svgNode('circle',{cx:x(row.member_fare),cy:y(row.total_contribution),r:4+Math.min(7,Math.sqrt(Math.max(0,row.mean_member_buyers||0))),fill:color,stroke:row===highest?'#24BCDC':'white','stroke-width':row===highest?4:1.5,tabindex:0,role:'button','data-price':row.member_fare,'data-profit':row.total_contribution,'aria-label':`${name(row.mode)} fare ${money(row.member_fare)}, contribution ${money(row.total_contribution)}, ${num(row.mean_member_buyers,1)} member buyers`});
      point.append(svgNode('title',{},point.getAttribute('aria-label')));for(const event of ['focus','mouseenter','click'])point.addEventListener(event,()=>describe(row));point.addEventListener('keydown',event=>{if(event.key==='Enter')describe(row);if(event.key===' ')event.preventDefault();});point.addEventListener('keyup',event=>{if(event.key===' '){event.preventDefault();describe(row);}});svg.append(point);
    }
  }
  describe(highest);
}
function renderCards(tracks) {
  $('optimization-track-cards').replaceChildren(...tracks.map(track=>{
    const latest=track.rounds.at(-1),best=track.best;
    const card=node('section',undefined,`optimizer-track ${track.mode}`),heading=node('h2',name(track.mode));
    heading.append(node('span',latest?`Round ${latest.round} · latest tested`:'Initial prices'));
    const prices=node('div',undefined,'track-prices');
    for(const [label,amount]of [['Member base fare',latest?.member_fare??state.data.config.initial_member_fare]]){
      const item=node('div');item.append(node('span',label),node('strong',money(amount)));prices.append(item);
    }
    const profit=node('p',undefined,'track-profit');
    if(latest){profit.append(node('strong',`${money(latest.incremental_contribution)} incremental`),document.createTextNode(` · ${pct(latest.service_rate)} mean new-member use`));}
    else profit.textContent='Waiting for the first market replay to finish.';
    card.append(heading,prices,profit);
    if(latest)card.append(node('p',`${evidenceLabel(latest)} · ${num(latest.mean_member_buyers,1)} member buyers · ${num(latest.mean_regular_buyers,1)} regular buyers · ${num(latest.member_supply_exposure,1)} member seats issued.`,'small muted'));
    if(best){const retained=node('p',undefined,'small muted');retained.append(node('strong','Retained test candidate: '),document.createTextNode(`${money(best.member_fare)} member fare.${best.feasible?'':' Service target unmet.'}`));card.append(retained);}
    return card;
  }));
}
function renderTable(tracks) {
  const rows=tracks.flatMap(track=>track.rounds.map(round=>({...round,mode:track.mode}))).sort((a,b)=>a.round-b.round||a.mode.localeCompare(b.mode));
  $('optimization-rounds-table').replaceChildren(...rows.map(row=>{
    const tr=node('tr'),th=node('th',`${name(row.mode)} / ${row.round}${row.search_step==='formula_p_star'?' · formula P*':''}`);th.scope='row';tr.append(th);
    for(const item of [money(row.member_fare),money(row.total_contribution),num(row.mean_member_buyers,1),num(row.mean_regular_buyers,1),num(row.mean_new_members,1),`${num(row.mean_member_tickets,1)} / ${num(row.mean_regular_tickets,1)}`,`${num(row.member_supply_exposure,1)} seats / ${num(row.mean_member_offer_customers,1)} viewers`,pct(row.profit_margin),money(baselineOf(row)),signed(row.incremental_contribution)])tr.append(node('td',item));
    const result=node('td');result.append(node('span',row.price_evidence_qualified===false?evidenceLabel(row):row.accepted?'Retained test':row.feasible?'Tested':'Service unmet',row.accepted?'round-kept':'round-rejected'));tr.append(result);return tr;
  }));
  if(!rows.length){const tr=node('tr'),td=node('td','No completed rounds yet.');td.colSpan=12;tr.append(td);$('optimization-rounds-table').append(tr);}
}
function renderFinal(tracks) {
  const root=$('optimization-final-content');root.replaceChildren();
  for(const track of tracks) {
    const item=node('div',undefined,'final-option'),body=node('div'),heading=node('strong',name(track.mode));
    const decision=track.decision||'PENDING';heading.append(node('span',decision==='OFFER'?'Validated offer':decision==='NO_OFFER'?(state.data.config.scope?'No offer for this flight':'No member offer'):'Validation pending','decision-chip'));body.append(heading);
    if(decision==='OFFER' && track.best && track.validation){
      body.append(node('p',`${money(track.best.member_fare)} member base fare`),node('p',`Independent market: ${money(track.validation.incremental_contribution)} incremental contribution · ${pct(track.validation.service_rate)} mean new-member use.`,'small muted'));
      body.append(node('p','Prepare a draft for this exact flight and release round. Current inventory is checked again.','small muted'));
      const button=node('button','Use these prices','button primary');button.type='button';button.disabled=state.data.status!=='completed'||!state.data.config.scope;button.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('uoption:prepare-policy',{detail:{...track.best,run_id:state.data.run_id,mode:track.mode,flight_id:state.data.config.scope.flight_id,forecast_day:state.data.config.scope.as_of_day,release_fraction:state.data.config.release_fraction}})));item.append(body,button);
    }else if(decision==='NO_OFFER'){
      body.append(node('p',state.data.config.scope?'The tested offer did not pass this flight’s search and independent validation requirements. Later member trips and renewal revenue are outside this result.':'The tested member offer did not pass both the search and independent validation requirements.'));
      const reasons=track.contribution_explanation?.no_offer_reasons;
      if(reasons?.length){const list=node('ul',undefined,'decision-reasons');for(const reason of reasons)list.append(node('li',reason));body.append(list);}
      if(track.validation)body.append(node('p',`Independent market: ${money(track.validation.incremental_contribution)} incremental contribution · ${pct(track.validation.service_rate)} mean new-member use.`,'small muted'));
      item.append(body);
    }else{
      body.append(node('p',track.rounds.length?'The current best candidate still needs a completed independent validation.':'Complete the market rounds to compare prices.'));item.append(body);
    }
    root.append(item);
  }
}
function renderFeedback(tracks){
  const root=$('optimization-forecast-feedback');root.replaceChildren();
  for(const track of tracks){
    const latest=track.rounds.at(-1),validated=Boolean(track.validation?.seat_feedback),profile=validated?track.best?.seat_calibration:latest?.seat_calibration,feedback=validated?track.validation.seat_feedback:latest?.seat_feedback;
    if(!profile&&!feedback)continue;
    const section=node('section');section.append(node('h3',`${name(track.mode)} · ${validated?'independent validation':'search replay diagnostics'}`));
    if(profile){const d28=profile.horizons?.['28'];section.append(node('p',`Profile generation ${num(profile.generation??0)}${d28?` · D28 demand scale ${num(d28.rate_scale,3)} · additional protection ${num(d28.extra_protection,1)} seats`:''}.`,'small muted'));}
    if(feedback?.horizons){const wrap=node('div',undefined,'table-wrapper');wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-label',`${name(track.mode)} forecast diagnostics`);const table=node('table'),thead=node('thead'),head=node('tr');for(const label of ['Horizon','Base error','Adjusted error','Base coverage','Adjusted coverage']){const th=node('th',label);th.scope='col';head.append(th);}thead.append(head);table.append(thead);const tbody=node('tbody');for(const[day,f]of Object.entries(feedback.horizons)){const tr=node('tr');for(const item of [`D${day}`,num(f.base_mae,1),num(f.adjusted_mae,1),pct(f.base_coverage),pct(f.adjusted_coverage)])tr.append(node('td',item));tbody.append(tr);}table.append(tbody);wrap.append(table);section.append(wrap);}
    root.append(section);
  }
}
function render(data){
  state.data=data;
  $('optimization-empty').hidden=true;$('optimization-progress').hidden=false;$('optimization-results').hidden=false;
  const progress=data.progress||{},counts=data.counts||{},tracks=data.tracks||[];
  text('optimization-status',statusLabel(data.status));
  const scope=data.config.scope; text('optimization-result-scope',scope?`${scope.origin} → ${scope.destination} · ${scope.departure_date} · ${scope.flight_id} · D${scope.as_of_day}`:'Historical unscoped experiment · unavailable for flight-specific publishing');
  $('optimization-horizon-note').hidden=!scope;
  text('optimization-round-count',`${num(progress.completed_rounds||0)} / ${num(progress.total_rounds??data.config.rounds*tracks.length)} rounds`);
  $('optimization-progress-bar').max=Math.max(1,progress.total_rounds??data.config.rounds*tracks.length);$('optimization-progress-bar').value=progress.completed_rounds||0;
  text('optimization-phase',`${progress.phase?String(progress.phase).replaceAll('_',' '):'Preparing markets'}${progress.active_mode?` · ${name(progress.active_mode)}`:''} · ${num(progress.completed_worlds||0)} / ${num(progress.total_worlds||0)} markets completed · ${num(data.config.customers)} travellers per market`);
  text('optimization-call-counts',`${num(counts.provider_calls||0)} new LLM calls · ${num(counts.cache_hits||0)} cached responses · ${num(counts.math_choices||0)} mathematical choices · ${num(counts.forced||0)} forced actions · ${num(counts.failures||0)} failures${data.config.total_live_budget?` · ${num(counts.live_attempts||0)} / ${num(data.config.total_live_budget)} authorized decisions`:''}`);
  $('optimization-resume-controls').hidden=!canResume(data.status);
  if(data.error && !['paused','paused_at_budget'].includes(data.status))showError(data.error);else showError('');
  $('optimization-export').href=`/api/optimization/runs/${encodeURIComponent(data.run_id)}/export`;
  $('optimization-events').href=`/api/optimization/runs/${encodeURIComponent(data.run_id)}/events`;
  renderCards(tracks);renderTable(tracks);renderFinal(tracks);renderContributionExplanation($('optimization-contribution-content'),tracks);renderFeedback(tracks);draw();controls();
}
// Mathematical track: closed-form scan picks P*, then the full simulation re-scores a fine grid around it.
function formulaSummary(){
  const box=$('optimization-formula'),e=state.data?.config?.formula_estimate;box.hidden=!e;if(!e){box.replaceChildren();return;}
  const math=(state.data.tracks||[]).find(t=>t.mode==='math'),best=math?.best;
  const parts=[node('strong',`Formula estimate P* = ${money(e.p_star)}`),
    document.createTextNode(` Scored ${num(e.prices_scored)} member fares from ${money(e.search_low)} to ${money(e.search_high)} (the saved fare cap) for ${num(e.travellers_scored)} simulated travellers using the mathematical customer model's choice probabilities; expected ${signed(e.expected_incremental)} versus no offer. The full simulation then tests P* and ${num(e.grid.length-1)} nearby prices.`)];
  if(best)parts.push(document.createTextNode(best.member_fare===e.p_star?` Simulation confirms P* as the best tested price.`:` Simulation moved the best tested price to ${money(best.member_fare)}.`));
  box.replaceChildren(...parts);
}
function draw(){if(!state.data)return;formulaSummary();const tracks=state.data.tracks||[];chart('optimization-fare-chart',tracks,'member_fare',{initialKey:'initial_member_fare',caption:'Evaluated member fare by round'});chart('optimization-profit-chart',tracks,'incremental_contribution',{caption:'Evaluated incremental contribution compared with no offer'}); priceProfit(tracks);}
async function poll(id){
  const token=++state.request;clearTimeout(state.timer);
  try{const data=await api(`/api/optimization/runs/${encodeURIComponent(id)}`);if(id!==state.runId||token!==state.request)return;render(data);if(running(data.status))state.timer=setTimeout(()=>poll(id),1500);else listRuns(false);}
  catch(error){if(id===state.runId&&token===state.request){showError(error.message);state.loading=false;controls();}}
}
async function listRuns(openLatest=false){
  try{const payload=await api('/api/optimization/runs'),runs=Array.isArray(payload)?payload:payload.runs||[];const select=$('optimization-run-select');
    select.replaceChildren(node('option','Select an experiment'));select.firstElementChild.value='';
    for(const run of runs){const option=node('option',`${run.config.mode==='both'?'Math + LLM':name(run.config.mode)} · ${run.config.scope?`${run.config.scope.origin}→${run.config.scope.destination} ${run.config.scope.departure_date} D${run.config.scope.as_of_day}`:'Historical whole-term'} · ${run.config.rounds} rounds · ${statusLabel(run.status)} · ${run.run_id}`);option.value=run.run_id;select.append(option);}
    if(state.runId)select.value=state.runId;else if(openLatest&&runs.length){state.runId=runs[0].run_id;select.value=state.runId;poll(state.runId);}state.listed=true;
  }catch(error){showError(`Saved experiments unavailable: ${error.message}`);}
}
function routeKey(flight){return `${flight.origin}-${flight.destination}`;}
function filteredFlights(){return state.flights.filter(f=>matchesDemand(f,$('optimization-demand').value));}
function fillRoutes(selected=$('optimization-route').value){
  const matches=filteredFlights(),routes=[...new Set(matches.map(routeKey))].sort();
  $('optimization-route').replaceChildren(new Option(routes.length?'Choose a route':'No routes match this demand level',''),...routes.map(route=>new Option(route.replace('-', ' → '),route)));
  $('optimization-route').disabled=!routes.length;
  if(routes.includes(selected))$('optimization-route').value=selected;
}
function fillFlights(selected=''){
  const route=$('optimization-route').value;
  const matching=filteredFlights(),flights=matching.filter(f=>routeKey(f)===route).sort((a,b)=>(a.departure_at||a.departure_date).localeCompare(b.departure_at||b.departure_date));
  $('optimization-flight').replaceChildren(new Option(route&&!flights.length?'No departures match this demand level':'Choose a departure / flight',''),...flights.map(f=>new Option(`${(f.departure_at||f.departure_date).slice(0,10)} · ${f.flight_id} · ${demandDescription(f)}${f.route_note?` · ${f.route_note}`:''}`,f.flight_id)));
  $('optimization-flight').disabled=!flights.length;
  if(flights.some(f=>f.flight_id===selected))$('optimization-flight').value=selected;
  text('optimization-demand-status',matching.length?`${num(matching.length)} flights match${route?`; ${num(flights.length)} on ${route.replace('-',' → ')}`:''}.`:'No flights match. Choose another demand level or All demand.');
}
async function loadScope(){
  const token=++state.scopeRequest;state.scope=null;$('optimization-fare').value='';$('optimization-load-demo').hidden=true;showError('');controls();
  const flightId=$('optimization-flight').value;
  if(!flightId){text('optimization-scope',filteredFlights().length?'Choose a route and departure to load this flight.':'No flight selected. Change the demand filter to continue.');text('optimization-initial-source','P₀ is the member fare cap: 80% of the selected flight’s normal base fare, before taxes and fees.');return;}
  text('optimization-scope','Loading the observed flight snapshot…');
  try{
    const result=await api('/api/optimization/initial-policy',{flight_id:flightId,forecast_day:val('optimization-day'),customers:val('optimization-customers'),program_cost:val('optimization-cost')});
    if(token!==state.scopeRequest)return;
    if(!result.scope)throw new Error('This backend does not support flight-scoped optimization. Refresh after updating the server.');
    state.scope=result.scope;$('optimization-fare').value=result.initial_member_fare;
    // Member fares never exceed 80% of the normal base fare; the server enforces the same cap.
    const cap=Number(result.scope.member_fare_cap??result.initial_member_fare);
    $('optimization-fare-max').max=String(cap);$('optimization-fare-max').value=String(cap);
    if(val('optimization-fare-min')>=cap)$('optimization-fare-min').value='0';
    const scope=result.scope;
    text('optimization-scope',`${scope.origin} → ${scope.destination} · ${scope.departure_date} · D${scope.as_of_day}. ${num(scope.available_seats)} physical empty seats / ${num(scope.capacity)} capacity; ${num(scope.releasable_seats)} forecast member seats.`);
    $('optimization-load-demo').hidden=scopeEligible(scope);
    text('optimization-initial-source',`P₀ ${money(result.initial_member_fare)} is the member fare cap: 80% of this flight’s ${money(scope.normal_base_fare)} normal base fare, before taxes and fees${scope.quote_age_days?` (last available quote ${scope.quote_age_days} days earlier)`:''}. Tested member fares never go above it.`);
    showError('');
  }catch(error){if(token===state.scopeRequest)showError(error.message);}finally{if(token===state.scopeRequest)controls();}
}
async function initializeFlights(){
  try{
    const data=await api('/api/flights');state.flights=data.flights||[];
    populateDemandFilter($('optimization-demand'),state.flights);fillRoutes();fillFlights();controls();
  }catch(error){showError(error.message);}
}
$('optimization-route').addEventListener('change',()=>{fillFlights();loadScope();});
$('optimization-demand').addEventListener('change',()=>{const selected=$('optimization-flight').value;fillRoutes();fillFlights(selected);loadScope();});
$('optimization-flight').addEventListener('change',loadScope);
$('optimization-day').addEventListener('change',loadScope);
$('optimization-share').addEventListener('change',controls);
$('optimization-suggest').addEventListener('click',loadScope);
$('optimization-load-demo').addEventListener('click',async()=>{const route=$('optimization-route').value;const demo=state.flights.find(f=>f.demo_priority===0&&Number(f.demo_d28_releasable)>0&&routeKey(f)===route)||state.flights.find(f=>f.demo_priority===0&&Number(f.demo_d28_releasable)>0);if(!demo){showError('Choose another flight or release round with positive member supply.');return;}if(!matchesDemand(demo,$('optimization-demand').value))$('optimization-demand').value='all';fillRoutes(routeKey(demo));fillFlights(demo.flight_id);$('optimization-day').value='28';await loadScope();});
window.addEventListener('uoption:optimize-flight',async event=>{
  if(!state.flights.length)await initializeFlights();
  const flight=state.flights.find(f=>f.flight_id===event.detail.flight_id);if(!flight)return;
  if(!matchesDemand(flight,$('optimization-demand').value))$('optimization-demand').value='all';
  fillRoutes(routeKey(flight));fillFlights(flight.flight_id);
  $('optimization-day').value=String([28,14,7].includes(event.detail.day)?event.detail.day:([28,14,7].find(day=>day<event.detail.day)||28));await loadScope();
});
initializeFlights();
$('optimization-form').addEventListener('submit',async event=>{
  event.preventDefault();if(state.loading)return;const blocked=state.scope?releaseDecision(state.scope,val('optimization-share')):{title:'Select a flight and release round first.'};if(blocked){showError(blocked.title);return;}showError('');state.loading=true;controls();
  const body={flight_id:$('optimization-flight').value,forecast_day:val('optimization-day'),mode:$('optimization-mode').value,rounds:val('optimization-rounds'),customers:val('optimization-customers'),initial_membership_fee:val('optimization-fee'),fare_min:val('optimization-fare-min'),fare_max:val('optimization-fare-max'),fee_min:val('optimization-fee-min'),fee_max:val('optimization-fee-max'),seed:val('optimization-seed'),replicates:val('optimization-replicates'),release_fraction:val('optimization-share'),min_service_rate:val('optimization-service'),program_cost:val('optimization-cost'),max_calls:val('optimization-budget'),total_live_budget:$('optimization-mode').value==='math'?0:val('optimization-total-budget')};
  if(val('optimization-fare')<body.fare_min||val('optimization-fare')>body.fare_max||body.initial_membership_fee<body.fee_min||body.initial_membership_fee>body.fee_max||body.fare_min>=body.fare_max||body.fee_min>=body.fee_max){showError('Search limits must contain the starting prices and have a minimum lower than the maximum.');state.loading=false;controls();return;}
  try{const data=await api('/api/optimization/runs',body);clearTimeout(state.timer);state.runId=data.run_id;state.data=null;await listRuns();await poll(state.runId);}
  catch(error){showError(error.message);}finally{state.loading=false;controls();}
});
$('optimization-resume').addEventListener('click',async()=>{
  if(!state.runId||state.loading||!$('optimization-total-budget').reportValidity())return;
  state.loading=true;controls();showError('');
  try{await api(`/api/optimization/runs/${encodeURIComponent(state.runId)}/resume`,{max_calls:val('optimization-budget'),additional_live_budget:val('optimization-total-budget')});await poll(state.runId);}catch(error){showError(error.message);}finally{state.loading=false;controls();}
});
$('optimization-run-select').addEventListener('change',()=>{const id=$('optimization-run-select').value;clearTimeout(state.timer);state.request++;if(!id)return;state.runId=id;state.data=null;poll(id);});
$('optimization-refresh').addEventListener('click',()=>{listRuns();if(state.runId)poll(state.runId);});
document.addEventListener('uoption:view',event=>{if(event.detail.name==='optimization'){listRuns(!state.listed);requestAnimationFrame(draw);}});
let resize;window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(draw,150);});
controls();
if(location.hash==='#optimization')listRuns(true);
// Read-only availability check also works when this module loads after app.js.
api('/api/summary').then(data=>provider(Boolean(data.llm?.live_configured||data.llm?.configured||data.llm?.live_available))).catch(()=>provider(false));

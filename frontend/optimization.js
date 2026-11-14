const $ = id => document.getElementById(id);
const state = { runId:null, data:null, timer:null, request:0, loading:false, configured:false, listed:false };
const num = (v, digits=0) => v == null || !Number.isFinite(Number(v)) ? '—' : Number(v).toLocaleString('en-HK',{maximumFractionDigits:digits});
const money = v => v == null ? '—' : `HK$${num(v,2)}`;
const pct = v => v == null ? '—' : `${num(Number(v)*100,1)}%`;
const name = mode => mode === 'live' ? 'Live LLM' : 'Mathematical';
const running = status => ['queued','running'].includes(status);
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
function controls() {
  const live=$('optimization-mode').value!=='math';
  $('optimization-budget-field').hidden=!live && !['both','live'].includes(state.data?.config?.mode);
  $('optimization-budget').disabled=$('optimization-budget-field').hidden;
  $('optimization-start').disabled=state.loading || running(state.data?.status);
  text('optimization-start',state.loading?'Starting…':running(state.data?.status)?'Optimization is running…':'Start optimization');
  $('optimization-resume').disabled=state.loading || running(state.data?.status);
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
const statusLabel = status => ({queued:'Queued',running:'Running',completed:'Completed',paused:'Paused at batch limit',paused_at_budget:'Paused at batch limit',interrupted:'Interrupted',failed:'Run needs attention'})[status] || status;
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
function renderCards(tracks) {
  $('optimization-track-cards').replaceChildren(...tracks.map(track=>{
    const latest=track.rounds.at(-1),best=track.best;
    const card=node('section',undefined,`optimizer-track ${track.mode}`),heading=node('h2',name(track.mode));
    heading.append(node('span',latest?`Round ${latest.round} · latest tested`:'Initial prices'));
    const prices=node('div',undefined,'track-prices');
    for(const [label,amount]of [['Member base fare',latest?.member_fare??state.data.config.initial_member_fare],['Membership fee',latest?.membership_fee??state.data.config.initial_membership_fee]]){
      const item=node('div');item.append(node('span',label),node('strong',money(amount)));prices.append(item);
    }
    const profit=node('p',undefined,'track-profit');
    if(latest){profit.append(node('strong',`${money(latest.incremental_contribution)} incremental`),document.createTextNode(` · ${pct(latest.service_rate)} member use`));}
    else profit.textContent='Waiting for the first market replay to finish.';
    card.append(heading,prices,profit);
    if(best){const retained=node('p',undefined,'small muted');retained.append(node('strong','Best retained: '),document.createTextNode(`${money(best.member_fare)} fare + ${money(best.membership_fee)} pass.${best.feasible?'':' Service target unmet.'}`));card.append(retained);}
    return card;
  }));
}
function renderTable(tracks) {
  const rows=tracks.flatMap(track=>track.rounds.map(round=>({...round,mode:track.mode}))).sort((a,b)=>a.round-b.round||a.mode.localeCompare(b.mode));
  $('optimization-rounds-table').replaceChildren(...rows.map(row=>{
    const tr=node('tr'),th=node('th',`${name(row.mode)} / ${row.round}`);th.scope='row';tr.append(th);
    for(const item of [money(row.member_fare),money(row.membership_fee),money(row.incremental_contribution),pct(row.service_rate)])tr.append(node('td',item));
    const result=node('td');result.append(node('span',row.accepted?'Retained':row.feasible?'Tested':'Service unmet',row.accepted?'round-kept':'round-rejected'));tr.append(result);return tr;
  }));
  if(!rows.length){const tr=node('tr'),td=node('td','No completed rounds yet.');td.colSpan=6;tr.append(td);$('optimization-rounds-table').append(tr);}
}
function renderFinal(tracks) {
  const root=$('optimization-final-content');root.replaceChildren();
  for(const track of tracks) {
    const item=node('div',undefined,'final-option'),body=node('div'),heading=node('strong',name(track.mode));
    const decision=track.decision||'PENDING';heading.append(node('span',decision==='OFFER'?'Validated offer':decision==='NO_OFFER'?'Keep normal sales':'Validation pending','decision-chip'));body.append(heading);
    if(decision==='OFFER' && track.best && track.validation){
      body.append(node('p',`${money(track.best.member_fare)} member base fare · ${money(track.best.membership_fee)} membership fee`),node('p',`Independent market: ${money(track.validation.incremental_contribution)} incremental contribution · ${pct(track.validation.service_rate)} member use.`,'small muted'));
      body.append(node('p','Copy these prices to a draft. Review the selected flight’s base-NHPP seat allocation before publishing.','small muted'));
      const button=node('button','Use these prices','button primary');button.type='button';button.disabled=state.data.status!=='completed';button.addEventListener('click',()=>window.dispatchEvent(new CustomEvent('uoption:prepare-policy',{detail:{...track.best,release_fraction:state.data.config.release_fraction}})));item.append(body,button);
    }else if(decision==='NO_OFFER'){
      body.append(node('p','The tested member offer did not pass both the search and independent validation requirements.'));
      if(track.validation)body.append(node('p',`Independent market: ${money(track.validation.incremental_contribution)} incremental contribution · ${pct(track.validation.service_rate)} member use.`,'small muted'));
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
  text('optimization-round-count',`${num(progress.completed_rounds||0)} / ${num(progress.total_rounds??data.config.rounds*tracks.length)} rounds`);
  $('optimization-progress-bar').max=Math.max(1,progress.total_rounds??data.config.rounds*tracks.length);$('optimization-progress-bar').value=progress.completed_rounds||0;
  text('optimization-phase',`${progress.phase?String(progress.phase).replaceAll('_',' '):'Preparing markets'}${progress.active_mode?` · ${name(progress.active_mode)}`:''} · ${num(progress.completed_worlds||0)} / ${num(progress.total_worlds||0)} markets completed · ${num(data.config.customers)} travellers per market`);
  text('optimization-call-counts',`${num(counts.provider_calls||0)} new LLM calls · ${num(counts.cache_hits||0)} cached responses · ${num(counts.math_choices||0)} mathematical choices · ${num(counts.forced||0)} forced actions · ${num(counts.failures||0)} failures`);
  $('optimization-resume-controls').hidden=!canResume(data.status);
  if(data.error)showError(data.error);else showError('');
  $('optimization-export').href=`/api/optimization/runs/${encodeURIComponent(data.run_id)}/export`;
  $('optimization-events').href=`/api/optimization/runs/${encodeURIComponent(data.run_id)}/events`;
  renderCards(tracks);renderTable(tracks);renderFinal(tracks);renderFeedback(tracks);draw();controls();
}
function draw(){if(!state.data)return;const tracks=state.data.tracks||[];chart('optimization-fare-chart',tracks,'member_fare',{initialKey:'initial_member_fare',caption:'Evaluated member fare by round'});chart('optimization-fee-chart',tracks,'membership_fee',{initialKey:'initial_membership_fee',caption:'Evaluated membership fee by round'});chart('optimization-profit-chart',tracks,'incremental_contribution',{caption:'Evaluated incremental contribution compared with no offer'});}
async function poll(id){
  const token=++state.request;clearTimeout(state.timer);
  try{const data=await api(`/api/optimization/runs/${encodeURIComponent(id)}`);if(id!==state.runId||token!==state.request)return;render(data);if(running(data.status))state.timer=setTimeout(()=>poll(id),1500);else listRuns(false);}
  catch(error){if(id===state.runId&&token===state.request){showError(error.message);state.loading=false;controls();}}
}
async function listRuns(openLatest=false){
  try{const payload=await api('/api/optimization/runs'),runs=Array.isArray(payload)?payload:payload.runs||[];const select=$('optimization-run-select');
    select.replaceChildren(node('option','Select an experiment'));select.firstElementChild.value='';
    for(const run of runs){const option=node('option',`${run.config.mode==='both'?'Math + LLM':name(run.config.mode)} · ${run.config.rounds} rounds · ${statusLabel(run.status)} · ${run.run_id}`);option.value=run.run_id;select.append(option);}
    if(state.runId)select.value=state.runId;else if(openLatest&&runs.length){state.runId=runs[0].run_id;select.value=state.runId;poll(state.runId);}state.listed=true;
  }catch(error){showError(`Saved experiments unavailable: ${error.message}`);}
}
$('optimization-suggest').addEventListener('click',async()=>{
  const button=$('optimization-suggest');button.disabled=true;showError('');
  try{
    const suggestion=await api('/api/optimization/initial-policy',{customers:val('optimization-customers'),program_cost:val('optimization-cost'),fare_min:val('optimization-fare-min'),fare_max:val('optimization-fare-max'),fee_min:val('optimization-fee-min'),fee_max:val('optimization-fee-max')});
    $('optimization-fare').value=suggestion.initial_member_fare;$('optimization-fee').value=suggestion.initial_membership_fee;
    text('optimization-initial-source',`Starting hypothesis from ${num(suggestion.source?.flights)} flights at D${suggestion.source?.as_of_day??28}. Median normal base fare: ${money(suggestion.source?.median_normal_base_fare)}. You can edit both prices.`);
  }catch(error){showError(error.message);}finally{button.disabled=false;}
});
$('optimization-form').addEventListener('submit',async event=>{
  event.preventDefault();if(state.loading)return;showError('');state.loading=true;controls();
  const body={mode:$('optimization-mode').value,rounds:val('optimization-rounds'),customers:val('optimization-customers'),initial_member_fare:val('optimization-fare'),initial_membership_fee:val('optimization-fee'),fare_min:val('optimization-fare-min'),fare_max:val('optimization-fare-max'),fee_min:val('optimization-fee-min'),fee_max:val('optimization-fee-max'),seed:val('optimization-seed'),replicates:val('optimization-replicates'),flights:val('optimization-flights'),release_fraction:val('optimization-share'),min_service_rate:val('optimization-service'),program_cost:val('optimization-cost'),max_calls:val('optimization-budget')};
  if(body.initial_member_fare<body.fare_min||body.initial_member_fare>body.fare_max||body.initial_membership_fee<body.fee_min||body.initial_membership_fee>body.fee_max||body.fare_min>=body.fare_max||body.fee_min>=body.fee_max){showError('Search limits must contain the starting prices and have a minimum lower than the maximum.');state.loading=false;controls();return;}
  try{const data=await api('/api/optimization/runs',body);clearTimeout(state.timer);state.runId=data.run_id;state.data=null;await listRuns();await poll(state.runId);}
  catch(error){showError(error.message);}finally{state.loading=false;controls();}
});
$('optimization-resume').addEventListener('click',async()=>{
  if(!state.runId||state.loading||!$('optimization-budget').reportValidity())return;
  state.loading=true;controls();showError('');
  try{await api(`/api/optimization/runs/${encodeURIComponent(state.runId)}/resume`,{max_calls:val('optimization-budget')});await poll(state.runId);}catch(error){showError(error.message);}finally{state.loading=false;controls();}
});
$('optimization-run-select').addEventListener('change',()=>{const id=$('optimization-run-select').value;clearTimeout(state.timer);state.request++;if(!id)return;state.runId=id;state.data=null;poll(id);});
$('optimization-refresh').addEventListener('click',()=>{listRuns();if(state.runId)poll(state.runId);});
document.addEventListener('uoption:view',event=>{if(event.detail.name==='optimization'){listRuns(!state.listed);requestAnimationFrame(draw);}});
let resize;window.addEventListener('resize',()=>{clearTimeout(resize);resize=setTimeout(draw,150);});
controls();
if(location.hash==='#optimization')listRuns(true);
// Read-only availability check also works when this module loads after app.js.
api('/api/summary').then(data=>provider(Boolean(data.llm?.live_configured||data.llm?.configured||data.llm?.live_available))).catch(()=>provider(false));

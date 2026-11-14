import {renderPriceChart} from './price-chart.js';
const el = id => document.getElementById(id);
let timer, current, disposeChart;
const money = value => value == null ? '—' : `HK$${Number(value).toFixed(2)}`;
async function request(url, body) {
  const response = await fetch(url, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed');
  return result;
}
function render(report) {
  el('continuous-result').hidden = false;
  disposeChart?.();disposeChart=renderPriceChart(el('continuous-chart'),report);
  const candidate = report.selected_candidate, validation = report.validation;
  const values = [['Search decision',report.best.decision === 'NO_OFFER' ? 'Keep normal sales' : 'Member offer candidate'],['Best tested hypothesis',money(candidate.member_fare)],
    ['Search incremental contribution',money(candidate.incremental_contribution)],
    ['Independent validation',`${money(validation.incremental_contribution)} · ${validation.feasible ? 'service met' : 'service failed'}`],
    ['Review status',report.ready_for_review ? 'Passed search and holdout; manual review only' : 'Do not adopt automatically'],
    ...report.stress.map(row => [`Stress: ${row.scenario}`,money(row.incremental_contribution)])];
  el('continuous-summary').replaceChildren(...values.flatMap(([key,value]) => {
    const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=value;return [dt,dd];
  }));
  el('continuous-trace').replaceChildren(...report.trace.map(row => {
    const tr=document.createElement('tr');
    [money(row.member_fare),money(row.incremental_contribution),row.mean_members.toFixed(1),`${(100*row.mean_service_rate).toFixed(1)}%`,row.feasible?'Yes':'No'].forEach(value=>{const td=document.createElement('td');td.textContent=value;tr.append(td);});return tr;
  }));
}
async function poll(id) {
  try {
    const data=await request(`/api/pricing/runs/${encodeURIComponent(id)}`);
    if (id!==current) return;
    el('continuous-status').textContent=`${id} · ${data.status}${data.error ? ' · '+data.error : ''}`;
    if (data.report) render(data.report);
    if (['queued','running'].includes(data.status)) timer=setTimeout(()=>poll(id),1500);
    else el('continuous-start').disabled=false;
  } catch(error) {el('continuous-status').textContent=error.message;el('continuous-start').disabled=false;}
}
el('continuous-form').addEventListener('submit',async event=>{
  event.preventDefault();clearTimeout(timer);el('continuous-start').disabled=true;el('continuous-result').hidden=true;
  try {
    const result=await request('/api/pricing/runs',{price_min:Number(el('continuous-min').value),price_max:Number(el('continuous-max').value),membership_fee:Number(el('continuous-fee').value),release_fraction:Number(el('continuous-share').value),evaluations:Number(el('continuous-evals').value)});
    current=result.run_id;const url=new URL(location.href);url.searchParams.set('pricing_run',current);url.hash='optimization';history.replaceState(null,'',url);el('continuous-report').href=`/api/pricing/runs/${encodeURIComponent(current)}`;poll(current);
  } catch(error) {el('continuous-status').textContent=error.message;el('continuous-start').disabled=false;}
});

// Opening a saved result only reads it; it never creates a new experiment.
const savedRun=new URLSearchParams(location.search).get('pricing_run');
if (savedRun && /^price-[a-f0-9]{16}$/.test(savedRun)) {
  if(location.hash!=='#optimization')location.hash='optimization';
  current=savedRun;el('continuous-start').disabled=true;
  el('continuous-report').href=`/api/pricing/runs/${encodeURIComponent(current)}`;poll(current);
}

el('show-price-curve').addEventListener('click',event=>{
  event.preventDefault();el('fare-curve-panel').scrollIntoView({behavior:'smooth',block:'start'});
  el('continuous-min').focus({preventScroll:true});
});

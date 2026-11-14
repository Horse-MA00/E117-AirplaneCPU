/** Read-only presentation of the saved paired-market accounting explanation. */
const el=(tag,text,className)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;};
const number=(value,digits=2)=>value==null||!Number.isFinite(Number(value))?'—':(Number(value)===0?0:Number(value)).toLocaleString('en-HK',{maximumFractionDigits:digits});
const money=value=>value==null?'—':`HK$${number(value)}`;
const percent=value=>value==null?'—':`${number(value*100,1)}%`;
const signed=value=>value==null?'—':`${value>0?'+':''}${money(value)}`;
const trackName=mode=>mode==='live'?'Live LLM':'Mathematical';

function table(captionText,headers,rows,id){
  const wrap=el('div',undefined,'table-wrapper contribution-table'),table=el('table'),caption=el('caption',captionText);
  caption.id=id;wrap.tabIndex=0;wrap.setAttribute('role','region');wrap.setAttribute('aria-labelledby',id);
  const head=el('thead'),headRow=el('tr');
  for(const label of headers){const th=el('th',label);th.scope='col';headRow.append(th);}
  head.append(headRow);table.append(caption,head);
  const body=el('tbody');
  for(const [label,...values]of rows){const row=el('tr'),th=el('th',label);th.scope='row';row.append(th);for(const value of values)row.append(el('td',value));body.append(row);}
  table.append(body);wrap.append(table);return wrap;
}

function phaseView(data,phase,mode,index){
  const root=el('section',undefined,'contribution-phase');root.dataset.phase=phase;root.dataset.mode=mode;
  const title=phase==='search'?'Selected search candidate':'Independent validation';
  root.append(el('h4',title));
  if(!data?.available){root.append(el('p',data?.reason||'A complete paired accounting breakdown is not available in this saved result.','small muted contribution-unavailable'));return root;}
  const metrics=el('dl',undefined,'contribution-comparison');
  for(const[label,value,kind]of [['No member offer',data.baseline_contribution,'baseline'],['With member offer',data.offer_contribution,'offer'],['Incremental contribution',data.incremental_contribution,'incremental']]){
    const item=el('div');item.dataset.metric=kind;item.append(el('dt',label),el('dd',kind==='incremental'?signed(value):money(value)));metrics.append(item);
  }
  root.append(metrics,el('p','Incremental contribution = with member offer − no member offer. Positive total contribution can still be lower than normal sales.','small muted'));
  const allocation=data.annual_fee_allocation;
  root.append(el('p',allocation==null?'The fee allocation is not uniform across these saved worlds.':`${percent(allocation)} of newly paid membership fees and membership service costs is allocated to this flight. The full fee is charged once.`,'small contribution-allocation'));
  const componentRows=(data.components||[]).map(c=>[`${c.kind==='cost'?'Cost':'Revenue'} · ${c.label}`,money(c.baseline),money(c.offer),signed(c.contribution_effect)]);
  const totals=data.totals||{};
  componentRows.push(['Total revenue',money(totals.baseline_revenue),money(totals.offer_revenue),''],['Total cost',money(totals.baseline_cost),money(totals.offer_cost),''],['Contribution',money(data.baseline_contribution),money(data.offer_contribution),signed(data.incremental_contribution)]);
  root.append(table(`${trackName(mode)} · ${title} · mean amounts in HKD`,['Revenue or cost','No offer','With offer','Effect on contribution'],componentRows,`contribution-${index}-${phase}-ledger`));
  root.append(el('p','Cost rows show positive spending; their effect on contribution has the opposite sign. Mandatory fees are pass-through amounts. Fixed aircraft costs and pre-existing bookings’ income are excluded.','small muted'));
  const buyers=data.buyers||{};
  root.append(el('p',`Purchasing households: ${number(buyers.baseline)} without an offer → ${number(buyers.offer)} with an offer; net change ${number(buyers.net_change)}. Households that actually flew: ${number(buyers.baseline_fulfilled)} → ${number(buyers.offer_fulfilled)}.`,'small contribution-buyers'));
  root.append(el('p','Member purchases and new subscriptions are not necessarily additional customers. Net buyer count alone does not identify which households changed choices.','small muted'));
  const cash=data.cash_view;
  if(cash){
    const section=el('section',undefined,'contribution-cash');section.append(el('h5','Full membership-fee cash view'),el('p',`${money(cash.baseline_contribution)} without an offer → ${money(cash.offer_contribution)} with an offer; incremental ${signed(cash.incremental_contribution)}.`));
    section.append(el('p','This view includes all newly collected pass fees and membership service costs. Cash collected during this replay alone does not establish annual programme profit.','small muted'));
    if(data.cash_flow?.baseline&&data.cash_flow?.offer){
      const details=el('details'),summary=el('summary','Payments, refunds and pass-through charges');details.append(summary);
      const rows=[['cash_collected','Payments collected'],['refunds_paid','Refunds paid'],['mandatory_remitted','Mandatory charges remitted'],['mandatory_liability','Mandatory charges still held'],['total_cost','Modelled costs'],['contribution','Cash contribution']].map(([key,label])=>[label,money(data.cash_flow.baseline[key]),money(data.cash_flow.offer[key])]);
      details.append(table(`${trackName(mode)} · ${title} · cash reconciliation`,['Cash movement','No offer','With offer'],rows,`contribution-${index}-${phase}-cash`));section.append(details);
    }
    root.append(section);
  }
  const service=data.service_requirement;
  if(service){
    const section=el('section',undefined,'contribution-service');section.append(el('h5','New-member use requirement'));
    if(service.available===false){section.append(el('p','Per-replay member-use records are not available in this saved result. The service requirement cannot be checked here.','small muted contribution-unavailable'));root.append(section);}
    else {
    section.append(el('p',`Mean use: ${percent(service.mean_rate)}. Lowest replay: ${percent(service.lowest_rate)}. New-member completion threshold: ${percent(service.minimum_rate)}. Each replay must pass its saved member-use requirement; the mean does not override a failure.`, 'small'));
    section.append(el('p','Use means a newly joined member completed a member trip. Member seats flown also includes existing members. A later voluntary cancellation lowers new-member use; it does not by itself prove a shortage of seats.','small muted'));
    const rows=(service.replicas||[]).map(r=>[`Seed ${r.seed}`,number(r.new_members),percent(r.service_rate),number(r.member_flown),r.passed?'Passed':'Not met']);
    section.append(table(`${trackName(mode)} · ${title} · each replay is checked separately`,['Replay','New joins','New-member use','Member seats flown','Requirement'],rows,`contribution-${index}-${phase}-service`));root.append(section);
    }
  }
  if(data.reconciliation?.passed===false)root.append(el('p','The saved accounting breakdown did not reconcile. Inspect the experiment record before interpreting these totals.','message error'));
  return root;
}

export function renderContributionExplanation(root,tracks){
  root.replaceChildren();
  tracks.forEach((track,index)=>{
    const section=el('section',undefined,'contribution-track');section.append(el('h3',trackName(track.mode)));
    const explanation=track.contribution_explanation;
    if(!explanation){section.append(el('p','This saved result does not include a paired accounting breakdown. Download its original experiment to inspect the available evidence.','small muted contribution-unavailable'));}
    else {section.append(phaseView(explanation.search,'search',track.mode,index),phaseView(explanation.validation,'validation',track.mode,index));}
    root.append(section);
  });
}

const NS = 'http://www.w3.org/2000/svg';
const money = value => `HK$${Number(value).toLocaleString('en-HK', {minimumFractionDigits:2, maximumFractionDigits:2})}`;
function svgNode(tag, attrs={}, text) {
  const node = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  if (text !== undefined) node.textContent = text;
  return node;
}

// Plot only evaluated prices; do not invent a smooth demand/profit function.
export function renderPriceChart(container, report) {
  container.replaceChildren();
  const rows = [...report.trace].sort((a,b) => a.member_fare-b.member_fare);
  if (!rows.length || rows.some(row => !Number.isFinite(row.mean_total_contribution) || !Number.isFinite(row.mean_baseline_contribution))) {
    const message = document.createElement('p');
    message.textContent = 'This historical report contains incremental returns only. Run a new search to plot total contribution.';
    container.append(message);
    return () => {};
  }
  const peak = rows.reduce((best,row) => row.mean_total_contribution > best.mean_total_contribution ? row : best);
  const baseline = rows[0].mean_baseline_contribution;
  const top = document.createElement('div'); top.className = 'price-curve-cards';
  const decision = report.best.decision === 'NO_OFFER' ? 'Keep normal sales' : `Offer at ${money(report.best.member_fare)}`;
  for (const [label, value, detail] of [
    ['Highest tested total', money(peak.mean_total_contribution), `At ${money(peak.member_fare)} · service rule ${peak.feasible ? 'met' : 'failed'}`],
    ['Without a member offer', money(baseline), 'Same simulated customers and flight catalogue'],
    ['Search decision', decision, report.ready_for_review ? 'Passed independent validation; review before publishing' : 'Not cleared for adoption by independent validation'],
  ]) {
    const card=document.createElement('div'), small=document.createElement('span'), strong=document.createElement('strong'), note=document.createElement('small');
    small.textContent=label; strong.textContent=value; note.textContent=detail;
    card.append(small,strong,note);top.append(card);
  }
  const legend=document.createElement('p');legend.className='price-curve-legend';
  for (const [className,label] of [['met','Service rule met'],['failed','Service rule failed'],['peak','Highest tested total'],['baseline','No offer']]) {
    const item=document.createElement('span'), key=document.createElement('i');key.className=className;key.setAttribute('aria-hidden','true');item.append(key,document.createTextNode(label));legend.append(item);
  }
  const plot=document.createElement('div');plot.className='price-curve-plot';
  const detail=document.createElement('p');detail.className='price-curve-detail';detail.setAttribute('aria-live','polite');
  function describe(row) {
    detail.textContent=`Price ${money(row.member_fare)} → total ${money(row.mean_total_contribution)}; change vs no offer ${money(row.incremental_contribution)}; service rule ${row.feasible?'met':'failed'}.`;
  }
  describe(peak);
  const note=document.createElement('p');note.className='small muted';
  note.textContent=`Average of ${report.search_seeds.length} simulated worlds · ${rows.length} tested prices · ${report.config.flights} flights and ${report.config.customers} travellers per world. Vertical scale is zoomed; lines only connect tested prices. These are synthetic estimates, not a guaranteed global optimum. Total contribution includes normal/member ticket income, pass fees and ancillary margin, less modelled costs; it excludes pass-through fees and aircraft fixed costs.`;
  container.append(top,legend,plot,detail,note);
  function draw() {
    const width=Math.max(280,plot.clientWidth), height=width<500?310:370;
    const left=width<500?64:84, right=18, upper=30, bottom=52;
    const x0=report.config.price_min, x1=report.config.price_max;
    const ys=[baseline,...rows.map(row=>row.mean_total_contribution)];
    const low=Math.min(...ys), high=Math.max(...ys), gap=Math.max((high-low)*.15,1);
    const ymin=low-gap, ymax=high+gap;
    const x=value=>left+(value-x0)/(x1-x0)*(width-left-right);
    const y=value=>upper+(ymax-value)/(ymax-ymin)*(height-upper-bottom);
    const svg=svgNode('svg',{viewBox:`0 0 ${width} ${height}`,role:'group','aria-labelledby':'price-curve-svg-title'});
    svg.append(svgNode('title',{id:'price-curve-svg-title'},'Member price versus expected total contribution'),svgNode('text',{x:0,y:15,class:'price-axis-title'},'Expected total contribution (HK$)'));
    for (let i=0;i<=4;i++) {
      const value=ymin+(ymax-ymin)*i/4, py=y(value);
      svg.append(svgNode('line',{x1:left,y1:py,x2:width-right,y2:py,class:'price-grid'}),svgNode('text',{x:left-10,y:py+4,'text-anchor':'end',class:'price-tick'},value.toLocaleString('en-HK',{maximumFractionDigits:0})));
    }
    const ticks=width<500?2:4;
    for(let i=0;i<=ticks;i++) {
      const value=x0+(x1-x0)*i/ticks;
      svg.append(svgNode('text',{x:x(value),y:height-bottom+23,'text-anchor':'middle',class:'price-tick'},Number(value.toFixed(2)).toLocaleString('en-HK')));
    }
    svg.append(svgNode('text',{x:left+(width-left-right)/2,y:height-5,'text-anchor':'middle',class:'price-axis-title'},'Member base fare (HK$)'));
    svg.append(svgNode('line',{x1:left,y1:y(baseline),x2:width-right,y2:y(baseline),class:'price-baseline','data-value':baseline}));
    svg.append(svgNode('polyline',{points:rows.map(row=>`${x(row.member_fare)},${y(row.mean_total_contribution)}`).join(' '),class:'price-return-line'}));
    for(const row of rows) {
      if(row===peak) svg.append(svgNode('circle',{cx:x(row.member_fare),cy:y(row.mean_total_contribution),r:9,class:'price-peak','data-peak-price':row.member_fare}));
      const point=svgNode('circle',{cx:x(row.member_fare),cy:y(row.mean_total_contribution),r:5,
        class:`price-point ${row.feasible?'met':'failed'}`,tabindex:'0',role:'button',
        'data-price':row.member_fare,'data-total':row.mean_total_contribution,
        'aria-label':`Price ${money(row.member_fare)}, total ${money(row.mean_total_contribution)}, service rule ${row.feasible?'met':'failed'}`});
      point.append(svgNode('title',{},point.getAttribute('aria-label')));
      for(const event of ['mouseenter','focus','click']) point.addEventListener(event,()=>describe(row));
      point.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();describe(row);}});
      svg.append(point);
    }
    plot.replaceChildren(svg);
  }
  draw();
  const observer=new ResizeObserver(draw);observer.observe(plot);
  return ()=>observer.disconnect();
}

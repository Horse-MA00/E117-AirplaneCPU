/** Legacy UI check: targets the retired Math / Math+LLM Optimize page.
 * Not part of the current test scripts; retained as historical test source. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.env.APP_URL || 'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1280,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const row=(fare,total,feasible)=>({member_fare:fare,mean_total_contribution:total,mean_baseline_contribution:1000,incremental_contribution:total-1000,feasible,mean_members:4,mean_service_rate:feasible?.8:.2});
const rows=[row(500,800,false),row(0,900,true),row(100,1200,false)];
let report={config:{price_min:0,price_max:500,flights:6,customers:14},trace:rows,search_seeds:[1,2],selected_candidate:rows[1],best:{decision:'NO_OFFER',member_fare:null},validation:{incremental_contribution:-100,feasible:false},stress:[],ready_for_review:false};
let writes=0;
page.on('request',r=>{if(r.url().includes('/api/pricing/runs') && r.method()==='POST')writes++;});
await page.route('**/api/pricing/runs/price-aaaaaaaaaaaaaaaa',route=>route.fulfill({json:{status:'completed',report}}));
try {
  await page.goto(origin+'/?pricing_run=price-aaaaaaaaaaaaaaaa#optimization');
  await page.locator('.price-point').first().waitFor();
  assert.deepEqual(await page.locator('.price-point').evaluateAll(nodes=>nodes.map(n=>Number(n.dataset.price))),[0,100,500]);
  assert.equal(await page.locator('.price-peak').getAttribute('data-peak-price'),'100');
  assert.equal(await page.locator('.price-baseline').getAttribute('data-value'),'1000');
  assert.match(await page.locator('.price-curve-cards').innerText(),/Keep normal sales/);
  assert.match(await page.locator('.price-curve-cards').innerText(),/HK\$1,200\.00/);
  await page.locator('.price-point[data-price="100"]').focus();
  assert.match(await page.locator('.price-curve-detail').innerText(),/service rule failed/);
  const positions=await page.locator('.price-point').evaluateAll(nodes=>nodes.map(n=>Number(n.getAttribute('cy'))));
  assert.ok(positions[1]<positions[0] && positions[1]<positions[2]);
  await page.setViewportSize({width:390,height:844});
  await page.waitForFunction(()=>document.querySelector('.price-curve-plot svg').viewBox.baseVal.width<400);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  report={...report,best:{decision:'OFFER',member_fare:100},ready_for_review:true,trace:rows.map(r=>({...r,feasible:true}))};
  await page.reload();await page.locator('.price-point').first().waitFor();
  assert.match(await page.locator('.price-curve-cards').innerText(),/Offer at HK\$100\.00/);
  report={...report,trace:rows.map(({mean_total_contribution,mean_baseline_contribution,...rest})=>rest)};
  await page.reload();await page.getByText('This historical report contains incremental returns only.',{exact:false}).waitFor();
  assert.equal(await page.locator('.price-point').count(),0);
  assert.equal(writes,0,'Viewing/refreshing saved reports must never create experiments');
  assert.deepEqual(errors,[]);
  console.log('Price chart passed: actual totals, sorted numeric prices, infeasible peak vs NO_OFFER, feasible winner, keyboard detail, mobile resize, read-only reload, honest historical fallback.');
} finally {await browser.close();}

/** UI contract checks. All API responses below are explicit fixtures; no provider calls. */
import assert from 'node:assert/strict';
import {readFile, mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin = 'http://127.0.0.1:18081';
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page = await browser.newPage({viewport:{width:1440,height:1080}});
const errors = [], blocked = [], writes = [];
page.on('pageerror', cause => errors.push(cause.message));
const flight = {flight_id:'FIXTURE-HKG-FUK', origin:'HKG', destination:'FUK', departure_date:'2027-05-18', demand_band:'low'};
const scope = {...flight, as_of_day:28, available_seats:90, releasable_seats:45, member_supply_exposure:45, optimization_eligible:true};
const config = {flight_id:flight.flight_id, forecast_day:28, rounds:3, customers:14, replicates:2, seed:117, total_call_budget:300};
const rounds = [{round:1, fare:410, ticket_revenue:1000, tickets_sold:6, reason:'Dataset P₀.'}, {round:2, fare:300, ticket_revenue:1500, tickets_sold:8, proposal:{reason:'<script>window.injection=true</script> More purchases at the lower fare.'}}, {round:3, fare:350, ticket_revenue:1400, tickets_sold:7, reason:'Test a smaller reduction.'}];
let status = 'paused', created = false;
const report = () => ({run_id:'feedback-fixture', status, config, scope, initial_fare:410, rounds:status==='completed'?rounds:rounds.slice(0,1), selected:status==='completed'?{fare:300,round:2}:{fare:410,round:1}, counts:{proposer_calls:2,customer_calls:80,provider_calls:78,cache_hits:4,forced:30,failures:0}, progress:{phase:status==='completed'?'complete':'search',round:2}, validation:status==='completed'?{initial:{ticket_revenue:1200,tickets_sold:6},selected:{ticket_revenue:1500,tickets_sold:8},no_offer:{ticket_revenue:1300,tickets_sold:6},delta_vs_initial:300,delta_vs_no_offer:200,standard_error_vs_initial:50,decision:'RECOMMEND_TESTED_FARE',seeds:[50120,50221]}:null});
await page.route('**/*', async route => {
  const request = route.request(), path = new URL(request.url()).pathname;
  if (path === '/feedback-pricing') return route.fulfill({contentType:'text/html',body:await readFile(new URL('./feedback-pricing.html',import.meta.url),'utf8')});
  if (['/feedback-pricing.js','/feedback-pricing.css'].includes(path)) return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(`.${path}`,import.meta.url),'utf8')});
  if (path === '/api/flights') return route.fulfill({json:{flights:[flight]}});
  if (path === '/api/summary') return route.fulfill({json:{llm:{configured:true}}});
  if (path === '/api/optimization/initial-policy') return route.fulfill({json:{initial_member_fare:410,scope}});
  if (path === '/api/feedback-pricing/runs') {
    if(request.method()==='POST'){writes.push(request.postDataJSON());created=true;return route.fulfill({json:report()});}
    return route.fulfill({json:{runs:created?[report()]:[]}});
  }
  if (path === '/api/feedback-pricing/runs/feedback-fixture/resume') {writes.push(request.postDataJSON());status='completed';return route.fulfill({json:report()});}
  if (path === '/api/feedback-pricing/runs/feedback-fixture') return route.fulfill({json:report()});
  if(path==='/favicon.ico')return route.fulfill({status:204});
  blocked.push(path);return route.abort();
});
try {
  await mkdir(new URL('test-results/',import.meta.url),{recursive:true});
  await page.goto(`${origin}/feedback-pricing`);
  await page.locator('#feedback-route').selectOption('HKG-FUK');
  await page.locator('#feedback-flight').selectOption(flight.flight_id);
  await page.waitForFunction(()=>document.getElementById('feedback-initial').value==='410');
  assert.equal(await page.locator('#feedback-initial').getAttribute('readonly'),'');
  assert.equal(await page.locator('#feedback-start').isEnabled(),true);
  await page.locator('#feedback-rounds').fill('3');
  await page.locator('#feedback-start').click();
  await page.waitForFunction(()=>document.getElementById('feedback-status').textContent==='Paused at call limit');
  assert.equal(writes.length,1);
  assert.equal(writes[0].flight_id,flight.flight_id);
  assert.equal('initial_membership_fee' in writes[0],false);
  assert.equal('initial_member_fare' in writes[0],false,'P₀ must come from dataset');
  assert.equal(await page.locator('#feedback-comparison').isHidden(),true,'Do not chart search as independent validation');
  await page.locator('#feedback-resume').click();
  await page.waitForFunction(()=>document.getElementById('feedback-status').textContent==='Experiment complete');
  assert.deepEqual(writes[1],{additional_call_budget:200});
  assert.equal(await page.locator('#feedback-delta').textContent(),'+HK$300');
  assert.equal(await page.locator('#feedback-selected-fare').textContent(),'HK$300');
  assert.equal(await page.locator('#feedback-decision').textContent(),'Tested fare supported');
  assert.equal(await page.locator('#feedback-comparison-table tr').count(),3);
  assert.equal(await page.locator('#feedback-round-table tr').count(),3);
  const bars=await page.locator('#feedback-comparison-chart rect').evaluateAll(nodes=>nodes.map(n=>({x:Number(n.getAttribute('x')),width:Number(n.getAttribute('width')),revenue:Number(n.getAttribute('data-revenue'))})));
  assert.ok(bars.every(bar=>bar.x===bars[0].x),'Every bar has the same zero origin');
  assert.ok(Math.abs(bars[1].width/bars[0].width-1500/1200)<.0001,'Bars use holdout, not search, revenue');
  assert.equal(await page.evaluate(()=>window.injection),undefined);
  assert.match(await page.locator('#feedback-round-table').textContent(),/<script>/,'Untrusted LLM reasons remain plain text');
  assert.match(await page.locator('#feedback-export').getAttribute('href'),/feedback-fixture\/export$/);
  await page.screenshot({path:'test-results/feedback-pricing-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(200);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'Page fits mobile viewport');
  await page.locator('#feedback-additional-budget').count();
  await page.locator('#feedback-route').focus();
  assert.notEqual(await page.locator('#feedback-route').evaluate(node=>getComputedStyle(node).outlineStyle),'none');
  await page.screenshot({path:'test-results/feedback-pricing-mobile.png',fullPage:true});
  await page.reload();
  await page.waitForFunction(()=>document.getElementById('feedback-status').textContent==='Experiment complete');
  assert.equal(writes.length,2,'Reload only reads saved results');
  assert.deepEqual(errors,[]); assert.deepEqual(blocked,[]);
  console.log(JSON.stringify({status:'passed',source:'mocked UI contract, no live LLM calls',checks:['dataset P₀','no membership fee payload','bounded resume','holdout-only comparison','zero-origin proportional bars','semantic numeric table','untrusted reasons rendered as text','keyboard focus','390px layout','read-only saved reload']}));
} finally {await browser.close();}

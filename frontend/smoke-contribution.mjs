/** Legacy UI check: targets the retired Math / Math+LLM Optimize page.
 * Not part of the current test scripts; retained as historical test source. */
/** Read-only UI regression using the frozen live experiment; no provider calls. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const repo=fileURLToPath(new URL('../',import.meta.url));
const original=JSON.parse(execFileSync(process.env.PYTHON||'python3',['-c',`
import json
from pathlib import Path
from backend.contribution_explanation import describe_track
r=json.loads(Path('llm_agent/experiments/member_supply_live_context_20261114/report.json').read_text())
for t in r['tracks']:
    t['contribution_explanation']=describe_track(r['config'],t,r['worlds'])
r.pop('worlds')
r['config']['scope']['history']=[h for h in r['config']['scope']['history'] if h['days_to_departure']<=28]
print(json.dumps(r))
`],{cwd:repo,encoding:'utf8',maxBuffer:8*1024*1024}));
let fixture=structuredClone(original);
const flight={...original.config.scope,demo_priority:0,demo_d28_releasable:44};
const origin=process.env.APP_URL||'http://127.0.0.1:18080';
const baseline=process.env.BASELINE_UI==='1';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],blocked=[];
page.on('pageerror',error=>errors.push(error.message));
const assets=['/app.js','/demand-filter.js','/optimization.js','/contribution-explanation.js','/seat-status.js','/styles.css','/continuous.js','/price-chart.js'];
async function source(path){
  return baseline?execFileSync('git',['show',`HEAD:frontend/${path}`],{cwd:repo,encoding:'utf8'}):readFile(new URL(path,import.meta.url),'utf8');
}
await page.route('**/*',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,reply=json=>route.fulfill({json});
  if(path==='/admin'||path==='/')return route.fulfill({contentType:'text/html',body:await source('index.html')});
  if(assets.includes(path))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await source(path.slice(1))});
  // Every API response is intercepted, including harmless forecast POST requests.
  if(path==='/api/forecast')return reply({forecast:{expected_remaining_demand:24.633,expected_empty_seats:100.367,expected_empty_rate:.5576,protection_p90:37,releasable_seats:44,risk_release_ceiling:88,beta:.012,rate_now:.7,forecast_curve:[],release_status:{safe_capacity:88,member_sold:0,total_active_unsold:0,currently_bookable:0,new_release_limit:44,round_history:[]}}});
  if(path==='/api/optimization/initial-policy')return reply({initial_member_fare:84,scope:flight});
  if(request.method()!=='GET'){blocked.push(`${request.method()} ${path}`);return route.abort();}
  if(path==='/api/summary')return reply({dataset:{catalog_rows:280364},llm:{configured:false}});
  if(path==='/api/member-portal/plan')return reply({membership:{fee:399,term_days:365}});
  if(path==='/api/flights')return reply({flights:[flight]});
  if(path===`/api/flights/${flight.flight_id}`)return reply({flight,history:original.config.scope.history});
  if(path==='/api/optimization/runs')return reply({runs:[fixture]});
  if(path===`/api/optimization/runs/${fixture.run_id}`)return reply(fixture);
  if(path.startsWith('/api/'))return reply({runs:[],panels:[],segments:[],offers:[]});
  if(path==='/favicon.ico')return route.fulfill({status:204});
  blocked.push(`${request.method()} ${path}`);return route.abort();
});
const phase=name=>page.locator(`.contribution-phase[data-phase="${name}"]`);
const metric=(name,kind)=>phase(name).locator(`[data-metric="${kind}"] dd`).innerText();
const refresh=async()=>{await page.locator('#optimization-refresh').click();};
try{
  await mkdir(new URL('test-results/',import.meta.url),{recursive:true});
  await page.goto(origin+'/admin#optimization');
  await page.waitForFunction(()=>document.getElementById('optimization-status').textContent==='Completed');
  assert.equal(await page.locator('#optimization-contribution-content').count(),1,'Saved contribution breakdown must be present');
  assert.equal(await metric('search','baseline'),'HK$14,785');
  assert.equal(await metric('search','offer'),'HK$12,421');
  assert.equal(await metric('search','incremental'),'HK$-2,364');
  assert.equal(await metric('validation','baseline'),'HK$11,452.5');
  assert.equal(await metric('validation','offer'),'HK$9,088.5');
  assert.equal(await metric('validation','incremental'),'HK$-2,364');
  const search=phase('search'),validation=phase('validation');
  assert.match(await search.getByRole('row',{name:/Revenue · Normal base fares/}).innerText(),/HK\$17,640\s+HK\$14,280\s+HK\$-3,360/);
  assert.match(await search.getByRole('row',{name:/Revenue · Member base fares/}).innerText(),/HK\$0\s+HK\$504\s+\+HK\$504/);
  assert.match(await search.getByRole('row',{name:/Revenue · Allocated new membership fees/}).innerText(),/HK\$0\s+HK\$532\s+\+HK\$532/);
  assert.match(await search.getByRole('row',{name:/Cost · Allocated membership service costs/}).innerText(),/HK\$0\s+HK\$40\s+HK\$-40/);
  assert.doesNotMatch(await search.innerText(),/HK\$-0(?:\D|$)/);
  assert.match(await search.locator('.contribution-allocation').innerText(),/33\.3%/);
  assert.match(await search.locator('.contribution-buyers').innerText(),/6 without an offer → 6 with an offer; net change 0/);
  assert.match(await search.locator('.contribution-buyers').innerText(),/actually flew: 4 → 4/);
  assert.match(await search.locator('.contribution-cash').innerText(),/HK\$14,785 without an offer → HK\$13,405 with an offer; incremental HK\$-1,380/);
  assert.match(await validation.locator('.contribution-service').innerText(),/Mean use: 75%\. Lowest replay: 50%\. New-member completion threshold: 60%/);
  assert.match(await validation.getByRole('row',{name:/Seed 50221/}).innerText(),/4\s+50%\s+4\s+Not met/);
  assert.match(await page.locator('#optimization-final-content').innerText(),/seed 50221: 50%.*60%/);
  assert.equal(await search.locator('thead th:not([scope="col"]), tbody th:not([scope="row"])').count(),0);
  assert.equal(await search.locator('.contribution-table:not([tabindex="0"])').count(),0);
  await search.locator('summary').focus();await page.keyboard.press('Enter');
  assert.equal(await search.locator('details').getAttribute('open'),'');
  assert.equal(await search.locator('details table caption').count(),1);
  await search.locator('summary').press('Enter');
  await search.locator('h4').evaluate(node=>node.scrollIntoView({block:'start'}));
  await page.mouse.wheel(0,-100);
  await page.screenshot({path:fileURLToPath(new URL('test-results/contribution-desktop.png',import.meta.url))});
  await validation.locator('.contribution-service').scrollIntoViewIfNeeded();
  await page.screenshot({path:fileURLToPath(new URL('test-results/contribution-validation-desktop.png',import.meta.url))});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile page must not overflow');
  const ledger=search.locator('.contribution-table').first();
  assert.ok(await ledger.locator('tbody th').first().evaluate(node=>node.getBoundingClientRect().width<=180),'Sticky mobile row labels must leave room for numeric cells');
  await ledger.focus();await page.keyboard.press('ArrowRight');
  await page.waitForFunction(()=>document.querySelector('.contribution-table').scrollLeft>0);
  assert.ok(await ledger.evaluate(node=>node.scrollWidth>node.clientWidth),'Mobile table preserves readable columns with horizontal scrolling');
  await ledger.evaluate(node=>{node.scrollLeft=0;});
  await search.locator('h4').scrollIntoViewIfNeeded();
  await page.screenshot({path:fileURLToPath(new URL('test-results/contribution-mobile.png',import.meta.url))});

  fixture=structuredClone(original);fixture.tracks[0].contribution_explanation.validation={available:false,reason:'Matching holdout accounting is unavailable.'};
  await refresh();await page.waitForFunction(()=>document.querySelector('[data-phase="validation"]').textContent.includes('Matching holdout accounting'));
  assert.equal(await validation.locator('table, [data-metric]').count(),0,'Missing validation must not fabricate zero-valued metrics');
  fixture=structuredClone(original);fixture.tracks[0].contribution_explanation.search.service_requirement={available:false};
  await refresh();await page.waitForFunction(()=>document.querySelector('[data-phase="search"] .contribution-service').textContent.includes('cannot be checked'));
  assert.equal(await search.locator('.contribution-service table').count(),0);
  fixture=structuredClone(original);delete fixture.tracks[0].contribution_explanation;
  await refresh();await page.waitForFunction(()=>document.getElementById('optimization-contribution-content').textContent.includes('does not include a paired accounting breakdown'));
  assert.equal(await page.locator('#optimization-contribution-content table').count(),0);
  assert.deepEqual(blocked,[],'No unexpected mutations or external requests are allowed');assert.deepEqual(errors,[]);
  console.log('Contribution UI passed: frozen live ledger, independent validation, attributed vs cash delta, household counts, failed replay, zero normalization, semantic and keyboard tables, mobile overflow, historical missing accounting/service. No live mutations or provider calls.');
}finally{await browser.close();}

/** Current Optimize entry: real offline Thompson run, no paid provider calls. */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const origin=process.env.APP_URL||'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],legacyRequests=[];
page.on('pageerror',e=>errors.push(e.message));
page.on('request',r=>{if(new URL(r.url()).pathname.startsWith('/api/optimization'))legacyRequests.push(r.url());});
try{
  await mkdir('test-results',{recursive:true});
  const savedId=process.env.OPTIMIZATION_RUN_ID;
  await page.goto(origin+`/adaptive-pricing${savedId?'?run='+encodeURIComponent(savedId):''}`);
  await page.waitForURL('**/adaptive-pricing**');
  await page.locator('#experiment-form').waitFor();
  assert.equal(await page.locator('#optimization-form, #optimization-mode').count(),0);
  let creation;
  if(savedId){creation={run_id:savedId};}
  else{
    await page.locator('#opt-from:not([disabled])').waitFor();
    await page.locator('#opt-from').selectOption('HKG');await page.locator('#opt-to').selectOption('KMQ');
    const scopeResponse=page.waitForResponse(r=>r.url().endsWith('/api/adaptive-pricing/scope')&&r.request().method()==='POST');
    await page.locator('#flight').selectOption('NET-HKG-KMQ-20270518');
    const snapshot=await (await scopeResponse).json();
    assert.equal(snapshot.scope.flight_id,'NET-HKG-KMQ-20270518');
    assert.equal(snapshot.scope.as_of_day,28);
    assert.ok(snapshot.scope.releasable_seats>0,'This offline demo needs a positive NHPP member quota');
    await page.waitForFunction(()=>!document.getElementById('start').disabled);
    if(await page.locator('#setup-panel').isHidden())await page.locator('#new-experiment').click(); // a saved result for this flight opens first
    await page.locator('#mode').selectOption('synthetic');
    await page.locator('#rounds').fill('3');
    await page.locator('#customers').fill('16');
    const started=page.waitForResponse(r=>r.url().endsWith('/api/adaptive-pricing/runs')&&r.request().method()==='POST');
    await page.locator('#start').click();
    const response=await started,sent=response.request().postDataJSON();
    assert.equal(sent.flight_id,'NET-HKG-KMQ-20270518');assert.equal(sent.forecast_day,28);assert.equal(sent.mode,'synthetic');
    assert.equal(sent.rounds,3);assert.equal('initial_member_fare' in sent,false);assert.equal('membership_fee' in sent,false);
    creation=await response.json();assert.ok(creation.run_id,JSON.stringify(creation));
  }
  await page.waitForFunction(()=>document.getElementById('run-status').textContent.startsWith('Complete.'),null,{timeout:180000});
  const response=await page.request.get(origin+`/api/adaptive-pricing/runs/${creation.run_id}/export`);
  assert.equal(response.status(),200);
  const exported=await response.json(),report=exported.report;
  assert.ok(exported.events.length>0,'Experiment audit events remain exportable');
  assert.equal(report.status,'completed',report.error||'Run did not complete');
  assert.equal(report.version,'member-thompson-v5-marketing');
  assert.equal(report.config.profile,'flexible_deal_seekers');
  assert.equal(report.counts.provider_calls,0,'Offline smoke must never call a paid LLM');
  assert.equal(report.rounds.length,report.config.rounds);
  assert.ok(report.rounds.every(r=>Number.isInteger(r.price)&&r.price>=0&&r.price<=report.scope.member_fare_cap));
  assert.equal(await page.locator('#round-table tr').count(),report.rounds.length);
  assert.ok(report.recommendation);assert.ok(report.validation);
  assert.equal(await page.locator('#curve-section').isVisible(),true);
  assert.equal(await page.locator('#validation-section').isVisible(),true);
  assert.equal(await page.locator('#comparison-bars .comparison-row').count(),3);
  assert.equal(await page.locator('#member-feedback-link').getAttribute('href'),`/admin?run=${creation.run_id}#customers`);
  assert.deepEqual(legacyRequests,[],'The Optimize page never loads the retired optimizer');
  await page.screenshot({path:'test-results/optimization-completed-desktop.png',fullPage:true});
  for(const width of [390,768]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow at ${width}`);
  }
  await page.screenshot({path:'test-results/optimization-completed-mobile.png',fullPage:true});
  await page.reload();
  await page.waitForFunction(()=>document.getElementById('run-status').textContent.startsWith('Complete.'));
  assert.equal(await page.locator('#round-table tr').count(),report.rounds.length);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',run_id:creation.run_id,optimizer:report.version,rounds:report.rounds.length,counts:report.counts,recommendation:report.recommendation.price,retained:report.validation.retained_price,verdict:report.validation.adoption_result}));
}finally{await browser.close();}

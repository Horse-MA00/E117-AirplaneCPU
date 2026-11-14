import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const origin=process.env.APP_URL||'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
try{
  await mkdir('test-results',{recursive:true});
  await page.goto(origin+'/admin#optimization');
  await page.locator('#optimization-form').waitFor();
  let creation;
  if(process.env.OPTIMIZATION_RUN_ID){
    creation={run_id:process.env.OPTIMIZATION_RUN_ID};
    await page.locator('#optimization-run-select').selectOption(creation.run_id);
  }else{
  await page.waitForFunction(()=>document.querySelectorAll('#optimization-route option').length>1);
  assert.equal(await page.locator('#optimization-start').isDisabled(),true);
  await page.locator('#optimization-route').selectOption('HKG-ICN');
  const suggested=page.waitForResponse(r=>r.url().endsWith('/api/optimization/initial-policy')&&r.request().method()==='POST');
  await page.locator('#optimization-flight').selectOption('NET-HKG-ICN-20270521');
  const suggestion=await (await suggested).json();
  assert.equal(suggestion.scope.flight_id,'NET-HKG-ICN-20270521');
  assert.equal(suggestion.scope.as_of_day,28);
  assert.equal(suggestion.initial_membership_fee,399);
  await page.waitForFunction(()=>!document.getElementById('optimization-start').disabled);
  assert.equal(await page.locator('#optimization-fare, #optimization-fee, #optimization-rounds, #optimization-customers, .optimization-settings').count(),0);
  await page.locator('#optimization-mode').selectOption('math');
  const started=page.waitForResponse(r=>r.url().endsWith('/api/optimization/runs')&&r.request().method()==='POST');
  await page.locator('#optimization-start').click();
  const startResponse=await started; const sent=startResponse.request().postDataJSON();assert.equal(sent.flight_id,'NET-HKG-ICN-20270521');assert.equal(sent.forecast_day,28);assert.equal('initial_member_fare' in sent,false);assert.equal('initial_membership_fee' in sent,false);assert.equal(sent.customers,14);assert.equal(sent.rounds,6);assert.equal(sent.replicates,2);assert.equal(sent.release_fraction,0.5);
  creation=await startResponse.json();assert.ok(creation.run_id,JSON.stringify(creation));
  }
  await page.waitForFunction(id=>document.getElementById('optimization-export').getAttribute('href')===`/api/optimization/runs/${id}/export` && ['Completed','Run needs attention'].includes(document.getElementById('optimization-status').textContent),creation.run_id,{timeout:600000});
  const response=await page.request.get(origin+`/api/optimization/runs/${creation.run_id}/export`);
  assert.equal(response.status(),200);
  const report=await response.json();assert.equal(report.status,'completed',report.error || 'Experiment not completed');
  assert.equal(report.config.initial_membership_fee,399);
  // Mathematical track: formula P* first, then the fixed fine grid; live defaults to six rounds.
  const grid=report.config.formula_estimate.grid;
  assert.equal(report.tracks[0].rounds.length,grid.length);
  assert.deepEqual(report.tracks[0].rounds.map(r=>r.member_fare),grid);
  assert.equal(report.tracks[0].rounds[0].search_step,'formula_p_star');
  assert.ok(report.tracks[0].rounds.every(r=>r.member_fare<=report.config.scope.member_fare_cap));
  assert.match(await page.locator('#optimization-formula').innerText(),/Formula estimate P\* = HK\$/);
  assert.equal(await page.locator('#optimization-rounds-table tr').count(),grid.length);
  assert.ok(report.tracks[0].rounds.some(r=>r.member_fare!==report.config.initial_member_fare));
  assert.ok(report.tracks[0].rounds.every(r=>r.membership_fee===report.config.initial_membership_fee));
  assert.equal(report.config.scope.flight_id,'NET-HKG-ICN-20270521');
  const qualified=report.tracks[0].rounds.filter(r=>r.price_evidence_qualified===true);
  assert.equal(await page.locator('#optimization-price-profit circle').count(),qualified.length);
  assert.ok(qualified.length>0,'Positive supply must produce observed member-offer exposure for this test flight');
  assert.match(await page.locator('#optimization-tradeoffs').innerText(),/Highest tested contribution/);
  assert.match(await page.locator('#optimization-tradeoffs').innerText(),/Most member buyers/);
  await page.locator('#optimization-price-profit circle').first().focus();
  assert.match(await page.locator('#optimization-price-detail').innerText(),/buyers/);
  assert.ok(report.worlds.every(w=>w.status==='completed'&&Object.values(w.result.checks).every(Boolean)));
  assert.ok(report.search_seeds.every(seed=>!report.validation_seeds.includes(seed)));
  assert.equal(report.counts.provider_calls,0);
  assert.ok(report.tracks[0].validation);
  assert.ok(['OFFER','NO_OFFER'].includes(report.tracks[0].decision));
  const eventPage=await (await page.request.get(origin+`/api/optimization/runs/${creation.run_id}/events?limit=2&offset=1`)).json();
  assert.equal(eventPage.events.length,2);assert.equal(eventPage.offset,1);
  const firstEvents=await (await page.request.get(origin+`/api/optimization/runs/${creation.run_id}/events?limit=1`)).json();
  assert.ok(eventPage.events[0].id>firstEvents.events[0].id);
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'test-results/optimization-completed-desktop.png',fullPage:true});
  for(const width of [390,768]){
    await page.setViewportSize({width,height:900});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow at ${width}`);
  }
  await page.setViewportSize({width:390,height:844});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.screenshot({path:'test-results/optimization-completed-mobile.png',fullPage:true});
  await page.reload();
  await page.locator('#optimization-run-select').selectOption(creation.run_id);
  await page.waitForFunction(()=>document.getElementById('optimization-status').textContent==='Completed');
  assert.equal(await page.locator('#optimization-rounds-table tr').count(),grid.length);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',run_id:creation.run_id,rounds:grid.length,worlds:report.worlds.length,
    decisions:report.counts,selected:report.tracks[0].best,decision:report.tracks[0].decision}));
}finally{await browser.close();}

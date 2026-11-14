import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=fileURLToPath(new URL('.',import.meta.url));
const files={'/adaptive-pricing':'adaptive-pricing.html','/admin':'index.html','/':'index.html'};
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://localhost').pathname;const file=files[path]||(/^\/[a-z0-9-]+\.(js|css)$/.test(path)?path.slice(1):null);if(!file){res.writeHead(404).end();return;}try{const data=await readFile(root+file);res.writeHead(200,{'Content-Type':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html'});res.end(data);}catch{res.writeHead(500).end();}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1050}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const weights=[.13,.09,.14,.10,.12,.10,.08,.04,.04,.05,.03,.02,.04,.02];
const names=['Flexible budget traveller','Student on term breaks','Fixed-leave employee','Frequent leisure traveller','Family on school holidays','Couple on a short break','Visiting friends and relatives','Urgent essential traveller','Self-funded business traveller','Inbound and cross-market traveller','Small travel group','Traveller needing assistance','Infrequent traveller','No matching route or dates'];
const legacyPopulation={source:'hypothetical_coverage_not_market_shares',segments:weights.map((weight,i)=>({id:`segment-${i}`,name:names[i],weight}))};
const population={profile:'flexible_deal_seekers',source:'assumed_target_mix',segments:['Students','Spontaneous solo travellers','Destination-flexible explorers','Frequent bargain travellers','Flexible weekday travellers','Flexible friends','Flexible couples','Deal-only occasional travellers'].map((name,i)=>({id:`flexible-${i}`,name,weight:[.20,.15,.15,.15,.1,.1,.08,.07][i]}))};
const populations=[population,{...legacyPopulation,profile:'broad_coverage'}];
const scope={flight_id:'TEST-HKG-KMQ',origin:'HKG',destination:'KMQ',departure_date:'2027-05-18',departure_time:'10:30',as_of_day:28,normal_base_fare:410,initial_member_fare:328,member_fare_cap:328,member_fare_cap_ratio:.8,releasable_seats:45};
const flights=[scope,{...scope,flight_id:'TEST-HKG-KMQ-ZERO'},{...scope,flight_id:'TEST-HKG-FUK',destination:'FUK'}];
const curve=[{price:0,expected_buyers:25,expected_member_revenue:0},{price:100,expected_buyers:20,expected_member_revenue:2000},{price:200,expected_buyers:16,expected_member_revenue:3200},{price:328,expected_buyers:8,expected_member_revenue:2624}];
const rounds=[{round:1,learning_updates:24,reused_analysis:false,analysis_source:'provider_live',price:328,member_buyers:8,member_revenue:2624,weighted_conversion:.3,curve,analysis:{summary:'Several members declined because the fare exceeded their base-fare budget. <img src=x onerror=alert(1)>'},decisions:[{person:{segment_label:'Flexible budget traveller',customer_id:'TEST-01'},decision:{action:'DECLINE',reason:'The base fare is above my travel budget. <img src=x onerror=alert(1)>'},source:'provider_live'}]},{round:2,learning_updates:0,reused_analysis:true,analysis_source:'provider_live',price:200,member_buyers:16,member_revenue:3200,weighted_conversion:.6,curve,analysis:{summary:'The lower fare increased the observed member purchases.'},decisions:[{person:{segment_label:'Student on term breaks',customer_id:'TEST-02'},decision:{action:'BUY_MEMBER',reason:'The date is suitable and this fare is within my base-fare budget.'},source:'provider_live'}]}];
rounds.push({...rounds[1],round:3});
rounds[1]={...rounds[1],learning_updates:24,reused_analysis:false};
const legacyRounds=structuredClone(rounds);
for(const row of rounds){row.unique_customers=16;row.learning_updates=row.round===1?16:32;row.reused_analysis=false;row.initial_comparison={price:328,revenue:2624,weighted_revenue:2624,weighted_conversion:.3};row.paired_delta_vs_initial=row.member_revenue-2624;row.hypothesis_test={source_round:row.round===1?null:row.round-1,direction:row.round===1?'hold':'lower',status:row.round===1?'not_tested':'supported',summary:'The paired fresh cohort bought more at the tested lower fare.'};}

let run={version:'member-thompson-v4-paired',run_id:'adaptive-test-117',status:'completed',scope,population,config:{profile:'flexible_deal_seekers',flight_id:scope.flight_id,forecast_day:28,mode:'synthetic',rounds:3,customers:28,concurrency:4,max_calls:600,seed:117,validation_repeats:3},progress:{completed_rounds:3,total_rounds:3,phase:'completed',cumulative_unique_customers:48},counts:{provider_calls:20,cache_hits:2,forced:4,failures:0,peak_parallel:4},rounds,recommendation:{price:200,revenue_max_price:328,volume_max_price:0,revenue_fraction:.9,model_curve:curve,curve:curve.filter(p=>[200,328].includes(p.price))},validation:{adoption_result:'INCONCLUSIVE',retained_price:328,break_even_conversion:.82,observed_conversion:.6,decision:'IMPROVED_IN_SIMULATION',delta_vs_initial:576,delta_vs_no_offer:-80,comparisons:[{policy:'initial',price:328,mean_buyers:8,mean_revenue:2624},{policy:'selected',price:200,mean_buyers:16,mean_revenue:3200},{policy:'no_offer',price:null,mean_buyers:8,mean_revenue:3280}]},elapsed_seconds:70};
const legacyRun={...run,version:'member-thompson-v3-flexible',run_id:'adaptive-legacy-117',rounds:legacyRounds,recommendation:{price:269.54,curve},validation:{decision:'DID_NOT_IMPROVE',comparisons:run.validation.comparisons},population:legacyPopulation,config:{...run.config,profile:undefined,weights:Object.fromEntries(legacyPopulation.segments.map(s=>[s.id,s.weight]))}};
let posts=[],scopeRequests=0;
await page.route('**/api/**',async route=>{
 const u=new URL(route.request().url()),path=u.pathname,method=route.request().method();
 if(path==='/api/flights')return route.fulfill({json:{flights}});
 if(path==='/api/adaptive-pricing/status')return route.fulfill({json:{live_configured:true,population,populations}});
 if(path==='/api/adaptive-pricing/scope'){
   scopeRequests++; const b=route.request().postDataJSON();
   if(b.flight_id==='TEST-HKG-FUK')await new Promise(r=>setTimeout(r,150));
   return route.fulfill({json:{scope:{...flights.find(f=>f.flight_id===b.flight_id),as_of_day:b.forecast_day,releasable_seats:b.flight_id.endsWith('ZERO')?0:45},population:populations.find(p=>p.profile===b.profile)||population}});
 }
 if(path==='/api/adaptive-pricing/runs'&&method==='GET')return route.fulfill({json:{runs:[run,legacyRun]}});
 if(path==='/api/adaptive-pricing/runs'&&method==='POST'){
   posts.push(route.request().postDataJSON());
   run={...run,population:populations.find(p=>p.profile===posts.at(-1).profile),config:{...run.config,...posts.at(-1)}};
   return route.fulfill({json:{...run,status:'running',rounds:[],recommendation:null,validation:null,progress:{phase:'search',completed_rounds:0,total_rounds:posts.at(-1).rounds}}});
 }
 if(path==='/api/adaptive-pricing/runs/adaptive-legacy-117')return route.fulfill({json:legacyRun});
 if(path==='/api/adaptive-pricing/runs/adaptive-test-117')return route.fulfill({json:run});
 return route.fulfill({status:404,json:{error:'Unexpected mock API route'}});
});
try{
 await page.goto(origin+'/adaptive-pricing');
 await page.locator('#route:not([disabled])').waitFor();
 assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(await page.locator('#profile').count(),0,'Customer scenario selector is removed');
 assert.equal(await page.getByText('Target customer scenario',{exact:true}).count(),0);
 assert.doesNotMatch(await page.locator('body').innerText(),/\blegacy\b/i);
 assert.equal(await page.locator('#customers').inputValue(),'16');
 assert.equal(await page.locator('#customers').getAttribute('min'),'8');
 assert.equal(await page.locator('#validation-repeats').inputValue(),'3');
 assert.equal(posts.length,0,'Opening setup never starts an experiment');
 assert.equal(await page.locator('#start').isDisabled(),true);
 await page.selectOption('#route','HKG → KMQ');await page.selectOption('#flight','TEST-HKG-KMQ');
 await page.waitForFunction(()=>document.getElementById('starting-fare').textContent==='HK$328');
 assert.equal(await page.locator('#start').isEnabled(),true);
 await page.locator('#start').click();
 await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$200');
 assert.equal(posts.length,1);assert.equal(posts[0].mode,'synthetic');assert.equal(Object.keys(posts[0].weights).length,8);assert.equal(posts[0].profile,'flexible_deal_seekers');
 assert.equal(await page.locator('#round-table tr').count(),3);
 assert.match(await page.locator('#delta-initial').innerText(),/576/);
 assert.match(await page.locator('#delta-no-offer').innerText(),/−HK\$80/);
 assert.equal(await page.locator('#curve-table tr').count(),4,'Full model curve preferred over tested-price subset');
 assert.match(await page.locator('#curve-caption').innerText(),/90%/);
 assert.match(await page.locator('#curve-caption').innerText(),/Final fitted posterior after all search choices/);
 assert.match(await page.locator('#round-table tr').nth(2).innerText(),/16 \/ 32.*Above initial revenue/s);
 assert.equal(await page.locator('#feedback-section').count(),0,'Member feedback belongs only on Experiments');
 assert.equal(await page.locator('#round-chart').count(),0,'Round-price chart is removed');
 assert.equal(await page.locator('#round-title').innerText(),'Round results');
 assert.equal(await page.locator('#member-feedback-link').getAttribute('href'),'/admin?run=adaptive-test-117#customers');
 assert.match(await page.locator('#run-people').innerText(),/48 unique search members/);
 assert.match(await page.locator('#break-even-rate').innerText(),/82.0%/);
 assert.match(await page.locator('#observed-rate').innerText(),/60.0%/);
 assert.match(await page.locator('#retained-price-note').innerText(),/HK\$328/);
 assert.match(await page.locator('#candidate-tradeoff').innerText(),/Highest predicted revenue: HK\$328.*Most predicted buyers: HK\$0/);
 assert.match(await page.locator('#validation-verdict').innerText(),/Insufficient evidence/);
 assert.equal(await page.locator('#comparison-bars .comparison-row').count(),3);
 assert.match(await page.locator('#run-counts').innerText(),/4 peak parallel calls/);
 await page.reload();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$200');
 assert.equal(posts.length,1,'Saved-run reload is read-only');
 assert.match(await page.locator('#run-cohort').innerText(),/Flexible bargain travellers/);
 await page.selectOption('#saved-run','adaptive-legacy-117');await page.locator('#load-run').click();
 await page.waitForFunction(()=>document.getElementById('run-cohort').textContent.includes('Broad customer coverage'));
 assert.equal(await page.locator('#weights input').count(),8,'Historical report does not replace the new-experiment population');
 assert.equal(await page.locator('#customers').getAttribute('min'),'8');
 assert.deepEqual(await page.locator('#weights input').evaluateAll(inputs=>inputs.map(input=>input.dataset.segment)),population.segments.map(s=>s.id));
 assert.doesNotMatch(await page.locator('body').innerText(),/\blegacy\b/i);
 assert.match(await page.locator('#run-cohort').innerText(),/Broad customer coverage.*14 assumed customer groups/);
 assert.equal(posts.length,1,'Loading a historical population is read-only');
 assert.equal(await page.locator('#recommended-price').innerText(),'HK$269.54','Historical decimal prices remain exact');
 assert.equal(await page.locator('#break-even-panel').isHidden(),true);
 assert.match(await page.locator('#round-table tr').nth(2).innerText(),/0.*Cached summary/s);
 await page.reload();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$269.54');
 assert.equal(await page.locator('#weights input').count(),8);
 await page.locator('#refresh-run').click();
 await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$269.54');
 assert.match(await page.locator('#run-cohort').innerText(),/Broad customer coverage.*14 assumed customer groups/);
 await page.selectOption('#saved-run','adaptive-test-117');await page.locator('#load-run').click();
 await page.waitForFunction(()=>document.getElementById('run-cohort').textContent.includes('Flexible bargain travellers'));
 assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(posts.length,1);
 await mkdir(root+'test-results',{recursive:true});
 await page.screenshot({path:root+'test-results/adaptive-pricing-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No page horizontal overflow');
 await page.evaluate(()=>{scrollTo(0,0);return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
 assert.ok(await page.locator('#curve-chart').evaluate(svg=>svg.viewBox.baseVal.width<400),'Remaining revenue chart uses readable mobile coordinates');
 await page.screenshot({path:root+'test-results/adaptive-pricing-mobile.png'});
 await page.locator('#recommendation').scrollIntoViewIfNeeded();
 await page.screenshot({path:root+'test-results/adaptive-pricing-mobile-result.png'});
 await page.selectOption('#flight','TEST-HKG-KMQ-ZERO');
 await page.waitForFunction(()=>document.getElementById('member-quota').textContent==='0');
 assert.equal(await page.locator('#start').isDisabled(),true);
 assert.equal(await page.locator('#recommendation').isHidden(),true,'Changing scope clears previous results');
 await page.selectOption('#flight','TEST-HKG-KMQ');await page.waitForFunction(()=>document.getElementById('start').disabled===false);
 await page.locator('.settings summary').click();
 await page.locator('#weight-0').fill('1');assert.equal(await page.locator('#start').isDisabled(),true);
 await page.locator('#reset-weights').click();assert.equal(await page.locator('#start').isEnabled(),true);
 await page.selectOption('#mode','live');await page.locator('#max-calls').fill('1');await page.locator('#start').click();
 assert.equal(posts.length,1);assert.match(await page.locator('#page-error').innerText(),/call limit must be at least/);
 assert.equal(await page.locator('#max-calls').getAttribute('aria-invalid'),'true');
 assert.equal(await page.locator('#max-calls').evaluate(el=>el===document.activeElement),true);
 await page.locator('#max-calls').fill('600');await page.locator('#start').click();
 await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$200');
 assert.equal(posts.length,2);assert.equal(posts[1].mode,'live');
 const completedRun=run;
 // The API owns final-fare projection. The UI must show its checked quote,
 // keep search evidence unchanged, and preserve older unformatted reports.
 for(const [raw,price] of [[255,249],[30,0],[38,0],[39,39],[103,99],[259,259]]){
   run={...completedRun,version:'member-thompson-v5-marketing',config:{...completedRun.config,final_member_fare_policy:'member-marketing-fare-v1'},
     recommendation:{...completedRun.recommendation,raw_price:raw,price,marketing_adjustment:{policy:'member-marketing-fare-v1',raw_price:raw,price,initial_price_before_marketing:328,initial_price:319}},
     validation:{...completedRun.validation,final_member_fare_policy:'member-marketing-fare-v1',initial_price_before_marketing:328,initial_price:319,selected_price_before_marketing:raw,selected_price:price,retained_price:price,adoption_result:'ADOPT_CANDIDATE',delta_vs_initial:42,
       comparisons:[{policy:'initial',price:319,mean_buyers:8,mean_revenue:2552},{policy:'selected',price,mean_buyers:16,mean_revenue:2594},{policy:'no_offer',price:null,mean_buyers:8,mean_revenue:3280}]}};
   await page.locator('#refresh-run').click();
   await page.waitForFunction(([raw,price])=>document.getElementById('marketing-fare-note').textContent.includes(`Search selection HK$${raw} → promotional quote HK$${price}`),[raw,price]);
   assert.equal(await page.locator('#recommended-price').innerText(),`HK$${price}`);
   assert.equal(await page.locator('#recommendation-title').innerText(),'Promotional base fare');
   assert.match(await page.locator('#validation-table').innerText(),/Formatted initial fare\s+HK\$319/);
   assert.match(await page.locator('#validation-detail').innerText(),/initial HK\$328 → HK\$319/);
   assert.match(await page.locator('#delta-label-initial').innerText(),/formatted initial/);
   assert.equal(await page.locator('#delta-initial').innerText(),'+HK$42','Holdout result is not recomputed using the raw search price');
   assert.match(await page.locator('#curve-caption').innerText(),/adjusted promotional fare, which may not have been tested during search/);
   assert.match(await page.locator('#retained-price-note').innerText(),new RegExp(`Retained promotional fare after confirmation: HK\\$${price}`));
   assert.match(await page.locator('#round-table tr').first().innerText(),/HK\$328/,'Search observations keep their original quotes');
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Promotional quote and formatted-initial labels fit on mobile');
   if(raw===255){await page.locator('#recommendation').scrollIntoViewIfNeeded();await page.screenshot({path:root+'test-results/promotional-fare-mobile.png'});}
 }
 run=completedRun;
 await page.locator('#refresh-run').click();
 await page.waitForFunction(()=>document.getElementById('recommendation-title').textContent==='Selected test fare');
 assert.equal(await page.locator('#marketing-fare-note').isHidden(),true,'Historical v4 reports do not acquire the new final-fare rule');
 for(const [validation,expected,rate] of [
   [{break_even_conversion:.82,max_fulfilled_conversion:.5,break_even_attainable:false},'at most 50.0%','82.0%'],
   [{break_even_conversion:0,max_fulfilled_conversion:.5,break_even_attainable:true},'no additional member purchases are required','0.0%'],
   [{break_even_conversion:null,max_fulfilled_conversion:.5,break_even_attainable:false},'cannot recover positive initial revenue','Not attainable at HK$0'],
 ]){
   run={...completedRun,validation:{...completedRun.validation,...validation}};
   await page.locator('#refresh-run').click();
   await page.waitForFunction(text=>document.getElementById('break-even-note').textContent.includes(text),expected);
   assert.equal(await page.locator('#break-even-rate').innerText(),rate);
 }
 run={...completedRun,rounds:completedRun.rounds.map((r,i)=>i===2?{...r,hypothesis_test:{...r.hypothesis_test,status:'not_supported'}}:r)};
 await page.locator('#refresh-run').click();
 await page.waitForFunction(()=>document.querySelector('#round-table tr:last-child').textContent.includes('Below initial revenue'));
 run=completedRun;
 run={...run,status:'running',recommendation:null,validation:null};
 await page.locator('#refresh-run').click();
 await page.waitForFunction(()=>document.getElementById('curve-caption').textContent.includes('Pre-round Thompson hypothesis before these choices'));
 assert.equal(await page.locator('#curve-table-caption').textContent(),'Pre-round Thompson hypothesis before these choices');
 assert.equal(posts.length,2,'Inspecting the pre-round proposal never starts another experiment');
 run=completedRun;
 run={...run,status:'failed',error:'Live call budget exhausted. Completed decisions are saved.'};
 await page.locator('#refresh-run').click();await page.getByText('failed: Live call budget exhausted.',{exact:false}).waitFor();
 assert.equal(await page.locator('#start').isEnabled(),true);
 await verifyFixedNewPopulation(browser,origin,legacyRun,errors);
 await verifyFeedbackPage(browser,origin,completedRun,legacyRun,errors);
 await verifyThompsonOnlyNavigation(browser,origin,completedRun,errors);
 assert.deepEqual(errors,[]);
 console.log('Adaptive pricing UI passed: scoped80%cap, fixed8groups-without-selector, historical14group-reports-preserved, explicitfixedprofile, new8group-run-after-historical-load, setup-failure-safe, zeroquota, invalidweights, boundedlive explicitstart, read-onlyreload, modelcurve, freshpairedcohorts, retainedfare, break-even-rate, groundedhypothesis, historicdecimalquotes, roundtrace, independentvalidation, Englishsafeoutputs, failedrun, mobileoverflow, Experiments-only-feedback, saved-run-and-round-links, read-only-feedback-navigation, safe-summary-and-reasons, feedback-errors-and-empty-state, promotional-boundaries, formatted-initial-holdout, Thompson-only-Admin-navigation, bookmarked-run-and-round-preservation, exact-flight-round-entry, no-legacy-optimizer-requests. All API calls mocked; no paid calls.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}


async function verifyFixedNewPopulation(browser, origin, historicalRun, errors) {
 for (const setup of ['ready','failed','missing-target']) {
  const page=await browser.newPage();
  page.on('pageerror',e=>errors.push(e.message));
  const starts=[], scopes=[];
  await page.route('**/api/**',async route=>{
   const path=new URL(route.request().url()).pathname, method=route.request().method();
   if(path==='/api/flights')return route.fulfill({json:{flights}});
   if(path==='/api/adaptive-pricing/status'){
    if(setup==='failed')return route.fulfill({status:503,json:{error:'Setup unavailable'}});
    return route.fulfill({json:{live_configured:false,population:setup==='ready'?population:legacyPopulation,populations:setup==='ready'?populations:[{...legacyPopulation,profile:'broad_coverage'}]}});
   }
   if(path==='/api/adaptive-pricing/runs'&&method==='GET')return route.fulfill({json:{runs:[historicalRun]}});
   if(path===`/api/adaptive-pricing/runs/${historicalRun.run_id}`)return route.fulfill({json:historicalRun});
   if(path==='/api/adaptive-pricing/runs'&&method==='POST'){
    const body=route.request().postDataJSON();starts.push(body);
    return route.fulfill({json:{run_id:'adaptive-fixed-population',status:'completed',scope,population,config:body,rounds:[]}});
   }
   if(path==='/api/adaptive-pricing/scope'){
    const body=route.request().postDataJSON();scopes.push(body);
    return route.fulfill({json:{scope:{...scope,as_of_day:body.forecast_day},population}});
   }
   return route.fulfill({status:404,json:{error:'Unexpected mock API route'}});
  });
  try {
   await page.goto(`${origin}/adaptive-pricing?run=${historicalRun.run_id}`);
   await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$269.54');
   assert.equal(await page.locator('#profile').count(),0);
   assert.match(await page.locator('#run-cohort').innerText(),/Broad customer coverage.*14 assumed customer groups/);
   assert.doesNotMatch(await page.locator('body').innerText(),/\blegacy\b/i);
   assert.equal(starts.length,0,'Viewing a saved population is read-only');
   if(setup==='ready'){
    assert.equal(await page.locator('#weights input').count(),8);
    assert.equal(await page.locator('#start').isEnabled(),true);
    await page.locator('#start').click();
    await page.waitForFunction(()=>document.getElementById('run-cohort').textContent.includes('Flexible bargain travellers'));
    assert.equal(starts.length,1);
    assert.equal(starts[0].profile,'flexible_deal_seekers');
    assert.deepEqual(starts[0].weights,Object.fromEntries(population.segments.map(s=>[s.id,s.weight])),'Historical weights never enter a new experiment');
    await page.selectOption('#release-day','14');
    await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D14');
    assert.equal(scopes.at(-1).profile,'flexible_deal_seekers');
    assert.equal(starts.length,1,'Changing the release round only loads its scope');
   }else{
    assert.equal(await page.locator('#start').isDisabled(),true,'Missing target configuration blocks new starts');
    assert.equal(await page.locator('#weights input').count(),0,'Saved broad groups cannot substitute for missing configuration');
    await page.locator('#experiment-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));
    assert.equal(starts.length,0,'The submit handler also enforces configured target population');
    await page.locator('#refresh-run').click();
    assert.equal(await page.locator('#recommended-price').innerText(),'HK$269.54');
   }
  }finally{await page.close();}
 }
}

async function verifyFeedbackPage(browser, origin, currentRun, historicalRun, errors) {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',e=>errors.push(e.message));
 let reads=0, writes=0, forecastReads=0, savedRuns=[currentRun,historicalRun], failReads=false;
 const feedbackFlight={...scope,capacity:180,departure_at:'2027-05-18T10:30:00+08:00'};
 await page.route('**/api/**',async route=>{
   const request=route.request(), path=new URL(request.url()).pathname;
   if(path==='/api/forecast'){forecastReads++;return route.fulfill({json:{forecast:{expected_remaining_demand:20,expected_empty_seats:90,expected_empty_rate:.5,protection_p90:70,releasable_seats:40,risk_release_ceiling:40,beta:.012,rate_now:.7,forecast_curve:[],release_status:{safe_capacity:40,member_sold:0,total_active_unsold:0,currently_bookable:0,new_release_limit:40,round_history:[]}}}});}
   if(request.method()!=='GET'){writes++;return route.fulfill({status:405,json:{error:'Feedback is read-only'}});}
   if(path==='/api/adaptive-pricing/runs')return route.fulfill({json:{runs:savedRuns}});
   if(path.startsWith('/api/adaptive-pricing/runs/')){
     reads++;
     if(failReads)return route.fulfill({status:503,json:{error:'Saved feedback temporarily unavailable'}});
     const id=path.split('/').at(-1), saved=savedRuns.find(r=>r.run_id===id);
     return route.fulfill(saved?{json:saved}:{status:404,json:{error:'Saved experiment not found'}});
   }
   if(path==='/api/flights')return route.fulfill({json:{flights:[feedbackFlight]}});
   if(path===`/api/flights/${feedbackFlight.flight_id}`)return route.fulfill({json:{flight:feedbackFlight,history:[28,14,7,0].map(days_to_departure=>({days_to_departure,capacity:180,booked_seats:70,available_seats:110,normal_base_fare:410,normal_total_fare:660,mandatory_fees:250}))}});
   if(path==='/api/summary')return route.fulfill({json:{dataset:{rows:0},llm:{configured:false}}});
   if(path==='/api/member-portal/plan')return route.fulfill({json:{membership:{fee:399,term_days:365}}});
   if(path==='/api/personas')return route.fulfill({json:{segments:[]}});
   return route.fulfill({json:{runs:[]}});
 });
 try{
   await page.goto(origin+'/admin?run=adaptive-test-117#customers');
   await page.waitForFunction(()=>document.getElementById('feedback-summary').textContent.includes('lower fare increased'));
   assert.equal(await page.locator('#feedback-run').inputValue(),currentRun.run_id);
   assert.equal(await page.locator('#feedback-round').inputValue(),'3');
   assert.equal(await page.locator('#view-customers #agent-form').count(),0,'Experiments no longer contains panel-run controls');
   assert.equal(await page.locator('#view-customers .section-tabs').count(),0,'Experiments only contains member feedback');
   assert.equal(await page.locator('#view-customers svg').count(),0,'Experiments contains no price charts');
   assert.equal(await page.locator('#view-panel').isVisible(),false,'Legacy panel stays outside Experiments');
   assert.match(await page.locator('#feedback-source').innerText(),/Saved LLM summary/);
   assert.match(await page.locator('#feedback-hypothesis').innerText(),/From round 2: lower.*Above initial revenue/);
   await page.selectOption('#feedback-round','1');
   assert.doesNotMatch(await page.locator('#feedback-hypothesis').innerText(),/round null/);
   assert.match(await page.locator('#feedback-summary').innerText(),/<img src=x/);
   assert.match(await page.locator('#feedback-list').innerText(),/<img src=x/);
   assert.equal(await page.locator('#view-customers img').count(),0,'Summaries and decision reasons are text, never executable HTML');
   assert.equal(writes,0,'Reading and changing rounds never starts an experiment');
   await mkdir(root+'test-results',{recursive:true});
   await page.screenshot({path:root+'test-results/member-feedback-desktop.png',fullPage:true});
   await page.selectOption('#feedback-run',historicalRun.run_id);
   await page.waitForFunction(()=>document.getElementById('feedback-source').textContent.includes('Reused summary'));
   assert.equal(new URL(page.url()).searchParams.get('run'),historicalRun.run_id,'Saved-run selection updates the shareable URL');
   await page.reload();
   await page.waitForFunction(()=>document.getElementById('feedback-run').value==='adaptive-legacy-117'&&!document.getElementById('feedback-content').hidden);
   await page.locator('#view-customers[aria-busy="false"]').waitFor();
   assert.equal(writes,0,'Saved feedback reload is read-only');
   await page.setViewportSize({width:390,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Feedback page has no mobile overflow');
   await page.screenshot({path:root+'test-results/member-feedback-mobile.png',fullPage:true});
   failReads=true;
   await page.locator('#feedback-refresh').click();
   await page.locator('#feedback-error:visible').waitFor();
   assert.match(await page.locator('#feedback-error').innerText(),/Saved feedback temporarily unavailable/);
   failReads=false;
   await page.locator('#feedback-refresh').click();
   await page.waitForFunction(()=>document.getElementById('feedback-error').hidden&&!document.getElementById('feedback-content').hidden);
   savedRuns=[];
   await page.goto(origin+'/admin#customers');
   await page.locator('#feedback-empty:visible').waitFor();
   assert.equal(await page.locator('#feedback-content').isHidden(),true);
   assert.ok(reads>=3,'Feedback loads selected saved runs');
   assert.equal(writes,0,'Feedback navigation, refresh, error recovery and empty state send only GET requests');
   assert.equal(forecastReads,0,'Feedback navigation never runs unrelated forecasts even with catalog flights');
   await page.locator('.primary-nav a[href="#flights"]').click();
   await page.waitForFunction(()=>document.getElementById('headroom-value').textContent==='40 seats');
   assert.ok(forecastReads>0,'Forecast loads lazily when the user opens Forecast seats');
   assert.equal(writes,0,'Lazy forecast does not start experiments');
 }finally{await page.close();}
}

async function verifyThompsonOnlyNavigation(browser, origin, currentRun, errors) {
 const page=await browser.newPage({viewport:{width:1440,height:1000}});
 page.on('pageerror',error=>errors.push(error.message));
 const bookmarked={...currentRun,run_id:'adaptive-1afc5c96d92f465d',rounds:[...currentRun.rounds,{...currentRun.rounds.at(-1),round:4}]};
 let starts=0, legacyReads=0, unrelatedReads=0;
 const snapshots=[];
 await page.route('**/api/**',async route=>{
   const request=route.request(), path=new URL(request.url()).pathname;
   if(path.startsWith('/api/optimization'))legacyReads++;
   if(path==='/api/flights')return route.fulfill({json:{flights}});
   if(path==='/api/adaptive-pricing/status')return route.fulfill({json:{live_configured:true,population,populations}});
   if(path==='/api/adaptive-pricing/runs'&&request.method()==='GET')return route.fulfill({json:{runs:[bookmarked]}});
   if(path===`/api/adaptive-pricing/runs/${bookmarked.run_id}`)return route.fulfill({json:bookmarked});
   if(path==='/api/adaptive-pricing/scope'){
     const body=request.postDataJSON();snapshots.push(body);
     return route.fulfill({json:{scope:{...scope,flight_id:body.flight_id,as_of_day:body.forecast_day},population}});
   }
   if(request.method()!=='GET')starts++;
   unrelatedReads++;
   return route.fulfill({status:404,json:{error:'Unexpected navigation request'}});
 });
 try {
   await page.goto(origin+'/admin?run=adaptive-1afc5c96d92f465d&round=4#optimization');
   await page.waitForURL('**/adaptive-pricing?**');
   await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$200');
   assert.equal(new URL(page.url()).searchParams.get('run'),bookmarked.run_id);
   assert.equal(new URL(page.url()).searchParams.get('round'),'4');
   assert.equal(await page.locator('#round-table tr').count(),4,'Saved Thompson observations are preserved');
   assert.equal(await page.locator('#optimization-form, #optimization-mode, #optimization-track-cards, #continuous-form').count(),0);
   assert.equal(await page.locator('script[src="/optimization.js"], script[src="/continuous.js"]').count(),0);
   assert.equal(await page.locator('.primary-nav a').count(),4);
   assert.equal(await page.locator('.primary-nav a[aria-current="page"]').innerText(),'Optimize prices');
   for(const label of ['Forecast seats','Experiments','Manage offers'])assert.equal(await page.getByRole('link',{name:label,exact:true}).count(),1);
   assert.equal(await page.locator('#mode option').count(),2,'Customer sources share the same Thompson optimizer');
   assert.match(await page.locator('#mode option[value="synthetic"]').innerText(),/offline/i);
   assert.equal(legacyReads,0);assert.equal(unrelatedReads,0,'Initial bookmark redirect skips old Admin requests');
   assert.equal(starts,0,'Viewing an existing run never starts another experiment');
   await page.reload();await page.waitForFunction(()=>document.getElementById('round-table').children.length===4);
   assert.equal(starts,0,'Reload is read-only');
   await page.goto(origin+'/admin?flight_id=TEST-HKG-KMQ&forecast_day=14#optimization');
   await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D14');
   assert.equal(await page.locator('#flight').inputValue(),'TEST-HKG-KMQ');
   assert.equal(await page.locator('#release-day').inputValue(),'14');
   assert.equal(new URL(page.url()).searchParams.has('run'),false);
   assert.equal(await page.locator('#recommendation').isHidden(),true,'New flight context does not show a previous recommendation');
   assert.equal(snapshots.at(-1).forecast_day,14);
   await page.goto(origin+'/?flight_id=TEST-HKG-KMQ&day=13#optimization');
   await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D7');
   assert.equal(snapshots.at(-1).forecast_day,7);
   await page.goto(origin+'/admin?run=opt-legacy-117#optimization');
   await page.locator('#route:not([disabled])').waitFor();
   assert.equal(new URL(page.url()).pathname,'/adaptive-pricing');
   assert.equal(new URL(page.url()).searchParams.has('run'),false,'Old optimizer IDs never load as Thompson runs');
   assert.equal(legacyReads,0);assert.equal(unrelatedReads,0);assert.equal(starts,0);
   await page.setViewportSize({width:390,height:844});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Admin navigation fits on mobile');
   await page.screenshot({path:root+'test-results/thompson-only-admin-mobile.png',fullPage:true});
 } finally { await page.close(); }
}

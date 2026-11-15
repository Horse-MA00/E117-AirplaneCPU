/** Current Thompson v5 UI, with fully mocked APIs and no paid calls. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('.',import.meta.url));
const aliases={'/adaptive-pricing':'adaptive-pricing.html','/admin':'index.html','/':'index.html','/members/airports.js':'members/airports.js'};
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://localhost').pathname,file=aliases[path]||(/^\/[a-z0-9-]+\.(js|css)$/.test(path)||/^\/fonts\/inter-\d{3}\.woff2$/.test(path)?path.slice(1):null);try{if(!file)throw Error();const body=await readFile(root+file);res.writeHead(200,{'Content-Type':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':file.endsWith('.woff2')?'font/woff2':'text/html'}).end(body);}catch{res.writeHead(404).end('Not found');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const population={profile:'flexible_deal_seekers',segments:['Students','Spontaneous solo travellers','Destination-flexible explorers','Frequent bargain travellers','Flexible weekday travellers','Flexible friends','Flexible couples','Deal-only occasional travellers'].map((name,i)=>({id:`flexible-${i}`,name,weight:[.20,.15,.15,.15,.1,.1,.08,.07][i]}))};
const scope={flight_id:'TEST-HKG-KMQ',origin:'HKG',destination:'KMQ',departure_date:'2027-05-18',departure_time:'10:30',as_of_day:28,normal_base_fare:410,initial_member_fare:328,member_fare_cap:328,releasable_seats:45};
const flights=[{...scope,capacity:180,departure_at:'2027-05-18T10:30:00+08:00',demand_band:'low'},
 {...scope,flight_id:'TEST-HKG-KMQ-ZERO',demand_band:'low'},
 {...scope,flight_id:'TEST-HKG-HND-HIGH',destination:'HND',demand_band:'high'}];
const curve=[{price:0,expected_buyers:25,expected_member_revenue:0},{price:100,expected_buyers:20,expected_member_revenue:2000},{price:255,expected_buyers:16,expected_member_revenue:4080},{price:328,expected_buyers:8,expected_member_revenue:2624}];
const rounds=[1,2,3].map(round=>({round,price:round===1?328:255,unique_customers:16,learning_updates:round*16,member_buyers:16,member_revenue:4080,weighted_conversion:.6,paired_delta_vs_initial:1456,curve,analysis_source:'provider_live',analysis:{summary:'Members liked the lower fare. <img src=x onerror=alert(1)>'},hypothesis_test:{source_round:round===1?null:round-1,direction:'lower',status:'supported',summary:'Fresh paired customers bought more.'},decisions:[{person:{segment_label:'Flexible budget traveller',customer_id:`TEST-${round}`},decision:{action:'BUY_MEMBER',reason:'This affordable fare fits my flexible trip. <img src=x onerror=alert(1)>'},source:'provider_live'}]}));
let report={version:'member-thompson-v5-marketing',run_id:'adaptive-test-current',status:'completed',scope,population,config:{name:'DEMO_LLM0',profile:'flexible_deal_seekers',final_member_fare_policy:'member-marketing-fare-v1',flight_id:scope.flight_id,forecast_day:28,mode:'synthetic',rounds:3,customers:16,concurrency:4,max_calls:600,seed:117,validation_repeats:3},rounds,counts:{provider_calls:20,cache_hits:2,forced:4,failures:0,peak_parallel:4},progress:{completed_rounds:3,total_rounds:3,cumulative_unique_customers:48},recommendation:{raw_price:255,price:249,revenue_max_price:255,volume_max_price:0,revenue_fraction:.95,model_curve:curve,marketing_adjustment:{policy:'member-marketing-fare-v1',initial_price_before_marketing:328,initial_price:319}},validation:{adoption_result:'ADOPT_CANDIDATE',retained_price:249,break_even_conversion:.82,observed_conversion:.6,initial_price_before_marketing:328,initial_price:319,selected_price_before_marketing:255,selected_price:249,delta_vs_initial:1432,delta_vs_no_offer:704,comparisons:[{policy:'initial',price:319,mean_buyers:8,mean_revenue:2552},{policy:'selected',price:249,mean_buyers:16,mean_revenue:3984},{policy:'no_offer',price:null,mean_buyers:8,mean_revenue:3280}]},elapsed_seconds:70};
let starts=[],scopes=[],setup='ready',empty=false,failFeedback=false,apiReads=0;
let extraRuns=[],holdResponse=null;
const runReads=[];
const heartbeat=value=>Object.fromEntries([...['run_id','version','status','config','counts','progress','error','elapsed_seconds'].map(key=>[key,value[key]]),['saved_rounds',value.rounds.length],['has_recommendation',Boolean(value.recommendation)],['has_validation',Boolean(value.validation)]]);
const deferred=()=>{let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};};
const hold=path=>holdResponse={path,started:deferred(),release:deferred()};
const waitHeld=async pending=>{let timer;try{await Promise.race([pending.started.promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(new Error(`Expected request did not start: ${pending.path}`)),5000))]);}finally{clearTimeout(timer);}};
const reads=(id,kind)=>runReads.filter(path=>path===`/api/adaptive-pricing/runs/${id}/${kind}`).length;
await page.route('**/api/**',async route=>{
 const request=route.request(),path=new URL(request.url()).pathname,method=request.method();apiReads++;
 if(path==='/api/flights')return route.fulfill({json:{flights}});
 if(path==='/api/summary')return route.fulfill({json:{dataset:{rows:200000}}});
 if(path==='/api/member-portal/plan')return route.fulfill({json:{membership:{fee:399,term_months:6,term_label:'6 months',term_days:181}}});
 if(path==='/api/adaptive-pricing/status')return route.fulfill(setup==='failed'?{status:503,json:{error:'Setup unavailable'}}:{json:{live_configured:true,population:setup==='ready'?population:null,populations:setup==='ready'?[population]:[]}});
 if(path==='/api/adaptive-pricing/scope'){const body=request.postDataJSON();scopes.push(body);return route.fulfill({json:{population,scope:{...scope,flight_id:body.flight_id,as_of_day:body.forecast_day,releasable_seats:body.flight_id.endsWith('ZERO')?0:45}}});}
 if(path==='/api/adaptive-pricing/runs'&&method==='GET')return route.fulfill(failFeedback?{status:503,json:{error:'Saved feedback unavailable'}}:{json:{runs:empty?[]:[report,...extraRuns]}});
 if(path==='/api/adaptive-pricing/runs'&&method==='POST'){const body=request.postDataJSON();starts.push(body);report={...report,config:{...report.config,...body}};return route.fulfill({json:report});}
 if(path.startsWith('/api/adaptive-pricing/runs/'))runReads.push(path);
 const saved=[report,...extraRuns].find(value=>path.startsWith(`/api/adaptive-pricing/runs/${value.run_id}/`));
 if(saved&&(path.endsWith('/view')||path.endsWith('/progress'))){
  const payload=structuredClone(path.endsWith('/progress')?heartbeat(saved):saved);
  if(holdResponse?.path===path){const pending=holdResponse;holdResponse=null;pending.started.resolve();await pending.release.promise;}
  return route.fulfill({json:payload});
 }
 return route.fulfill({status:404,json:{error:'Not found'}});
});
try{
 await mkdir(root+'test-results',{recursive:true});
 await page.goto(origin+'/adaptive-pricing');await page.locator('#opt-from:not([disabled])').waitFor();
 assert.equal(await page.locator('#profile').count(),0);assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(await page.locator('#customers').getAttribute('min'),'8');assert.equal(await page.locator('#start').isDisabled(),true);
 assert.doesNotMatch(await page.locator('body').innerText(),/legacy|Math \+ LLM|Target customer scenario/i);
 await page.selectOption('#opt-from','HKG');await page.selectOption('#opt-to','KMQ');await page.selectOption('#flight',scope.flight_id);
 await page.waitForFunction(()=>!document.getElementById('start').disabled);
 assert.equal(scopes.at(-1).profile,'flexible_deal_seekers');assert.equal(starts.length,0);
    if(await page.locator('#setup-panel').isHidden())await page.locator('#new-experiment').click(); // a saved result for this flight opens first
 await page.locator('#start').click();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');
 assert.equal(starts.length,1);assert.equal(starts[0].profile,'flexible_deal_seekers');assert.equal(Object.keys(starts[0].weights).length,8);
 assert.equal(starts[0].mode,'synthetic');assert.equal('membership_fee' in starts[0],false);
 assert.equal(await page.locator('#round-table tr').count(),3);assert.equal(await page.locator('#curve-table tr').count(),4);
 assert.match(await page.locator('#curve-caption').innerText(),/Final fitted posterior.*95%/);
 assert.match(await page.locator('#marketing-fare-note').textContent(),/HK\$255 → promotional quote HK\$249/);
 assert.match(await page.locator('#validation-table').innerText(),/Formatted initial fare\s+HK\$319/);
 assert.equal(await page.locator('#delta-initial').innerText(),'+HK$1,432');assert.equal(await page.locator('#comparison-bars .comparison-row').count(),3);
 assert.match(await page.locator('#run-counts').innerText(),/20 provider calls · 2 cache hits · 4 forced decisions · 0 failures/);
 assert.equal(await page.locator('#feedback-section,#round-chart').count(),0);
 await page.reload();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');assert.equal(starts.length,1);
 assert.match(await page.locator('#saved-run option:checked').textContent(),/^DEMO_LLM0 · TEST-HKG-KMQ/);
 const completed=structuredClone(report);
 for(const [raw,price] of [[255,249],[30,0],[38,0],[39,39],[103,99],[259,259]]){
  report={...completed,recommendation:{...completed.recommendation,raw_price:raw,price},validation:{...completed.validation,selected_price_before_marketing:raw,selected_price:price,retained_price:price}};
  await page.locator('#refresh-run').click();await page.waitForFunction(([raw,price])=>document.getElementById('marketing-fare-note').textContent.includes(`HK$${raw} → promotional quote HK$${price}`),[raw,price]);
  assert.equal(await page.locator('#recommended-price').innerText(),`HK$${price}`);
  assert.equal(await page.locator('#round-table tr').nth(1).locator('td').first().innerText(),'HK$255','Final quote formatting never rewrites search evidence');
 }
 const stressScenario={id:'low_fare_60',version:'zero-fare-stress-v1',label:'Low-fare stress test',normal_base_fare:60,budget_multiplier:.10,source_scope:scope};
 const zeroStress={...completed,scenario:stressScenario,scope:{...scope,normal_base_fare:60,member_fare_cap:48,initial_member_fare:48,scenario:stressScenario},config:{...completed.config,name:'DEMO_ZERO0',demo_scenario:'low_fare_60'},recommendation:{...completed.recommendation,raw_price:20,price:0,marketing_adjustment:{...completed.recommendation.marketing_adjustment,initial_price_before_marketing:48,initial_price:39}},validation:{...completed.validation,adoption_result:'NO_OFFER',retained_price:null,initial_price_before_marketing:48,initial_price:39,selected_price_before_marketing:20,selected_price:0}};
 report=zeroStress;await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);
 await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$0');
 assert.match(await page.locator('#saved-run option:checked').textContent(),/^DEMO_ZERO0 ·/);
 assert.equal(await page.locator('#setup-panel').isHidden(),true);
 assert.equal(await page.locator('#scenario-notice').isVisible(),true,'Scenario assumptions remain visible with completed settings folded');
 assert.match(await page.locator('#scenario-notice').innerText(),/Hypothetical low-fare scenario.*HK\$60.*Ticket budgets 10%.*Source NHPP quota 45 seats held fixed/);
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.locator('#scenario-notice').isVisible(),true);
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.setViewportSize({width:1440,height:1000});
 assert.match(await page.locator('#run-cohort').textContent(),/Assumed normal base fare HK\$60.*Ticket budgets 10%.*Source NHPP quota 45 seats held fixed.*HK\$410/);
 assert.match(await page.locator('#scope-message').textContent(),/hypothetical inputs are not a new flight forecast/);
 assert.equal(await page.locator('#normal-fare').textContent(),'HK$60');
 assert.match(await page.locator('#marketing-fare-note').textContent(),/HK\$20 → promotional quote HK\$0/);
 assert.equal(await page.locator('#retained-price-note').textContent(),'No member offer retained.');
 assert.equal(await page.locator('#publish-link').isHidden(),true);assert.equal(await page.locator('#publish-link').getAttribute('href'),null);
 assert.equal(await page.locator('#start').isDisabled(),true);
 await page.locator('#experiment-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));assert.equal(starts.length,1);
 // Even an adopted stress-test price must not become an ordinary flight's
 // publishing shortcut; the scenario assumptions differ from its quote.
 report={...zeroStress,validation:{...zeroStress.validation,adoption_result:'ADOPT_CANDIDATE',retained_price:0}};
 await page.locator('#refresh-run').click();await page.waitForFunction(()=>document.getElementById('retained-price-note').textContent.includes('HK$0'));
 assert.equal(await page.locator('#publish-link').isHidden(),true);assert.equal(await page.locator('#publish-link').getAttribute('href'),null);
 report=zeroStress;
 await page.goto(origin+`/admin?run=${report.run_id}#customers`);await page.locator('#feedback-content:visible').waitFor();
 assert.match(await page.locator('#feedback-context').textContent(),/DEMO_ZERO0.*assumed normal fare HK\$60, ticket budgets 10%.*quota 45 seats held fixed/);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.setViewportSize({width:1440,height:1000});
 // Start settings after a stress report restore the real source quote. The
 // same stress report is not silently reloaded as the flight's latest result.
 await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$0');
 await page.locator('#new-experiment').click();await page.waitForFunction(()=>document.getElementById('normal-fare').textContent==='HK$410');
 assert.equal(await page.locator('#scenario-notice').isHidden(),true,'Source flight settings clear the hypothetical scenario notice');
 assert.equal(await page.locator('#recommendation').isHidden(),true);assert.equal(starts.length,1);
 report=completed;await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');
 assert.equal(await page.locator('#scenario-notice').isHidden(),true,'Normal saved experiments do not inherit scenario assumptions');
 // Loading a saved low-demand flight from a high-demand filter restores its
 // selectors and navigation together, without silently starting another run.
 await page.selectOption('#opt-demand','high');
 assert.equal(await page.locator('#flight').isDisabled(),true,'The route and demand combination has no matching flight');
 assert.equal(await page.locator('#opt-to option[value="KMQ"]').count(),1,'Demand must never remove an airport option');
 assert.equal(await page.locator('#opt-to').inputValue(),'KMQ','An empty demand result preserves the chosen destination');
 await page.selectOption('#saved-run',report.run_id);await page.locator('#load-run').click();
 await page.waitForFunction(()=>document.getElementById('flight').value==='TEST-HKG-KMQ');
 assert.equal(await page.locator('#opt-demand').inputValue(),'all');
 assert.equal(await page.locator('#opt-from').inputValue(),'HKG');
 assert.equal(await page.locator('#opt-to').inputValue(),'KMQ');
 assert.equal(await page.locator('#release-day').inputValue(),'28');
 assert.match(await page.locator('#flight-description').textContent(),/TEST-HKG-KMQ/);
 assert.match(await page.locator('#publish-link').getAttribute('href'),/flight_id=TEST-HKG-KMQ&forecast_day=28#members$/);
 assert.equal(starts.length,1,'Restoring a saved experiment must remain read-only');
 await page.selectOption('#opt-demand','low');
 await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249'&&!document.getElementById('recommendation').hidden);
 assert.equal(await page.locator('#opt-demand').inputValue(),'low','A filter that includes the saved flight remains selected');
 // A direct saved D7 URL starts from the HTML's D28 defaults. Restore the
 // native value, visible round buttons and scoped result as one selection.
 report={...completed,scope:{...completed.scope,as_of_day:7},config:{...completed.config,forecast_day:7}};
 await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);
 await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D7');
 assert.equal(await page.locator('#release-day').inputValue(),'7');
 assert.equal(await page.locator('[data-round="7"]').getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('[data-round="28"]').getAttribute('aria-pressed'),'false');
 // Normal-motion browsers transition the background for 150ms after aria
 // changes. Wait for the visible state, not just the synchronous scope text.
 await page.waitForFunction(()=>getComputedStyle(document.querySelector('[data-round="7"]')).backgroundColor==='rgb(111, 44, 145)');
 assert.equal(await page.locator('[data-round="7"]').evaluate(b=>getComputedStyle(b).backgroundColor),'rgb(111, 44, 145)');
 assert.equal(await page.locator('[data-round][aria-pressed="true"]').count(),1);
 assert.equal(starts.length,1);
 report=completed;await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);
 await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D28');
 assert.equal(await page.locator('[data-round="28"]').getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('[data-round="7"]').getAttribute('aria-pressed'),'false');
 await page.screenshot({path:root+'test-results/adaptive-pricing-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 await page.screenshot({path:root+'test-results/adaptive-pricing-mobile.png',fullPage:true});
 await page.selectOption('#flight','TEST-HKG-KMQ-ZERO');await page.waitForFunction(()=>document.getElementById('member-quota').textContent==='0');assert.equal(await page.locator('#start').isDisabled(),true);
 await page.selectOption('#flight',scope.flight_id);await page.waitForFunction(()=>!document.getElementById('start').disabled);
 // With a result on screen the settings are folded; open them as an admin would.
 if(await page.locator('#setup-panel').isHidden())await page.locator('#new-experiment').click();
 await page.locator('.settings summary').click();await page.locator('#weight-0').fill('1');assert.equal(await page.locator('#start').isDisabled(),true);
 await page.locator('#reset-weights').click();assert.equal(await page.locator('#start').isEnabled(),true);
 await page.selectOption('#mode','live');await page.locator('#max-calls').fill('1');await page.locator('#start').click();
 assert.match(await page.locator('#page-error').innerText(),/call limit must be at least/);assert.equal(starts.length,1);
 await page.locator('#max-calls').fill('600');await page.locator('#start').click();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');assert.equal(starts.length,2);assert.equal(starts[1].mode,'live');
 await page.goto(origin+`/admin?run=${report.run_id}&round=1#customers`);await page.locator('#feedback-content:visible').waitFor();
 assert.match(await page.locator('#feedback-run option:checked').textContent(),/^DEMO_LLM0 · TEST-HKG-KMQ/);
 assert.match(await page.locator('#feedback-context').textContent(),/^DEMO_LLM0 · HKG → KMQ/);
 assert.equal(await page.locator('#feedback-round').inputValue(),'1');assert.match(await page.locator('#feedback-summary').innerText(),/<img src=x/);assert.equal(await page.locator('#view-customers img').count(),0);
 assert.match(await page.locator('#feedback-list').innerText(),/<img src=x/);assert.equal(await page.locator('#view-pricing,#view-panel,#view-market').count(),0);
 await page.selectOption('#feedback-round','3');await page.reload();await page.locator('#feedback-content:visible').waitFor();assert.equal(await page.locator('#feedback-round').inputValue(),'3');assert.equal(starts.length,2);
 failFeedback=true;await page.locator('#feedback-refresh').click();await page.locator('#feedback-error:visible').waitFor();failFeedback=false;await page.locator('#feedback-refresh').click();await page.locator('#feedback-content:visible').waitFor();
 empty=true;await page.goto(origin+'/admin#customers');await page.locator('#feedback-empty:visible').waitFor();empty=false;
 for(const hash of ['optimization','pricing','panel','market','does-not-exist']){
  const reads=apiReads;await page.goto(origin+`/admin?run=adaptive-removed#${hash}`);await page.locator('#view-unavailable:visible').waitFor();
  assert.equal(new URL(page.url()).pathname,'/admin');assert.equal(new URL(page.url()).hash,`#${hash}`);assert.equal(apiReads,reads,'Retired hashes are not redirected and load no data');
 }
 for(const path of ['/optimization.js','/continuous.js','/price-chart.js','/contribution-explanation.js','/pricing-navigation.js'])assert.equal((await page.request.get(origin+path)).status(),404);
 await page.goto(origin+'/adaptive-pricing?run=adaptive-removed');await page.locator('#page-error:visible').waitFor();assert.equal(await page.locator('#recommendation').isHidden(),true);
 await page.goto(origin+`/adaptive-pricing?run=${report.run_id}&round=2`);await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');
 assert.equal(await page.locator('.primary-nav a[aria-current="page"]').innerText(),'Optimize prices');assert.equal(await page.locator('.primary-nav a').count(),5);
 assert.match(await page.locator('#member-feedback-link').getAttribute('href'),/round=2#customers$/);
 await page.goto(origin+`/adaptive-pricing?flight_id=${scope.flight_id}&forecast_day=14`);await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D14');assert.equal(scopes.at(-1).forecast_day,14);
 for(const unavailable of ['failed','missing-target']){
  setup=unavailable;await page.goto(origin+`/adaptive-pricing?run=${report.run_id}`);await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');
  assert.equal(await page.locator('#start').isDisabled(),true);assert.equal(await page.locator('#weights input').count(),0);
  await page.locator('#experiment-form').evaluate(form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true})));assert.equal(starts.length,2);
 }
 // Active runs fetch only heartbeat metadata until a saved result changes.
 setup='ready';
 const activeId=completed.run_id;
 report={...completed,status:'running',rounds:completed.rounds.slice(0,1),recommendation:null,validation:null,elapsed_seconds:1,progress:{completed_rounds:1,total_rounds:3,phase:'searching'}};
 await page.goto(origin+`/adaptive-pricing?run=${activeId}`);
 await page.waitForFunction(()=>document.getElementById('elapsed').textContent==='0m 1s elapsed');
 let views=reads(activeId,'view'),progressReads=reads(activeId,'progress');
 const poll=async()=>{
  report={...report,elapsed_seconds:report.elapsed_seconds+1};
  const elapsed=report.elapsed_seconds;
  await page.waitForFunction(seconds=>document.getElementById('elapsed').textContent===`0m ${seconds}s elapsed`,elapsed);
  assert.equal(reads(activeId,'progress'),++progressReads);
 };
 for(let i=0;i<2;i++){
  await poll();assert.equal(reads(activeId,'view'),views,'A steady heartbeat must not fetch saved detail');
  assert.equal(await page.locator('#round-table tr').count(),1);
 }
 report={...report,rounds:completed.rounds.slice(0,2),progress:{...report.progress,completed_rounds:2}};
 await poll();assert.equal(reads(activeId,'view'),++views,'A newly saved round fetches detail once');
 assert.equal(await page.locator('#round-table tr').count(),2);
 report={...report,recommendation:completed.recommendation};
 await poll();assert.equal(reads(activeId,'view'),++views,'A saved recommendation fetches detail');
 assert.equal(await page.locator('#recommended-price').innerText(),'HK$249');
 report={...report,validation:completed.validation};
 await poll();assert.equal(reads(activeId,'view'),++views,'Saved confirmation fetches detail');
 assert.equal(await page.locator('#delta-initial').innerText(),'+HK$1,432');
 report={...report,status:'completed'};
 await poll();assert.equal(reads(activeId,'view'),++views,'A terminal state fetches its final detail');
 assert.match(await page.locator('#run-status').innerText(),/^Complete/);
 const terminalPolls=reads(activeId,'progress');
 await page.waitForTimeout(1700);
 assert.equal(reads(activeId,'progress'),terminalPolls,'Terminal runs stop polling');
 const refreshed=page.waitForResponse(response=>new URL(response.url()).pathname===`/api/adaptive-pricing/runs/${activeId}/view`);
 await page.locator('#refresh-run').click();await (await refreshed).finished();
 assert.equal(reads(activeId,'view'),++views,'Manual refresh always reloads saved detail');

 // Responses captured for an old selection cannot overwrite a newer run.
 const other={...completed,run_id:'adaptive-test-other',config:{...completed.config,name:'OTHER_RUN'},recommendation:{...completed.recommendation,raw_price:199,price:199}};
 extraRuns=[other];report={...report,status:'running',recommendation:null,validation:null};
 await page.goto(origin+`/adaptive-pricing?run=${activeId}`);
 await page.waitForFunction(()=>document.getElementById('run-status').textContent.startsWith('Searching'));
 const selectOther=async()=>{
  await page.selectOption('#saved-run',other.run_id);await page.locator('#load-run').click();
  await page.waitForFunction(id=>document.getElementById('export-run').getAttribute('href').includes(id)&&!document.getElementById('recommendation').hidden&&document.getElementById('recommended-price').textContent==='HK$199',other.run_id);
 };
 const releaseStale=async pending=>{
  const response=page.waitForResponse(value=>new URL(value.url()).pathname===pending.path);
  pending.release.resolve();await (await response).finished();
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await page.locator('#recommended-price').innerText(),'HK$199');
  assert.match(await page.locator('#export-run').getAttribute('href'),/adaptive-test-other\/export$/);
  assert.equal(new URL(page.url()).searchParams.get('run'),other.run_id);
 };
 let pending=hold(`/api/adaptive-pricing/runs/${activeId}/progress`);
 await waitHeld(pending);
 views=reads(activeId,'view');await selectOther();await releaseStale(pending);
 assert.equal(reads(activeId,'view'),views,'An obsolete heartbeat must not trigger a detail request');
 await page.selectOption('#saved-run',activeId);await page.locator('#load-run').click();
 await page.waitForFunction(id=>document.getElementById('export-run').getAttribute('href').includes(id),activeId);
 pending=hold(`/api/adaptive-pricing/runs/${activeId}/view`);
 await page.locator('#refresh-run').click();await waitHeld(pending);
 await selectOther();await releaseStale(pending);
 assert.equal(runReads.some(path=>/^\/api\/adaptive-pricing\/runs\/[^/]+$/.test(path)),false,'UI reads never fetch complete audit reports');
 assert.equal(starts.length,2,'Heartbeat, refresh and saved-run switching remain read-only');
 assert.deepEqual(errors,[]);
 console.log('Current Thompson v5 UI passed: fixed8groups, scoped starts, bounded live submit, raw-vs-promotional evidence, final 0/9 fares, explicitly labelled zero-fare stress scenarios, stress publication guard and source-input reset, saved reports, curves, confirmation, mobile, safe feedback, retired hashes unavailable without redirect, deleted assets404, removed reports404, configuration-failure guard, lightweight heartbeat polling, result-boundary/manual detail refresh and stale-response isolation. All APIs mocked; no paid calls.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}

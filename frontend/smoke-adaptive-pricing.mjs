import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile, mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';

const root=fileURLToPath(new URL('.',import.meta.url));
const files={'/adaptive-pricing':'adaptive-pricing.html','/adaptive-pricing.js':'adaptive-pricing.js','/adaptive-pricing.css':'adaptive-pricing.css'};
const server=createServer(async(req,res)=>{const file=files[new URL(req.url,'http://localhost').pathname];if(!file){res.writeHead(404).end();return;}try{const data=await readFile(root+file);res.writeHead(200,{'Content-Type':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html'});res.end(data);}catch{res.writeHead(500).end();}});
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
const rounds=[{round:1,learning_updates:24,reused_analysis:false,analysis_source:'provider_live',price:328,member_buyers:8,member_revenue:2624,weighted_conversion:.3,curve,analysis:{summary:'Several members declined because the fare exceeded their base-fare budget.'},decisions:[{person:{segment_label:'Flexible budget traveller',customer_id:'TEST-01'},decision:{action:'DECLINE',reason:'The base fare is above my travel budget. <img src=x onerror=alert(1)>'},source:'provider_live'}]},{round:2,learning_updates:0,reused_analysis:true,analysis_source:'provider_live',price:200,member_buyers:16,member_revenue:3200,weighted_conversion:.6,curve,analysis:{summary:'The lower fare increased the observed member purchases.'},decisions:[{person:{segment_label:'Student on term breaks',customer_id:'TEST-02'},decision:{action:'BUY_MEMBER',reason:'The date is suitable and this fare is within my base-fare budget.'},source:'provider_live'}]}];
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
 assert.equal(await page.locator('#profile').inputValue(),'flexible_deal_seekers');
 assert.equal(await page.locator('#customers').inputValue(),'16');
 assert.equal(await page.locator('#customers').getAttribute('min'),'8');
 assert.equal(await page.locator('#validation-repeats').inputValue(),'3');
 await page.selectOption('#profile','broad_coverage');assert.equal(await page.locator('#weights input').count(),14);assert.equal(await page.locator('#customers').getAttribute('min'),'14');
 await page.selectOption('#profile','flexible_deal_seekers');assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(posts.length,0,'Changing the scenario never starts a paid experiment');
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
 assert.match(await page.locator('#analysis-source-note').innerText(),/Fresh LLM analysis/);
 assert.match(await page.locator('#run-people').innerText(),/48 unique search members/);
 assert.match(await page.locator('#break-even-rate').innerText(),/82.0%/);
 assert.match(await page.locator('#observed-rate').innerText(),/60.0%/);
 assert.match(await page.locator('#retained-price-note').innerText(),/HK\$328/);
 assert.match(await page.locator('#candidate-tradeoff').innerText(),/Highest predicted revenue: HK\$328.*Most predicted buyers: HK\$0/);
 assert.match(await page.locator('#hypothesis-note').innerText(),/From round 2: lower.*Above initial revenue/);
 assert.match(await page.locator('#validation-verdict').innerText(),/Insufficient evidence/);
 assert.equal(await page.locator('#comparison-bars .comparison-row').count(),3);
 assert.match(await page.locator('#run-counts').innerText(),/4 peak parallel calls/);
 await page.selectOption('#feedback-round','1');
 assert.match(await page.locator('#feedback-list').innerText(),/<img src=x/);
 assert.equal(await page.locator('#feedback-list img').count(),0,'LLM output is text, never executable HTML');
 await page.reload();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$200');
 assert.equal(posts.length,1,'Saved-run reload is read-only');
 assert.match(await page.locator('#run-cohort').innerText(),/Flexible bargain travellers/);
 await page.selectOption('#saved-run','adaptive-legacy-117');await page.locator('#load-run').click();
 await page.waitForFunction(()=>document.getElementById('profile').value==='broad_coverage');
 assert.equal(await page.locator('#weights input').count(),14,'Historical run restores its own broad-cohort weights');
 assert.match(await page.locator('#run-cohort').innerText(),/Broad customer coverage.*14 assumed customer groups/);
 assert.equal(posts.length,1,'Loading a historical population is read-only');
 assert.equal(await page.locator('#recommended-price').innerText(),'HK$269.54','Historical decimal prices remain exact');
 assert.equal(await page.locator('#break-even-panel').isHidden(),true);
 assert.match(await page.locator('#round-table tr').nth(2).innerText(),/0.*Cached summary/s);
 await page.reload();await page.waitForFunction(()=>document.getElementById('profile').value==='broad_coverage');
 assert.equal(await page.locator('#weights input').count(),14);
 await page.selectOption('#saved-run','adaptive-test-117');await page.locator('#load-run').click();
 await page.waitForFunction(()=>document.getElementById('profile').value==='flexible_deal_seekers');
 assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(posts.length,1);
 await mkdir(root+'test-results',{recursive:true});
 await page.screenshot({path:root+'test-results/adaptive-pricing-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No page horizontal overflow');
 await page.evaluate(()=>{scrollTo(0,0);return new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));});
 assert.ok(await page.locator('#round-chart').evaluate(svg=>svg.viewBox.baseVal.width<400),'Charts use readable mobile coordinates');
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
 assert.match(await page.locator('#hypothesis-note').innerText(),/Below initial revenue/);
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
 assert.deepEqual(errors,[]);
 console.log('Adaptive pricing UI passed: scoped80%cap, target8groups, legacy14groups, explicitprofile, historicalprofile-reload, zeroquota, invalidweights, boundedlive explicitstart, read-onlyreload, modelcurve, freshpairedcohorts, retainedfare, break-even-rate, groundedhypothesis, historicdecimalquotes, roundtrace, independentvalidation, Englishsafeoutputs, failedrun, mobileoverflow. All API calls mocked; no paid calls.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}

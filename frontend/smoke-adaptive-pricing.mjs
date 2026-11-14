/** Current Thompson v5 UI, with fully mocked APIs and no paid calls. */
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {readFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const root=fileURLToPath(new URL('.',import.meta.url));
const aliases={'/adaptive-pricing':'adaptive-pricing.html','/admin':'index.html','/':'index.html'};
const server=createServer(async(req,res)=>{const path=new URL(req.url,'http://localhost').pathname,file=aliases[path]||(/^\/[a-z0-9-]+\.(js|css)$/.test(path)?path.slice(1):null);try{if(!file)throw Error();const body=await readFile(root+file);res.writeHead(200,{'Content-Type':file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':'text/html'}).end(body);}catch{res.writeHead(404).end('Not found');}});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const origin=`http://127.0.0.1:${server.address().port}`;
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const population={profile:'flexible_deal_seekers',segments:['Students','Spontaneous solo travellers','Destination-flexible explorers','Frequent bargain travellers','Flexible weekday travellers','Flexible friends','Flexible couples','Deal-only occasional travellers'].map((name,i)=>({id:`flexible-${i}`,name,weight:[.20,.15,.15,.15,.1,.1,.08,.07][i]}))};
const scope={flight_id:'TEST-HKG-KMQ',origin:'HKG',destination:'KMQ',departure_date:'2027-05-18',departure_time:'10:30',as_of_day:28,normal_base_fare:410,initial_member_fare:328,member_fare_cap:328,releasable_seats:45};
const flights=[{...scope,capacity:180,departure_at:'2027-05-18T10:30:00+08:00'},{...scope,flight_id:'TEST-HKG-KMQ-ZERO'}];
const curve=[{price:0,expected_buyers:25,expected_member_revenue:0},{price:100,expected_buyers:20,expected_member_revenue:2000},{price:255,expected_buyers:16,expected_member_revenue:4080},{price:328,expected_buyers:8,expected_member_revenue:2624}];
const rounds=[1,2,3].map(round=>({round,price:round===1?328:255,unique_customers:16,learning_updates:round*16,member_buyers:16,member_revenue:4080,weighted_conversion:.6,paired_delta_vs_initial:1456,curve,analysis_source:'provider_live',analysis:{summary:'Members liked the lower fare. <img src=x onerror=alert(1)>'},hypothesis_test:{source_round:round===1?null:round-1,direction:'lower',status:'supported',summary:'Fresh paired customers bought more.'},decisions:[{person:{segment_label:'Flexible budget traveller',customer_id:`TEST-${round}`},decision:{action:'BUY_MEMBER',reason:'This affordable fare fits my flexible trip. <img src=x onerror=alert(1)>'},source:'provider_live'}]}));
let report={version:'member-thompson-v5-marketing',run_id:'adaptive-test-current',status:'completed',scope,population,config:{profile:'flexible_deal_seekers',final_member_fare_policy:'member-marketing-fare-v1',flight_id:scope.flight_id,forecast_day:28,mode:'synthetic',rounds:3,customers:16,concurrency:4,max_calls:600,seed:117,validation_repeats:3},rounds,counts:{provider_calls:20,cache_hits:2,forced:4,failures:0,peak_parallel:4},progress:{completed_rounds:3,total_rounds:3,cumulative_unique_customers:48},recommendation:{raw_price:255,price:249,revenue_max_price:255,volume_max_price:0,revenue_fraction:.95,model_curve:curve,marketing_adjustment:{policy:'member-marketing-fare-v1',initial_price_before_marketing:328,initial_price:319}},validation:{adoption_result:'ADOPT_CANDIDATE',retained_price:249,break_even_conversion:.82,observed_conversion:.6,initial_price_before_marketing:328,initial_price:319,selected_price_before_marketing:255,selected_price:249,delta_vs_initial:1432,delta_vs_no_offer:704,comparisons:[{policy:'initial',price:319,mean_buyers:8,mean_revenue:2552},{policy:'selected',price:249,mean_buyers:16,mean_revenue:3984},{policy:'no_offer',price:null,mean_buyers:8,mean_revenue:3280}]},elapsed_seconds:70};
let starts=[],scopes=[],setup='ready',empty=false,failFeedback=false,apiReads=0;
await page.route('**/api/**',async route=>{
 const request=route.request(),path=new URL(request.url()).pathname,method=request.method();apiReads++;
 if(path==='/api/flights')return route.fulfill({json:{flights}});
 if(path==='/api/summary')return route.fulfill({json:{dataset:{rows:200000}}});
 if(path==='/api/member-portal/plan')return route.fulfill({json:{membership:{fee:399,term_days:365}}});
 if(path==='/api/adaptive-pricing/status')return route.fulfill(setup==='failed'?{status:503,json:{error:'Setup unavailable'}}:{json:{live_configured:true,population:setup==='ready'?population:null,populations:setup==='ready'?[population]:[]}});
 if(path==='/api/adaptive-pricing/scope'){const body=request.postDataJSON();scopes.push(body);return route.fulfill({json:{population,scope:{...scope,flight_id:body.flight_id,as_of_day:body.forecast_day,releasable_seats:body.flight_id.endsWith('ZERO')?0:45}}});}
 if(path==='/api/adaptive-pricing/runs'&&method==='GET')return route.fulfill(failFeedback?{status:503,json:{error:'Saved feedback unavailable'}}:{json:{runs:empty?[]:[report]}});
 if(path==='/api/adaptive-pricing/runs'&&method==='POST'){const body=request.postDataJSON();starts.push(body);report={...report,config:{...report.config,...body}};return route.fulfill({json:report});}
 if(path===`/api/adaptive-pricing/runs/${report.run_id}`)return route.fulfill({json:report});
 return route.fulfill({status:404,json:{error:'Not found'}});
});
try{
 await mkdir(root+'test-results',{recursive:true});
 await page.goto(origin+'/adaptive-pricing');await page.locator('#route:not([disabled])').waitFor();
 assert.equal(await page.locator('#profile').count(),0);assert.equal(await page.locator('#weights input').count(),8);
 assert.equal(await page.locator('#customers').getAttribute('min'),'8');assert.equal(await page.locator('#start').isDisabled(),true);
 assert.doesNotMatch(await page.locator('body').innerText(),/legacy|Math \+ LLM|Target customer scenario/i);
 await page.selectOption('#route','HKG → KMQ');await page.selectOption('#flight',scope.flight_id);
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
 const completed=structuredClone(report);
 for(const [raw,price] of [[255,249],[30,0],[38,0],[39,39],[103,99],[259,259]]){
  report={...completed,recommendation:{...completed.recommendation,raw_price:raw,price},validation:{...completed.validation,selected_price_before_marketing:raw,selected_price:price,retained_price:price}};
  await page.locator('#refresh-run').click();await page.waitForFunction(([raw,price])=>document.getElementById('marketing-fare-note').textContent.includes(`HK$${raw} → promotional quote HK$${price}`),[raw,price]);
  assert.equal(await page.locator('#recommended-price').innerText(),`HK$${price}`);
  assert.equal(await page.locator('#round-table tr').nth(1).locator('td').first().innerText(),'HK$255','Final quote formatting never rewrites search evidence');
 }
 report=completed;await page.locator('#refresh-run').click();await page.waitForFunction(()=>document.getElementById('recommended-price').textContent==='HK$249');
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
 assert.deepEqual(errors,[]);
 console.log('Current Thompson v5 UI passed: fixed8groups, scoped starts, bounded live submit, raw-vs-promotional evidence, final 0/9 fares, saved reports, curves, confirmation, mobile, safe feedback, retired hashes unavailable without redirect, deleted assets404, removed reports404, configuration-failure guard. All APIs mocked; no paid calls.');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}

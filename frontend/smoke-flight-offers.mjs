/** Manual publication checks. Every API is mocked; no inventory is persisted. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin='http://127.0.0.1:18080';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],submissions=[],retired=[];
page.on('pageerror',error=>errors.push(error.message));
const flights=['2027-05-15','2027-05-18'].map(date=>({flight_id:`TEST-HKG-FUK-${date.replaceAll('-','')}`,origin:'HKG',destination:'FUK',departure_at:date+'T10:30:00+08:00',departure_date:date,capacity:180,demand_band:'low'}));
const [a,b]=flights.map(f=>f.flight_id);
let planFee=399,fail=false,late=false,lateSeen;
// The Forecast view and the offer form each request a forecast for the shared selection; hold all of them.
const lateWaiters=[];const releaseLate=()=>lateWaiters.splice(0).forEach(resolve=>resolve());
const population={profile:'flexible_deal_seekers',segments:Array.from({length:8},(_,i)=>({id:`flexible-${i}`,name:`Flexible travellers ${i+1}`,weight:1/8}))};
await page.route('**/*',async route=>{
 const request=route.request(),path=new URL(request.url()).pathname;
 if(path==='/admin'||path==='/')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./index.html',import.meta.url),'utf8')});
 if(path==='/adaptive-pricing')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./adaptive-pricing.html',import.meta.url),'utf8')});
 if(path==='/members/airports.js')return route.fulfill({contentType:'text/javascript',body:await readFile(new URL('./members/airports.js',import.meta.url),'utf8')});
  if(/^\/[a-z0-9-]+\.(js|css)$/.test(path))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(`.${path}`,import.meta.url),'utf8')});
 if(path.startsWith('/api/optimization')){retired.push(path);return route.fulfill({status:404});}
 if(path==='/api/summary')return route.fulfill({json:{dataset:{rows:200000}}});
 if(path==='/api/flights')return route.fulfill({json:{flights}});
 if(path.startsWith('/api/flights/'))return route.fulfill({json:{flight:flights.find(f=>f.flight_id===path.split('/').at(-1)),history:[28,14,7,0].map(days_to_departure=>({days_to_departure,capacity:180,booked_seats:70,normal_base_fare:410}))}});
 if(path==='/api/forecast'){
  const body=request.postDataJSON();if(late&&body.flight_id===b){lateSeen();await new Promise(resolve=>lateWaiters.push(resolve));}
  if(fail&&body.flight_id===b)return route.fulfill({status:503,json:{error:'Temporary forecast outage'}});
  return route.fulfill({json:{forecast:{releasable_seats:10,risk_release_ceiling:40,expected_remaining_demand:15,expected_empty_seats:95,expected_empty_rate:.5,protection_p90:70,forecast_curve:[],release_status:{round_already_issued:false,blocked_reason:null}}}});
 }
 if(path==='/api/member-portal/plan'){if(request.method()==='POST')planFee=request.postDataJSON().membership_fee;return route.fulfill({json:{membership:{fee:planFee,term_months:6,term_label:'6 months',term_days:181}}});}
 if(path==='/api/offers'){if(request.method()==='POST'){submissions.push(request.postDataJSON());return route.fulfill({json:{offer:{id:'fixture-published'}}});}return route.fulfill({json:{offers:[]}});}
 if(path==='/api/adaptive-pricing/runs')return route.fulfill({json:{runs:[]}});
 if(path==='/api/adaptive-pricing/status')return route.fulfill({json:{population,live_configured:false}});
 if(path==='/api/adaptive-pricing/scope'){const body=request.postDataJSON();return route.fulfill({json:{population,scope:{...flights.find(f=>f.flight_id===body.flight_id),as_of_day:body.forecast_day,normal_base_fare:410,member_fare_cap:328,releasable_seats:10}}});}
 return route.fulfill({status:404});
});
try{
 await mkdir('test-results',{recursive:true});await page.goto(origin+'/admin#members');await page.waitForFunction(()=>document.querySelectorAll('#flight-select option').length>1);
 const offerReady=async(id,day)=>{await page.waitForFunction(([id,day])=>document.getElementById('offer-flight-context').textContent.includes(`${id} · D${day}`)&&document.getElementById('offer-guidance').getAttribute('aria-busy')==='false',[id,day]);};
 // The shared flight bar drives Publish: no separate offer selectors remain.
 assert.equal(await page.locator('#offer-route,#offer-flight,#offer-day').count(),0);
 await page.selectOption('#flight-select',a);await page.locator('[data-day="14"]').click();await offerReady(a,14);
 assert.equal(await page.locator('#offer-optimization-suggestion,#offer-binding-status').count(),0);
 await page.locator('#offer-fare').fill('249');await page.locator('#offer-quantity').fill('3');
 await page.getByRole('link',{name:'Member feedback',exact:true}).click();await page.getByRole('link',{name:'Publish offers',exact:true}).click();await offerReady(a,14);
 assert.equal(await page.locator('#offer-fare').inputValue(),'249');assert.equal(await page.locator('#offer-quantity').inputValue(),'3');assert.equal(submissions.length,0);
 assert.match(await page.locator('#offer-preview').innerText(),/HKD 249/,'The member preview follows the draft fare, in the member site\'s HKD format');
 await page.locator('#publish-button').click();await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('fixture-published'));
 assert.deepEqual(submissions[0],{flight_id:a,days_to_departure:14,quantity:3,base_fare:249});
 await page.locator('#member-fee').fill('499');await page.locator('#save-plan-button').click();await page.waitForFunction(()=>document.getElementById('membership-status').textContent.includes('499'));assert.equal(planFee,499);
 assert.match(await page.locator('#membership-status').innerText(),/for 6 months/);
 assert.match(await page.locator('#offer-preview').innerText(),/First purchase incl\. pass: HKD 748/,'Saving the pass fee immediately updates the first-purchase preview');
 assert.match(await page.locator('#offer-preview').innerText(),/Membership HKD 499 for 6 months/);
 assert.equal(await page.locator('label[for=member-fee]').innerText(),'6-month membership fee (HK$)');
 await page.selectOption('#flight-select',b);await offerReady(b,14);assert.equal(await page.locator('#offer-fare').inputValue(),'');
 const link=new URL(await page.getByRole('link',{name:'Optimize this flight',exact:true}).getAttribute('href'),origin);assert.equal(link.pathname,'/adaptive-pricing');assert.equal(link.searchParams.get('flight_id'),b);assert.equal(link.searchParams.get('forecast_day'),'14');
 await page.locator('#offer-fare').fill('99');await page.locator('#offer-quantity').fill('11');await page.locator('#publish-button').click();assert.equal(submissions.length,1,'Native maximum prevents excess quota');
 await page.locator('#offer-quantity').fill('2');await page.locator('#publish-button').click();await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('fixture-published'));assert.equal(submissions.length,2);
 assert.deepEqual(submissions[1],{flight_id:b,days_to_departure:14,quantity:2,base_fare:99});
 fail=true;await page.locator('[data-day="7"]').click();await page.waitForFunction(()=>document.getElementById('offer-guidance').textContent.includes('Temporary forecast outage'));assert.equal(await page.locator('#publish-button').isDisabled(),true);
 fail=false;late=true;const started=new Promise(resolve=>lateSeen=resolve);await page.locator('[data-day="28"]').click();await started;
 late=false;await page.selectOption('#flight-select',a);await offerReady(a,28);releaseLate();await page.waitForLoadState('networkidle');assert.equal(await page.locator('#flight-select').inputValue(),a);assert.match(await page.locator('#offer-flight-context').innerText(),new RegExp(a));
 // Empty demand invalidates an in-flight release request and clears the old flight's publication state.
 await page.getByRole('link',{name:'Results',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('#results-composition span').length>0);
 await page.getByRole('link',{name:'Publish offers',exact:true}).click();await offerReady(a,28);
 late=true;const emptyStarted=new Promise(resolve=>lateSeen=resolve);await page.selectOption('#flight-select',b);await emptyStarted;
 await page.selectOption('#forecast-demand','high');late=false;releaseLate();await page.waitForLoadState('networkidle');
 assert.equal(await page.locator('#flight-select').isDisabled(),true);
 assert.match(await page.locator('#offer-flight-context').innerText(),/Choose a flight/);
 assert.match(await page.locator('#offer-preview').innerText(),/Choose a flight/);
 assert.equal(await page.locator('#results-composition span').count(),0);
 assert.equal(await page.locator('#results-sold').textContent(),'—');
 await page.locator('#offer-fare').fill('99');await page.locator('#offer-quantity').fill('1');
 assert.equal(await page.locator('#publish-button').isDisabled(),true,'A field edit cannot reactivate publication for the discarded flight');
 assert.equal(submissions.length,2);
 await page.selectOption('#forecast-demand','all');await offerReady(a,28);
 await page.getByRole('link',{name:'Optimize this flight',exact:true}).click();await page.waitForFunction(()=>document.getElementById('scope-day')?.textContent==='D28');assert.equal(await page.locator('#flight').inputValue(),a);
 assert.equal(submissions.length,2);assert.deepEqual(retired,[]);assert.deepEqual(errors,[]);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 console.log('Manual offers passed: flight/day scoped quota, explicit fare/quantity, draft retention, six-month pass fee + immediate preview refresh, empty-demand stale-publication guard, native quota guard, forecast failure, stale response guard, Thompson link, no old optimizer calls. No persisted changes.');
}finally{await browser.close();}

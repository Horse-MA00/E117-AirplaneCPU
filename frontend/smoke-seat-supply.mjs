/** Static source overrides isolate UI changes from any running live experiment. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin=process.env.APP_URL||'http://127.0.0.1:18080';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const flight={flight_id:'DEMO-UI-ICN',origin:'HKG',destination:'ICN',departure_at:'2027-05-15T10:00:00+08:00',capacity:180,demo_priority:0,demo_d28_releasable:44};
const history=[28,14,13,7,1,0].map(days_to_departure=>({days_to_departure,capacity:180,booked_seats:70,available_seats:110,normal_base_fare:500,normal_total_fare:750,mandatory_fees:250}));
let scenario='off',starts=0,exposed=false;
const row=(round,member_fare)=>({round,member_fare,membership_fee:399,total_contribution:1000+member_fare,incremental_contribution:member_fare,profit_margin:.5,mean_member_buyers:exposed?2:0,mean_regular_buyers:3,mean_new_members:exposed?1:0,mean_member_tickets:exposed?3:0,mean_regular_tickets:4,mean_member_offer_customers:exposed?4:0,member_supply_exposure:exposed?7:0,price_evidence_qualified:exposed,price_evidence_status:exposed?'observed_member_sales':'uninformative_no_supply',feasible:exposed,service_rate:exposed?1:0,accepted:false});
function report(){return {run_id:'opt-ui-supply',status:'completed',config:{scope:{...flight,departure_date:'2027-05-15',as_of_day:28},mode:'math',initial_member_fare:75,initial_membership_fee:399,rounds:2,customers:7,price_comparison_protocol:'fixed-seat-profile-local-fare-v1'},progress:{completed_rounds:2,total_rounds:2},counts:{},tracks:[{mode:'math',rounds:[row(1,0),row(2,70)],best:null,decision:'NO_OFFER'}]};}
function forecast(day){
  const carry=scenario==='carry',sold=scenario==='sold',protectedAll=scenario==='protected';
  const occupied=sold?78:70,protection=protectedAll?180-occupied:sold?95:103,headroom=protectedAll?0:7,published=carry?7:0;
  const reason=day===0?'Sales cutoff: no new releases or bookings.':scenario==='quality'?'Release paused: data quality hold.':scenario==='issued'?`D${day} was already published. This round cannot issue more seats.`:carry?'Earlier valid quota already covers the safe capacity. 7 already-published seats remain bookable.':protectedAll?'Normal-demand protection leaves no member headroom.':`7 seats of forecast headroom; next release D7. No new quota at D${day}.`;
  const result={expected_remaining_demand:15,expected_empty_seats:95,expected_empty_rate:95/180,protection_p90:protectedAll?300:protection,risk_release_ceiling:7,releasable_seats:0,beta:.012,rate_now:.7,forecast_curve:[],release_status:{safe_capacity:headroom,member_sold:sold?8:0,total_active_unsold:published,currently_bookable:published,new_release_limit:0,round_history:[]},seat_inventory:{capacity:180,normal_booked:70,member_booked:sold?8:0,occupied,physical_available:180-occupied,normal_protected:protection,member_headroom:headroom,published_bookable:published,unpublished_headroom:headroom-published,held_seats:0,new_releasable_today:0,next_release_day:7,release_reason:reason,release_state:scenario==='issued'?'round_already_issued':undefined}};
  if(scenario==='historical'){Object.assign(result.seat_inventory,{unpublished_headroom:3,held_seats:4,held_published_headroom:4,next_release_day:null,release_state:'historical_view',release_reason:'Historical view: a later release was already published.'});result.release_status.historical_view=true;}
  if(scenario==='overage'){Object.assign(result.seat_inventory,{normal_booked:178,member_booked:2,confirmed_member_bookings:5,reported_occupied:183,member_inventory_overage:3,occupied:180,physical_available:0,normal_protected:0,member_headroom:0,published_bookable:0,unpublished_headroom:0,held_seats:0,next_release_day:null,release_state:'no_physical_seats',release_reason:'No physical seats remain.'});}
  return result;
}
await page.route('**/*',async route=>{
  const u=new URL(route.request().url()),path=u.pathname,reply=json=>route.fulfill({json});
  if(path==='/admin'||path==='/')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./index.html',import.meta.url),'utf8')});
  if(['/app.js','/optimization.js','/contribution-explanation.js','/seat-status.js','/styles.css','/continuous.js','/price-chart.js'].includes(path))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(`.${path}`,import.meta.url),'utf8')});
  if(path==='/api/summary')return reply({dataset:{catalog_rows:280364},llm:{configured:false}});
  if(path==='/api/member-portal/plan')return reply({membership:{fee:399,term_days:365}});
  if(path==='/api/flights')return reply({flights:[flight]});
  if(path===`/api/flights/${flight.flight_id}`)return reply({flight,history});
  if(path==='/api/forecast')return reply({forecast:forecast(route.request().postDataJSON().days_to_departure)});
  if(path==='/api/optimization/initial-policy')return reply({initial_member_fare:75,scope:{...flight,departure_date:'2027-05-15',as_of_day:28,available_seats:110,normal_base_fare:500,releasable_seats:0,member_supply_exposure:0,optimization_eligible:false,optimization_unavailable_reason:'No member supply at this snapshot.'}});
  if(path==='/api/optimization/runs'){
    if(route.request().method()==='POST'){starts++;return route.fulfill({status:400,json:{error:'No supply'}});}
    return reply({runs:[report()]});
  }
  if(path==='/api/optimization/runs/opt-ui-supply')return reply(report());
  if(path.startsWith('/api/'))return reply({runs:[],panels:[],segments:[],offers:[]});
  return route.continue();
});
try{
  await mkdir('test-results',{recursive:true});await page.goto(origin+'/admin');
  await page.waitForFunction(()=>document.getElementById('headroom-value').textContent==='7 seats');
  await page.locator('#day-slider').fill('15');
  await page.waitForFunction(()=>document.getElementById('member-allocation-detail').textContent.includes('D13'));
  assert.equal(await page.locator('#release-value').innerText(),'0 seats');
  assert.equal(await page.locator('#bookable-value').innerText(),'0 seats');
  assert.match(await page.locator('#member-allocation-detail').innerText(),/7 seats of forecast headroom; next release D7/);
  assert.match(await page.locator('#seat-composition-legend').innerText(),/Unpublished forecast headroom/);
  const sum=()=>page.locator('#seat-composition span').evaluateAll(parts=>parts.reduce((total,p)=>total+Number(p.dataset.seats),0));
  assert.equal(await sum(),180);await page.screenshot({path:'test-results/forecast-headroom-offround-desktop.png',fullPage:true});
  scenario='carry';await page.locator('[data-day="14"]').click();
  await page.waitForFunction(()=>document.getElementById('bookable-value').textContent==='7 seats');
  assert.equal(await page.locator('#release-value').innerText(),'0 seats');assert.equal(await sum(),180);
  assert.match(await page.locator('#release-status').innerText(),/quota already covers/);
  scenario='sold';await page.locator('[data-day="7"]').click();
  await page.waitForFunction(()=>document.getElementById('booked-value').textContent==='78');
  assert.match(await page.locator('#booked-detail').innerText(),/70 normal \+ 8 member/);assert.equal(await sum(),180);
  scenario='protected';await page.locator('[data-day="28"]').click();
  await page.waitForFunction(()=>document.getElementById('headroom-value').textContent==='0 seats');
  assert.equal(await page.locator('#protection-value').innerText(),'110 seats');assert.equal(await sum(),180);
  for(const [mode,day,message] of [['quality',14,'data quality'],['issued',7,'already published']]){scenario=mode;await page.locator(`[data-day="${day}"]`).click();await page.waitForFunction(text=>document.getElementById('member-allocation-detail').textContent.includes(text),message);}
  scenario='historical';await page.locator('#day-slider').fill('15');
  await page.waitForFunction(()=>document.getElementById('headroom-detail').textContent.includes('4 published on hold'));
  assert.match(await page.locator('#headroom-detail').innerText(),/3 unpublished \+ 0 published and bookable \+ 4 published on hold/);
  assert.equal(await sum(),180);assert.equal(await page.locator('#go-pricing').isDisabled(),true);
  assert.doesNotMatch(await page.locator('#go-pricing').innerText(),/null|undefined/);
  assert.equal(await page.locator('#seat-composition [data-part="published-held"]').getAttribute('data-seats'),'4');
  scenario='overage';await page.locator('[data-day="7"]').click();
  await page.waitForFunction(()=>document.getElementById('booked-value').textContent==='183');
  assert.match(await page.locator('#booked-detail').innerText(),/178 normal \+ 5 member/);
  assert.equal(await page.locator('#risk-release-value').innerText(),'0 seats');
  assert.equal(await page.locator('#member-sold-value').innerText(),'5 seats');
  assert.match(await page.locator('#seat-inventory-warning').innerText(),/3 over capacity/);
  assert.equal(await page.locator('#seat-inventory-warning').isVisible(),true);assert.equal(await sum(),180);
  assert.equal(await page.locator('#go-pricing').isDisabled(),true);
  assert.match(await page.locator('#chart-caption').innerText(),/Normal-demand baseline only/);
  assert.match(await page.locator('#chart-caption').innerText(),/Member demo bookings are excluded/);
  assert.match(await page.locator('#empty-detail').innerText(),/member bookings excluded/);
  await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:'test-results/forecast-seat-status-mobile.png',fullPage:true});
  await page.locator('a[href="#optimization"]').first().click();await page.waitForFunction(()=>document.getElementById('optimization-status').textContent==='Completed');
  await page.locator('#optimization-route').selectOption('HKG-ICN');await page.locator('#optimization-flight').selectOption(flight.flight_id);
  await page.waitForFunction(()=>document.getElementById('optimization-scope').textContent.includes('No member supply'));
  assert.equal(await page.locator('#optimization-start').isDisabled(),true);assert.equal(starts,0);
  assert.equal(await page.locator('#optimization-price-profit circle').count(),0);
  assert.match(await page.locator('#optimization-price-evidence').innerText(),/No member-price evidence/);
  assert.equal(await page.locator('#optimization-rounds-table tr').count(),2);
  exposed=true;await page.locator('#optimization-refresh').click();
  await page.waitForFunction(()=>document.querySelectorAll('#optimization-price-profit circle').length===2);
  assert.match(await page.locator('#optimization-tradeoffs').innerText(),/Most member buyers/);
  await page.locator('#optimization-price-profit circle').first().focus();
  assert.match(await page.locator('#optimization-price-detail').innerText(),/2 member buyers \/ 3 regular buyers/);
  assert.match(await page.locator('#optimization-price-detail').innerText(),/1 joins/);
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.deepEqual(errors,[]);console.log('Seat-supply UI passed: 7 headroom/0 new, carried bookable quota, sold once, reserve clamp, reason states, no-supply start guard, split buyer metrics, exposure-qualified chart, held quota, historical action guard, raw overcapacity warning, normal-only baseline labels, mobile.');
}catch(error){console.error(JSON.stringify({pageErrors:errors,banner:await page.locator('#error').textContent(),headroom:await page.locator('#headroom-value').textContent()}));throw error;}finally{await browser.close();}

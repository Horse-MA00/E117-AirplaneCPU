/** Offline UI checks: real local assets, fully intercepted synthetic API responses. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
import {catalogAirportCodes} from './members/airports.js';
const origin='http://127.0.0.1:18080';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],blocked=[];
page.on('pageerror',e=>errors.push(e.message));
const flights=[['HND','low',.42,350],['ICN','medium',.74,560],['TPE','high',.92,830]].map(([destination,demand_band,demand_expected_load_rate,normal_base_fare])=>({flight_id:`DEMO-HKG-${destination}-20270515`,origin:'HKG',destination,departure_at:'2027-05-15T10:00:00+08:00',departure_date:'2027-05-15',capacity:180,demand_band,demand_expected_load_rate,demand_reference_day:28,normal_base_fare}));
const extraFlights=[
 {...flights[0],flight_id:'SAME-DATE-HKG-HND'},
 {...flights[0],flight_id:'TEST-HKG-NRT',destination:'NRT'},
 {...flights[0],flight_id:'RETURN-HND-HKG',origin:'HND',destination:'HKG'},
 {...flights[0],flight_id:'CATALOG-HKG-ZZZ',destination:'ZZZ'},
];
let includeUnknown=false,includeRoutes=false,starts=0,forecastCalls=0;
const population={profile:'flexible_deal_seekers',segments:Array.from({length:8},(_,i)=>({id:`flexible-${i}`,name:`Flexible travellers ${i+1}`,weight:1/8}))};
const scopeRequests=[];
const catalogue=()=>[...flights,...(includeRoutes?extraFlights:[]),...(includeUnknown?[{...flights[0],flight_id:'UNCLASSIFIED-HKG-HND',demand_band:undefined,demand_expected_load_rate:null}]:[])];
const history=f=>[28,14,7,1,0].map(days_to_departure=>({days_to_departure,capacity:180,booked_seats:70,available_seats:110,normal_base_fare:f.normal_base_fare,normal_total_fare:f.normal_base_fare+250,mandatory_fees:250}));
await page.route('**/*',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,reply=json=>route.fulfill({json});
  if(path==='/admin'||path==='/')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./index.html',import.meta.url),'utf8')});
  if(/^\/fonts\/inter-\d{3}\.woff2$/.test(path))return route.fulfill({contentType:'font/woff2',body:await readFile(new URL(`.${path}`,import.meta.url))});
  if(path==='/members/airports.js')return route.fulfill({contentType:'text/javascript',body:await readFile(new URL('./members/airports.js',import.meta.url),'utf8')});
  if(/^\/[a-z0-9-]+\.(js|css)$/.test(path))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(`.${path}`,import.meta.url),'utf8')});
  if(path==='/api/summary')return reply({dataset:{catalog_rows:280364},llm:{configured:false}});
  if(path==='/api/member-portal/plan')return reply({membership:{fee:399,term_months:6,term_label:'6 months',term_days:181}});
  if(path==='/api/flights')return reply({flights:catalogue()});
  if(path.startsWith('/api/flights/')){const f=catalogue().find(f=>f.flight_id===decodeURIComponent(path.split('/').at(-1)));return reply({flight:f,history:history(f)});}
  if(path==='/api/forecast'){forecastCalls++;return reply({forecast:{expected_remaining_demand:20,expected_empty_seats:90,expected_empty_rate:.5,protection_p90:70,releasable_seats:40,risk_release_ceiling:40,beta:.012,rate_now:.7,forecast_curve:[],release_status:{safe_capacity:40,member_sold:0,total_active_unsold:0,currently_bookable:0,new_release_limit:40,round_history:[]}}});}
  if(path==='/adaptive-pricing')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./adaptive-pricing.html',import.meta.url),'utf8')});
  if(path==='/api/adaptive-pricing/status')return reply({live_configured:false,population,populations:[population]});
  if(path==='/api/adaptive-pricing/scope'){
    const body=request.postDataJSON(),flight=catalogue().find(f=>f.flight_id===body.flight_id);
    scopeRequests.push(body);
    return reply({population,scope:{initial_member_fare:Math.floor(flight.normal_base_fare*.8),...flight,as_of_day:body.forecast_day,available_seats:110,normal_base_fare:flight.normal_base_fare,member_fare_cap:Math.floor(flight.normal_base_fare*.8),member_fare_cap_ratio:.8,releasable_seats:40,member_supply_exposure:40,optimization_eligible:true}});
  }
  if(path==='/api/adaptive-pricing/runs'){if(request.method()==='POST')starts++;return reply({runs:[]});}
  if(path.startsWith('/api/'))return reply({runs:[],panels:[],segments:[],offers:[]});
  if(path==='/favicon.ico')return route.fulfill({status:204});
  blocked.push(path);return route.abort();
});
try{
  await mkdir(new URL('test-results/',import.meta.url),{recursive:true});
  await page.goto(origin+'/admin');
  await page.waitForFunction(()=>document.getElementById('headroom-value').textContent==='40 seats');
  assert.equal(await page.getByLabel('Demand level',{exact:true}).count(),1);
  assert.equal(await page.locator('search[aria-label="Filter forecast flights"]').count(),1);
  assert.equal(await page.locator('#forecast-demand option[value="low"]').innerText(),'Low demand (1)');
  assert.equal(await page.locator('#forecast-demand option[value="medium"]').innerText(),'Medium demand (1)');
  assert.equal(await page.locator('#forecast-demand option[value="high"]').innerText(),'High demand (1)');
  await page.locator('#flight-select').selectOption(flights[0].flight_id);
  await page.locator('#forecast-demand').selectOption('low');
  assert.equal(await page.locator('#flight-select').inputValue(),flights[0].flight_id,'A matching selection must be retained');
  assert.equal(await page.locator('#flight-select option').count(),1);
  await page.locator('#forecast-demand').focus();
  assert.notEqual(await page.locator('#forecast-demand').evaluate(n=>getComputedStyle(n).outlineStyle),'none');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('#context-from').evaluate(n=>document.activeElement===n),true,'Keyboard focus follows the DOM order: demand, From, To, flight');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('#context-to').evaluate(n=>document.activeElement===n),true,'To follows From without a hidden route-search control');
  await page.keyboard.press('Tab');
  assert.equal(await page.locator('#flight-select').evaluate(n=>document.activeElement===n),true,'Keyboard focus follows the DOM order');
  await page.locator('#forecast-demand').selectOption('medium');
  await page.waitForFunction(()=>document.getElementById('flight-select').value.includes('ICN'));
  await page.locator('#forecast-demand').selectOption('high');
  await page.waitForFunction(()=>document.getElementById('flight-select').value.includes('TPE'));
  await page.locator('[data-day="14"]').click();
  assert.equal(await page.locator('#forecast-demand').inputValue(),'high');
  assert.equal(await page.locator('#flight-select option').count(),1,'Moving the timeline must not reclassify D28 groups');
  // D14 also refreshes the offer suggestion; settle both reads before counting
  // requests caused by the later empty selection.
  await page.waitForLoadState('networkidle');
  // A day change can send more than one forecast request (Forecast view and offer form).
  // Let them all land before taking the baseline, so a late reply is not counted as a stale request.
  const settleForecasts=async()=>{for(let previous=-1;previous!==forecastCalls;){previous=forecastCalls;await page.waitForTimeout(300);}};
  await settleForecasts();
  const calls=forecastCalls;
  await page.locator('#forecast-demand').selectOption('unknown');
  assert.equal(await page.locator('#flight-select').isDisabled(),true);
  assert.equal(await page.locator('#flight-main').isHidden(),true,'Empty filters must hide stale forecasts');
  assert.equal(await page.locator('#flight-filter-empty').isVisible(),true);
  assert.equal(await page.locator('#go-pricing').isDisabled(),true);
  await page.locator('[data-day="7"]').click();
  await settleForecasts();
  assert.equal(forecastCalls,calls,'Empty selection must not request a stale flight');
  await page.locator('#forecast-demand').selectOption('low');
  await page.waitForFunction(()=>!document.getElementById('flight-main').hidden&&document.getElementById('headroom-value').textContent==='40 seats');
  await page.screenshot({path:'test-results/demand-filter-forecast-desktop.png',fullPage:true});
  await page.locator('[data-day="28"]').click();
  await page.waitForFunction(()=>!document.getElementById('go-pricing').disabled);
  await page.locator('#go-pricing').click();
  await page.waitForFunction(()=>document.getElementById('scope-day')?.textContent==='D28');
  assert.equal(await page.locator('#flight').inputValue(),flights[0].flight_id,'Filtered Forecast selection reaches Thompson');
  assert.equal(await page.locator('#release-day').inputValue(),'28');
  assert.equal(await page.locator('#optimization-form').count(),0);
  await page.locator('#release-day').selectOption('14');
  await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D14');
  assert.equal(scopeRequests.at(-1).forecast_day,14);
  assert.equal(scopeRequests.at(-1).flight_id,flights[0].flight_id);
  assert.ok(scopeRequests.every(body=>!['initial_member_fare','initial_membership_fee','fare_max'].some(key=>key in body)));
  assert.equal(starts,0,'Opening a scoped Thompson experiment never starts it');
  await page.screenshot({path:'test-results/demand-filter-optimization-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Mobile layout must not overflow');
  await page.screenshot({path:'test-results/demand-filter-optimization-mobile.png',fullPage:true});
  // Full location lists stay independent of both demand and the opposite
  // endpoint. Flights, not airport choices, are filtered by the intersection.
  includeRoutes=true;await page.goto(origin+'/admin');
  await page.waitForFunction(()=>document.getElementById('headroom-value').textContent==='40 seats');
  const checkFullPlaces=async(from,to)=>{
    for(const id of [from,to]){
      const codes=await page.locator(`#${id} option`).evaluateAll(options=>options.map(o=>o.value));
      for(const code of [...catalogAirportCodes,'ZZZ'])assert.ok(codes.includes(code),`${id} omits ${code}`);
      assert.ok(codes.includes('region:JP'));assert.ok(codes.includes(''),'Anywhere remains available');
      assert.equal(await page.locator(`#${id}`).isDisabled(),false);
    }
  };
  await checkFullPlaces('context-from','context-to');
  await page.selectOption('#context-from','HND');await page.selectOption('#context-to','HKG');
  await page.waitForFunction(()=>document.getElementById('flight-select').value==='RETURN-HND-HKG');
  await page.selectOption('#context-from','region:JP');
  assert.equal(await page.locator('#flight-select').inputValue(),'RETURN-HND-HKG','Country From includes returning flights');
  await page.selectOption('#context-from','HKG');await page.selectOption('#context-to','region:JP');
  const japanIds=await page.locator('#flight-select option').evaluateAll(options=>options.map(o=>o.value));
  assert.deepEqual(japanIds.sort(),[flights[0].flight_id,'SAME-DATE-HKG-HND','TEST-HKG-NRT'].sort());
  for(const id of japanIds)assert.ok((await page.locator(`#flight-select option[value="${id}"]`).innerText()).includes(id),'Same-day flight labels retain distinct complete synthetic IDs');
  await page.selectOption('#flight-select','SAME-DATE-HKG-HND');await page.selectOption('#forecast-demand','low');
  assert.equal(await page.locator('#flight-select').inputValue(),'SAME-DATE-HKG-HND','A matching selected flight survives combined filters');
  await checkFullPlaces('context-from','context-to');
  await page.selectOption('#context-from','FUK');await page.selectOption('#context-to','ICN');
  assert.equal(await page.locator('#context-from').inputValue(),'FUK');assert.equal(await page.locator('#context-to').inputValue(),'ICN');
  assert.equal(await page.locator('#flight-select').isDisabled(),true);assert.equal(await page.locator('#flight-main').isHidden(),true);
  assert.equal(await page.locator('#go-pricing').isDisabled(),true);assert.equal(await page.locator('#publish-button').isDisabled(),true);
  await checkFullPlaces('context-from','context-to');
  await page.selectOption('#context-from','');await page.selectOption('#context-to','');
  assert.equal(await page.locator('#flight-select option').count(),5,'Anywhere includes all low-demand directions, including extra catalog airports');
  await page.goto(origin+'/adaptive-pricing?flight_id=RETURN-HND-HKG&forecast_day=7');
  await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D7');
  assert.equal(await page.locator('#opt-from').inputValue(),'HND');assert.equal(await page.locator('#opt-to').inputValue(),'HKG');
  await checkFullPlaces('opt-from','opt-to');
  await page.selectOption('#opt-to','PUS');
  assert.equal(await page.locator('#opt-to').inputValue(),'PUS');assert.equal(await page.locator('#flight').isDisabled(),true);
  assert.equal(await page.locator('#start').isDisabled(),true);assert.equal(await page.locator('#normal-fare').innerText(),'—');
  await page.waitForLoadState('networkidle');const emptyScopeCalls=scopeRequests.length;
  await page.locator('[data-round="14"]').click();await page.waitForLoadState('networkidle');
  assert.equal(scopeRequests.length,emptyScopeCalls,'An empty From/To combination must not reuse the discarded scope');
  await checkFullPlaces('opt-from','opt-to');
  await page.selectOption('#opt-from','region:JP');await page.selectOption('#opt-to','HKG');await page.selectOption('#flight','RETURN-HND-HKG');
  await page.waitForFunction(()=>document.getElementById('scope-day').textContent==='D14');
  assert.equal(scopeRequests.at(-1).flight_id,'RETURN-HND-HKG');assert.equal(starts,0);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'The expanded location bar fits mobile');
  includeRoutes=false;
  includeUnknown=true;await page.goto(origin+'/admin');
  await page.waitForFunction(()=>document.querySelector('#forecast-demand option[value="unknown"]').textContent==='Unclassified (1)');
  await page.locator('#forecast-demand').selectOption('unknown');
  assert.equal(await page.locator('#flight-select').inputValue(),'UNCLASSIFIED-HKG-HND','Missing metadata must stay unclassified');
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  console.log(JSON.stringify({status:'passed',checks:['three demand bands and counts','fixed D28 reference','selection preservation','empty state and stale-request prevention','filtered-flight Thompson entry','scope refresh without price overrides','keyboard labels and mobile layout','missing metadata fallback','full airport/country choices independent of filters','return routes and country matching','same-day flight identifiers','empty From/To state and scope guard'],optimization_starts:starts}));
}finally{await browser.close();}

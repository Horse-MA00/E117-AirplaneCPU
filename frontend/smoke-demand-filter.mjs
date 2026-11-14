/** Offline UI checks: real local assets, fully intercepted synthetic API responses. */
import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';
const origin='http://127.0.0.1:18080';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[],blocked=[];
page.on('pageerror',e=>errors.push(e.message));
const flights=[['HND','low',.42,350],['ICN','medium',.74,560],['TPE','high',.92,830]].map(([destination,demand_band,demand_expected_load_rate,normal_base_fare])=>({flight_id:`DEMO-HKG-${destination}-20270515`,origin:'HKG',destination,departure_at:'2027-05-15T10:00:00+08:00',departure_date:'2027-05-15',capacity:180,demand_band,demand_expected_load_rate,demand_reference_day:28,normal_base_fare}));
let includeUnknown=false,starts=0,forecastCalls=0;
const population={profile:'flexible_deal_seekers',segments:Array.from({length:8},(_,i)=>({id:`flexible-${i}`,name:`Flexible travellers ${i+1}`,weight:1/8}))};
const scopeRequests=[];
const catalogue=()=>includeUnknown?[...flights,{...flights[0],flight_id:'UNCLASSIFIED-HKG-HND',demand_band:undefined,demand_expected_load_rate:null}]:flights;
const history=f=>[28,14,7,1,0].map(days_to_departure=>({days_to_departure,capacity:180,booked_seats:70,available_seats:110,normal_base_fare:f.normal_base_fare,normal_total_fare:f.normal_base_fare+250,mandatory_fees:250}));
await page.route('**/*',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname,reply=json=>route.fulfill({json});
  if(path==='/admin'||path==='/')return route.fulfill({contentType:'text/html',body:await readFile(new URL('./index.html',import.meta.url),'utf8')});
  if(/^\/[a-z0-9-]+\.(js|css)$/.test(path))return route.fulfill({contentType:path.endsWith('.css')?'text/css':'text/javascript',body:await readFile(new URL(`.${path}`,import.meta.url),'utf8')});
  if(path==='/api/summary')return reply({dataset:{catalog_rows:280364},llm:{configured:false}});
  if(path==='/api/member-portal/plan')return reply({membership:{fee:399,term_days:181,term_months:6,term_label:'6 months'}});
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
  const calls=forecastCalls;
  await page.locator('#forecast-demand').selectOption('unknown');
  assert.equal(await page.locator('#flight-select').isDisabled(),true);
  assert.equal(await page.locator('#flight-main').isHidden(),true,'Empty filters must hide stale forecasts');
  assert.equal(await page.locator('#flight-filter-empty').isVisible(),true);
  assert.equal(await page.locator('#go-pricing').isDisabled(),true);
  await page.locator('[data-day="7"]').click();
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
  includeUnknown=true;await page.goto(origin+'/admin');
  await page.waitForFunction(()=>document.querySelector('#forecast-demand option[value="unknown"]').textContent==='Unclassified (1)');
  await page.locator('#forecast-demand').selectOption('unknown');
  assert.equal(await page.locator('#flight-select').inputValue(),'UNCLASSIFIED-HKG-HND','Missing metadata must stay unclassified');
  assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  console.log(JSON.stringify({status:'passed',checks:['three demand bands and counts','fixed D28 reference','selection preservation','empty state and stale-request prevention','filtered-flight Thompson entry','scope refresh without price overrides','keyboard labels and mobile layout','missing metadata fallback'],optimization_starts:starts}));
}finally{await browser.close();}

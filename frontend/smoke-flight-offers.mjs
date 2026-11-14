/** Real catalog/forecasts; fixture suggestions and intercepted publication.
 * No offer is persisted by this test. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';

const origin=process.env.APP_URL||'http://127.0.0.1:8000';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];
page.on('pageerror',error=>errors.push(error.message));
const a='NET-HKG-FUK-20270515',b='NET-HKG-FUK-20270518';
let submissions=[],planFee=399;
await page.route('**/api/member-portal/plan',route=>{if(route.request().method()==='POST')planFee=route.request().postDataJSON().membership_fee;return route.fulfill({json:{membership:{fee:planFee,term_days:365}}});});
await page.route('**/api/forecast',async route=>{
  const response=await route.fetch(),data=await response.json();
  if([a,b].includes(route.request().postDataJSON().flight_id)){
    data.forecast.releasable_seats=10;
    data.forecast.release_status={...data.forecast.release_status,round_already_issued:false,blocked_reason:null};
  }
  await route.fulfill({response,json:data});
});
await page.route('**/api/optimization/suggestions?**',route=>{
  const url=new URL(route.request().url()),flight=url.searchParams.get('flight_id');
  return route.fulfill({json:{flight_id:flight,forecast_day:Number(url.searchParams.get('day')),current_release_limit:10,
    suggestions:flight===a?[{run_id:'opt-browser-fixture',mode:'math',decision:'OFFER',member_fare:42.25,membership_fee:499,suggested_new_seats:3}]:[],
    reason:'No completed validated optimization for this exact flight and round.'}});
});
await page.route('**/api/offers',route=>{
  if(route.request().method()!=='POST')return route.continue();
  submissions.push(route.request().postDataJSON());
  return route.fulfill({json:{offer:{id:'fixture-published'},simulated:true}});
});
try{
  await page.goto(origin+'/admin#members');
  await page.waitForFunction(()=>document.querySelectorAll('#offer-route option').length>1);
  const routes=await page.locator('#offer-route option').evaluateAll(options=>options.map(o=>o.value).filter(Boolean));
  assert.ok(routes.length>=74);
  const forecastFlight=await page.locator('#flight-select').inputValue();
  await page.locator('#offer-route').selectOption('HKG-FUK');
  await page.locator('#offer-flight').selectOption(a);
  await page.locator('#offer-day').selectOption('14');
  await page.getByRole('button',{name:'Use this suggestion',exact:true}).waitFor();
  await page.getByRole('button',{name:'Use this suggestion',exact:true}).click();
  assert.equal(await page.locator('#offer-fare').inputValue(),'42.25');
  assert.equal(await page.locator('#offer-quantity').inputValue(),'3');
  assert.equal(await page.locator('#publish-button').isDisabled(),true,'Linked offer waits for the matching published pass fee');
  assert.match(await page.locator('#offer-binding-status').innerText(),/Save the HK\$499/);
  await page.locator('#save-plan-button').click();
  await page.waitForFunction(()=>!document.querySelector('#publish-button').disabled);
  assert.equal(planFee,499);
  assert.equal(await page.locator('#flight-select').inputValue(),forecastFlight,'Manage selection must not switch Forecast selection');
  await page.screenshot({path:'test-results/offer-flight-suggestion-desktop.png',fullPage:true});
  await page.locator('#publish-button').click();
  await page.waitForFunction(()=>document.querySelector('#notice').textContent.includes('fixture-published'));
  assert.equal(submissions.length,1);
  assert.deepEqual(submissions[0],{flight_id:a,days_to_departure:14,quantity:3,base_fare:42.25,optimization_run_id:'opt-browser-fixture',optimization_mode:'math'});
  await page.locator('#offer-flight').selectOption(b);
  await page.waitForFunction(()=>document.querySelector('#offer-optimization-suggestion').textContent.includes('No completed validated optimization'));
  assert.equal(await page.locator('#offer-fare').inputValue(),'','Changing flight clears the old price draft');
  assert.equal(await page.getByRole('button',{name:'Use this suggestion',exact:true}).count(),0);
  await page.locator('#offer-fare').fill('50');await page.locator('#offer-quantity').fill('2');
  const posted=page.waitForResponse(response=>response.url().endsWith('/api/offers')&&response.request().method()==='POST');
  await page.locator('#publish-button').click();
  await posted;
  assert.equal(submissions.length,2);
  assert.deepEqual(submissions[1],{flight_id:b,days_to_departure:14,quantity:2,base_fare:50},'Manual draft must not retain the other flight’s optimization binding');
  await page.locator('#offer-route').selectOption('FUK-HKG');
  assert.equal(await page.locator('#publish-button').isDisabled(),true);
  assert.equal(await page.locator('#offer-fare').inputValue(),'');
  assert.match(await page.locator('#offer-flight-context').innerText(),/Choose a departure/);
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'No horizontal overflow');
  await page.screenshot({path:'test-results/offer-flight-selection-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log('Flight offers passed: 74 routes, independent selectors, matched suggestion, exact publish binding, cross-flight draft clearing, unbound manual edit, mobile layout.');
}finally{await browser.close();}

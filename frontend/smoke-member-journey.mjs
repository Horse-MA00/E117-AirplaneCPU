import assert from 'node:assert/strict';
import {readFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {chromium} from 'playwright';
const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_EXECUTABLE_PATH?{executablePath:process.env.CHROMIUM_EXECUTABLE_PATH}:{})});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const origin=process.env.APP_URL || 'http://127.0.0.1:8000';
const root=new URL('./members/',import.meta.url);
await page.route('**/members/**',async route=>{
 const path=new URL(route.request().url()).pathname.slice('/members/'.length)||'index.html';
 try {await route.fulfill({body:await readFile(new URL(path,root)),contentType:path.endsWith('.js')?'text/javascript':path.endsWith('.css')?'text/css':'text/html'});} catch {await route.continue();}
});
const flights=[{flight_id:'out',offer_id:'out',origin:'HKG',destination:'NRT',departure_date:'2027-05-15',base_fare:100,mandatory_fees:250,total:350,normal_total:700,bookable_seats:10},
 {flight_id:'back',offer_id:'back',origin:'NRT',destination:'HKG',departure_date:'2027-05-18',base_fare:100,mandatory_fees:250,total:350,normal_total:700,bookable_seats:10},
 {flight_id:'sold',offer_id:'sold',origin:'HKG',destination:'KIX',departure_date:'2027-05-15',base_fare:50,mandatory_fees:250,total:300,normal_total:600,bookable_seats:0}];
flights[0].mandatory_fees=673;flights[0].total=773;
flights[0].fee_breakdown={checked_on:'2026-11-14',terminal_assumption:'Hong Kong',note:'Demo estimate',components:[],lines:[{label:'YR · Fuel surcharge',amount:318},{label:'Government & airport charges',amount:355}]};
flights[1].base_fare=50;flights[1].mandatory_fees=959.67;flights[1].total=1009.67;
flights[1].fee_breakdown={checked_on:'2026-11-14',terminal_assumption:'Terminal 2',note:'Demo estimate',components:[],lines:[{label:'YR · Fuel surcharge',amount:617.88},{label:'Government & airport charges',amount:302.07},{label:'E-payment fee',amount:39.72}]};
for (const flight of flights) { flight.normal_base_fare=500; flight.normal_total=500+Number(flight.mandatory_fees || 250); }
const account={customer_id:'journey-fixture',membership:null,bookings:[]};let joins=0,books=0;
await page.route('**/api/member-portal/**',async route=>{
 const path=new URL(route.request().url()).pathname;
 if(path.endsWith('/session'))return route.fulfill({json:{authenticated:true,user:{customer_id:account.customer_id,email:account.customer_id+'@uoption.test',name:'Journey fixture'},account,simulated:true}});
 if(path.endsWith('/config'))return route.fulfill({json:{membership:{fee:399,term_days:181,term_months:6,term_label:'6 months'}}});
 if(path.endsWith('/flights'))return route.fulfill({json:{flights}});
 if(path.includes('/accounts/'))return route.fulfill({json:account});
 const body=route.request().postDataJSON();
 if(path.endsWith('/join')){joins++;account.membership={active:true,fee:399,expires:2000000000};return route.fulfill({json:{member:account.membership}});}
 if(path.endsWith('/book')){books++;const f=flights.find(f=>f.offer_id===body.offer_id);assert.equal(body.expected_total,f.total);f.bookable_seats--;const b={...f,id:'booking-'+books};account.bookings.push(b);return route.fulfill({json:{booking:b}});}
 await route.abort();
});
try {
 await page.goto(`${origin}/members/`);
 await page.locator('.flight-card').first().waitFor();
 // Route draft, date shortcut and sorting share the same applied-filter model.
 assert.equal(await page.locator('.date-fare').count(),2);
 await page.locator('#origin').selectOption('HKG');
 await page.locator('#destination').selectOption('region:JP');
 await page.locator('#swap-airports').click();
 assert.equal(await page.locator('#origin').inputValue(),'region:JP');
 assert.equal(await page.locator('#destination').inputValue(),'HKG');
 assert.equal(await page.locator('.flight-card').count(),2);
 await page.locator('#search-button').click();
 assert.equal(await page.locator('.flight-card').count(),1);
 assert.equal(await page.locator('.date-fare').count(),1);
 await page.locator('#clear-search').click();
 // Selecting a visible date must not silently submit a draft route.
 await page.locator('#destination').selectOption('KIX');
 await page.locator('.date-fare[data-date="2027-05-15"]').click();
 assert.equal(await page.locator('#destination').inputValue(),'');
 assert.equal(await page.locator('.flight-card').count(),1);
 assert.equal(await page.locator('.date-fare[data-date="2027-05-15"]').getAttribute('aria-pressed'),'true');
 await page.locator('#clear-search').click();
 await page.locator('#flight-sort').selectOption('total');
 assert.equal(await page.locator('.flight-card').first().getAttribute('data-flight-id'),'out');
 await page.locator('#flight-sort').selectOption('price');
 assert.equal(await page.locator('.flight-card').first().getAttribute('data-flight-id'),'back');
 await page.locator('#flight-sort').selectOption('date');
 // A reversed range is blocked and focused.
 await page.locator('#departure-from').fill('2027-05-18');
 await page.locator('#departure-to').fill('2027-05-15');
 await page.locator('#departure-to').blur();
 await page.locator('#search-button').click();
 assert.equal(await page.locator('#departure-to').evaluate(el=>document.activeElement===el),true);
 assert.equal(await page.locator('#flight-search').evaluate(el=>el.checkValidity()),false);
 await page.locator('#clear-search').click();
 assert.equal(await page.locator('#available-only').isChecked(),true);
 assert.equal(await page.locator('.flight-card').count(),2);
 assert.equal(await page.locator('.journey-discovery, #journey-plan').count(),0);
 assert.match(await page.locator('.first-purchase').first().innerText(),/1,172/);
 await page.locator('.choose-flight').first().click();
 assert.match(await page.locator('#checkout-content').innerText(),/YR · Fuel surcharge/);
 assert.match(await page.locator('#checkout-content').innerText(),/Government & airport charges/);
 // Non-members see the membership + ticket total on the button, plus what this click charges.
 assert.match(await page.locator('#checkout-submit').innerText(),/Membership \+ ticket total · HKD 1,172[\s\S]*join the pass for HKD 399, then confirm the ticket for HKD 773/);
 await page.locator('#checkout-submit').click();
 await page.waitForFunction(()=>document.querySelector('#checkout-submit').textContent.includes('Confirm booking'));
 await page.locator('#checkout-submit').click();
 await page.getByRole('button',{name:'Review return flight',exact:true}).waitFor();
 await page.getByRole('button',{name:'Review return flight',exact:true}).click();
 await page.locator('#checkout-submit').click();
 await page.waitForFunction(()=>document.querySelector('#trip-count').textContent==='2');
 assert.equal(joins,1);assert.equal(books,2);
 await page.keyboard.press('Escape');
 // Fresh identity fixture to inspect offers at both sizes.
 account.customer_id='journey-fresh';account.membership=null;account.bookings=[];
 await page.reload();await page.locator('.flight-card').first().waitFor();
 await mkdir(new URL('./test-results/',import.meta.url),{recursive:true});
 await page.screenshot({path:fileURLToPath(new URL('./test-results/member-journey-desktop.png',import.meta.url)),fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:fileURLToPath(new URL('./test-results/member-journey-mobile.png',import.meta.url)),fullPage:true});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 // Stale availability must stop before a new membership is charged.
 await page.locator('.choose-flight').first().click();
 const beforeJoin=joins;flights[0].bookable_seats=0;
 await page.locator('#checkout-submit').click();
 await page.waitForFunction(()=>document.querySelector('#checkout-error').textContent.includes('No new membership'));
 assert.equal(joins,beforeJoin);await page.keyboard.press('Escape');
 flights[0].bookable_seats=10;
 flights[1].bookable_seats=0;await page.locator('#refresh-flights').click();
 await page.waitForFunction(()=>document.querySelectorAll('.flight-card').length===1);
 assert.equal(errors.length,0,errors.join('\n'));
 console.log('PASS: streamlined search, first-ticket totals, post-purchase return, one membership/two tickets, sold-out refresh, mobile overflow');
} finally {await browser.close();}

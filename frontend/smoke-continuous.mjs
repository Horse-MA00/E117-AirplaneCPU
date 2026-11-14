/** Legacy UI check: targets the retired Math / Math+LLM Optimize page.
 * Not part of the current test scripts; retained as historical test source. */
import assert from 'node:assert/strict';
import {chromium} from 'playwright';
const origin=process.env.APP_URL || 'http://127.0.0.1:8765';
const browser=await chromium.launch({headless:true,executablePath:process.env.CHROMIUM_EXECUTABLE_PATH});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',error=>errors.push(error.message));
try {
  await page.goto(origin+'/#optimization');
  await page.locator('#legacy-price-details > summary').click();
  await page.locator('#continuous-form').waitFor();
  assert.equal(await page.locator('#market-mode').inputValue(),'probabilistic');
  await page.locator('#continuous-evals').fill('3');
  await page.locator('#continuous-start').click();
  await page.waitForFunction(()=>document.getElementById('continuous-status').textContent.includes('completed'),null,{timeout:180000});
  assert.equal(await page.locator('#continuous-trace tr').count(),3);
  const url=await page.locator('#continuous-report').getAttribute('href');
  const response=await page.request.get(origin+url);assert.equal(response.status(),200);
  const result=(await response.json()).report;
  assert.equal(result.customer_model,'probabilistic-customer-v1');
  assert.equal(result.trace.length,3);
  assert.equal(result.search_seeds.some(s=>result.validation_seeds.includes(s)),false);
  assert.ok(result.validation.checks_passed);
  assert.ok(result.validation.markets.every(m=>m.complete && Object.values(m.checks).every(Boolean)));
  assert.ok(result.validation.markets.some(m=>m.feedback.length>0));
  assert.ok(result.trace.every(r=>r.member_fare>=0 && r.member_fare<=500));
  assert.equal(await page.locator('.price-point').count(),result.trace.length);
  const peak=[...result.trace].sort((a,b)=>b.mean_total_contribution-a.mean_total_contribution || a.member_fare-b.member_fare)[0];
  assert.equal(Number(await page.locator('.price-peak').getAttribute('data-peak-price')),peak.member_fare);
  for(const row of result.trace) {
    assert.equal(Number(await page.locator(`.price-point[data-price="${row.member_fare}"]`).getAttribute('data-total')),row.mean_total_contribution);
    assert.ok(Math.abs(row.mean_total_contribution-row.mean_baseline_contribution-row.incremental_contribution)<.02);
  }
  await page.screenshot({path:'test-results/continuous-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:'test-results/continuous-mobile.png',fullPage:true});
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'passed',evaluations:3,independent_validation:true,real_shared_market:true,best:result.best}));
} finally {await browser.close();}

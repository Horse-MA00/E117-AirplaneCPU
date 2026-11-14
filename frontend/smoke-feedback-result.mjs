/** Verify an existing completed experiment against the real API; no LLM calls. */
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
import {chromium} from 'playwright';

const origin = process.env.APP_URL || 'http://127.0.0.1:8000';
const runId = process.env.FEEDBACK_RUN_ID;
if (!runId || !/^feedback-[a-f0-9]{16}$/.test(runId)) throw new Error('Set FEEDBACK_RUN_ID to an existing completed experiment ID.');
const response = await fetch(`${origin}/api/feedback-pricing/runs/${encodeURIComponent(runId)}`);
assert.equal(response.ok, true, 'The requested saved experiment exists');
const report = await response.json();
assert.equal(report.status, 'completed', 'Wait until this experiment completes before running the result smoke');
assert.ok(report.validation, 'A complete independent comparison is required');
const money = value => `HK$${new Intl.NumberFormat('en-HK', {maximumFractionDigits:2}).format(value)}`;
const numeric = value => new Intl.NumberFormat('en-HK', {maximumFractionDigits:2}).format(value);
const expectedRows = [report.validation.initial, report.validation.selected, report.validation.no_offer];
const expectedDecisions = {REJECT_OFFER:'Offer not supported', KEEP_INITIAL:'Keep initial fare', RECOMMEND_TESTED_FARE:'Tested fare supported'};
const browser = await chromium.launch({headless:true, executablePath:process.env.CHROMIUM_EXECUTABLE_PATH || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
const page = await browser.newPage({viewport:{width:1440,height:1080}});
const errors = [], forbiddenWrites = [];
page.on('pageerror', error => errors.push(error.message));
await page.route('**/api/feedback-pricing/**', async route => {
  if (route.request().method() !== 'GET') {forbiddenWrites.push(route.request().url()); return route.abort();}
  return route.continue();
});
try {
  await mkdir(new URL('test-results/',import.meta.url),{recursive:true});
  await page.goto(`${origin}/feedback-pricing?run=${encodeURIComponent(runId)}`);
  await page.waitForFunction(()=>document.getElementById('feedback-status').textContent==='Experiment complete');
  assert.equal(await page.locator('#feedback-comparison').isVisible(),true);
  assert.equal(await page.locator('#feedback-selected-fare').textContent(),money(report.selected.fare));
  assert.equal(await page.locator('#feedback-delta').textContent(),`${report.validation.delta_vs_initial>0?'+':''}${money(report.validation.delta_vs_initial)}`);
  assert.equal(await page.locator('#feedback-decision').textContent(),expectedDecisions[report.validation.decision]);
  const cells = await page.locator('#feedback-comparison-table tr').evaluateAll(rows=>rows.map(row=>Array.from(row.cells,cell=>cell.textContent)));
  assert.equal(cells.length,3);
  expectedRows.forEach((expected,index)=>{
    assert.equal(cells[index][2],money(expected.ticket_revenue));
    assert.equal(cells[index][3],numeric(expected.tickets_sold));
  });
  assert.equal(cells[0][1],money(report.initial_fare));
  assert.equal(cells[1][1],money(report.selected.fare));
  const bars = await page.locator('#feedback-comparison-chart rect').evaluateAll(nodes=>nodes.map(node=>({revenue:Number(node.dataset.revenue),x:Number(node.getAttribute('x')),width:Number(node.getAttribute('width'))})));
  assert.deepEqual(bars.map(bar=>bar.revenue),expectedRows.map(row=>row.ticket_revenue));
  assert.ok(bars.every(bar=>bar.x===bars[0].x),'All comparison bars begin at zero');
  const positive = bars.find(bar=>bar.revenue>0);
  if(positive) for(const bar of bars) assert.ok(Math.abs(bar.width / positive.width - bar.revenue / positive.revenue)<.000001,'Bar lengths are proportional to the API revenue');
  assert.equal(await page.locator('#feedback-round-table tr').count(),report.rounds.length);
  const searchCells = await page.locator('#feedback-round-table tr').evaluateAll(rows=>rows.map(row=>Array.from(row.cells,cell=>cell.textContent)));
  report.rounds.forEach((round,index)=>{assert.equal(searchCells[index][1],money(round.fare));assert.equal(searchCells[index][2],money(round.ticket_revenue));assert.equal(searchCells[index][3],numeric(round.tickets_sold));});
  assert.equal(await page.locator('#feedback-export').getAttribute('href'),`/api/feedback-pricing/runs/${runId}/export`);
  assert.equal(await page.locator('#feedback-events').getAttribute('href'),`/api/feedback-pricing/runs/${runId}/events`);
  await page.screenshot({path:'test-results/feedback-pricing-result-desktop.png',fullPage:true});
  await page.locator('#feedback-comparison').screenshot({path:'test-results/feedback-pricing-result-comparison.png'});
  await page.setViewportSize({width:390,height:844});
  await page.waitForTimeout(250);
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true,'Completed result fits mobile viewport');
  await page.screenshot({path:'test-results/feedback-pricing-result-mobile.png',fullPage:true});
  await page.locator('#feedback-comparison').screenshot({path:'test-results/feedback-pricing-result-comparison-mobile.png'});
  assert.deepEqual(errors,[]); assert.deepEqual(forbiddenWrites,[]);
  const after=await (await fetch(`${origin}/api/feedback-pricing/runs/${encodeURIComponent(runId)}`)).json();
  assert.deepEqual(after.counts,report.counts,'Viewing results must not consume calls or advance decisions');
  console.log(JSON.stringify({status:'passed',run_id:runId,source:'real completed LLM experiment, read-only verification',selected_fare:report.selected.fare,decision:report.validation.decision,comparison_revenue:expectedRows.map(row=>row.ticket_revenue),checks:['exact API amounts','selected fare even when rejected','zero-origin proportional bars','search vs holdout separation','semantic tables','export and raw links','desktop/mobile layout','unchanged call counters'],llm_runs_started:0}));
} finally {await browser.close();}

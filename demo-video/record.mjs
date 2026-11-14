// Records the demo flow on a clean copy of the app and logs every camera,
// cursor and click event in output time. See README.md for the storyboard.
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const OUT = path.join(HERE, 'out');
const FRAMES = path.join(OUT, 'frames');
const APP = path.join(OUT, 'app');
const PORT = Number(process.env.DEMO_PORT || 8123);
const BASE = `http://127.0.0.1:${PORT}`;
const FLIGHT = 'DEMO-HKG-HIJ-20270515';
const W = 1920, H = 1080, DSF = Number(process.env.DEMO_DSF || 2);
const FAST_SECONDS = 2.5; // the optimization run is compressed to this length

const durations = JSON.parse(fs.readFileSync(path.join(OUT, 'narration', 'durations.json'), 'utf8'));

// ---------- clean server ----------
function copyApp() {
  fs.rmSync(APP, { recursive: true, force: true });
  const skip = new Set(['.git', 'node_modules', 'demo-video', '.runtime'].map(p => path.join(ROOT, p)));
  skip.add(path.join(ROOT, 'data', 'private'));
  fs.mkdirSync(APP, { recursive: true });
  for (const name of fs.readdirSync(ROOT)) {
    const src = path.join(ROOT, name);
    if (skip.has(src)) continue;
    fs.cpSync(src, path.join(APP, name), { recursive: true, filter: s => !skip.has(s) && path.basename(s) !== 'node_modules' });
  }
}
async function startServer() {
  copyApp();
  const server = spawn(process.env.PYTHON || 'python3', ['-m', 'backend.server', '--port', String(PORT)], { cwd: APP, stdio: ['ignore', 'inherit', 'inherit'] });
  for (let i = 0; i < 120; i++) {
    try { if ((await fetch(BASE + '/api/summary')).ok) return server; } catch { /* not up yet */ }
    await sleep(0.5);
  }
  server.kill();
  throw new Error('backend did not start');
}

// ---------- clock: output time = raw time minus fast-forward savings ----------
const sleep = s => new Promise(r => setTimeout(r, s * 1000));
let t0 = null;
const raw = () => (performance.now() - t0) / 1000;
const fastSegs = [];
let fastOpen = null;
function toOut(r) {
  let shift = 0;
  for (const s of fastSegs) {
    if (r >= s.re) { shift += (s.re - s.rs) - s.c; continue; }
    if (r > s.rs) return s.rs - shift + (r - s.rs) * s.c / (s.re - s.rs);
    break;
  }
  if (fastOpen && r > fastOpen.rs) return fastOpen.rs - shift;
  return r - shift;
}
const now = () => toOut(raw());
async function until(t) { const d = t - now(); if (d > 0) await sleep(d); }

const events = [];
const ev = (type, extra = {}) => events.push({ type, t: +now().toFixed(3), ...extra });
function fastStart() { ev('fast-start'); fastOpen = { rs: raw(), c: FAST_SECONDS }; }
function fastEnd() { const s = { ...fastOpen, re: raw() }; fastSegs.push(s); fastOpen = null; ev('fast-end', { factor: +((s.re - s.rs) / s.c).toFixed(1) }); }
function say(id) { ev('line', { id }); return now() + durations[id]; }

// ---------- capture: CDP screencast of the active page ----------
const frames = [];
let active = null;
async function attach(page) {
  const cdp = await page.context().newCDPSession(page);
  cdp.on('Page.screencastFrame', ({ data, sessionId }) => {
    cdp.send('Page.screencastFrameAck', { sessionId }).catch(() => {});
    if (active?.cdp !== cdp || t0 === null) return;
    const file = `f${String(frames.length).padStart(6, '0')}.jpg`;
    fs.writeFileSync(path.join(FRAMES, file), Buffer.from(data, 'base64'));
    frames.push({ r: raw(), file });
  });
  return { page, cdp };
}
async function activate(target) {
  if (active) await active.cdp.send('Page.stopScreencast');
  active = target;
  if (t0 === null) t0 = performance.now();
  ev('cut');
  await target.cdp.send('Page.startScreencast', { format: 'jpeg', quality: 92, maxWidth: W * DSF, maxHeight: H * DSF });
}

// ---------- camera and cursor ----------
let cameraWide = true;
let cursor = { x: W * 0.62, y: H * 0.72 };
const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
function frameFor(boxes, { pad = 56, maxZoom = 1.9 } = {}) {
  const x0 = Math.min(...boxes.map(b => b.x)) - pad, y0 = Math.min(...boxes.map(b => b.y)) - pad;
  const x1 = Math.max(...boxes.map(b => b.x + b.width)) + pad, y1 = Math.max(...boxes.map(b => b.y + b.height)) + pad;
  const w = Math.min(W, Math.max(x1 - x0, (y1 - y0) * 16 / 9, W / maxZoom)), h = w * 9 / 16;
  // Targets sit a little above centre so the captions never cover them.
  return { x: clamp((x0 + x1) / 2 - w / 2, 0, W - w), y: clamp((y0 + y1) / 2 - h * 0.44, 0, H - h), w, h };
}
async function camera(boxes, { dur = 0.8, hold = 0, ...opts } = {}) {
  const rect = boxes ? frameFor(boxes, opts) : { x: 0, y: 0, w: W, h: H };
  cameraWide = rect.w >= W - 1;
  ev('camera', { rect, dur });
  await sleep(dur + hold);
}
const wide = (o = {}) => camera(null, o);
const boxOf = async loc => { const b = await loc.boundingBox(); if (!b) throw new Error(`no box for ${loc}`); return b; };
const centre = b => ({ x: b.x + b.width / 2, y: b.y + b.height / 2 });
async function cursorTo(box, dur = 0.6) {
  const to = centre(box);
  ev('cursor', { from: cursor, to, dur });
  cursor = to;
  await sleep(dur);
}
async function scrollTo(page, loc, top = 110) {
  if (!cameraWide) await wide({ dur: 0.6 });
  const box = await boxOf(loc);
  const y0 = await page.evaluate(() => window.scrollY);
  const target = Math.max(0, y0 + box.y - top);
  if (Math.abs(target - y0) < 8) return;
  ev('scroll');
  await page.evaluate(y => window.scrollTo({ top: y, behavior: 'smooth' }), target);
  let last = -1;
  for (let i = 0; i < 40; i++) { await sleep(0.08); const y = await page.evaluate(() => window.scrollY); if (y === last) break; last = y; }
  // The cursor stays still on screen while the page scrolls under it.
}
// Wait until re-rendering above an element stops moving it.
async function settle(loc) {
  let last = null, still = 0;
  for (let i = 0; i < 30 && still < 4; i++) {
    const b = await boxOf(loc);
    still = last && Math.abs(b.y - last.y) < 1 ? still + 1 : 0;
    last = b;
    await sleep(0.12);
  }
}
async function inView(page, loc) {
  const b = await boxOf(loc);
  if (b.y < 80 || b.y + b.height > H - 40) await scrollTo(page, loc, Math.max(110, (H - b.height) / 2));
}
async function click(page, loc, { context = [], hold = 0.5, ...cam } = {}) {
  await inView(page, loc);
  const box = await boxOf(loc);
  await camera([...context, box], { dur: 0.7, ...cam });
  await sleep(0.15);
  await cursorTo(box);
  ev('click', { at: cursor });
  await loc.click();
  await sleep(hold);
}
async function hover(page, loc, { context = [], hold = 0.4, ...cam } = {}) {
  await inView(page, loc);
  const box = await boxOf(loc);
  await camera([...context, box], { dur: 0.7, ...cam });
  await sleep(0.1);
  await cursorTo(box);
  await loc.hover();
  await sleep(hold);
}
// Native <select> pop-ups are drawn by the OS and never reach the screencast, so
// the composition draws the list from the real option labels logged here.
async function pick(page, select, label) {
  await inView(page, select);
  const box = await boxOf(select);
  const options = await select.evaluate(s => [...s.options].map(o => o.textContent.trim()));
  const index = options.indexOf(label);
  if (index < 0) throw new Error(`option ${label} not in ${options}`);
  const rowH = 40, list = { x: box.x, y: box.y + box.height + 4, width: box.width, height: rowH * options.length + 12 };
  await camera([box, list], { dur: 0.7 });
  await sleep(0.15);
  await cursorTo(box);
  ev('click', { at: cursor });
  ev('dropdown-open', { box, options, current: await select.evaluate(s => s.selectedIndex), index, rowH });
  await sleep(0.5);
  await cursorTo({ x: box.x + 24, y: list.y + 6 + index * rowH, width: Math.min(220, box.width - 48), height: rowH }, 0.55);
  ev('click', { at: cursor });
  await select.selectOption({ label });
  await sleep(0.12);
  ev('dropdown-close');
  await sleep(0.4);
}

// ---------- the storyboard ----------
async function run(browser) {
  const launchOpts = { viewport: { width: W, height: H }, deviceScaleFactor: DSF };
  const context = await browser.newContext(launchOpts);
  const admin = await attach(await context.newPage());
  const member = await attach(await context.newPage());
  const A = admin.page, M = member.page;
  for (const p of [A, M]) p.on('pageerror', e => console.error('page error:', e.message));

  // Set-up before the first frame: the forecast page with the Hiroshima flight selected.
  await A.goto(BASE + '/admin#flights');
  await A.waitForSelector('#flight-select:not([disabled])');
  await A.selectOption('#flight-select', FLIGHT);
  await A.waitForFunction(() => /\d/.test(document.querySelector('#release-value')?.textContent || ''));
  await A.waitForTimeout(1500);
  // Recording-only blank space below the last section, so the published offer
  // list can scroll above the captions. No product code changes.
  await A.addStyleTag({ content: 'body { padding-bottom: 50vh; }' });
  await A.evaluate(() => window.scrollTo(0, 0));
  const facts = { forecast: await A.locator('.forecast-metrics').innerText() };

  // 1 Forecast seats
  await activate(admin);
  await sleep(0.4);
  let end = say('forecast');
  await sleep(0.6);
  await camera([await boxOf(A.locator('.forecast-toolbar'))], { dur: 0.9, hold: 0.7 });
  await scrollTo(A, A.locator('.forecast-metrics'), 96);
  await camera([await boxOf(A.locator('#seat-composition')), await boxOf(A.locator('#seat-composition-legend'))], { dur: 0.8, pad: 40 });
  await until(end - 3.4);
  await camera([await boxOf(A.locator('.forecast-metrics .stat-card.featured'))], { dur: 0.8, pad: 70 });
  await until(end - 0.2);
  await click(A, A.locator('#go-pricing'), { hold: 0.2 });

  // 2 Optimize prices
  await A.waitForSelector('#view-optimization:not([hidden])');
  await A.waitForFunction(() => document.querySelector('#optimization-flight')?.value);
  await wide({ dur: 0.5, hold: 0.4 });
  end = say('optimize-run');
  await click(A, A.locator('#optimization-start'), { context: [await boxOf(A.locator('.optimization-setup'))], hold: 0.3 });
  fastStart();
  const useButton = A.locator('#optimization-final-content').getByRole('button', { name: 'Use these prices' });
  await useButton.waitFor({ timeout: 600000 });
  await A.waitForFunction(() => /complete/i.test(document.querySelector('#optimization-status')?.textContent || ''), null, { timeout: 600000 });
  await sleep(0.6);
  fastEnd();
  facts.final = await A.locator('#optimization-final-content').innerText();
  await scrollTo(A, A.locator('.price-profit-panel'), 90);
  const chart = A.locator('.price-profit-panel svg').first();
  await camera([await boxOf(chart)], { dur: 0.8, pad: 30 });
  await until(end + 0.2);
  end = say('optimize-result');
  await sleep(0.4);
  await hover(A, A.locator('.price-profit-panel circle[stroke="#24BCDC"]').first(), { context: [await boxOf(chart)], pad: 30, hold: 0.2 });
  await until(end - 3.6);
  await scrollTo(A, A.locator('#optimization-final'), 100);
  await camera([await boxOf(A.locator('#optimization-final'))], { dur: 0.8, pad: 30 });
  await until(end - 0.3);
  await click(A, useButton, { context: [await boxOf(A.locator('#optimization-final'))], pad: 30, hold: 0.2 });

  // 3 Manage offers
  await A.waitForSelector('#view-members:not([hidden])');
  await A.waitForFunction(() => Number(document.querySelector('#offer-quantity')?.value) > 1);
  await wide({ dur: 0.5, hold: 0.3 });
  end = say('publish');
  await scrollTo(A, A.locator('#offer-optimization-suggestion'), 160);
  await camera([await boxOf(A.locator('#offer-optimization-suggestion')), await boxOf(A.locator('#publish-button'))], { dur: 0.8, hold: 0.5 });
  facts.publish = { quantity: await A.inputValue('#offer-quantity'), fare: await A.inputValue('#offer-fare') };
  await click(A, A.locator('#publish-button'), { context: [await boxOf(A.locator('#offer-quantity'))], hold: 0.6 });
  const memberLoad = M.goto(BASE + '/members').then(() => M.waitForSelector('#flight-results[aria-busy="false"] .choose-flight', { timeout: 20000 }));
  const firstOffer = A.locator('#offers-list > *').first();
  await scrollTo(A, A.locator('#offers-list'), 300);
  await camera([await boxOf(firstOffer)], { dur: 0.8, pad: 50 });
  await until(Math.max(end + 0.3, now() + 1.0));
  facts.offerBefore = await firstOffer.innerText();
  await memberLoad;
  await M.evaluate(() => window.scrollTo(0, 0));

  // 4 Member site
  await wide({ dur: 0.01 });
  await activate(member);
  await sleep(0.6);
  end = say('member-search');
  await pick(M, M.locator('#destination-region'), 'Japan');
  await click(M, M.locator('#search-button'), { hold: 0.4 });
  const card = M.locator('#flight-results > *').first();
  await scrollTo(M, card, 200);
  await camera([await boxOf(card)], { dur: 0.8, pad: 40 });
  await until(end + 0.2);
  end = say('member-book');
  await click(M, card.getByRole('button', { name: /Select/ }), { context: [await boxOf(card)], hold: 0.6 });
  const dialog = M.locator('#checkout');
  await click(M, M.locator('#checkout-submit'), { context: [await boxOf(dialog)], dur: 0.6, hold: 0.9 });
  await click(M, M.locator('#checkout-submit'), { context: [await boxOf(dialog)], dur: 0.4, hold: 0.3 });
  await M.waitForFunction(() => /Booking complete/i.test(document.querySelector('#checkout')?.textContent || ''));
  await camera([await boxOf(dialog)], { dur: 0.5 });
  await until(Math.max(end + 0.3, now() + 1.0));
  facts.booked = await dialog.innerText();

  // 5 Back to admin: the same quota, one seat fewer
  await wide({ dur: 0.01 });
  await activate(admin);
  await scrollTo(A, firstOffer, 380);
  await sleep(0.3);
  end = say('closing');
  await click(A, A.locator('#refresh-offers'), { context: [await boxOf(firstOffer)], hold: 0.2 });
  await A.waitForFunction(() => /\b9 unspent/.test(document.querySelector('#offers-list')?.innerText || ''), null, { timeout: 15000 })
    .catch(async e => { console.error('offers list after refresh:', await A.locator('#offers-list').innerText()); throw e; });
  await settle(firstOffer);
  await camera([await boxOf(firstOffer.getByText('HK$370').first()), await boxOf(firstOffer.getByText(/unspent quota/).first())], { dur: 0.9, pad: 70 });
  await until(end + 0.6);
  facts.offerAfter = await firstOffer.innerText();
  ev('outro');
  await sleep(0.2);
  await context.close();
  return facts;
}

async function main() {
  fs.rmSync(FRAMES, { recursive: true, force: true });
  fs.mkdirSync(FRAMES, { recursive: true });
  const server = await startServer();
  const exe = process.env.CHROMIUM_PATH;
  let browser;
  try {
    browser = await chromium.launch(exe ? { executablePath: exe } : {});
    const facts = await run(browser);
    const end = now();
    const timeline = {
      size: { width: W, height: H, dsf: DSF },
      end: +end.toFixed(3),
      events,
      frames: frames.map(f => ({ t: +toOut(f.r).toFixed(4), file: f.file })),
      durations,
      facts,
    };
    fs.writeFileSync(path.join(OUT, 'timeline.json'), JSON.stringify(timeline, null, 1));
    console.log(`recorded ${frames.length} frames, ${end.toFixed(1)} s of output time`);
    console.log(JSON.stringify(facts, null, 1));
  } finally {
    await browser?.close();
    server.kill();
  }
}
main().catch(e => { console.error(e); process.exit(1); });

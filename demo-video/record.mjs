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
const FLIGHT = 'SYN-00017'; // HKG→Fukuoka, saved Thompson experiment DEMO_LLM0
const DAY = 7;
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
// A pause drops waiting time (page loads) from the video entirely.
function pause() { fastOpen = { rs: raw(), c: 0 }; }
function resume() { fastSegs.push({ ...fastOpen, re: raw() }); fastOpen = null; }
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
  if (fastOpen) resume();
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
const ADMIN = `${BASE}/admin?flight_id=${FLIGHT}&forecast_day=${DAY}`;
async function typeInto(page, loc, text, { context = [], ...cam } = {}) {
  await click(page, loc, { context, hold: 0.15, ...cam });
  await loc.fill('');
  await loc.pressSequentially(text, { delay: 140 });
  await sleep(0.3);
}

async function run(browser) {
  const context = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: DSF });
  const tab = await attach(await context.newPage());
  const P = tab.page;
  P.on('pageerror', e => console.error('page error:', e.message));

  // Set-up before the first frame: the forecast page for the demo flight and round.
  await P.goto(`${ADMIN}#flights`);
  await P.waitForFunction(() => /\d/.test(document.querySelector('#release-value')?.textContent || ''), null, { timeout: 30000 });
  await P.waitForTimeout(1500);
  const facts = { forecast: await P.locator('#flight-main').innerText() };

  // 1 Forecast seats
  await activate(tab);
  await sleep(0.4);
  let end = say('forecast');
  await sleep(0.8);
  await camera([await boxOf(P.locator('#seat-composition')), await boxOf(P.locator('#seat-composition-legend'))], { dur: 0.9, pad: 40 });
  await until(end - 3.2);
  await camera([await boxOf(P.locator('#release-value').locator('xpath=ancestor::article[1]'))], { dur: 0.8, pad: 60 });
  await until(end - 0.1);
  await click(P, P.locator('#go-pricing'), { hold: 0.1 });
  pause();

  // 2 Optimize prices: the saved Thompson experiment for this flight opens by itself.
  await P.waitForURL(/adaptive-pricing/);
  await P.locator('#recommended-price').filter({ hasText: /HK\$\d/ }).waitFor({ timeout: 30000 });
  await P.locator('#delta-no-offer').filter({ hasText: /\d/ }).waitFor({ timeout: 30000 });
  await P.waitForTimeout(400);
  await activate(tab); // restart the screencast on the new document
  await wide({ dur: 0.01, hold: 0.5 });
  end = say('optimize');
  await camera([await boxOf(P.locator('#curve-chart'))], { dur: 0.8, pad: 40, hold: 1.4 });
  await camera([await boxOf(P.locator('#recommendation'))], { dur: 0.8, pad: 40 });
  await until(end - 5.0);
  await camera([await boxOf(P.locator('#delta-no-offer')), await boxOf(P.locator('#delta-initial'))], { dur: 0.8, pad: 70 });
  await until(end - 0.4);
  facts.optimize = { price: await P.locator('#recommended-price').innerText(), vsNoOffer: await P.locator('#delta-no-offer').innerText() };
  await click(P, P.locator('#publish-link'), { hold: 0.1 });
  pause();

  // 3 Publish offers: the manager types the fare.
  await P.waitForURL(/#members/);
  await P.waitForFunction(() => Number(document.querySelector('#offer-quantity')?.value) > 0, null, { timeout: 30000 });
  await P.waitForTimeout(400);
  await activate(tab);
  await wide({ dur: 0.01, hold: 0.3 });
  end = say('publish');
  const form = P.locator('#offer-form');
  await typeInto(P, P.locator('#offer-fare'), '229', { context: [await boxOf(form), await boxOf(P.locator('#offer-preview'))], pad: 30 });
  await click(P, P.locator('#publish-button'), { context: [await boxOf(form)], hold: 0.6 });
  await P.locator('#publish-next').waitFor({ state: 'visible' });
  const openMember = P.locator('#publish-next').getByRole('link', { name: /Open member site/ });
  await until(end + 0.2);
  facts.publish = { quantity: await P.inputValue('#offer-quantity').catch(() => ''), next: await P.locator('#publish-next').innerText() };
  await click(P, openMember, { context: [await boxOf(P.locator('#publish-next'))], pad: 24, maxZoom: 2.3, hold: 0.1 });
  pause();

  // 4 Member site: sign in with the demo member account and book.
  await P.waitForURL(/members\/login/);
  await P.getByText('Use member account').waitFor();
  await P.waitForTimeout(300);
  await activate(tab);
  await wide({ dur: 0.01, hold: 0.2 });
  await click(P, P.getByText('Use member account'), { hold: 0.25 });
  await click(P, P.getByRole('button', { name: 'Sign in' }), { hold: 0.1 });
  pause();
  await P.waitForURL(/\/members\/?$/);
  const card = P.locator('#flight-results > *').filter({ has: P.locator('.choose-flight') }).first();
  await card.waitFor({ timeout: 30000 });
  await P.waitForTimeout(300);
  await activate(tab);
  await wide({ dur: 0.01 });
  end = say('member');
  await scrollTo(P, card, 260);
  await camera([await boxOf(card)], { dur: 0.8, pad: 40, hold: 0.6 });
  await click(P, card.locator('.choose-flight'), { context: [await boxOf(card)], hold: 0.6 });
  const dialog = P.locator('#checkout');
  await click(P, P.locator('#checkout-submit'), { context: [await boxOf(dialog)], dur: 0.6, hold: 0.3 });
  await P.waitForFunction(() => /Booking complete|trip is saved/i.test(document.querySelector('#checkout')?.innerText || ''), null, { timeout: 15000 });
  await camera([await boxOf(dialog)], { dur: 0.5 });
  await until(Math.max(end + 0.3, now() + 0.8));
  facts.booked = await dialog.innerText();

  // 5 Results: the same inventory, one seat sold.
  pause();
  await P.goto(`${ADMIN}#results`);
  await P.waitForFunction(() => /^\s*1\s*$/.test(document.querySelector('#results-sold')?.innerText || ''), null, { timeout: 30000 });
  await P.waitForTimeout(500);
  await activate(tab);
  await wide({ dur: 0.01, hold: 0.3 });
  end = say('results');
  const sold = P.locator('#results-sold').locator('xpath=ancestor::article[1]');
  const revenue = P.locator('#results-revenue').locator('xpath=ancestor::article[1]');
  await camera([await boxOf(sold), await boxOf(revenue)], { dur: 0.9, pad: 40 });
  await until(end + 0.6);
  facts.results = await P.locator('#view-results').innerText();
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

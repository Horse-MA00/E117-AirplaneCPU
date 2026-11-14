/** Real demo sessions against an isolated SQLite DB; no provider calls or demo-seat mutations. */
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { once } from 'node:events';
import { access, mkdir, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const output = fileURLToPath(new URL('./test-results/', import.meta.url));
const temporary = await mkdtemp(join(tmpdir(), 'uoption-login-'));
let python = process.env.PYTHON || join(root, '.venv/bin/python');
try {
  await access(python);
} catch {
  python = process.env.PYTHON || 'python3';
}
const child = spawn(
  python,
  [
    '-u',
    '-c',
    `
import sys
from backend import oag
oag.load_env = lambda: None
from backend import server
from backend.store import Store
server._store = Store(sys.argv[1])
http = server.Server(('127.0.0.1', 0), server.Handler)
print(http.server_port, flush=True)
http.serve_forever()
`,
    join(temporary, 'test.sqlite3'),
  ],
  { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] },
);
let stderr = '';
child.stderr.on('data', (chunk) => {
  stderr += chunk;
});
let browser;
try {
  const port = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error(`Login test server did not start: ${stderr}`)), 15000);
    let output = '';
    child.stdout.on('data', (chunk) => {
      output += chunk;
      if (/^\d+\n/.test(output)) {
        clearTimeout(timeout);
        resolve(Number(output.split('\n')[0]));
      }
    });
    child.on('error', (error) => {
      clearTimeout(timeout);
      reject(error);
    });
    child.on('exit', (code) => {
      clearTimeout(timeout);
      reject(new Error(`Login test server exited ${code}: ${stderr}`));
    });
  });
  const origin = `http://127.0.0.1:${port}`;
  await mkdir(output, { recursive: true });
  browser = await chromium.launch({
    headless: true,
    ...(process.env.CHROMIUM_EXECUTABLE_PATH ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH } : {}),
  });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const session = async () => (await context.request.get(`${origin}/api/member-portal/session`)).json();
  async function signIn(kind) {
    await page.goto(`${origin}/members/login`);
    await page.locator(`#demo-${kind}`).click();
    assert.equal(await page.locator('#login-email').inputValue(), `${kind}@uoption.test`);
    assert.equal(await page.locator('#login-password').inputValue(), 'FlyPass399!');
    assert.ok(page.url().endsWith('/members/login'), 'Selecting a demo only fills the form.');
    await page.locator('#login-submit').click();
    await page.waitForURL((url) => url.pathname === '/members' || url.pathname === '/members/');
    await page.waitForFunction(() => document.querySelector('#current-account').textContent.includes('@uoption.test'));
  }
  async function signOut() {
    await page.locator('#sign-out').click();
    await page.waitForURL('**/members/login');
    assert.equal((await session()).authenticated, false);
  }
  await page.goto(`${origin}/members`);
  await page.waitForURL('**/members/login');
  assert.equal(await page.locator('#login-email').getAttribute('autocomplete'), 'username');
  assert.equal(await page.locator('#login-password').getAttribute('autocomplete'), 'current-password');
  assert.equal(await page.locator('#login-email').getAttribute('type'), 'email');
  await page.locator('#login-submit').click();
  assert.equal(await page.locator('#login-email').evaluate((el) => el.validity.valueMissing), true);
  await page.locator('#demo-member').click();
  await page.locator('#toggle-password').click();
  assert.equal(await page.locator('#login-password').getAttribute('type'), 'text');
  assert.equal(await page.locator('#toggle-password').getAttribute('aria-pressed'), 'true');
  await page.locator('#toggle-password').click();
  await page.locator('#login-password').fill('incorrect');
  await page.locator('#login-submit').click();
  await page.waitForFunction(() => document.querySelector('#login-error').textContent.includes('incorrect'));
  assert.equal((await session()).authenticated, false);
  assert.equal(await page.locator('#login-submit').isEnabled(), true);
  await page.locator('#demo-guest').click();
  await page.screenshot({ path: join(output, 'member-login-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
  await page.screenshot({ path: join(output, 'member-login-mobile.png'), fullPage: true });

  await signIn('guest');
  assert.equal((await session()).account.membership, null);
  assert.match(await page.locator('#hero-term').innerText(), /6 months/);
  assert.match(await page.locator('#pass-term').innerText(), /6 months/);
  assert.equal(await page.locator('#join-pass').isEnabled(), true);
  const radii = await page.locator('.booking-hero').evaluate((el) => {
    const s = getComputedStyle(el);
    return [s.borderTopLeftRadius, s.borderTopRightRadius, s.borderBottomLeftRadius, s.borderBottomRightRadius];
  });
  assert.ok(
    radii.every((radius) => parseFloat(radius) > 0),
    'All four hero corners are rounded on mobile.',
  );
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.screenshot({ path: join(output, 'member-signed-in-desktop.png'), fullPage: true });
  const cookies = await context.cookies();
  const authCookie = cookies.find((c) => c.name === 'uoption_demo_session');
  assert.equal(authCookie.httpOnly, true);
  assert.equal(authCookie.sameSite, 'Lax');
  assert.equal((await context.request.get(`${origin}/api/member-portal/accounts/demo-member`)).status(), 403);
  await signOut();
  assert.equal((await context.request.get(`${origin}/api/member-portal/accounts/demo-guest`)).status(), 401);

  await signIn('member');
  const paid = await session();
  assert.equal(paid.account.membership.active, true);
  assert.equal(paid.account.membership.fee, 399);
  assert.equal(await page.locator('#join-pass').isDisabled(), true);
  await page.evaluate(() => localStorage.setItem('uoption-member-demo-account', 'demo-guest'));
  await page.reload();
  await page.waitForFunction(() =>
    document.querySelector('#current-account').textContent.includes('member@uoption.test'),
  );
  assert.equal((await session()).user.customer_id, 'demo-member');
  await signOut();

  await signIn('guest');
  assert.equal((await session()).account.membership, null, 'Guest did not inherit member status.');
  await page.locator('#join-pass').click();
  assert.match(await page.locator('#checkout-content').innerText(), /6 months/);
  assert.match(await page.locator('#checkout-submit').innerText(), /399/);
  await page.locator('#checkout-submit').click();
  await page.waitForFunction(() => document.querySelector('#checkout-title').textContent === 'Your pass is active');
  const upgraded = (await session()).account.membership;
  assert.equal(upgraded.active, true);
  const calendarDays = Math.round((upgraded.expires - upgraded.created) / 86400);
  assert.ok(calendarDays >= 181 && calendarDays <= 184);
  await page.keyboard.press('Escape');
  await signOut();
  await signIn('guest');
  assert.deepEqual((await session()).account.membership, upgraded, 'Relogin preserves the purchase and expiry.');
  assert.equal(await page.locator('#join-pass').isDisabled(), true);
  await context.clearCookies();
  await page.locator('#refresh-account').click();
  await page.waitForURL('**/members/login');
  assert.deepEqual(errors, []);
  console.log(
    'Member login passed: both real sessions, invalid credentials, logout, identity isolation, six-month plan, guest upgrade persistence, desktop/mobile layout and four rounded hero corners. Zero provider calls.',
  );
} finally {
  await browser?.close();
  if (child.exitCode === null) {
    const exit = once(child, 'exit');
    child.kill('SIGTERM');
    await exit;
  }
  await rm(temporary, { recursive: true, force: true });
}

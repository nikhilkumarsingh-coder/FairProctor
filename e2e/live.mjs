// Live: two copying candidates halfway through (colluders.py --items 15 --no-submit), TEAM01 writing on a phone with a
// second person in view and leaving the tab, and the admin watching the live monitor.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const problems = [];
const watch = (page, name) => {
  page.on('pageerror', (e) => problems.push(`[${name}] pageerror: ${e.message}`));
  page.on('response', (r) => r.status() >= 400 && problems.push(`[${name}] ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`));
};
const shot = async (p, n, full = false) => { await p.waitForTimeout(450); await p.screenshot({ path: SHOTS + n + '.png', fullPage: full }); };
const step = (s) => console.log('·', s);

step('admin opens the live monitor');
const admin = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
watch(admin, 'admin');
await admin.goto(BASE + '/staff/login');
await admin.fill('#email', 'admin@fairproctor.demo'); await admin.fill('#password', 'Admin@2026');
await admin.getByRole('button', { name: /^Log in/ }).click();
await admin.waitForURL('**/admin');
await admin.getByRole('link', { name: 'Live monitor' }).first().click();
await admin.getByText('Demo sitting').first().click();
await admin.waitForURL('**/review/live/1');
await admin.getByText('Candidates by live risk').waitFor();
await admin.getByText('Answer match').first().waitFor({ timeout: 30000 });
await shot(admin, 'l01-monitor-colluders', true);

step('TEAM01 writes on a phone (a stand-in face detector: one face, two when the test says so)');
const ctx = await browser.newContext({ ...devices['Pixel 7'], permissions: ['camera'] });
await ctx.addInitScript(() => {
  window.__faces = 1;
  window.FaceDetector = class {
    async detect() {
      const one = (x) => ({ boundingBox: { x, y: 110, width: 200, height: 250 },
        landmarks: [{ type: 'eye', locations: [{ x: x + 60, y: 200 }] }, { type: 'eye', locations: [{ x: x + 140, y: 200 }] }, { type: 'nose', locations: [{ x: x + 100, y: 240 }] }] });
      return window.__faces === 2 ? [one(220), one(20)] : [one(220)];
    }
  };
});
const c = await ctx.newPage();
watch(c, 'TEAM01');
await c.goto(BASE + '/login');
await c.fill('#roll_no', 'TEAM01'); await c.fill('#code', codes.TEAM01);
await c.getByRole('button', { name: /^Log in/ }).click();
await c.waitForURL('**/exam');
await c.getByRole('button', { name: /Continue/ }).click();
await c.locator('label[for=understood]').click();
await c.getByRole('button', { name: /Continue/ }).click();
await c.getByText(/Mbps|kbps/).waitFor({ timeout: 25000 });
await c.getByRole('button', { name: /Allow camera/ }).click();
await c.getByText('Sharpness').waitFor();
await c.getByRole('button', { name: /Start test/ }).click();
await c.getByText('Question 1', { exact: true }).waitFor();
for (let i = 0; i < 5; i++) {                 // questions come in this candidate's own (shuffled) order
  await c.getByText(`Question ${i + 1}`, { exact: true }).waitFor();
  await c.waitForTimeout(200);
  if (await c.locator('#short').count()) {
    await c.fill('#short', '7');
    await c.getByRole('button', { name: 'Save answer' }).click();
    await c.getByText('Answer saved').waitFor();
  } else {
    await c.getByRole('radio').nth(i % 4).click();
  }
  await c.getByRole('button', { name: /^Next/ }).click();
}
step('second person in view → banner');
await c.evaluate(() => { window.__faces = 2; });
await c.getByText('Another person seems to be in view').waitFor({ timeout: 30000 });
await shot(c, 'l02-candidate-second-person');
await c.evaluate(() => { window.__faces = 1; });
step('leaves the test tab → popup');
await c.evaluate(() => { Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
await c.waitForTimeout(4000);
await c.evaluate(() => { Object.defineProperty(document, 'hidden', { value: false, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
await c.getByText('You left the test screen').waitFor();
await shot(c, 'l03-candidate-left-popup');
await c.getByRole('button', { name: 'Continue the test' }).click();
await c.getByText('Saved', { exact: true }).waitFor({ timeout: 30000 });

step('admin sees the alerts pop up');
await admin.getByText(/left the test screen for/).first().waitFor({ timeout: 40000 });
await admin.getByText(/more than one face for 5 s|a second person was in view/).first().waitFor({ timeout: 20000 });
await shot(admin, 'l04-monitor-alerts', true);
step('model re-run includes TEAM01 (≤ 1 min)');
await admin.getByText(/Left screen 1×/).first().waitFor({ timeout: 20000 });
await admin.waitForFunction(() => !document.body.innerText.includes('too early'), null, { timeout: 120000 }).catch(() => console.log('  (TEAM01 risk not shown yet)'));
await shot(admin, 'l05-monitor-later', true);
const rows = await admin.locator('main button.block').allInnerTexts();
console.log('  ' + rows.map((r) => r.replace(/\s+/g, ' ').slice(0, 160)).join('\n  '));
await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or failed requests');

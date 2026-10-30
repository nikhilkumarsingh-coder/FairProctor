// Proctoring rules on a phone (run on a freshly seeded database, backend running): a second face for 5 s gives a
// counted warning, logging in again is counted (not an end), the 6th time the test screen is left ends the test,
// the candidate sees why, a reviewer reopens it from the live monitor (the candidate continues, the count starts
// again), and after scoring the reviewer sees a "Proctoring rules" card with the reasons and the reopen.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url)); fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const problems = [];
const expected = [/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED/];
const watch = (p, name) => {
  p.on('pageerror', (e) => problems.push(`[${name}] ${e.message}`));
  p.on('console', (m) => m.type() === 'error' && !expected.some((x) => x.test(m.text())) && problems.push(`[${name}] console: ${m.text()}`));
  p.on('response', (r) => r.status() >= 400 && problems.push(`[${name}] ${r.status()} ${r.url().replace(BASE, '')}`));
};
const step = (s) => console.log('·', s);
const shot = async (p, n) => { await p.waitForTimeout(400); await p.screenshot({ path: SHOTS + n + '.png' }); };

const ctx = await browser.newContext({ ...devices['Pixel 7'], permissions: ['camera'] });
await ctx.addInitScript(() => {           // stand-in face detector: one face, or two when the test says so
  window.__faces = 1;
  window.FaceDetector = class {
    async detect() {
      const one = (x) => ({ boundingBox: { x, y: 110, width: 200, height: 250 }, landmarks: [] });
      return window.__faces === 2 ? [one(220), one(20)] : [one(220)];
    }
  };
});
const c = await ctx.newPage(); watch(c, 'TEAM01');
await c.goto(BASE + '/login');
await c.fill('#roll_no', 'TEAM01'); await c.fill('#code', codes.TEAM01);
await c.getByRole('button', { name: /^Log in/ }).click();
await c.waitForURL('**/exam');
await c.getByRole('button', { name: /Continue/ }).click();
await c.locator('label[for=understood]').click();
await c.getByRole('button', { name: /Continue/ }).click();
await c.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
await c.getByRole('button', { name: /Allow camera/ }).click();
await c.getByText('Sharpness').waitFor();
await c.getByRole('button', { name: /Start test/ }).click();
await c.getByText('Question 1').waitFor();
await c.waitForTimeout(2500);

await c.evaluate(() => { window.__faces = 2; });
await c.waitForTimeout(3500);
if (await c.getByText('Counted 1 of 5').count()) throw new Error('a second face for 3 s must not count yet');
await c.getByText('Counted 1 of 5').waitFor({ timeout: 6000 });
await shot(c, 'r01-second-face-5s');
await c.evaluate(() => { window.__faces = 1; });
step('second face: counted after 5 s (not after 3 s), with the limit shown');

const again = await (await browser.newContext({ ...devices['Pixel 7'] })).newPage();
await again.goto(BASE + '/login');
await again.fill('#roll_no', 'TEAM01'); await again.fill('#code', codes.TEAM01);
await again.getByRole('button', { name: /^Log in/ }).click();
await again.waitForURL('**/exam');
step('logging in again during the test: allowed and counted');

const leave = async () => {
  await c.evaluate(() => { Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await c.waitForTimeout(600);
  await c.evaluate(() => { Object.defineProperty(document, 'hidden', { value: false, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
};
for (let k = 1; k <= 5; k++) {
  await leave();
  await c.getByText(`Times so far: ${k} of 5`).waitFor();
  if (k === 5) await shot(c, 'r02-left-5-of-5');
  await c.getByRole('button', { name: 'Continue the test' }).click();
}
await leave();
await c.getByText('Your test has ended').waitFor();
await c.getByText('The test screen was left more than 5 times.').waitFor();
await c.getByRole('button', { name: /See result/ }).waitFor({ timeout: 30000 });
await shot(c, 'r03-test-ended');
await c.getByRole('button', { name: /See result/ }).click();
await c.getByText('Your test has ended').waitFor();
step('6th time leaving the test screen: the test ends, answers submitted, reason shown on the result page');

// any reviewer (here the reviewer, not the admin) checks the ended test in the live monitor and reopens it
const rev = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage(); watch(rev, 'reviewer');
await rev.goto(BASE + '/staff/login');
await rev.fill('#email', 'reviewer@fairproctor.demo'); await rev.fill('#password', 'Review@2026');
await rev.getByRole('button', { name: /^Log in/ }).click();
await rev.waitForURL(/\/review/);
await rev.goto(BASE + '/review/live');
await rev.getByText('Demo sitting').first().click();
await rev.getByText(/1 test was ended by a rule/).waitFor({ timeout: 20000 });
await rev.locator('[id^=reopen-pick-]').first().click();
await rev.getByText('Ended by a rule: review and reopen').waitFor();
await rev.getByRole('button', { name: /Reopen the test/ }).click();
await rev.getByText(/at least 5 characters/).waitFor();                   // a reason is required
await rev.fill('textarea[id^=reopen-]', 'Checked the snapshots: it was a notification, not another app');
await shot(rev, 'r04-reviewer-reopen');
await rev.getByRole('button', { name: /Reopen the test/ }).click();
await rev.getByText(/Test reopened · .* min given back/).waitFor();
step('a reviewer reviews the ended test in the live monitor and reopens it with a note');

await c.getByText('A reviewer reopened your test').waitFor({ timeout: 25000 });
await shot(c, 'r05-candidate-reopened');
await c.getByRole('button', { name: /Continue the test/ }).click();
await c.getByText(/^Question \d+/).first().waitFor({ timeout: 20000 });
await c.waitForTimeout(1500);
await leave();
await c.getByText('Times so far: 1 of 5').waitFor();
await shot(c, 'r06-count-starts-again');
await c.getByRole('button', { name: 'Continue the test' }).click();
step('candidate: told the test was reopened, continues with the answers kept, the count starts again from 0');
for (let k = 2; k <= 5; k++) {
  await leave();
  await c.getByText(`Times so far: ${k} of 5`).waitFor();
  await c.getByRole('button', { name: 'Continue the test' }).click();
}
await leave();
await c.getByText('Your test has ended').waitFor();
step('leaving 6 more times ends it again');

const adm = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage(); watch(adm, 'admin');
await adm.goto(BASE + '/staff/login');
await adm.fill('#email', 'admin@fairproctor.demo'); await adm.fill('#password', 'Admin@2026');
await adm.getByRole('button', { name: /^Log in/ }).click();
await adm.waitForURL('**/admin');
await adm.goto(BASE + '/review/live');
await adm.getByText('Demo sitting').first().click();
await adm.getByText(/Test ended \(tab switch\)/).first().waitFor({ timeout: 20000 });
await shot(adm, 'r07-live-monitor');
step('live monitor shows the ended test and the counts');
const sits = await adm.evaluate(async () => (await fetch('/api/admin/sittings', { headers: { Authorization: 'Bearer ' + (localStorage.getItem('fp-staff-token') || '').replace(/"/g, '') } })).json());
const demo = sits.find((s) => s.title === 'Demo sitting');
await adm.goto(BASE + `/admin/sittings/${demo.id}`);
await adm.getByRole('button', { name: /Close & score/ }).click();
await adm.getByRole('dialog').getByRole('button', { name: /Close & score/ }).click();
await adm.getByText('Result of scoring').waitFor({ timeout: 120000 });
await adm.goto(BASE + '/review');
await adm.fill('input[aria-label=Search]', 'TEAM01');
await adm.waitForTimeout(1000);
await adm.locator('#row-0').getByText('Test ended').waitFor();
await adm.locator('#row-0 a').click();
await adm.getByText('Proctoring rules').waitFor();
await adm.getByText(/Test ended by a rule/).waitFor();
await adm.getByText(/and reopened by .* min given back/).waitFor();
await adm.getByText(/Logged in again during the test 1 time/).waitFor();
await adm.getByText(/More than one face for 5 s or longer: 1 time/).waitFor();
await adm.getByText('Proctoring rules').scrollIntoViewIfNeeded();
await shot(adm, 'r08-reviewer-rules');
step('reviewer: in the queue with a "Test ended" chip and a Proctoring rules card');

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

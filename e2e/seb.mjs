// Safe Exam Browser: a normal browser is stopped with instructions; "SEB" (its JavaScript API simulated with the
// right Config Key) can write the test. Run on a freshly seeded database, backend running.
import { chromium, devices } from 'playwright';
import crypto from 'node:crypto';
import fs from 'node:fs';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = new URL('./shots/', import.meta.url).pathname; fs.mkdirSync(SHOTS, { recursive: true });
const CK = crypto.createHash('sha256').update('seb settings for the e2e test').digest('hex');
const H = (u) => crypto.createHash('sha256').update(u + CK).digest('hex');
const step = (s) => console.log('·', s);
const problems = [];
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });

const j = async (r) => { if (!r.ok()) throw new Error(r.url() + ' ' + r.status() + ' ' + await r.text()); return r.json(); };
const api = await (await browser.newContext()).request;
const tok = (await j(await api.post(BASE + '/api/auth/login', { data: { email: 'admin@fairproctor.demo', password: 'Admin@2026' } }))).access_token;
const auth = { Authorization: 'Bearer ' + tok };
const sits = await j(await api.get(BASE + '/api/admin/sittings', { headers: auth }));
const demo = sits.find((s) => s.title === 'Demo sitting');
const codes = Object.fromEntries((await j(await api.post(BASE + `/api/admin/sittings/${demo.id}/candidates`, { headers: { ...auth, 'content-type': 'text/csv' }, data: 'roll_no,name\nSEB01,Laptop One\n' }))).candidates.map((c) => [c.roll_no, c.code]));
await j(await api.put(BASE + `/api/admin/sittings/${demo.id}/seb`, { headers: auth, data: { required: true, config_key: CK, file_base64: Buffer.from('<plist>e2e</plist>').toString('base64') } }));
step('admin requires Safe Exam Browser for the sitting');

async function candidate(seb) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 860 }, permissions: ['camera'] });
  if (seb) {
    // SEB's JavaScript API: the Config Key hashed with the current page URL (precomputed for the pages we visit)
    const keys = Object.fromEntries(['/', '/login', '/exam', '/exam/consent', '/exam/precheck', '/exam/run', '/exam/result'].map((p) => [BASE + p, H(BASE + p)]));
    await ctx.addInitScript((keys) => {
      window.SafeExamBrowser = { version: 'SafeExamBrowser_Windows_3.8_test', security: { get configKey() { return keys[location.href.split('#')[0].split('?')[0]] || ''; } } };
    }, keys);
  }
  const p = await ctx.newPage();
  p.on('pageerror', (e) => problems.push(String(e)));
  p.on('response', (r) => r.status() >= 400 && !(r.status() === 403 && !seb) && problems.push(`${r.status()} ${r.url().replace(BASE, '')}`));
  await p.goto(BASE + '/login');
  await p.fill('#roll_no', 'SEB01'); await p.fill('#code', codes.SEB01);
  await p.getByRole('button', { name: /^Log in/ }).click();
  await p.waitForURL('**/exam');
  return p;
}

const plain = await candidate(false);
await plain.getByText('This test opens only in Safe Exam Browser').waitFor();
const href = await plain.getByRole('link', { name: 'Open in Safe Exam Browser' }).getAttribute('href');
if (!/^seb:\/\/.+\/api\/seb\/.+\.seb$/.test(href)) throw new Error('bad SEB link ' + href);
if (await plain.getByRole('button', { name: /Continue/ }).count()) throw new Error('normal browser must not continue');
const forced = await plain.evaluate(async () => (await fetch('/api/exam/start', { method: 'POST', headers: { Authorization: 'Bearer ' + localStorage.getItem('fp-token').replace(/"/g, ''), 'Content-Type': 'application/json' }, body: '{}' })).status);
if (forced !== 403) throw new Error('start without SEB returned ' + forced);
await plain.waitForTimeout(800);
await plain.screenshot({ path: SHOTS + 'seb01-normal-browser.png' });
step('normal browser: stopped, with install steps and an seb:// link; the API refuses too');

const s = await candidate(true);
await s.getByText('Safe Exam Browser: checked').waitFor();
await s.screenshot({ path: SHOTS + 'seb02-in-seb.png' });
await s.getByRole('button', { name: /Continue/ }).click();
await s.waitForURL('**/exam/consent');
await s.locator('label[for=understood]').click();
await s.getByRole('button', { name: /Continue/ }).click();
await s.waitForURL('**/exam/precheck');
await s.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
await s.getByRole('button', { name: /Allow camera/ }).click();
await s.getByText('Sharpness').waitFor();
await s.getByRole('button', { name: /Start test/ }).click();
await s.waitForURL('**/exam/run');
await s.getByText('Question 1').waitFor();
await s.locator('button[role=radio], [role=radiogroup] button').first().click().catch(() => {});
await s.waitForTimeout(6000);
step('inside SEB: checked, consent, pre-check and the test run');

const adm = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage();
await adm.goto(BASE + '/staff/login');
await adm.fill('#email', 'admin@fairproctor.demo'); await adm.fill('#password', 'Admin@2026');
await adm.getByRole('button', { name: /^Log in/ }).click();
await adm.waitForURL('**/admin');
await adm.goto(BASE + `/admin/sittings/${demo.id}`);
await adm.getByText('Require Safe Exam Browser').waitFor();
await adm.getByText('Safe Exam Browser', { exact: true }).scrollIntoViewIfNeeded();
await adm.screenshot({ path: SHOTS + 'seb03-admin.png' });
step('admin sees the Safe Exam Browser card');

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

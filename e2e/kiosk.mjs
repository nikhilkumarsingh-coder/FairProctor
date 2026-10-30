// Device decided automatically (run on a freshly seeded database, backend running). The demo sitting requires Safe
// Exam Browser on laptops. A phone is let in with kiosk mode (full screen; leaving it shows a "back to full screen"
// bar and is noted, never a rule); a laptop is asked for SEB; a laptop that pretends to be a phone is let in and gets
// a "device check" flag in the live monitor.
import fs from 'node:fs';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url)); fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const step = (s) => console.log('·', s);
const shot = async (p, n) => { await p.waitForTimeout(400); await p.screenshot({ path: SHOTS + n + '.png' }); };
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const problems = [];
const expected = [/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED/];
const watch = (p, name, ok = []) => {
  p.on('pageerror', (e) => problems.push(`[${name}] ${e.message}`));
  p.on('console', (m) => m.type() === 'error' && ![...expected, ...ok].some((x) => x.test(m.text())) && problems.push(`[${name}] console: ${m.text()}`));
  p.on('response', (r) => r.status() >= 400 && !ok.some((x) => x.test(r.url())) && problems.push(`[${name}] ${r.status()} ${r.url().replace(BASE, '')}`));
};
const face = () => { window.FaceDetector = class { async detect() { return [{ boundingBox: { x: 220, y: 110, width: 200, height: 250 }, landmarks: [] }]; } }; };

// admin: require SEB on laptops for the demo sitting
const adm = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage(); watch(adm, 'admin');
await adm.goto(BASE + '/staff/login');
await adm.fill('#email', 'admin@fairproctor.demo'); await adm.fill('#password', 'Admin@2026');
await adm.getByRole('button', { name: /^Log in/ }).click();
await adm.waitForURL('**/admin');
const tok = await adm.evaluate(() => (localStorage.getItem('fp-staff-token') || '').replace(/"/g, ''));
const call = (method, path, body) => adm.evaluate(async ([m, p, b, t]) => (await fetch(p, { method: m, headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined })).json(), [method, path, body, tok]);
const demo = (await call('GET', '/api/admin/sittings')).find((s) => s.title === 'Demo sitting');
const seb = await call('PUT', `/api/admin/sittings/${demo.id}/seb`, { required: true, config_key: crypto.createHash('sha256').update('kiosk e2e').digest('hex') });
if (!seb.required) throw new Error('could not require SEB');
await adm.goto(BASE + `/admin/sittings/${demo.id}`);
await adm.getByText('Require Safe Exam Browser on laptops').scrollIntoViewIfNeeded();
await shot(adm, 'k01-admin-seb-laptops');
step('admin: Safe Exam Browser required on laptops; phones use kiosk mode');

// a phone: no SEB asked, full screen on Start
const phone = await (await browser.newContext({ ...devices['Pixel 7'], permissions: ['camera'] })).newPage();
await phone.context().addInitScript(face); watch(phone, 'phone');
await phone.goto(BASE + '/login');
await phone.fill('#roll_no', 'TEAM01'); await phone.fill('#code', codes.TEAM01);
await phone.getByRole('button', { name: /^Log in/ }).click();
await phone.waitForURL('**/exam');
if (await phone.getByText('This test opens only in Safe Exam Browser').count()) throw new Error('phone was asked for SEB');
await phone.getByRole('button', { name: /Continue/ }).click();
await phone.getByText('When you leave the test tab, app or full screen').waitFor();
await phone.locator('label[for=understood]').click();
await phone.getByRole('button', { name: /Continue/ }).click();
await phone.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
await phone.getByRole('button', { name: /Allow camera/ }).click();
await phone.getByText('Sharpness').waitFor();
await phone.getByRole('button', { name: /Start test/ }).click();
await phone.getByText('Question 1').waitFor();
await phone.waitForFunction(() => !!document.fullscreenElement, null, { timeout: 5000 });
step('phone: no SEB, the test opens in full screen');
await phone.waitForTimeout(1500);
await phone.evaluate(() => document.exitFullscreen());
await phone.locator('#kiosk-off').waitFor();
await shot(phone, 'k02-phone-left-full-screen');
await phone.getByRole('button', { name: 'Back to full screen' }).click();
await phone.waitForFunction(() => !!document.fullscreenElement, null, { timeout: 5000 });
await phone.locator('#kiosk-off').waitFor({ state: 'detached' });
step('phone: leaving full screen shows a "back to full screen" bar (not a warning, not counted)');

// a laptop: asked for SEB
const laptop = await (await browser.newContext({ viewport: { width: 1366, height: 800 } })).newPage(); watch(laptop, 'laptop', [/\/api\/exam\/start/]);
await laptop.goto(BASE + '/login');
await laptop.fill('#roll_no', 'TEAM02'); await laptop.fill('#code', codes.TEAM02);
await laptop.getByRole('button', { name: /^Log in/ }).click();
await laptop.waitForURL('**/exam');
await laptop.getByText('This test opens only in Safe Exam Browser').waitFor();
await shot(laptop, 'k03-laptop-needs-seb');
step('laptop: asked to open the test in Safe Exam Browser');

// a laptop pretending to be a phone: let in, flagged
const spoof = await (await browser.newContext({ userAgent: devices['Pixel 7'].userAgent, viewport: { width: 1920, height: 1080 }, permissions: ['camera'] })).newPage();
await spoof.context().addInitScript(face); watch(spoof, 'spoof');
await spoof.goto(BASE + '/login');
await spoof.fill('#roll_no', 'TEAM03'); await spoof.fill('#code', codes.TEAM03);
await spoof.getByRole('button', { name: /^Log in/ }).click();
await spoof.waitForURL('**/exam');
await spoof.getByRole('button', { name: /Continue/ }).click();
await spoof.locator('label[for=understood]').click();
await spoof.getByRole('button', { name: /Continue/ }).click();
await spoof.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
await spoof.getByRole('button', { name: /Allow camera/ }).click();
await spoof.getByText('Sharpness').waitFor();
await spoof.getByRole('button', { name: /Start test/ }).click();
await spoof.getByText('Question 1').waitFor();
step('a laptop pretending to be a phone gets in (it could be a tablet)…');

await adm.goto(BASE + '/review/live');
await adm.getByText('Demo sitting').first().click();
await adm.getByText('Device check: says phone, looks like a laptop (skipped SEB)').waitFor({ timeout: 20000 });
await adm.getByText(/Left full screen 1× · noted only/).waitFor({ timeout: 20000 });
await adm.getByText('Device check: says phone, looks like a laptop (skipped SEB)').scrollIntoViewIfNeeded();
await shot(adm, 'k04-live-device-check');
step('…and the live monitor shows a "device check" for it, and the phone\'s full-screen exit as noted only');

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

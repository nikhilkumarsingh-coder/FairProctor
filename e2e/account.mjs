// Account page: profile, language, password change (other devices logged out), code-login candidates, staff view.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch();
const problems = [];
const expected = [/400 POST \/api\/auth\/change-password/, /401 GET \/api\/me/, /401 POST \/api\/auth\/login/, /status of 40[01]/];
const note = (s) => { if (!expected.some((x) => x.test(s))) problems.push(s); };
async function open(name, device = devices['Pixel 7']) {
  const ctx = await browser.newContext(device); const page = await ctx.newPage();
  page.on('pageerror', (e) => note(`[${name}] pageerror: ${e.message}`));
  page.on('console', (m) => m.type() === 'error' && note(`[${name}] console: ${m.text()}`));
  page.on('response', (r) => r.status() >= 400 && note(`[${name}] ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`));
  return page;
}
const shot = async (p, n, full = true) => { await p.waitForTimeout(450); await p.screenshot({ path: SHOTS + n + '.png', fullPage: full }); };
const step = (s) => console.log('·', s);
const email = `meera${Date.now() % 100000}@example.com`;

step('admin adds a reviewer in the staff app (no sign-up)');
const s = await open('admin', { viewport: { width: 1440, height: 900 } });
await s.goto(BASE + '/staff');
await s.waitForURL('**/staff/login');
await s.fill('#email', 'admin@fairproctor.demo'); await s.fill('#password', 'Admin@2026');
await s.getByRole('button', { name: /^Log in/ }).click();
await s.waitForURL('**/admin');
await s.getByRole('button', { name: 'Add reviewer' }).click();
await s.fill('#r-name', 'Meera Iyer'); await s.fill('#r-email', email); await s.fill('#r-password', 'first2026ok');
await s.getByRole('dialog').getByRole('button', { name: 'Add reviewer' }).click();
await s.getByRole('cell', { name: email }).waitFor();
await shot(s, 'a00-admin-staff-accounts');

step('the reviewer logs in at /staff/login and opens the account page');
const a = await open('device-A', { viewport: { width: 1280, height: 900 } });
await a.goto(BASE + '/staff/login');
await a.fill('#email', email); await a.fill('#password', 'first2026ok');
await a.getByRole('button', { name: /^Log in/ }).click();
await a.waitForURL('**/review');
await a.getByRole('link', { name: /Meera Iyer/ }).click();
await a.waitForURL('**/staff/account');
await a.getByText('Change password').first().waitFor();
await shot(a, 'a01-account');

step('second device logged in with the same account');
const b = await open('device-B', { viewport: { width: 1280, height: 900 } });
await b.goto(BASE + '/staff/login');
await b.fill('#email', email); await b.fill('#password', 'first2026ok');
await b.getByRole('button', { name: /^Log in/ }).click();
await b.waitForURL('**/review');

step('profile: validation, then the name (staff screens stay in English)');
await a.fill('#p-name', 'M');
await a.getByRole('button', { name: 'Save changes' }).click();
await a.getByText('Enter your full name.').waitFor();
await a.fill('#p-name', 'Meera  S. Iyer');
await a.getByRole('button', { name: 'Save changes' }).click();
await a.getByText('Profile saved').waitFor();
await a.getByText('Meera S. Iyer').first().waitFor();
await shot(a, 'a02-account-staff');

step('password: wrong current, mismatch, weak, then success');
await a.fill('#pw-current', 'nope2026x'); await a.fill('#pw-next', 'second2026ok'); await a.fill('#pw-again', 'second2026ok');
await a.getByRole('button', { name: 'Change password' }).click();
await a.getByText('Your current password is not correct.').waitFor();
await a.fill('#pw-current', 'first2026ok'); await a.fill('#pw-again', 'second2026no');
await a.getByRole('button', { name: 'Change password' }).click();
await a.getByText('The two passwords do not match.').waitFor();
await a.fill('#pw-next', 'short'); await a.fill('#pw-again', 'short');
await a.getByRole('button', { name: 'Change password' }).click();
await a.getByText('Use at least 8 characters').first().waitFor();
await shot(a, 'a03-password-errors');
await a.fill('#pw-next', 'second2026ok'); await a.fill('#pw-again', 'second2026ok');
await a.getByRole('button', { name: 'Change password' }).click();
await a.getByText(/Password changed/).waitFor();
await a.reload();
await a.getByText('Meera S. Iyer').first().waitFor();            // this device stays logged in

step('other device is logged out');
await b.reload();
await b.waitForURL('**/staff/login?expired=1');
await b.getByText(/log in again/).waitFor();
await shot(b, 'a04-other-device-expired', false);
await b.fill('#email', email); await b.fill('#password', 'first2026ok');
await b.getByRole('button', { name: /^Log in/ }).click();
await b.getByText('Login details are not correct.').waitFor();
await b.fill('#password', 'second2026ok');
await b.getByRole('button', { name: /^Log in/ }).click();
await b.waitForURL('**/review');

step('roll no. + code candidate, and staff');
const wrong = await open('staff-on-candidate-page');
await wrong.goto(BASE + '/admin');                        // the staff app; not logged in there
await wrong.waitForURL('**/staff/login?next=%2Fadmin');
const c = await open('TEAM01');
await c.goto(BASE + '/login');
await c.fill('#roll_no', 'TEAM01'); await c.fill('#code', codes.TEAM01);
await c.getByRole('button', { name: /^Log in/ }).click();
await c.waitForURL('**/exam');
await c.goto(BASE + '/account');                         // the candidate app's own account page
await c.getByText(/roll no. and a code from your test centre/).waitFor();
await shot(c, 'a05-account-code-login');
await c.getByRole('radio', { name: 'हिन्दी' }).click();               // candidates choose their language
await c.getByRole('button', { name: 'Save changes' }).click();
await c.getByText('प्रोफ़ाइल सेव हो गई').waitFor();
await shot(c, 'a05b-account-hindi');
await c.getByRole('radio', { name: 'English' }).click();
await c.getByRole('button', { name: /सेव करें/ }).click();
await c.getByText('Profile saved').waitFor();
await s.goto(BASE + '/admin');
await s.getByRole('link', { name: /Demo Admin/ }).click();
await s.waitForURL('**/staff/account');
await s.getByText('Change password').first().waitFor();
await shot(s, 'a06-account-admin', false);

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no unexpected errors');

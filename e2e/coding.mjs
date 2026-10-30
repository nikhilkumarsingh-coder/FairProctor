// Coding test in the browser: an honest coder (typed, Python + JavaScript + C++), a paster, the live monitor,
// close & score, the reviewer's code view, the candidate's marks and the admin's coding test page.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const logins = fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8');
const codes = Object.fromEntries([...logins.matchAll(/(CODE0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const problems = [];
const expected = [/status of 4\d\d/];
const watch = (page, name) => {
  page.on('pageerror', (e) => problems.push(`[${name}] pageerror: ${e.message}`));
  page.on('response', (r) => { const s = `${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`; if (r.status() >= 400 && !expected.some((x) => x.test(s))) problems.push(`[${name}] ${s}`); });
};
const shot = async (p, n, full = false) => { await p.waitForTimeout(450); await p.screenshot({ path: SHOTS + n + '.png', fullPage: full }); };
const step = (s) => console.log('·', s);

const P1 = `import sys
d = sys.stdin.read().split()
n = int(d[0])
s = sorted(set(map(int, d[1:1 + n])), reverse=True)
print(s[1] if len(s) > 1 else -1)`;
const P2 = `const L = require('fs').readFileSync(0, 'utf8').split('\\n');
const t = Number(L[0]);
const P = {')': '(', ']': '[', '}': '{'};
const out = [];
for (let i = 1; i <= t; i++) { const s = L[i].trim(); const st = []; let ok = true; for (const c of s) { if ('([{'.includes(c)) st.push(c); else if (st.pop() !== P[c]) { ok = false; break; } } out.push(ok && st.length === 0 ? 'YES' : 'NO'); }
console.log(out.join('\\n'));`;
const P3_SLOW = `import sys
d = sys.stdin.read().split()
n, k = int(d[0]), int(d[1])
a = list(map(int, d[2:2 + n]))
print(sum(1 for i in range(n) for j in range(i + 1, n) if a[i] + a[j] == k))`;
const P3 = `#include <bits/stdc++.h>
using namespace std;
int main() {
ios::sync_with_stdio(false); cin.tie(nullptr);
int n; long long k; cin >> n >> k;
unordered_map<long long, long long> seen; long long c = 0;
for (int i = 0; i < n; i++) { long long x; cin >> x; auto it = seen.find(k - x); if (it != seen.end()) c += it->second; seen[x]++; }
cout << c << "\\n";
}`;

async function into(page, name) {
  await page.goto(BASE + '/login');
  await page.fill('#roll_no', name); await page.fill('#code', codes[name]);
  await page.getByRole('button', { name: /^Log in/ }).click();
  await page.waitForURL('**/exam');
  await page.getByText('Coding test').first().waitFor();
}
async function startTest(page) {
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.locator('label[for=understood]').click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
  const start = page.getByRole('button', { name: /Start test/ });
  if (!(await start.isDisabled())) throw new Error('Start test must wait for the camera');
  await page.getByRole('button', { name: /Allow camera/ }).click();        // the camera is required
  await page.getByText('Sharpness').waitFor();
  await page.getByRole('button', { name: /Start test/ }).click();
  await page.getByText('Sample tests').waitFor();
}
async function typeCode(page, code, delay = 70) {
  const ed = page.getByRole('textbox', { name: /·/ });
  await ed.click();
  await page.keyboard.press('Control+A');
  await page.keyboard.press('Delete');
  for (const line of code.split('\n')) {                                // the editor indents new lines itself
    await page.keyboard.type(line.trimStart(), { delay });
    await page.keyboard.press('Enter');
  }
}

// ---------------- CODE01: honest
step('CODE01 opens the coding test');
const ctx1 = await browser.newContext({ viewport: { width: 1440, height: 950 }, permissions: ['camera'] });
const a = await ctx1.newPage(); watch(a, 'CODE01');
await into(a, 'CODE01');
await shot(a, 'k01-home');
await startTest(a);
await shot(a, 'k02-problem-starter');
step('P1 in Python: typed, samples, submit');
await typeCode(a, P1);
await a.getByRole('button', { name: /Run samples/ }).click();
await a.getByText(/2 \/ 2 tests passed/).waitFor({ timeout: 30000 });
await shot(a, 'k03-run-samples');
await a.getByRole('button', { name: /Submit code/ }).click();
await a.getByText(/8 \/ 8 tests passed/).waitFor({ timeout: 60000 });
await shot(a, 'k04-accepted');
step('P2 in JavaScript');
await a.getByRole('tab', { name: /P2/ }).click();
await a.selectOption('#lang', 'javascript');
await typeCode(a, P2, 45);
await a.getByRole('button', { name: /Submit code/ }).click();
await a.getByText(/4 \/ 4 tests passed/).waitFor({ timeout: 60000 });
step('P3: slow Python first (time limit), then C++');
await a.getByRole('tab', { name: /P3/ }).click();
await typeCode(a, P3_SLOW, 45);
await a.getByRole('button', { name: /Submit code/ }).click();
await a.getByText('Time limit exceeded').first().waitFor({ timeout: 90000 });
await shot(a, 'k05-time-limit');
await a.getByRole('button', { name: /Run with my input/ }).first().click();
await a.fill('#custom', '4 2\n1 1 1 1\n');
await a.getByRole('button', { name: /Run with my input/ }).last().click();
await a.getByText('Your output').first().waitFor();
await a.selectOption('#lang', 'cpp');
await typeCode(a, P3, 45);
await a.getByRole('button', { name: /Submit code/ }).click();
await a.getByText(/8 \/ 8 tests passed/).waitFor({ timeout: 90000 });
await shot(a, 'k06-cpp-accepted');

// ---------------- CODE02: leaves, pastes a solution
step('CODE02 pastes a solution after leaving the tab');
const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 950 }, permissions: ['camera', 'clipboard-read', 'clipboard-write'] });
const b = await ctx2.newPage(); watch(b, 'CODE02');
await into(b, 'CODE02');
await startTest(b);
await b.evaluate(() => { Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
await b.waitForTimeout(3000);
await b.evaluate(() => { Object.defineProperty(document, 'hidden', { value: false, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
await b.getByRole('button', { name: 'Continue the test' }).click();
await b.evaluate((t) => navigator.clipboard.writeText(t), 'import sys\nd=sys.stdin.read().split();n=int(d[0]);a=set(map(int,d[1:1+n]))\ns=sorted(a,reverse=True)\nprint(s[1] if len(s)>1 else -1)\n');
const ed = b.getByRole('textbox', { name: /·/ });
await ed.click(); await b.keyboard.press('Control+A'); await b.keyboard.press('Control+V');
await b.getByText(/Pasting is recorded/).waitFor();
await b.getByRole('button', { name: /Submit code/ }).click();
await b.getByText(/8 \/ 8 tests passed/).waitFor({ timeout: 60000 });
await b.waitForTimeout(11000);                                          // let the typing/paste events upload

// ---------------- live monitor
step('admin: live monitor of the coding sitting');
const adm = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage(); watch(adm, 'admin');
await adm.goto(BASE + '/staff/login');
await adm.fill('#email', 'admin@fairproctor.demo'); await adm.fill('#password', 'Admin@2026');
await adm.getByRole('button', { name: /^Log in/ }).click();
await adm.waitForURL('**/admin');
await adm.getByRole('link', { name: 'Live monitor' }).first().click();
await adm.getByText('Coding sitting').first().click();
await adm.getByText('Candidates by live risk').waitFor();
await adm.getByText(/pasted \d+ characters into P1/).first().waitFor({ timeout: 30000 });
await shot(adm, 'k07-live-monitor', true);

step('both finish; admin closes and scores');
for (const p of [a, b]) {
  await p.getByRole('button', { name: /Finish test/ }).first().click();
  await p.getByRole('dialog').getByRole('button', { name: 'Submit', exact: true }).click();
  await p.waitForURL('**/exam/done', { timeout: 30000 });
}
await adm.goto(BASE + '/admin');
await adm.getByText('Coding sitting').first().click();
await adm.getByRole('button', { name: /Close & score/ }).click();
await adm.getByRole('dialog').getByRole('button', { name: /Close & score/ }).click();
await adm.getByText('Result of scoring').waitFor({ timeout: 300000 });
await adm.getByRole('link', { name: /Open review queue/ }).click();
await adm.getByRole('tab', { name: /All/ }).click();
await adm.fill('input[aria-label=Search]', 'CODE');
await adm.waitForTimeout(1200);
await shot(adm, 'k08-queue');
const rows = await adm.locator('#row-0, #row-1, #row-2').allInnerTexts();
console.log('  ' + rows.map((r) => r.replace(/\s+/g, ' ').slice(0, 170)).join('\n  '));
await adm.fill('input[aria-label=Search]', 'CODE02');
await adm.waitForTimeout(1000);
await adm.locator('#row-0 a').click();
await adm.getByRole('heading', { name: 'Programs' }).waitFor();
await shot(adm, 'k09-session-code', true);

step('candidate marks and admin coding test page');
await a.goto(BASE + '/exam/result');
await a.getByText('Your marks').waitFor();
await shot(a, 'k10-result-marks', true);
await adm.goto(BASE + '/admin');
await adm.locator('table').getByRole('link', { name: /Coding Round/ }).click();
await adm.getByText('Languages on this server').waitFor();
await shot(adm, 'k11-admin-coding-test');
await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

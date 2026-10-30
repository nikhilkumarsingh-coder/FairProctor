// Demo: the "Try the demo" buttons on the login page, the story (Rahul first in the queue, Priya cleared with what was
// not counted, both candidates' results) and the fairness report of the scored morning sitting.
// Needs a fresh seed from the command line (python -m backend.scripts.seed_demo --reset), which includes the story.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const browser = await chromium.launch();
const problems = [];
const watch = (page, name) => {
  page.on('pageerror', (e) => problems.push(`[${name}] pageerror: ${e.message}`));
  page.on('response', (r) => r.status() >= 400 && problems.push(`[${name}] ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`));
};
const shot = async (p, n, full = false) => { await p.waitForTimeout(450); await p.screenshot({ path: SHOTS + n + '.png', fullPage: full }); };
const step = (s) => console.log('·', s);
async function page(name, phone = false, staff = false) {
  const ctx = await browser.newContext(phone ? { ...devices['Pixel 7'] } : { viewport: { width: 1440, height: 950 } });
  const p = await ctx.newPage();
  watch(p, name);
  await p.goto(BASE + (staff ? '/staff/login' : '/login'));     // candidates and staff have separate login pages
  await p.getByText('Try the demo').waitFor();
  return p;
}
const click = (p, name) => p.getByRole('button', { name }).click();

step('demo box on the login page');
let p = await page('login', true);
await shot(p, 'd01-login-demo', true);

step('Priya: cleared, with what was not counted');
await click(p, /Priya/);
await p.waitForURL('**/exam/result');
await p.getByText('Not counted against you').waitFor();
for (const words of [/Low-bandwidth video/, /dim room/, /walking past/, /Phone held at an angle/]) await p.getByText(words).first().waitFor();
await shot(p, 'd02-priya-result', true);
await p.context().close();

step('Rahul: being reviewed, sees the moments and can explain');
p = await page('rahul', true);
await click(p, /Rahul/);
await p.waitForURL('**/exam/result');
await p.getByText('Long pauses with no activity before correct answers').waitFor();
await p.getByRole('button', { name: /Explain this/ }).waitFor();
await shot(p, 'd03-rahul-result', true);
await p.context().close();

step('reviewer: Rahul is the only real candidate flagged; his evidence');
p = await page('reviewer', false, true);
await click(p, /^Reviewer$/);
await p.waitForURL('**/review');
await p.getByText('Hide reference sessions').click();
await p.locator('#row-0').waitFor();
const first = (await p.locator('#row-0').innerText()).replace(/\s+/g, ' ');
console.log('  queue, real candidates only:', first.slice(0, 120));
if (!/Review first/.test(first) || !/Silent pause/.test(first)) problems.push('Rahul is not first in the real-candidate queue');
await shot(p, 'd04-queue-real-only');
await p.locator('#row-0 a').click();
await p.getByText('Why this session is in the queue').waitFor();
await p.getByText(/Head was down/).first().waitFor();
await shot(p, 'd05-rahul-evidence', true);
await p.context().close();

step('admin: morning sitting, evidence links, fairness report');
p = await page('admin', false, true);
await click(p, /^Admin$/);
await p.waitForURL('**/admin');
await p.getByText('Morning sitting — already scored').first().click();
await p.getByRole('link', { name: 'Open evidence' }).first().waitFor();
await shot(p, 'd06-morning-sitting');
await p.getByRole('link', { name: /Fairness report/ }).click();
await p.getByText('Biggest extra flagging · old rules').waitFor();
await p.getByText('Phone vs Laptop / desktop').waitFor();
await shot(p, 'd07-fairness', true);
await p.getByRole('tab', { name: 'Review first' }).click();
await p.getByText('No group was flagged more often than its reference group.').waitFor();
await shot(p, 'd08-fairness-review-first');
await p.getByText('Show the numbers').first().click();
await p.locator('details[open] table').first().waitFor();
await p.context().close();

step('a fresh candidate for each test');
for (const [label, title] of [[/Question test/, /Aptitude/], [/Coding test/, /Coding Round/]]) {
  p = await page('fresh', true);
  await click(p, label);
  await p.waitForURL('**/exam');
  await p.getByText(title).first().waitFor();
  await p.context().close();
}
await browser.close();
if (problems.length) { console.log('PROBLEMS:\n  ' + problems.join('\n  ')); process.exit(1); }
console.log('no page errors or failed requests');

// Admin + reviewer flow on a desktop browser, then the flagged candidate's result and appeal on a phone.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch();
const problems = [];
const expected = [/POST \/api\/admin\/tests\/\d+\/items$/, /POST \/api\/review\/sessions\/.*\/decision$/];
function watch(page, name) {
  page.on('pageerror', (e) => problems.push(`[${name}] pageerror: ${e.message}`));
  page.on('response', (r) => { const s = `${r.request().method()} ${r.url().replace(BASE, '')}`; if (r.status() >= 400 && !expected.some((x) => x.test(s))) problems.push(`[${name}] ${r.status()} ${s}`); });
}
async function desk(name) { const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } }); const page = await ctx.newPage(); watch(page, name); return page; }
async function phone(name) { const ctx = await browser.newContext({ ...devices['Pixel 7'] }); const page = await ctx.newPage(); watch(page, name); return page; }
const shot = async (page, n, full = false) => { await page.waitForTimeout(450); await page.screenshot({ path: SHOTS + n + '.png', fullPage: full }); };
const step = (s) => console.log('·', s);
async function staffLogin(page, email, pw) {
  await page.goto(BASE + '/staff/login');
  await page.fill('#email', email); await page.fill('#password', pw);
  await page.getByRole('button', { name: /^Log in/ }).click();
}

// ---------------- admin
const admin = await desk('admin');
await staffLogin(admin, 'admin@fairproctor.demo', 'Admin@2026');
await admin.waitForURL('**/admin');
await admin.getByText('Demo sitting').waitFor();
await shot(admin, 's01-admin-home');
step('new test');
await admin.getByRole('button', { name: 'New test' }).click();
await admin.getByRole('button', { name: /Create and add questions/ }).click();
await admin.getByText('Give the test a title.').waitFor();
await admin.fill('#t-title', 'Demo quiz'); await admin.fill('#t-dur', '20');
await admin.getByRole('button', { name: /Create and add questions/ }).click();
await admin.waitForURL(/\/admin\/tests\/\d+/);
await admin.fill('#csv', 'text,option_a,option_b,correct\nWhat is 2+2?,3,4,B\nBad row,1,2,Z\n');
await admin.getByRole('button', { name: 'Upload' }).click();
await admin.getByText(/not one of the options/).waitFor();
await shot(admin, 's02-admin-csv-bad-rows');
await admin.fill('#csv', 'text,option_a,option_b,option_c,correct,kind\nWhat is 2+2?,3,4,5,B,mcq\nCapital of India?,Delhi,Mumbai,Pune,A,mcq\nWhat is 7 × 6?,,,,42,short\n');
await admin.getByRole('button', { name: 'Upload' }).click();
await admin.getByText('3 questions saved').waitFor();
await shot(admin, 's03-admin-test');
step('new sitting + import candidates');
await admin.goto(BASE + '/admin');
await admin.getByRole('button', { name: 'New sitting' }).click();
await admin.selectOption('#s-test', { label: /Demo quiz/ }).catch(async () => {
  const v = await admin.locator('#s-test option', { hasText: 'Demo quiz' }).getAttribute('value'); await admin.selectOption('#s-test', v);
});
await admin.fill('#s-title', 'Morning batch');
await admin.getByRole('button', { name: 'Create sitting' }).click();
await admin.waitForURL(/\/admin\/sittings\/\d+/);
await admin.fill('#csv', 'roll_no,name,language\nCS-001,Asha Kumari,hi\nCS-002,Rahul Verma,en\n');
await admin.getByRole('button', { name: 'Upload' }).click();
await admin.getByText('Login codes — save them now').waitFor();
await shot(admin, 's04-admin-codes');
await admin.keyboard.press('Escape');
await admin.getByRole('button', { name: /Open now/ }).click();
await admin.getByText('live', { exact: true }).first().waitFor();
step('close & score the demo sitting');
await admin.goto(BASE + '/admin/sittings/1');
await admin.getByText('Reference sessions').waitFor();
await shot(admin, 's05-admin-sitting-live');
await admin.getByRole('button', { name: /Close & score/ }).click();
await admin.getByRole('dialog').getByRole('button', { name: /Close & score/ }).click();
await admin.getByText(/Scoring the sitting/).waitFor({ timeout: 10000 }).then(() => shot(admin, 's06-admin-scoring')).catch(() => {});
await admin.getByText('Result of scoring').waitFor({ timeout: 300000 });
await shot(admin, 's07-admin-scored');

// ---------------- reviewer
const rev = await desk('reviewer');
await staffLogin(rev, 'reviewer@fairproctor.demo', 'Review@2026');
await rev.waitForURL('**/review');
await rev.getByText('Review first').first().waitFor();
await rev.locator('#row-0').waitFor();
await shot(rev, 's08-review-queue');
await rev.goto(BASE + '/admin');
await rev.getByText('You do not have access to this page').waitFor();
await rev.goto(BASE + '/review');
await rev.getByRole('button', { name: 'Answer match' }).click();
await rev.waitForTimeout(800);
await shot(rev, 's09-review-filter-match');
await rev.getByRole('button', { name: 'Answer match' }).click();
await rev.getByRole('tab', { name: /All/ }).click();
await rev.fill('input[aria-label=Search]', 'TEAM');
await rev.waitForTimeout(1200);
await shot(rev, 's10-review-team');
const teamRows = await rev.locator('#row-0, #row-1, #row-2').allInnerTexts();
console.log('  team rows:\n   ' + teamRows.map((t) => t.replace(/\s+/g, ' ').slice(0, 150)).join('\n   '));
await rev.fill('input[aria-label=Search]', 'TEAM02');
await rev.waitForTimeout(1000);
await rev.locator('#row-0 a').click();
await rev.waitForURL('**/review/s/**');
await rev.getByText('Why this session is in the queue').waitFor();
await shot(rev, 's11-review-session', true);
const chip = rev.locator('button:has(svg) >> text=/\\d\\d:\\d\\d/').first();
if (await chip.count()) { await chip.click(); await rev.waitForTimeout(600); await shot(rev, 's12-review-moment'); }
await rev.locator('label:has-text("Confirm")').click();
await rev.getByRole('button', { name: 'Save decision' }).click();
await rev.getByText(/at least 10 characters/).waitFor();
await rev.fill('#note', 'Same rare wrong options as the partner on Q1, Q4, Q7, answered seconds apart.');
await rev.getByRole('button', { name: 'Save decision' }).click();
await rev.getByText('Decision saved').waitFor();
await rev.getByText('Team member 2').waitFor();
await shot(rev, 's13-review-confirmed');

// ---------------- flagged candidate reads the result and explains
const c2 = await phone('TEAM02');
await c2.goto(BASE + '/login');
await c2.fill('#roll_no', 'TEAM02'); await c2.fill('#code', codes.TEAM02);
await c2.getByRole('button', { name: /^Log in/ }).click();
await c2.waitForURL('**/exam');
await c2.getByRole('button', { name: /See result/ }).click();
await c2.getByText('What was noticed').waitFor();
await shot(c2, 'c20-result-confirmed', true);
await c2.getByRole('button', { name: 'हिं' }).click();
await shot(c2, 'c21-result-hi', true);
await c2.getByRole('button', { name: 'EN' }).click();
await c2.getByRole('button', { name: /Explain this/ }).click();
await c2.getByRole('button', { name: 'Send' }).click();
await c2.getByText('Please write at least a few words.').waitFor();
await c2.locator('label[for=m0]').click();
await c2.fill('#appeal', 'We study at the same coaching centre and practise the same question bank, so we made the same mistakes.');
await shot(c2, 'c22-appeal-sheet');
await c2.getByRole('button', { name: 'Send' }).click();
await c2.getByText('Waiting for the reviewer').waitFor();

await rev.goto(BASE + '/review/appeals');
await rev.getByText('coaching centre').waitFor();
await shot(rev, 's14-appeals');
await rev.getByRole('button', { name: /Uphold decision/ }).click();
await rev.fill('textarea', 'The same rare wrong answers at the same moments are very unlikely from shared practice alone.');
await rev.getByRole('button', { name: 'Send reply' }).click();
await rev.getByText('Reply sent to the candidate').waitFor();
await c2.reload();
await c2.getByText('very unlikely').waitFor();
await shot(c2, 'c23-result-replied', true);

// ---------------- TEAM01 (took the test in the browser)
const c1 = await phone('TEAM01');
await c1.goto(BASE + '/login');
await c1.fill('#roll_no', 'TEAM01'); await c1.fill('#code', codes.TEAM01);
await c1.getByRole('button', { name: /^Log in/ }).click();
await c1.waitForURL('**/exam');
await c1.goto(BASE + '/exam/result');
await c1.getByText(/test data is deleted after/).waitFor();   // retention note; no delete button on the candidate page
if (await c1.getByRole('button', { name: /Delete my data/ }).count()) throw new Error('delete button should be gone');
await c1.getByText('Photos taken during your test').waitFor();      // the candidate sees their own snapshots
await shot(c1, 'c24-team01-result', true);
step('candidate sees the photos taken at flagged moments');
await rev.goto(BASE + '/review');
await rev.locator('#row-0').waitFor();
await rev.getByRole('tab', { name: /All/ }).click();
await rev.fill('input[aria-label=Search]', 'TEAM01');
await rev.waitForTimeout(1000);
await rev.locator('#row-0 a').click();
await rev.getByText('Camera snapshots at flagged moments').waitFor();
await rev.getByText('Camera snapshots at flagged moments').scrollIntoViewIfNeeded();
await shot(rev, 's11b-review-snapshots');
step('reviewer sees the snapshots next to the evidence');

// ---------------- staff screens on a phone, and dark mode
const rp = await phone('reviewer-phone');
await staffLogin(rp, 'reviewer@fairproctor.demo', 'Review@2026');
await rp.waitForURL('**/review');
await rp.locator('#row-0').waitFor();
await shot(rp, 'm01-queue-phone');
await rp.locator('#row-0 a').click();
await rp.getByText('Why this session is in the queue').waitFor();
await shot(rp, 'm02-session-phone');
await rev.getByRole('button', { name: 'Dark mode' }).click();
await rev.goto(BASE + '/review');
await rev.locator('#row-0').waitFor();
await shot(rev, 's15-queue-dark');
await rev.locator('#row-0 a').click();
await rev.getByText('Why this session is in the queue').waitFor();
await shot(rev, 's16-session-dark');

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

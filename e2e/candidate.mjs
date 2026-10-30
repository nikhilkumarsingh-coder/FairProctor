// Candidate flow in a phone-sized browser against the real backend.
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] });
const problems = [];
// expected: the deliberate wrong join code (404) and requests made while the phone is set offline
// ERR_TUNNEL_CONNECTION_FAILED: a test machine without internet cannot fetch the phone detector from the CDN (it then
// simply does not run: no evidence either way)
const expected = [/404 POST \/api\/exam\/join/, /ERR_INTERNET_DISCONNECTED/, /status of 404/, /ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED/];
const note = (s) => { if (!expected.some((x) => x.test(s))) problems.push(s); };
async function phone(name) {
  const ctx = await browser.newContext({ ...devices['Pixel 7'], permissions: ['camera'] });
  // Linux Chromium has no FaceDetector: a stand-in returns one centred face (head down now and then),
  // so the camera-numbers path (frames upload, gaze) is exercised end to end.
  await ctx.addInitScript(() => {
    let n = 0;
    window.FaceDetector = class {
      async detect() {
        n++;
        const down = Math.floor(Date.now() / 5000) % 3 === 0;
        return [{ boundingBox: { x: 220, y: 110, width: 200, height: 250 },
          landmarks: [{ type: 'eye', locations: [{ x: 280, y: 200 }] }, { type: 'eye', locations: [{ x: 360, y: 200 }] },
                      { type: 'nose', locations: [{ x: 320, y: down ? 275 : 240 }] }] }];
      }
    };
  });
  const page = await ctx.newPage();
  page.on('console', (m) => m.type() === 'error' && note(`[${name}] console: ${m.text()}`));
  page.on('pageerror', (e) => note(`[${name}] pageerror: ${e.message}`));
  page.on('response', (r) => r.status() >= 400 && note(`[${name}] ${r.status()} ${r.request().method()} ${r.url().replace(BASE, '')}`));
  return { ctx, page };
}
const shot = async (page, n) => { await page.waitForTimeout(450); await page.screenshot({ path: SHOTS + n + '.png', fullPage: false }); };
const step = (s) => console.log('·', s);

// --- TEAM01: login with roll no + code, consent, pre-check, exam, submit
{
  const { page } = await phone('TEAM01');
  await page.goto(BASE + '/');
  await page.waitForURL('**/login');
  await shot(page, 'c01-login');
  step('validation: empty submit');
  await page.getByRole('button', { name: /^Log in/ }).click();
  await page.getByText('Please fill this in.').first().waitFor();
  await shot(page, 'c02-login-validation');
  await page.fill('#roll_no', 'team01');
  await page.fill('#code', codes.TEAM01.toLowerCase());
  await page.getByRole('button', { name: /^Log in/ }).click();
  await page.waitForURL('**/exam');
  await page.getByText('Campus Hiring Assessment').first().waitFor();
  await shot(page, 'c03-home');
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.waitForURL('**/exam/consent');
  await page.getByText('What is never recorded').waitFor();
  await shot(page, 'c04-consent');
  step('Hindi toggle');
  await page.getByRole('button', { name: 'हिं' }).click();
  await page.getByText('क्या कभी रिकॉर्ड नहीं होता').waitFor().catch(() => {});
  await shot(page, 'c05-consent-hi');
  await page.getByRole('button', { name: 'EN' }).click();
  await page.locator('label[for=understood]').click();
  await page.getByRole('button', { name: /Continue/ }).click();
  await page.waitForURL('**/exam/precheck');
  await page.getByText(/Mbps|kbps/).waitFor({ timeout: 25000 });
  await page.getByRole('button', { name: /Allow camera/ }).click();
  await page.getByText('Sharpness').waitFor();
  await page.waitForTimeout(2000);
  await shot(page, 'c06-precheck');
  await page.getByRole('button', { name: /Start test/ }).click();
  await page.waitForURL('**/exam/run');
  await page.getByText('Question 1').waitFor();
  // the camera stops mid-test (permission taken back, another app): the questions are covered until it is back on
  await page.waitForTimeout(2500);
  await page.evaluate(() => document.querySelector('video')?.srcObject?.getVideoTracks().forEach((tr) => tr.dispatchEvent(new Event('ended'))));
  await page.getByText('Turn the camera back on').waitFor();
  await shot(page, 'c07b-camera-lock');
  await page.getByRole('button', { name: /Try again/ }).click();
  await page.getByText('Turn the camera back on').waitFor({ state: 'detached' });
  console.log('· camera stops mid-test → questions locked until it is back on');
  // calculator in the top bar: one icon, a small drop-down calculator
  await page.getByRole('button', { name: 'Calculator' }).click();
  const calc = page.getByRole('dialog', { name: 'Calculator' });
  for (const k of ['1', '2', 'plus', '7']) await calc.getByRole('button', { name: k, exact: true }).click();
  await calc.getByRole('button', { name: 'equals' }).click();
  await calc.getByText('12+7 =').waitFor();
  if (!(await calc.innerText()).includes('19')) throw new Error('calculator: 12+7 should be 19');
  await page.keyboard.type('(2+3)*4');
  await calc.getByText('= 20').waitFor();
  await page.keyboard.press('Enter');
  await shot(page, 'c07c-calculator');
  await page.keyboard.press('Escape');
  await calc.waitFor({ state: 'detached' });
  console.log('· calculator: opens from the top bar, sums by tap and keyboard, Esc closes');
  await page.waitForTimeout(24000);   // camera frames + a 20 s pause with no input
  await shot(page, 'c07-exam-q1');
  step('answer all questions');
  for (let i = 0; i < 30; i++) {
    await page.getByText(`Question ${i + 1}`, { exact: true }).waitFor();
    const short = await page.locator('#short').count();
    if (short) {
      await page.fill('#short', '42');
      await page.getByRole('button', { name: 'Save answer' }).click();
      await page.getByText('Answer saved').waitFor();
      if (i === 25) {
        await page.locator('#short').evaluate((el) => { const d = new DataTransfer(); d.setData('text/plain', 'x'.repeat(57)); el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: d, bubbles: true })); });
        await shot(page, 'c09-exam-short');
      }
    } else {
      const opts = page.getByRole('radio');
      await opts.nth(i % 4).click();
      if (i === 2) { await page.getByRole('button', { name: /Mark for review/ }).click(); await shot(page, 'c08-exam-answered'); }
    }
    if (i < 29) await page.getByRole('button', { name: /^Next/ }).click();
  }
  step('focus loss + offline queue');
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { value: true, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.waitForTimeout(3000);
  await page.evaluate(() => { Object.defineProperty(document, 'hidden', { value: false, configurable: true }); document.dispatchEvent(new Event('visibilitychange')); });
  await page.getByText('You left the test screen').waitFor();            // the live notice
  await shot(page, 'c10b-left-screen-notice');
  await page.getByRole('button', { name: 'Continue the test' }).click();
  await page.context().setOffline(true);
  await page.getByRole('button', { name: /All questions/ }).click();
  await page.waitForTimeout(300);
  await shot(page, 'c10-exam-grid');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(11000);
  await page.getByText('Offline — saved on your phone').waitFor({ timeout: 15000 });
  await shot(page, 'c11-exam-offline');
  await page.context().setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await page.getByText('Saved', { exact: true }).waitFor({ timeout: 20000 });
  await page.getByRole('button', { name: /Review & submit/ }).click();
  await page.getByText('Submit your test?').waitFor();
  await shot(page, 'c12-submit-dialog');
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await page.waitForURL('**/exam/done', { timeout: 30000 });
  await shot(page, 'c13-done');
  await page.getByRole('button', { name: /See result/ }).click();
  await page.waitForURL('**/exam/result');
  await page.getByText('Results will appear here').waitFor();
  await shot(page, 'c14-result-pending');
}

// --- No self sign-up: the test centre adds candidates; staff have their own login page
{
  const { page } = await phone('visitor');
  await page.goto(BASE + '/login');
  await page.getByText('No roll no. or code? Ask your test centre').waitFor();
  if (await page.getByText(/Create an account/).count()) throw new Error('the sign-up link must be gone');
  if (await page.locator('#email').count()) throw new Error('the candidate login has no email login');
  await page.goto(BASE + '/signup');
  await page.getByText('Page not found').waitFor();
  step('no sign-up: candidate login is roll no. + code only');
  await page.goto(BASE + '/login');
  step('dark mode');
  await page.getByRole('button', { name: 'Dark mode' }).click();
  await shot(page, 'c17-login-dark');
}
await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no unexpected console errors or failed requests');

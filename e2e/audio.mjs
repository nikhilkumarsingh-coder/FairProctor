// Microphone "speech-like sound" check (run on a freshly seeded database, backend running). The phone's microphone
// plays a recording of someone reading aloud (MUSAN, via SPEECH_WAV; or a synthetic voice when not given):
// the candidate allows the mic in the pre-check and sees the level, the test shows a "Mic on" badge, the live
// monitor shows "speech-like sound … not counted alone", and after scoring the reviewer sees a Sound lane on the
// timeline and the sound listed under "Not counted against this candidate".
//
//   SPEECH_WAV=/path/to/musan/speech/librivox/speech-librivox-0000.wav node audio.mjs
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, devices } from 'playwright';
const BASE = process.env.BASE_URL || 'http://127.0.0.1:8000';
const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url)); fs.mkdirSync(SHOTS, { recursive: true });
const codes = Object.fromEntries([...fs.readFileSync(new URL('../backend/data/demo_logins.txt', import.meta.url), 'utf8').matchAll(/(TEAM0\d)\s+(\w{6})/g)].map((m) => [m[1], m[2]]));
const step = (s) => console.log('·', s);
const shot = async (p, n) => { await p.waitForTimeout(400); await p.screenshot({ path: SHOTS + n + '.png' }); };

/** 16 kHz 16-bit mono WAV of a crude voice (4 syllables a second, gliding pitch), when no recording is given. */
function syntheticVoice(file, seconds = 30) {
  const SR = 16000, n = SR * seconds, buf = Buffer.alloc(44 + 2 * n);
  buf.write('RIFF', 0); buf.writeUInt32LE(36 + 2 * n, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(2 * SR, 28);
  buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(2 * n, 40);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR, syl = (t * 4) % 1, env = syl < 0.45 ? Math.sin((Math.PI * syl) / 0.45) : 0;
    ph += (2 * Math.PI * (150 + 50 * Math.sin(2 * Math.PI * 0.7 * t) + 70 * syl)) / SR;
    const v = env * 0.3 * (Math.sin(ph) + 0.5 * Math.sin(2 * ph) + 0.25 * Math.sin(3 * ph));
    buf.writeInt16LE(Math.max(-32767, Math.min(32767, Math.round(v * 32767))), 44 + 2 * i);
  }
  fs.writeFileSync(file, buf);
  return file;
}
const wav = process.env.SPEECH_WAV || syntheticVoice(path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'fp-voice-')), 'voice.wav'));

const browser = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`] });
const problems = [];
const expected = [/ERR_TUNNEL_CONNECTION_FAILED|ERR_NAME_NOT_RESOLVED/];
const watch = (p, name) => {
  p.on('pageerror', (e) => problems.push(`[${name}] ${e.message}`));
  p.on('console', (m) => m.type() === 'error' && !expected.some((x) => x.test(m.text())) && problems.push(`[${name}] console: ${m.text()}`));
  p.on('response', (r) => r.status() >= 400 && problems.push(`[${name}] ${r.status()} ${r.url().replace(BASE, '')}`));
};

const ctx = await browser.newContext({ ...devices['Pixel 7'], permissions: ['camera', 'microphone'] });
await ctx.addInitScript(() => {
  window.FaceDetector = class { async detect() { return [{ boundingBox: { x: 220, y: 110, width: 200, height: 250 }, landmarks: [] }]; } };
});
const c = await ctx.newPage(); watch(c, 'TEAM01');
await c.goto(BASE + '/login');
await c.fill('#roll_no', 'TEAM01'); await c.fill('#code', codes.TEAM01);
await c.getByRole('button', { name: /^Log in/ }).click();
await c.waitForURL('**/exam');
await c.getByRole('button', { name: /Continue/ }).click();
await c.getByText('Microphone, if you allow it').waitFor();
await c.getByText('No sound recording').waitFor();
await c.locator('label[for=understood]').click();
await c.getByRole('button', { name: /Continue/ }).click();
step('consent: the microphone check is explained (what is kept, and that no sound is recorded)');
await c.getByText(/Mbps|kbps|Could not test/).waitFor({ timeout: 25000 });
await c.getByRole('button', { name: /Allow camera/ }).click();
await c.getByText('Sharpness').waitFor();
await c.getByText('Microphone (optional)').waitFor();
await c.getByRole('button', { name: /Allow microphone/ }).click();
await c.getByText('Microphone working').waitFor();
await c.waitForFunction(() => { const b = document.querySelector('[aria-label="Sound level"] > div'); return b && parseFloat(b.style.width) > 0; }, null, { timeout: 10000 });
await c.getByText('Microphone working').scrollIntoViewIfNeeded();
await shot(c, 'a01-precheck-mic');
step('pre-check: microphone allowed separately from the camera, level meter moves');
await c.getByRole('button', { name: /Start test/ }).click();
await c.getByText('Question 1').waitFor();
await c.getByLabel('Mic on').first().waitFor({ timeout: 10000 });
await shot(c, 'a02-exam-mic-badge');
step('test: "Mic on" badge on the camera bubble');

const adm = await (await browser.newContext({ viewport: { width: 1440, height: 1000 } })).newPage(); watch(adm, 'admin');
await adm.goto(BASE + '/staff/login');
await adm.fill('#email', 'admin@fairproctor.demo'); await adm.fill('#password', 'Admin@2026');
await adm.getByRole('button', { name: /^Log in/ }).click();
await adm.waitForURL('**/admin');
await adm.goto(BASE + '/review/live');
await adm.getByText('Demo sitting').first().click();
await adm.getByText(/Speech-like sound \d+× · not counted alone/).first().waitFor({ timeout: 60000 });
await adm.getByText(/Speech-like sound \d+×/).first().scrollIntoViewIfNeeded();
await shot(adm, 'a03-live-speech-chip');
step('live monitor: "Speech-like sound N× · not counted alone" (neutral, not an alert)');

for (let i = 0; i < 30; i++) {
  await c.getByText(`Question ${i + 1}`, { exact: true }).waitFor();
  if (await c.locator('#short').count()) {
    await c.fill('#short', '42');
    await c.getByRole('button', { name: 'Save answer' }).click();
    await c.getByText('Answer saved').waitFor();
  } else {
    await c.getByRole('radio').nth(i % 4).click();
  }
  if (i < 29) await c.getByRole('button', { name: /^Next/ }).click();
}
await c.getByRole('button', { name: /Review & submit/ }).click();
await c.getByRole('button', { name: 'Submit', exact: true }).click();
await c.waitForURL('**/exam/done', { timeout: 30000 });
step('candidate answers and submits');

const sits = await adm.evaluate(async () => (await fetch('/api/admin/sittings', { headers: { Authorization: 'Bearer ' + (localStorage.getItem('fp-staff-token') || '').replace(/"/g, '') } })).json());
const demo = sits.find((s) => s.title === 'Demo sitting');
await adm.goto(BASE + `/admin/sittings/${demo.id}`);
await adm.getByRole('button', { name: /Close & score/ }).click();
await adm.getByRole('dialog').getByRole('button', { name: /Close & score/ }).click();
await adm.getByText('Result of scoring').waitFor({ timeout: 120000 });
await adm.goto(BASE + '/review');
await adm.getByRole('tab', { name: /All/ }).click();
await adm.fill('input[aria-label=Search]', 'TEAM01');
await adm.waitForTimeout(1000);
await adm.locator('#row-0 a').click();
await adm.getByText(/^Sound \(\d+\)$/).waitFor();
await adm.getByText(/Speech-like sound was picked up \d+ times?/).waitFor();
await adm.getByText(/^Sound \(\d+\)$/).scrollIntoViewIfNeeded();
await shot(adm, 'a04-reviewer-sound-lane');
step('reviewer: Sound lane on the timeline, and the sound under "Not counted against this candidate"');

await browser.close();
console.log(problems.length ? 'PROBLEMS:\n' + problems.join('\n') : 'no page errors or unexpected failed requests');

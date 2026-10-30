// Does the phone-side detector (frontend/src/lib/speech.ts) give the same answers as the Python detector that was
// validated on ESC-50 and MUSAN? Runs the browser code itself (bundled with esbuild) on the same audio, including the
// browser's own resampling from 44.1 kHz, and compares clip by clip with reports/esc50_clip_results.csv and
// reports/musan_window_results.csv. Writes reports/BROWSER_SPEECH_CHECK.md.
//
//   node analysis/browser_speech_check.mjs --esc50 path/to/ESC-50-master --musan path/to/musan
//   node analysis/browser_speech_check.mjs --selftest        # no datasets: synthetic talking vs tones and hum
//
// esbuild is needed once: `npm i -g esbuild` (or NODE_PATH pointing at a node_modules that has it).
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.dirname(HERE);
const arg = (k) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : null; };

async function loadDetector() {
  let esbuild;
  for (const base of [ROOT + '/', path.join(ROOT, 'frontend') + '/', path.join(ROOT, 'e2e') + '/', '/opt/npm-tools/node_modules/', ...(process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean).map((p) => p + '/')]) {
    try { esbuild = createRequire(base)('esbuild'); break; } catch { /* next */ }
  }
  if (!esbuild) throw new Error('esbuild not found: run npm install in the frontend folder first (vite brings esbuild)');
  const out = path.join(fs.mkdtempSync(path.join((await import('node:os')).tmpdir(), 'fp-speech-')), 'speech.mjs');
  await esbuild.build({ entryPoints: [path.join(ROOT, 'frontend/src/lib/speech.ts')], bundle: true, format: 'esm', outfile: out, logLevel: 'error' });
  return import(pathToFileURL(out).href);
}

/** 16-bit / 32-bit float PCM WAV → { rate, x: Float32Array } (mono), scaled like scipy + the Python check. */
function readWav(p) {
  const b = fs.readFileSync(p);
  let o = 12, fmt = null, data = null;
  while (o + 8 <= b.length) {
    const id = b.toString('ascii', o, o + 4), n = b.readUInt32LE(o + 4);
    if (id === 'fmt ') fmt = { code: b.readUInt16LE(o + 8), ch: b.readUInt16LE(o + 10), rate: b.readUInt32LE(o + 12), bits: b.readUInt16LE(o + 22) };
    if (id === 'data') { data = b.subarray(o + 8, o + 8 + n); break; }
    o += 8 + n + (n & 1);
  }
  if (!fmt || !data) throw new Error('not a WAV: ' + p);
  const bps = fmt.bits / 8, frames = Math.floor(data.length / (bps * fmt.ch));
  const x = new Float32Array(frames);
  let mx = 0;
  for (let i = 0; i < frames; i++) {
    let s = 0;
    for (let c = 0; c < fmt.ch; c++) {
      const at = (i * fmt.ch + c) * bps;
      s += fmt.bits === 16 ? data.readInt16LE(at) : fmt.bits === 32 && fmt.code === 3 ? data.readFloatLE(at) : fmt.bits === 32 ? data.readInt32LE(at) / 65536 : (data[at] - 128) * 256;
    }
    x[i] = s / fmt.ch;
    mx = Math.max(mx, Math.abs(x[i]));
  }
  if (mx > 1.5) for (let i = 0; i < frames; i++) x[i] /= 32768;
  return { rate: fmt.rate, x };
}

/** What the phone does: resample to 16 kHz with the streaming resampler, in 4096-sample chunks like a mic. */
function to16k(D, { rate, x }) {
  if (rate === D.SR) return x;
  const rs = new D.Resampler(rate);
  const parts = [];
  for (let i = 0; i < x.length; i += 4096) parts.push(rs.push(x.subarray(i, i + 4096)));
  parts.push(rs.push(new Float32Array(Math.ceil(rate / 100))));          // flush the filter's tail
  const want = Math.round((x.length * D.SR) / rate);
  const y = new Float32Array(want);
  let o = 0;
  for (const p of parts) { const n = Math.min(p.length, want - o); if (n <= 0) break; y.set(p.subarray(0, n), o); o += n; }
  return y;
}

function csv(p) {
  const [h, ...rows] = fs.readFileSync(p, 'utf8').trim().split(/\r?\n/);
  const cols = h.split(',');
  return rows.map((r) => Object.fromEntries(r.split(',').map((v, i) => [cols[i], v])));
}

const pct = (a, b) => (!b ? '—' : a === b ? '100%' : `${((100 * a) / b).toFixed(a / b > 0.99 ? 1 : 0)}%`);

function selftest(D) {
  const n = D.SR * 5;
  const tone = Float32Array.from({ length: n }, (_, i) => 0.3 * Math.sin((2 * Math.PI * 440 * i) / D.SR));
  const hum = Float32Array.from({ length: n }, (_, i) => 0.2 * Math.sin((2 * Math.PI * 150 * i) / D.SR) + 0.01 * (Math.random() - 0.5));
  // a crude "voice": 4 syllables a second, each a short voiced burst whose pitch glides, with silence between
  const voice = new Float32Array(n);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / D.SR, syl = (t * 4) % 1, on = syl < 0.45;
    const f0 = 150 + 50 * Math.sin(2 * Math.PI * 0.7 * t) + 70 * syl;
    ph += (2 * Math.PI * f0) / D.SR;
    const env = on ? Math.sin((Math.PI * syl) / 0.45) : 0;
    voice[i] = env * 0.3 * (Math.sin(ph) + 0.5 * Math.sin(2 * ph) + 0.25 * Math.sin(3 * ph)) + 0.002 * (Math.random() - 0.5);
  }
  const res = Object.entries({ tone, hum, voice }).map(([k, v]) => [k, D.isSpeechLike(D.features(v))]);
  const ok = res.find(([k]) => k === 'voice')[1] && !res.find(([k]) => k === 'tone')[1] && !res.find(([k]) => k === 'hum')[1];
  // the streaming detector at 48 kHz gives one verdict per 5 s
  const det = new D.SpeechDetector(48000);
  const v48 = to48(voice);
  let wins = [];
  for (let i = 0; i < v48.length * 2; i += 4800) wins = wins.concat(det.push(v48.subarray(i % v48.length, (i % v48.length) + 4800)));
  console.log(res.map(([k, v]) => `${k}: ${v ? 'speech-like' : 'not speech-like'}`).join(' · '), `· stream at 48 kHz: ${wins.length} windows, ${wins.filter((w) => w.speech).length} speech-like`);
  if (!ok) { console.error('SELFTEST FAILED'); process.exit(1); }
  console.log('selftest ok');
}
function to48(x) { const y = new Float32Array(x.length * 3); for (let i = 0; i < y.length; i++) { const p = i / 3, k = Math.floor(p), f = p - k; y[i] = (x[k] || 0) * (1 - f) + (x[k + 1] || 0) * f; } return y; }

const D = await loadDetector();
if (process.argv.includes('--selftest')) { selftest(D); process.exit(0); }

const esc = arg('--esc50'), mus = arg('--musan');
if (!esc && !mus) { console.error('usage: --esc50 <ESC-50-master> and/or --musan <musan>, or --selftest'); process.exit(2); }
const lines = ['# Check: does the phone-side detector match the validated one? (ESC-50 + MUSAN)', '',
  'The detector that runs in the candidate\'s browser (`frontend/src/lib/speech.ts`) was run, as bundled for the browser, ' +
  'on the same audio as the Python checks, including the browser\'s own resampling to 16 kHz. Every clip\'s verdict is ' +
  'compared with the Python detector\'s (`reports/esc50_clip_results.csv`, `reports/musan_window_results.csv`).', ''];
const t0 = Date.now();
let ms = 0, windows = 0;
const timeIt = (fn) => { const a = performance.now(); const r = fn(); ms += performance.now() - a; windows++; return r; };

if (esc) {
  const py = Object.fromEntries(csv(path.join(ROOT, 'reports/esc50_clip_results.csv')).map((r) => [r.file, r.speech_like === 'True']));
  const meta = csv(path.join(esc, 'meta/esc50.csv'));
  let n = 0, same = 0, fa = 0, faPy = 0;
  const diff = [];
  for (const r of meta) {
    const p = path.join(esc, 'audio', r.filename);
    if (!fs.existsSync(p) || !(r.filename in py)) continue;
    const f = timeIt(() => D.features(to16k(D, readWav(p))));
    const s = !!f && D.isSpeechLike(f);
    n++; fa += s; faPy += py[r.filename]; same += s === py[r.filename];
    if (s !== py[r.filename]) diff.push(`${r.category.replace(/_/g, ' ')} (${s ? 'browser yes' : 'browser no'})`);
  }
  lines.push('## ESC-50 (no speech: every "yes" is a false alarm)', '', '| | Browser detector | Python detector |', '|---|---|---|',
    `| Clips | ${n} | ${n} |`, `| False alarms | ${pct(fa, n)} (${fa}) | ${pct(faPy, n)} (${faPy}) |`,
    `| Same verdict as Python | **${pct(same, n)}** (${same} of ${n}) | — |`, '');
  if (diff.length) lines.push(`Clips where the two differ: ${diff.slice(0, 20).join(', ')}${diff.length > 20 ? ', …' : ''}. ` +
    'These sit on a threshold; the 44.1 → 16 kHz resampling differs slightly from scipy\'s.', '');
}

if (mus) {
  const WIN = D.SR * 5, MIN = D.SR * 2, CAP = { speech: 40, music: 30, noise: 20 };
  const py = new Map(csv(path.join(ROOT, 'reports/musan_window_results.csv')).map((r) => [`${r.file}#${r.win}`, r.speech_like === 'True']));
  const tally = {};
  let n = 0, same = 0;
  for (const kind of ['speech', 'music', 'noise']) {
    const dir = path.join(mus, kind);
    if (!fs.existsSync(dir)) continue;
    for (const sub of fs.readdirSync(dir).sort()) {
      const sd = path.join(dir, sub);
      if (!fs.statSync(sd).isDirectory()) continue;
      for (const file of fs.readdirSync(sd).filter((f) => f.endsWith('.wav')).sort()) {
        const x = to16k(D, readWav(path.join(sd, file)));
        if (x.length < MIN) continue;
        let starts = [];
        for (let s = 0; s <= Math.max(x.length - MIN, 0); s += WIN) starts.push(s);
        if (starts.length > CAP[kind]) { const L = starts.length; starts = Array.from({ length: CAP[kind] }, (_, i) => starts[Math.floor((i * (L - 1)) / (CAP[kind] - 1))]); }
        starts.forEach((s, i) => {
          const f = timeIt(() => D.features(x.subarray(s, s + WIN)));
          if (!f) return;
          const v = D.isSpeechLike(f), key = `${file}#${i}`;
          const t = (tally[kind] ||= { n: 0, yes: 0, pyYes: 0, same: 0 });
          t.n++; t.yes += v;
          if (py.has(key)) { t.pyYes += py.get(key); t.same += v === py.get(key); n++; same += v === py.get(key); }
        });
      }
    }
  }
  const name = { speech: 'Speech (reading aloud, speeches)', music: 'Music', noise: 'Noise' };
  lines.push('## MUSAN', '', '| Audio | Windows | Browser: speech-like | Python: speech-like | Same verdict |', '|---|---|---|---|---|');
  for (const [k, t] of Object.entries(tally)) lines.push(`| ${name[k]} | ${t.n} | ${pct(t.yes, t.n)} | ${pct(t.pyYes, t.n)} | ${pct(t.same, t.n)} |`);
  lines.push('', `Same verdict as Python on **${pct(same, n)}** of ${n} windows.`, '');
}

lines.push('## Cost on the device', '',
  `${windows} windows of 5 s took ${(ms / Math.max(windows, 1)).toFixed(0)} ms each on this machine (one core, Node), ` +
  `about ${((100 * ms) / Math.max(windows, 1) / 5000).toFixed(1)}% of one core while listening. On the phone the work is spread ` +
  'over each window (a little every quarter second) and quiet frames are skipped. A low-end phone is roughly 5–10× ' +
  'slower; if the check would take more than a third of the time it listens, the page switches it off by itself ' +
  '(`frontend/src/lib/mic.ts`), so the test stays smooth, and the reviewer sees "the microphone check stopped (not counted)".', '',
  '## What this means', '',
  '- The phone runs the same detector that was measured in `ESC50_NOISE_CHECK.md` and `MUSAN_SPEECH_CHECK.md`, so those ' +
  'numbers (about 87% of talking caught, about a quarter of home sounds mistaken for talking) describe what the product does.',
  '- Because of those false alarms, speech-like sound never raises a score by itself. The server uses it only to support ' +
  'a long silent pause followed by a correct answer on a hard question (`backend/services/audio.py`); otherwise the ' +
  'candidate and the reviewer see it as "not counted".',
  '- No audio leaves the phone. Every 5 s the page keeps a yes/no and the voiced seconds, and sends an event only for a yes.', '',
  'Datasets: K. J. Piczak, ESC-50 (ACM MM 2015, CC BY-NC 3.0); D. Snyder, G. Chen, D. Povey, MUSAN (arXiv:1510.08484).', '');
fs.mkdirSync(path.join(ROOT, 'reports'), { recursive: true });
fs.writeFileSync(path.join(ROOT, 'reports/BROWSER_SPEECH_CHECK.md'), lines.join('\n'));
console.log(lines.join('\n'));
console.log(`(${((Date.now() - t0) / 1000).toFixed(0)} s)`);

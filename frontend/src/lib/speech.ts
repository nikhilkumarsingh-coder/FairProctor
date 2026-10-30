/** "Speech-like sound" check that runs on the phone. No audio is stored or sent: every 5 s the page keeps only a
 *  yes/no and a few seconds-counts, and sends an event only when the answer is yes.
 *
 *  This is a line-by-line port of the detector validated on ESC-50 and MUSAN (analysis/esc50_noise_check.py,
 *  reports/ESC50_NOISE_CHECK.md, MUSAN_SPEECH_CHECK.md, BROWSER_SPEECH_CHECK.md). A 5-second window is speech-like only
 *  when all five hold: loud enough above the room's own background, voiced in the human pitch range (80–400 Hz),
 *  a syllable-like 2–8 Hz rhythm, moving pitch (not a fixed tone like an alarm), and short voiced bursts.
 *  It mistakes about a quarter of home sounds (rooster, dog, laughing) and any TV for talking, so it is never
 *  evidence on its own: the server only uses it to support another signal (services/audio.py). */

export const SR = 16000;
export const WINDOW_S = 5;
const FRAME = 512;
const HOP = 256;
const LAG_LO = Math.floor(SR / 400);      // 40  (numpy: SR // F0_MAX)
const LAG_HI = Math.floor(SR / 80);       // 200 (exclusive)
const HANN = Float32Array.from({ length: FRAME }, (_, n) => 0.5 - 0.5 * Math.cos((2 * Math.PI * n) / (FRAME - 1)));

export type SpeechFeatures = {
  active_s: number; voiced_frac: number; syllable_rhythm: number; pitch_move: number; short_runs: number;
  n_runs: number; voiced_s: number;
};

function percentile(v: ArrayLike<number>, p: number): number {
  const s = Float64Array.from(v).sort();
  const i = ((s.length - 1) * p) / 100;
  const lo = Math.floor(i);
  const hi = Math.min(lo + 1, s.length - 1);
  return s[lo] + (s[hi] - s[lo]) * (i - lo);
}

function median(v: number[]): number {
  const s = [...v].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
}

const COS = Float64Array.from({ length: 512 }, (_, i) => Math.cos((2 * Math.PI * i) / 512));
const SIN = Float64Array.from({ length: 512 }, (_, i) => -Math.sin((2 * Math.PI * i) / 512));

/** Per-frame numbers: loudness and the strongest pitch lag. Computed as the audio arrives, so the phone does a little
 *  work every quarter second instead of all of it at the end of each window. */
class Frames {
  rms: Float64Array; db: Float64Array; lag: Int32Array; peak: Float64Array; n = 0;
  private fr = new Float64Array(FRAME);
  constructor(max: number) { this.rms = new Float64Array(max); this.db = new Float64Array(max); this.lag = new Int32Array(max); this.peak = new Float64Array(max); }
  add(x: Float32Array, o: number) {
    const fr = this.fr, i = this.n++;
    let e = 0;
    for (let k = 0; k < FRAME; k++) { const v = (x[o + k] || 0) * HANN[k]; fr[k] = v; e += v * v; }
    this.rms[i] = Math.sqrt(e / FRAME + 1e-12);
    this.db[i] = 20 * Math.log10(this.rms[i]);
    if (this.db[i] <= -50) { this.lag[i] = LAG_LO; this.peak[i] = 0; return; }   // too quiet to be active: pitch unused
    // normalised autocorrelation in the pitch range (same as numpy's zero-padded FFT version)
    let best = -Infinity, bestLag = LAG_LO;
    for (let L = LAG_LO; L < LAG_HI; L++) {
      let s = 0;
      for (let k = 0, m = FRAME - L; k < m; k++) s += fr[k] * fr[k + L];
      if (s > best) { best = s; bestLag = L; }
    }
    this.lag[i] = bestLag;
    this.peak[i] = best / (e + 1e-12);
  }
}

function finish(F: Frames): SpeechFeatures | null {
  const { n, rms, db, lag, peak } = F;
  if (n < 10) return null;
  const floor = percentile(db.subarray(0, n), 10);
  const active = new Uint8Array(n);
  const voiced = new Uint8Array(n);
  let nActive = 0, nVoiced = 0;
  for (let i = 0; i < n; i++) {
    active[i] = db[i] > floor + 10 && db[i] > -50 ? 1 : 0;
    voiced[i] = active[i] && peak[i] > 0.45 ? 1 : 0;
    nActive += active[i];
    nVoiced += voiced[i];
  }
  // syllable rhythm: share of the loudness envelope's modulation energy at 2–8 Hz
  const envSrc: number[] = [];
  for (let i = 0; i < n; i++) if (nActive > 8 ? active[i] : true) envSrc.push(rms[i]);
  const env = envSrc.slice(0, 512);                       // numpy rfft(env, 512) truncates / zero-pads to 512
  const mean = envSrc.reduce((a, b) => a + b, 0) / envSrc.length;
  for (let i = 0; i < env.length; i++) env[i] -= mean;
  const df = SR / HOP / 512;
  let band = 0, all = 0;
  for (let k = 1; k * df <= 30; k++) {
    const f = k * df;
    if (f <= 0.5) continue;
    let re = 0, im = 0;
    for (let t = 0; t < env.length; t++) { const j = (k * t) & 511; re += env[t] * COS[j]; im += env[t] * SIN[j]; }
    const p = re * re + im * im;
    all += p;
    if (f >= 2 && f <= 8) band += p;
  }
  const rhythm = band / (all + 1e-12);
  // voiced runs: their length and how much the pitch moves inside them
  const runs: [number, number][] = [];
  let st = -1;
  for (let i = 0; i <= n; i++) {
    if (i < n && voiced[i]) { if (st < 0) st = i; }
    else if (st >= 0) { runs.push([st, i]); st = -1; }
  }
  const movs: number[] = [];
  let short = 0;
  for (const [a, b] of runs) {
    if (((b - a) * HOP) / SR < 0.6) short++;
    if (b - a >= 4) {
      const lf: number[] = [];
      for (let i = a; i < b; i++) lf.push(Math.log(SR / lag[i]));
      const m = lf.reduce((s, v) => s + v, 0) / lf.length;
      movs.push(Math.sqrt(lf.reduce((s, v) => s + (v - m) ** 2, 0) / lf.length));
    }
  }
  return {
    active_s: (nActive * HOP) / SR, voiced_frac: nVoiced / Math.max(nActive, 1), syllable_rhythm: rhythm,
    pitch_move: movs.length ? median(movs) : 0, short_runs: runs.length ? short / runs.length : 0,
    n_runs: runs.length, voiced_s: (nVoiced * HOP) / SR,
  };
}

/** Features of one window of 16 kHz mono samples (null when shorter than ~0.17 s). */
export function features(x: Float32Array): SpeechFeatures | null {
  const n = 1 + Math.max(0, Math.floor((x.length - FRAME) / HOP));
  if (n < 10) return null;
  const F = new Frames(n);
  for (let i = 0; i < n; i++) F.add(x, i * HOP);
  return finish(F);
}

export function isSpeechLike(f: SpeechFeatures): boolean {
  return f.voiced_frac >= 0.3 && f.syllable_rhythm >= 0.3 && f.pitch_move >= 0.02 && f.pitch_move <= 0.35
    && f.short_runs >= 0.6 && f.n_runs >= 3;
}

/** Streaming windowed-sinc resampler to 16 kHz (phones record at 44.1 or 48 kHz). */
export class Resampler {
  private buf: Float32Array = new Float32Array(0);
  private pos = 0;                 // next output position, in input samples from buf[0]
  private readonly step: number;
  private readonly fc: number;     // cut-off in cycles per input sample
  private readonly W: number;      // kernel half-width in input samples
  constructor(private readonly inRate: number, private readonly outRate = SR) {
    this.step = inRate / outRate;
    this.fc = 0.5 * Math.min(1, outRate / inRate) * 0.92;
    this.W = Math.ceil(12 / (2 * this.fc));
  }
  push(x: Float32Array): Float32Array {
    if (this.inRate === this.outRate) return x;
    const b = new Float32Array(this.buf.length + x.length);
    b.set(this.buf); b.set(x, this.buf.length);
    this.buf = b;
    const out: number[] = [];
    const { W, fc } = this;
    while (this.pos + W < b.length) {
      const c = this.pos;
      const k0 = Math.max(0, Math.ceil(c - W)), k1 = Math.min(b.length - 1, Math.floor(c + W));
      let s = 0;
      for (let k = k0; k <= k1; k++) {
        const d = k - c;
        const w = 0.5 + 0.5 * Math.cos((Math.PI * d) / W);
        const a = 2 * fc * d;
        s += b[k] * 2 * fc * (a === 0 ? 1 : Math.sin(Math.PI * a) / (Math.PI * a)) * w;
      }
      out.push(s);
      this.pos += this.step;
    }
    const drop = Math.max(0, Math.floor(this.pos - W));
    if (drop) { this.buf = this.buf.slice(drop); this.pos -= drop; }
    return Float32Array.from(out);
  }
}

export type SpeechWindow = { speech: boolean; voiced_s: number; active_s: number; features: SpeechFeatures | null };

/** Feed raw microphone samples; every 5 s of audio returns one verdict. */
export class SpeechDetector {
  private rs: Resampler;
  private win = new Float32Array(SR * WINDOW_S);
  private fill = 0;
  private F = new Frames(1 + Math.floor((SR * WINDOW_S - FRAME) / HOP));
  /** Loudness of the last chunk, in dB (for the level meter), -100 when silent. */
  level = -100;
  constructor(inRate: number) { this.rs = new Resampler(inRate); }
  push(raw: Float32Array): SpeechWindow[] {
    let e = 0;
    for (let i = 0; i < raw.length; i++) e += raw[i] * raw[i];
    this.level = raw.length ? 10 * Math.log10(e / raw.length + 1e-10) : -100;
    const x = this.rs.push(raw);
    const out: SpeechWindow[] = [];
    let i = 0;
    while (i < x.length) {
      const take = Math.min(x.length - i, this.win.length - this.fill);
      this.win.set(x.subarray(i, i + take), this.fill);
      this.fill += take; i += take;
      while (this.F.n * HOP + FRAME <= this.fill) this.F.add(this.win, this.F.n * HOP);
      if (this.fill === this.win.length) {
        const f = finish(this.F);
        out.push({ speech: !!f && isSpeechLike(f), voiced_s: f?.voiced_s || 0, active_s: f?.active_s || 0, features: f });
        this.fill = 0;
        this.F.n = 0;
      }
    }
    return out;
  }
}

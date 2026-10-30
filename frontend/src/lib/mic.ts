// Microphone for the "speech-like sound" check (lib/speech.ts). Raw sound stays in this file: the detector turns every
// 5 s into a yes/no and two seconds-counts. Nothing is recorded, stored or sent.
import { SpeechDetector, type SpeechWindow } from "./speech";

let stream: MediaStream | null = null;

export function micStream() {
  return stream && stream.getAudioTracks().some((t) => t.readyState === "live") ? stream : null;
}

/** Ask for the microphone (a separate prompt from the camera, so saying no to it never blocks the camera). The
 *  phone's own noise suppression and gain are switched off: the detector was measured on unprocessed sound. */
export async function openMic(): Promise<MediaStream> {
  const live = micStream();
  if (live) return live;
  stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, channelCount: 1 },
    video: false,
  });
  return stream;
}

export function closeMic() {
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
}

export type MicStop = "ended" | "slow" | "error";

/** Run the detector on the open microphone. Returns a function that stops it. If this phone is too slow for the
 *  check (it would take more than a third of the time it listens), the check switches itself off: the test must
 *  stay smooth, and a missing check never counts against anyone. */
export function listen(opts: { onWindow?: (w: SpeechWindow) => void; onLevel?: (db: number) => void; onStop?: (why: MicStop) => void }): () => void {
  const s = micStream();
  if (!s) { opts.onStop?.("ended"); return () => {}; }
  const AC: typeof AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;
  let ctx: AudioContext;
  let src: MediaStreamAudioSourceNode;
  try {
    ctx = new AC({ sampleRate: 16000 });                 // the browser resamples well; we resample ourselves otherwise
    src = ctx.createMediaStreamSource(s);
  } catch {
    try { ctx = new AC(); src = ctx.createMediaStreamSource(s); }
    catch { opts.onStop?.("error"); return () => {}; }
  }
  const det = new SpeechDetector(ctx.sampleRate);
  const proc = ctx.createScriptProcessor(4096, 1, 1);
  const mute = ctx.createGain();
  mute.gain.value = 0;                                   // the processor must reach the speakers to run; silently
  let busy = 0, heard = 0, stopped = false;
  const stop = (why?: MicStop) => {
    if (stopped) return;
    stopped = true;
    proc.onaudioprocess = null;
    try { src.disconnect(); proc.disconnect(); mute.disconnect(); } catch { /* already gone */ }
    ctx.close().catch(() => {});
    document.removeEventListener("pointerdown", resume);
    document.removeEventListener("keydown", resume);
    s.getAudioTracks().forEach((t) => t.removeEventListener("ended", onEnded));
    if (why) opts.onStop?.(why);
  };
  proc.onaudioprocess = (e) => {
    const x = e.inputBuffer.getChannelData(0);
    const t0 = performance.now();
    const wins = det.push(new Float32Array(x));
    busy += performance.now() - t0;
    heard += (x.length / ctx.sampleRate) * 1000;
    opts.onLevel?.(det.level);
    wins.forEach((w) => opts.onWindow?.(w));
    if (heard > 15000) {                                 // judged over the last ~15 s of sound
      if (busy / heard > 0.33) { stop("slow"); return; }
      busy /= 2; heard /= 2;
    }
  };
  src.connect(proc); proc.connect(mute); mute.connect(ctx.destination);
  // a page opened fresh (a refresh during the test) may start with sound paused until the first tap
  const resume = () => { ctx.resume().catch(() => {}); };
  if (ctx.state === "suspended") { resume(); document.addEventListener("pointerdown", resume); document.addEventListener("keydown", resume); }
  const onEnded = () => stop("ended");
  s.getAudioTracks().forEach((t) => t.addEventListener("ended", onEnded));
  return () => stop();
}

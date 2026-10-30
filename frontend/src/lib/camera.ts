// Camera + face detector shared by the pre-check and the exam (one permission prompt, one stream).
// Only numbers leave this file: face count, light, sharpness, head direction. Never images.

export type Box = { x: number; y: number; w: number; h: number; kp?: { x: number; y: number }[] };
export type Mode = "native" | "mediapipe" | "manual";

let stream: MediaStream | null = null;
let detector: any = null;
let mode: Mode = "manual";
let detectorTried = false;

export function cameraStream() {
  return stream && stream.getVideoTracks().some((t) => t.readyState === "live") ? stream : null;
}

export async function openCamera(): Promise<MediaStream> {
  const live = cameraStream();
  if (live) return live;
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 480 } },
    audio: false,
  });
  return stream;
}

export function closeCamera() {
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
}

/** Native FaceDetector when the browser has it; else MediaPipe (only on a fast connection); else manual. */
export async function setupDetector(downKbps?: number): Promise<Mode> {
  if (detectorTried && (mode !== "manual" || !downKbps || downKbps <= 1500)) return mode;
  detectorTried = true;
  const W = window as any;
  if ("FaceDetector" in W) {
    try {
      detector = new W.FaceDetector({ fastMode: true, maxDetectedFaces: 3 });
      return (mode = "native");
    } catch { /* not usable */ }
  }
  if (downKbps && downKbps > 1500) {
    try {
      const base = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
      const vision = await import(/* @vite-ignore */ base);
      const files = await vision.FilesetResolver.forVisionTasks(base + "/wasm");
      detector = await vision.FaceDetector.createFromOptions(files, {
        baseOptions: { modelAssetPath: "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite" },
        runningMode: "VIDEO",
      });
      return (mode = "mediapipe");
    } catch (e) {
      console.warn("face detector unavailable", e);
    }
  }
  return (mode = "manual");
}

export const detectorMode = () => mode;

// ---------------------------------------------------------------- phone in view (supporting evidence only)
// MediaPipe EfficientDet-Lite0 (COCO "cell phone"), loaded only on a fast connection (~4.6 MB, served by our own
// server). Runs on this device about once a second on a small brightened copy of the frame; only "seen / not seen"
// leaves this file. Thresholds come from reports/PHONE_DETECTOR_CHECK.md (0.4 after brightening: ~0.3% false alarms).
let phoneDet: any = null;
let phoneTried = false;
const PHONE_SCORE = 0.4;

export async function setupPhoneDetector(downKbps?: number): Promise<boolean> {
  if (phoneDet) return true;
  if (phoneTried || !downKbps || downKbps <= 1500) return false;
  phoneTried = true;
  try {
    const base = "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@0.10.14";
    const vision = await import(/* @vite-ignore */ base);
    const files = await vision.FilesetResolver.forVisionTasks(base + "/wasm");
    phoneDet = await vision.ObjectDetector.createFromOptions(files, {
      baseOptions: { modelAssetPath: "/models/efficientdet_lite0.tflite" },
      runningMode: "IMAGE", scoreThreshold: 0.3, maxResults: 5, categoryAllowlist: ["cell phone"],
    });
    return true;
  } catch (e) {
    console.warn("phone detector unavailable", e);
    return false;
  }
}

let phoneCanvas: HTMLCanvasElement | null = null;

/** true / false = checked; null = could not check (no detector, no frame): never counts as evidence. */
export function detectPhone(v: HTMLVideoElement): boolean | null {
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!phoneDet || !vw || !vh) return null;
  const W = 320, H = Math.round((320 * vh) / vw);
  phoneCanvas ??= document.createElement("canvas");
  if (phoneCanvas.width !== W || phoneCanvas.height !== H) { phoneCanvas.width = W; phoneCanvas.height = H; }
  const ctx = phoneCanvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(v, 0, 0, W, H);
  brighten(ctx, W, H);
  try {
    const r = phoneDet.detect(phoneCanvas);
    return r.detections.some((d: any) => d.categories?.[0]?.score >= PHONE_SCORE);
  } catch {
    return null;
  }
}

/** Dark rooms hide phones from the detector: stretch the levels (1st–99th percentile) and lift the shadows. */
function brighten(ctx: CanvasRenderingContext2D, W: number, H: number) {
  const img = ctx.getImageData(0, 0, W, H), px = img.data;
  const hist = new Uint32Array(256);
  for (let i = 0; i < px.length; i += 4) hist[(px[i] * 77 + px[i + 1] * 150 + px[i + 2] * 29) >> 8]++;
  const n = W * H;
  let lo = 0, hi = 255, acc = 0;
  for (; lo < 255 && (acc += hist[lo]) < n * 0.01; lo++);
  acc = 0;
  for (; hi > 0 && (acc += hist[hi]) < n * 0.01; hi--);
  if (hi - lo < 8) return;
  let mean = 0;
  for (let k = 0; k < 256; k++) mean += k * hist[k];
  mean /= n;
  const gamma = mean < 60 ? 0.55 : mean < 100 ? 0.75 : 1;
  if (lo < 4 && hi > 250 && gamma === 1) return;           // already well exposed
  const lut = new Uint8ClampedArray(256);
  for (let k = 0; k < 256; k++) lut[k] = 255 * Math.pow(Math.min(1, Math.max(0, (k - lo) / (hi - lo))), gamma);
  for (let i = 0; i < px.length; i += 4) { px[i] = lut[px[i]]; px[i + 1] = lut[px[i + 1]]; px[i + 2] = lut[px[i + 2]]; }
  ctx.putImageData(img, 0, 0);
}

/** Faces as fractions of the frame, or null when no detector is available (= unknown, not "no face"). */
export async function detectFaces(v: HTMLVideoElement): Promise<Box[] | null> {
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh) return null;
  try {
    if (mode === "native") {
      const f = await detector.detect(v);
      return f.map((x: any) => ({
        x: x.boundingBox.x / vw, y: x.boundingBox.y / vh, w: x.boundingBox.width / vw, h: x.boundingBox.height / vh,
        kp: nativeKp(x.landmarks || [], vw, vh),
      }));
    }
    if (mode === "mediapipe") {
      const r = detector.detectForVideo(v, performance.now());
      return r.detections.map((d: any) => ({
        x: d.boundingBox.originX / vw, y: d.boundingBox.originY / vh, w: d.boundingBox.width / vw, h: d.boundingBox.height / vh,
        kp: (d.keypoints || []).map((p: any) => ({ x: p.x, y: p.y })),   // right eye, left eye, nose, mouth, ears
      }));
    }
  } catch { /* fall through */ }
  return null;
}

function nativeKp(lm: any[], vw: number, vh: number) {
  const pt = (l: any) => { const p = l.locations?.[0]; return p ? { x: p.x / vw, y: p.y / vh } : null; };
  const eyes = lm.filter((l) => l.type === "eye").map(pt).filter(Boolean).sort((a: any, b: any) => a.x - b.x);
  const nose = lm.filter((l) => l.type === "nose").map(pt)[0];
  return eyes.length === 2 && nose ? [eyes[0], eyes[1], nose] : undefined;
}

// Map the region the candidate SEES inside the oval (3:4 box, object-fit: cover) to the camera frame.
// Phones often deliver portrait frames, so a fixed box in a squashed frame measures hair and shirt instead of the face.
export function visibleToFrame(nx: number, ny: number, vw: number, vh: number): [number, number] {
  const br = 300 / 400, vr = vw / vh;
  let x0 = 0, y0 = 0, w = 1, h = 1;
  if (vr > br) { w = br / vr; x0 = (1 - w) / 2; } else { h = vr / br; y0 = (1 - h) / 2; }
  return [x0 + nx * w, y0 + ny * h];
}

export type Analysis = { face: number; faceHi: number; bg: number; sharp: number; f: Box | null; count: number | null };

let canvas: HTMLCanvasElement | null = null;

/** Light on the face (median + 90th percentile), light behind, sharpness (variance of the Laplacian) at 160×120. */
export function analyse(v: HTMLVideoElement, faces: Box[] | null): Analysis {
  const vw = v.videoWidth || 640, vh = v.videoHeight || 480;
  const W = vw >= vh ? 160 : 120, H = vw >= vh ? 120 : 160;
  canvas ??= document.createElement("canvas");
  if (canvas.width !== W) { canvas.width = W; canvas.height = H; }
  const ctx = canvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(v, 0, 0, W, H);
  const px = ctx.getImageData(0, 0, W, H).data;
  const L = new Float32Array(W * H);
  for (let i = 0; i < L.length; i++) L[i] = 0.299 * px[i * 4] + 0.587 * px[i * 4 + 1] + 0.114 * px[i * 4 + 2];
  const f = faces && faces.length ? faces.reduce((a, b) => (a.w * a.h > b.w * b.h ? a : b)) : null;
  let box;
  if (f) box = { x0: (f.x + f.w * 0.2) * W, x1: (f.x + f.w * 0.8) * W, y0: (f.y + f.h * 0.25) * H, y1: (f.y + f.h * 0.85) * H };
  else {
    const [ax, ay] = visibleToFrame(103 / 300, 85 / 400, vw, vh), [bx, by] = visibleToFrame(197 / 300, 215 / 400, vw, vh);
    box = { x0: ax * W, y0: ay * H, x1: bx * W, y1: by * H };
  }
  const [vx0, vy0] = visibleToFrame(0, 0, vw, vh), [vx1, vy1] = visibleToFrame(1, 1, vw, vh);
  const bgTop = vy0 + (vy1 - vy0) * 0.18, bgL = vx0 + (vx1 - vx0) * 0.15, bgR = vx1 - (vx1 - vx0) * 0.15;
  const facePx: number[] = [];
  let bs = 0, bn = 0;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
    const l = L[y * W + x], nx = x / W, ny = y / H;
    if (x >= box.x0 && x <= box.x1 && y >= box.y0 && y <= box.y1) facePx.push(l);
    else if (nx >= vx0 && nx <= vx1 && ny >= vy0 && ny <= vy1 && (ny < bgTop || nx < bgL || nx > bgR)) { bs += l; bn++; }
  }
  facePx.sort((a, b) => a - b);
  const q = (p: number) => (facePx.length ? facePx[Math.min(facePx.length - 1, Math.floor(p * facePx.length))] : 0);
  let s = 0, s2 = 0, n = 0;
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    const i = y * W + x, lap = 4 * L[i] - L[i - 1] - L[i + 1] - L[i - W] - L[i + W];
    s += lap; s2 += lap * lap; n++;
  }
  return { face: q(0.5), faceHi: q(0.9), bg: bs / Math.max(bn, 1), sharp: s2 / n - (s / n) ** 2, f, count: faces ? faces.length : null };
}

export type Tone = "ok" | "fix" | "bad";
export type Checks = { light: [Tone, string]; back: [Tone, string]; sharp: [Tone, string]; face: [Tone, string] };

/** The tested pre-check rules. "Too dark" needs a low median AND no well-lit skin, so darker skin in a fine room passes. */
export function rules(a: { face: number; faceHi: number; bg: number; sharp: number }, f: Box | null, count: number | null): Checks {
  const light: [Tone, string] = a.face < 45 || (a.face < 65 && a.faceHi < 95) ? ["bad", "lightDim"] : a.face > 215 ? ["fix", "lightHot"] : ["ok", "lightOk"];
  const back: [Tone, string] = a.bg - a.face > 45 && a.bg > 120 ? ["bad", "backBad"] : ["ok", "backOk"];
  const sharp: [Tone, string] = a.sharp < 35 ? ["fix", "sharpBad"] : ["ok", "sharpOk"];
  let face: [Tone, string];
  if (count === null) face = ["fix", "faceManual"];
  else if (!f) face = ["bad", "faceNone"];
  else {
    const cx = f.x + f.w / 2, cy = f.y + f.h / 2;
    face = f.w < 0.13 ? ["fix", "faceFar"] : Math.abs(cx - 0.5) > 0.16 || cy > 0.62 ? ["fix", "faceManual"] : ["ok", "faceOk"];
  }
  return { light, back, sharp, face };
}

/** Head direction from keypoints, against the candidate's own first frames (looking down at a phone is normal). */
export class GazeEstimator {
  private base: number[] = [];
  read(f: Box | null): string {
    if (!f) return "away";
    const k = f.kp;
    if (!k || k.length < 3) return "unknown";
    const [re, le, nose] = k;
    const ex = (re.x + le.x) / 2, ey = (re.y + le.y) / 2, d = Math.hypot(le.x - re.x, le.y - re.y) || 1e-3;
    const yaw = (nose.x - ex) / d, pitch = (nose.y - ey) / d;
    if (this.base.length < 3) { this.base.push(pitch); return "centre"; }
    const b = [...this.base].sort((x, y) => x - y)[1];
    if (yaw > 0.45) return "left";
    if (yaw < -0.45) return "right";
    if (pitch - b > 0.25) return "down";
    return "centre";
  }
}

let snapCanvas: HTMLCanvasElement | null = null;
/** A small JPEG of the current camera picture (about 240 px wide, under 40 KB), brightened so a dim room is readable.
 *  Taken only at flagged moments; null when there is no picture. */
export function snapshot(v: HTMLVideoElement): string | null {
  const vw = v.videoWidth, vh = v.videoHeight;
  if (!vw || !vh || v.readyState < 2) return null;
  const W = 240, H = Math.round((240 * vh) / vw);
  snapCanvas ??= document.createElement("canvas");
  if (snapCanvas.width !== W || snapCanvas.height !== H) { snapCanvas.width = W; snapCanvas.height = H; }
  const ctx = snapCanvas.getContext("2d", { willReadFrequently: true })!;
  ctx.drawImage(v, 0, 0, W, H);
  brighten(ctx, W, H);
  for (const q of [0.6, 0.45, 0.3]) {
    const url = snapCanvas.toDataURL("image/jpeg", q);
    if (url.startsWith("data:image/jpeg") && url.length * 0.75 < 38_000) return url;
  }
  return null;
}

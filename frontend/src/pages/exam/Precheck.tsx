import { useEffect, useRef, useState } from "react";
import { CandidateShell } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { analyse, detectFaces, openCamera, rules, setupDetector, type Box, type Checks, type Tone } from "@/lib/camera";
import { closeMic, listen, openMic } from "@/lib/mic";
import { enterKiosk } from "@/lib/kiosk";
import type { ExamMe } from "@/lib/types";
import { useApi } from "@/lib/useApi";
import { cn } from "@/lib/cn";
import { useT, type Key } from "@/lib/i18n";
import { navigate } from "@/lib/router";
import { store } from "@/lib/storage";

type Net = { down: number; up: number } | { error: true } | null;
const fmt = (k: number) => (k >= 1000 ? (k / 1000).toFixed(1) + " Mbps" : k + " kbps");

async function testNet(): Promise<Net> {
  const slow = new Promise<Net>((r) => setTimeout(() => r({ down: 50, up: 20 }), 20000));   // 20 s for 150 KB = very slow
  return Promise.race([measure(), slow]);
}

async function measure(): Promise<Net> {
  try {
    const t0 = performance.now();
    const r = await api<Response>(`/api/precheck/probe?kb=150&r=${Math.random()}`, { raw: true });
    const b = await r.arrayBuffer();
    const down = (b.byteLength * 8) / 1000 / ((performance.now() - t0) / 1000);
    const u0 = performance.now();
    await fetch(((import.meta.env.VITE_API_URL as string) || "") + "/api/precheck/probe", { method: "POST", body: new Uint8Array(60 * 1024) });
    const up = (60 * 1024 * 8) / 1000 / ((performance.now() - u0) / 1000);
    return { down: Math.round(down), up: Math.round(up) };
  } catch {
    return { error: true };
  }
}

export const isPhone = () => /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent);

function Tile({ icon, label, tone, text }: { icon: IconName; label: string; tone: Tone | "wait"; text: string }) {
  const c = {
    ok: "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-200 dark:ring-emerald-900",
    fix: "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-200 dark:ring-amber-900",
    bad: "bg-rose-50 text-rose-900 ring-rose-200 dark:bg-rose-950/50 dark:text-rose-200 dark:ring-rose-900",
    wait: "bg-white text-slate-600 ring-slate-200 dark:bg-slate-900 dark:text-slate-300 dark:ring-slate-800",
  }[tone];
  return (
    <li className={cn("flex items-start gap-3 rounded-xl p-3 ring-1 transition-colors", c)}>
      <span className="mt-0.5"><Icon name={tone === "ok" ? "checkCircle" : tone === "wait" ? icon : "alert"} size={20} /></span>
      <div className="min-w-0">
        <p className="text-sm font-semibold">{label}</p>
        <p className="text-sm opacity-90">{text}</p>
      </div>
    </li>
  );
}

export default function Precheck() {
  const { t } = useT();
  const [net, setNet] = useState<Net>(null);
  const [cam, setCam] = useState<"idle" | "on" | "blocked">("idle");
  const [checks, setChecks] = useState<Checks | null>(null);
  const [box, setBox] = useState<Box | null>(null);
  const video = useRef<HTMLVideoElement>(null);
  const last = useRef<Record<string, unknown>>({});
  const running = useRef(false);

  useEffect(() => { testNet().then(setNet); return () => { running.current = false; }; }, []);

  // microphone: optional unless the server says it is required; a separate prompt, so a "no" never blocks the camera
  const me = useApi<ExamMe>("/api/exam/me");
  const micMode = me.data?.mic || "optional";
  const [mic, setMic] = useState<"idle" | "on" | "blocked">("idle");
  const [level, setLevel] = useState(0);
  const stopMic = useRef<() => void>(() => {});
  useEffect(() => () => stopMic.current(), []);
  async function startMic() {
    try {
      await openMic();
      setMic("on");
      store.set("fp-mic", "on");
      stopMic.current = listen({ onLevel: (db) => setLevel(Math.max(0, Math.min(1, (db + 70) / 50))) });
    } catch {
      setMic("blocked");
      store.set("fp-mic", null);
      closeMic();
    }
  }

  async function startCam() {
    try {
      const s = await openCamera();
      setCam("on");
      requestAnimationFrame(async () => {
        if (!video.current) return;
        video.current.srcObject = s;
        await video.current.play().catch(() => {});
        await setupDetector(net && "down" in net ? net.down : undefined);
        running.current = true;
        loop([]);
      });
    } catch {
      setCam("blocked");
    }
  }

  async function loop(hist: ReturnType<typeof analyse>[]) {
    if (!running.current || !video.current) return;
    const v = video.current;
    if (v.readyState >= 2) {
      const faces = await detectFaces(v);
      const a = analyse(v, faces);
      hist = [...hist, a].slice(-6);                       // smooth over ~1.5 s
      const avg = (k: "face" | "faceHi" | "bg" | "sharp") => hist.reduce((s, h) => s + h[k], 0) / hist.length;
      const m = { face: avg("face"), faceHi: avg("faceHi"), bg: avg("bg"), sharp: avg("sharp") };
      setChecks(rules(m, a.f, a.count));
      setBox(a.f);
      last.current = { brightness: Math.round(m.face), backlight: Math.round(m.bg - m.face), face_found: a.count === null ? null : !!a.f,
        face_size: a.f ? +a.f.w.toFixed(2) : null, blur: Math.round(m.sharp), camera_ok: true };
    }
    setTimeout(() => loop(hist), 250);
  }

  const netOk = net && "down" in net;
  const problems = checks ? Object.values(checks).filter(([tone, key]) => tone !== "ok" && key !== "faceManual").length : 0;
  const ready = net !== null && cam === "on" && (micMode !== "required" || mic === "on");   // no camera, no test

  async function go() {
    if (me.data?.kiosk !== false) enterKiosk();          // full screen needs this tap; never blocks the start
    running.current = false;
    stopMic.current();                                     // the test page starts its own check on the same microphone
    if (mic !== "on") store.set("fp-mic", null);
    const lowNet = !netOk || net.up < 400 || net.down < 1000;
    const c = checks;
    const light = !c ? "ok" : c.back[0] === "bad" ? "backlit" : c.light[1] === "lightDim" ? "dim" : c.light[1] === "lightHot" ? "bright" : "ok";
    const framing = !c ? "ok" : c.face[1] === "faceNone" ? "no_face" : c.face[1] === "faceFar" ? "too_far" : c.face[1] === "faceManual" && box ? "off_centre" : "ok";
    store.set("fp-precheck", JSON.stringify({ device: isPhone() ? "phone" : "desktop", bandwidth_class: lowNet ? "low" : "normal", precheck_light: light, precheck_framing: framing }));
    store.set("fp-net-down", netOk ? String(net.down) : null);
    api("/api/exam/precheck", { body: { ...last.current, camera_ok: cam === "on", passed: problems === 0,
      down_kbps: netOk ? net.down : null, up_kbps: netOk ? net.up : null } }).catch(() => {});
    navigate("/exam/run");
  }

  const tile = (k: keyof Checks, icon: IconName, label: Key) =>
    <Tile icon={icon} label={t(label)} tone={checks ? checks[k][0] : "wait"} text={checks ? t(checks[k][1] as Key) : t("checking")} />;

  // face box → overlay coordinates (video is mirrored and object-fit: cover in a 3:4 box)
  let rect = null as null | { x: number; y: number; w: number; h: number };
  if (box && video.current?.videoWidth) {
    const vr = video.current.videoWidth / video.current.videoHeight, br = 300 / 400;
    let sx = 300, sy = 400, ox = 0, oy = 0;
    if (vr > br) { sx = 400 * vr; ox = (300 - sx) / 2; } else { sy = 300 / vr; oy = (400 - sy) / 2; }
    rect = { x: ox + (1 - box.x - box.w) * sx, y: oy + box.y * sy, w: box.w * sx, h: box.h * sy };
  }

  return (
    <CandidateShell>
      <div className="animate-fade-in space-y-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("precheckTitle")}</h1>
          <p className="mt-1 text-slate-500 dark:text-slate-400">{t("precheckIntro")}</p>
        </div>

        <ul className="space-y-2">
          <Tile icon="wifi" label={t("tileNet")} tone={net === null ? "wait" : !netOk ? "fix" : net.up >= 400 ? "ok" : "fix"}
            text={net === null ? t("checking") : !netOk ? t("netNone") : `${net.up >= 400 ? t("netGood") : t("netSlow")} · ${t("netResult", { down: fmt(net.down), up: fmt(net.up) })}`} />
        </ul>

          <Card>
            <CardContent className="space-y-4 pt-5">
              {cam !== "on" && (
                <div className="space-y-3 text-center">
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-pink-50 text-pink-700 dark:bg-pink-950 dark:text-pink-300"><Icon name="camera" size={28} /></div>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{t("cameraHow")}</p>
                  {cam === "blocked" && <Alert tone="warning" className="space-y-1 text-left"><p className="font-semibold">{t("cameraBlocked")}</p><p className="text-sm">{t("cameraFix")}</p></Alert>}
                  <Button size="lg" className="w-full" onClick={startCam}><Icon name="camera" size={18} />{t(cam === "blocked" ? "tryAgain" : "allowCamera")}</Button>
                </div>
              )}
              <div className={cn("relative mx-auto aspect-[3/4] w-full max-w-[300px] overflow-hidden rounded-3xl bg-slate-900", cam !== "on" && "hidden")}>
                <video ref={video} playsInline muted className="h-full w-full -scale-x-100 object-cover" />
                <svg viewBox="0 0 300 400" className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden>
                  <defs><mask id="oval"><rect width="300" height="400" fill="white" /><ellipse cx="150" cy="170" rx="88" ry="118" fill="black" /></mask></defs>
                  <rect width="300" height="400" fill="rgba(2,6,23,.45)" mask="url(#oval)" />
                  <ellipse cx="150" cy="170" rx="88" ry="118" fill="none" strokeWidth="3"
                    stroke={checks && problems === 0 ? "#34d399" : "#fff"} strokeDasharray={checks && problems === 0 ? "0" : "8 6"} />
                  {rect && <rect x={rect.x} y={rect.y} width={rect.w} height={rect.h} rx="10" fill="none" stroke="#f472b6" strokeWidth="2" />}
                </svg>
                {checks && (
                  <span className="absolute inset-x-3 bottom-3 rounded-full bg-slate-950/70 px-3 py-1.5 text-center text-sm font-semibold text-white backdrop-blur">
                    {problems === 0 ? t("allGood") : t((Object.values(checks).find(([tone, key]) => tone !== "ok" && key !== "faceManual")?.[1] || "checking") as Key)}
                  </span>
                )}
              </div>
              {cam === "on" && (
                <ul className="space-y-2">
                  {tile("back", "sunDim", "tileBack")}
                  {tile("light", "sun", "tileLight")}
                  {tile("face", "scan", "tileFace")}
                  {tile("sharp", "aperture", "tileSharp")}
                </ul>
              )}
            </CardContent>
          </Card>

        {micMode !== "off" && cam === "on" && (
          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-start gap-3">
                <div className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-pink-50 text-pink-700 dark:bg-pink-950 dark:text-pink-300"><Icon name={mic === "blocked" ? "micOff" : "mic"} size={20} /></div>
                <div className="min-w-0">
                  <p className="font-semibold">{t(micMode === "required" ? "micTitleRequired" : "micTitle")}</p>
                  <p className="text-sm text-slate-600 dark:text-slate-300">{t("micHow")}</p>
                </div>
              </div>
              {mic === "on" ? (
                <div className="space-y-1.5" role="status">
                  <p className="flex items-center gap-1.5 text-sm font-semibold text-emerald-700 dark:text-emerald-300"><Icon name="checkCircle" size={16} />{t("micOn")}</p>
                  <div className="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" aria-label={t("micLevel")}>
                    <div className="h-full rounded-full bg-emerald-500 transition-[width] duration-150" style={{ width: `${Math.round(level * 100)}%` }} />
                  </div>
                </div>
              ) : (
                <>
                  {mic === "blocked" && <Alert tone="warning" className="text-sm">{t(micMode === "required" ? "micBlockedRequired" : "micBlocked")}</Alert>}
                  <Button variant="outline" className="w-full" onClick={startMic}><Icon name="mic" size={18} />{t(mic === "blocked" ? "tryAgain" : "allowMic")}</Button>
                </>
              )}
            </CardContent>
          </Card>
        )}

        {(cam === "on" && checks) && (
          <p role="status" className={cn("text-center font-semibold", problems ? "text-amber-700 dark:text-amber-300" : "text-emerald-700 dark:text-emerald-300")}>
            {problems ? t("thingsLeft", { n: problems }) : t("allGood")}
          </p>
        )}
        <div className="space-y-2 pb-4">
          <Button size="lg" className="w-full" disabled={!ready} onClick={go}>
            <Icon name="play" size={18} />{t("startTest")}
          </Button>
          {cam === "on" && problems > 0 && <p className="text-center text-sm text-slate-500">{t("fairLine")}</p>}
        </div>
      </div>
    </CandidateShell>
  );
}

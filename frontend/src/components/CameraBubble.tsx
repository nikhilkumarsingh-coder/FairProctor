import { useEffect, useRef, useState, type MutableRefObject } from "react";
import { cameraStream, detectorMode, detectFaces, detectPhone, analyse, GazeEstimator, openCamera, setupDetector, setupPhoneDetector, snapshot } from "@/lib/camera";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { store } from "@/lib/storage";
import { Icon } from "./Icon";

/** Small hideable camera preview. Every second it counts faces for the proctoring rules; every 5 s it turns the
 *  picture into numbers for the server (faces, head direction, light).
 *  On a fast connection a phone detector also runs about once a second; each 5 s frame carries the share of
 *  those checks that saw a phone (phone), or nothing when it could not check. */
export type Snap = { before: string | null; at: string | null };

export function CameraBubble({ enabled, mic = false, attempt = 0, onCamera, onFrame, onCheck, onPhone, snapRef }: {
  enabled: boolean;
  /** the speech-like sound check is listening (shown so the candidate always knows) */
  mic?: boolean;
  /** bump to try opening the camera again */
  attempt?: number;
  /** true once the picture is live, false when the camera cannot open or stops (permission revoked, unplugged, another app) */
  onCamera?: (on: boolean) => void;
  onFrame: (f: { faces: number; face_visible: boolean; gaze: string; brightness?: number; blur?: number; phone?: number }) => void;
  /** every second: how many faces the device sees (null = could not check) — for the 5-second proctoring rules */
  onCheck?: (faces: number | null) => void;
  /** every second on a fast link: whether the phone detector saw a phone (null = could not check) */
  onPhone?: (seen: boolean | null) => void;
  /** filled with a function that takes a snapshot now, plus the picture kept from the previous 5 s check */
  snapRef?: MutableRefObject<(() => Snap) | null>;
}) {
  const { t } = useT();
  const video = useRef<HTMLVideoElement>(null);
  const [on, setOn] = useState(false);
  const [hidden, setHidden] = useState(store.get("fp-bubble") === "hidden");
  const cb = useRef(onFrame);
  cb.current = onFrame;
  const camCb = useRef(onCamera);
  camCb.current = onCamera;
  const checkCb = useRef(onCheck);
  checkCb.current = onCheck;
  const phoneCb = useRef(onPhone);
  phoneCb.current = onPhone;
  const prev = useRef<string | null>(null);              // the last 5 s picture, kept only in memory as "before"
  if (snapRef) snapRef.current = () => ({ before: prev.current, at: video.current && on ? snapshot(video.current) : null });

  useEffect(() => {
    if (!enabled) return;
    let alive = true, timer: ReturnType<typeof setTimeout>, phoneTimer: ReturnType<typeof setTimeout>;
    let seen = 0, checked = 0;
    const gaze = new GazeEstimator();
    (async () => {
      try {
        const s = cameraStream() || (await openCamera());
        if (!alive || !video.current) return;
        video.current.srcObject = s;
        await video.current.play().catch(() => {});
        setOn(true);
        camCb.current?.(true);
        s.getVideoTracks().forEach((tr) => tr.addEventListener("ended", () => {
          if (!alive) return;
          alive = false; clearTimeout(timer); clearTimeout(phoneTimer);
          setOn(false); camCb.current?.(false);
        }));
        await setupDetector(Number(store.get("fp-net-down")) || undefined);
        setupPhoneDetector(Number(store.get("fp-net-down")) || undefined).then((ok) => {
          if (!ok || !alive) return;
          const check = () => {
            const v = video.current;
            if (!alive) return;
            if (v && v.readyState >= 2 && document.visibilityState === "visible") {
              const p = detectPhone(v);
              if (p !== null) { checked += 1; if (p) seen += 1; }
              phoneCb.current?.(p);
            }
            phoneTimer = setTimeout(check, 1000);
          };
          phoneTimer = setTimeout(check, 1000);
        });
      } catch {
        setOn(false);
        if (alive) camCb.current?.(false);
        return;
      }
      // Faces are checked every second (the 5-second proctoring rules); the numbers sent to the server stay one frame
      // every 5 s, as the scoring model was built on.
      let n = 0;
      const tick = async () => {
        const v = video.current;
        if (!alive || !v) return;
        if (v.readyState >= 2 && detectorMode() !== "manual") {
          const faces = await detectFaces(v);
          if (!alive) return;
          if (faces) {
            const big = faces.filter((f) => f.w >= 0.08);
            checkCb.current?.(Math.min(big.length, 20));
            if (n % 5 === 0) {
              const a = analyse(v, faces);
              cb.current({
                faces: Math.min(big.length, 20), face_visible: big.length > 0, gaze: gaze.read(a.f && a.f.w >= 0.08 ? a.f : null),
                brightness: Math.round(Math.max(0, Math.min(255, a.face))), blur: +Math.max(0, Math.min(1, 1 - a.sharp / 200)).toFixed(2),
                ...(checked ? { phone: +(seen / checked).toFixed(2) } : {}),
              });
              seen = 0; checked = 0;
              prev.current = snapshot(v);
            }
            n += 1;
          } else {
            checkCb.current?.(null);
          }
        }
        timer = setTimeout(tick, 1000);
      };
      timer = setTimeout(tick, 1500);
    })();
    return () => { alive = false; clearTimeout(timer); clearTimeout(phoneTimer); };
  }, [enabled, attempt]);

  const toggle = () => { store.set("fp-bubble", hidden ? null : "hidden"); setHidden(!hidden); };

  const off = !enabled || !on;
  return (
    <div className="fixed bottom-24 right-3 z-30">
      {/* one <video> for the whole life of the bubble, so the stream stays attached when the look changes */}
      <div className={cn("relative overflow-hidden rounded-2xl bg-slate-900 shadow-xl ring-2 ring-white transition-all dark:ring-slate-800", off || hidden ? "h-0 w-0 ring-0" : "h-28 w-21")}>
        <video ref={video} playsInline muted className="h-full w-full -scale-x-100 object-cover" />
        <span className="absolute left-1.5 top-1.5 h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400 ring-2 ring-slate-900" />
        {mic && <span className="absolute right-1 top-1 grid h-5 w-5 place-items-center rounded-full bg-slate-900/80 text-white" title={t("micListening")} aria-label={t("micListening")}><Icon name="mic" size={11} /></span>}
      </div>
      {off ? (
        <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-900/85 px-3 py-1.5 text-xs font-semibold text-white shadow-lg backdrop-blur">
          <Icon name="cameraOff" size={14} /> {t("cameraOff")}
        </span>
      ) : (
        <button onClick={toggle} className={cn("inline-flex items-center gap-1.5 rounded-full bg-slate-900/85 px-3 py-1.5 text-xs font-semibold text-white shadow-lg backdrop-blur",
          hidden ? "" : "absolute -bottom-3 left-1/2 -translate-x-1/2")} aria-label={hidden ? t("show") : t("hide")}>
          <Icon name={hidden ? "camera" : "eye"} size={13} /> {hidden ? t("cameraOn") : t("hide")}{hidden && mic && <> · <Icon name="mic" size={12} /></>}
        </button>
      )}
    </div>
  );
}

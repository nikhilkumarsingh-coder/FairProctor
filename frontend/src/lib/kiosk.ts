// Kiosk mode for the test (decided automatically, see backend/services/device.py): full screen, the screen kept on,
// portrait on phones, and leaving full screen noticed. Inside Safe Exam Browser it does nothing (SEB locks the screen
// itself). A web page cannot lock a phone: other apps, notifications and split screen still work, so leaving full
// screen is only noted for the reviewer, never counted as a rule. iPhone browsers have no full screen for pages:
// there it keeps the screen on and nothing else.
import { inSeb } from "./seb";

export type DeviceSignals = { touch: number; w: number; h: number; coarse: boolean; fullscreen: boolean; wake_lock: boolean };

const doc = document as Document & { webkitFullscreenElement?: Element; webkitExitFullscreen?: () => void };

export function canFullscreen(): boolean {
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void };
  return !!(document.fullscreenEnabled || (el as { webkitRequestFullscreen?: unknown }).webkitRequestFullscreen) &&
    !/iPhone|iPod/.test(navigator.userAgent);
}

export function signals(): DeviceSignals {
  return {
    touch: Math.min(20, navigator.maxTouchPoints || 0),
    w: Math.round(screen.width), h: Math.round(screen.height),
    coarse: matchMedia("(pointer: coarse)").matches,
    fullscreen: canFullscreen(),
    wake_lock: "wakeLock" in navigator,
  };
}

export const isFullscreen = () => !!(document.fullscreenElement || doc.webkitFullscreenElement);

/** Call from a tap or click (browsers allow full screen only then). Never throws. */
export async function enterKiosk(): Promise<boolean> {
  if (inSeb() || !canFullscreen()) return false;
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => Promise<void> | void };
  try {
    if (!isFullscreen()) {
      if (el.requestFullscreen) await el.requestFullscreen({ navigationUI: "hide" });
      else await el.webkitRequestFullscreen?.();
    }
    const o = screen.orientation as ScreenOrientation & { lock?: (o: string) => Promise<void> };
    if (matchMedia("(pointer: coarse)").matches) await o?.lock?.("portrait").catch(() => {});
    return isFullscreen();
  } catch {
    return false;
  }
}

export function exitKiosk() {
  try { if (isFullscreen()) (document.exitFullscreen ? document.exitFullscreen() : doc.webkitExitFullscreen?.())?.catch?.(() => {}); }
  catch { /* already out */ }
}

/** Keep the screen on while the test runs (re-taken when the page comes back to the front). Returns a stop function. */
export function keepScreenOn(): () => void {
  const nav = navigator as Navigator & { wakeLock?: { request: (t: "screen") => Promise<{ release: () => Promise<void> }> } };
  if (!nav.wakeLock) return () => {};
  let lock: { release: () => Promise<void> } | null = null, stopped = false;
  const take = async () => {
    if (stopped || document.hidden) return;
    try { lock = await nav.wakeLock!.request("screen"); } catch { /* battery saver, or not allowed */ }
  };
  const again = () => { if (!document.hidden) take(); };
  take();
  document.addEventListener("visibilitychange", again);
  return () => { stopped = true; document.removeEventListener("visibilitychange", again); lock?.release().catch(() => {}); };
}

/** Calls back with true / false whenever the page enters or leaves full screen. Returns a stop function. */
export function onFullscreenChange(cb: (on: boolean) => void): () => void {
  const h = () => cb(isFullscreen());
  document.addEventListener("fullscreenchange", h);
  document.addEventListener("webkitfullscreenchange", h);
  return () => { document.removeEventListener("fullscreenchange", h); document.removeEventListener("webkitfullscreenchange", h); };
}

// Safe Exam Browser (SEB): when the page runs inside SEB, its JavaScript API gives the Config Key hashed with the page
// URL. We send it, with the URL it belongs to, on every API call so the server can check the test runs in SEB with the
// sitting's settings. Outside SEB this does nothing. https://safeexambrowser.org/developer/seb-config-key.html
type SebApi = { security?: { configKey?: string; browserExamKey?: string; updateKeys?: (cb: () => void) => void }; version?: string };

const loadedAt = location.href.split("#")[0];

function api(): SebApi | undefined {
  return (window as unknown as { SafeExamBrowser?: SebApi }).SafeExamBrowser;
}

export function inSeb(): boolean {
  return !!api() || /\bSEB\b/.test(navigator.userAgent);
}

// SEB 3.0 for macOS/iOS fills the keys only after updateKeys(); newer versions have them at once.
try { api()?.security?.updateKeys?.(() => {}); } catch { /* not in SEB */ }

export function sebHeaders(): Record<string, string> {
  const key = api()?.security?.configKey;
  if (!key) return {};
  return { "X-SEB-Config-Key-Hash": key, "X-SEB-Page-Url": loadedAt, "X-SEB-Page-Url-Now": location.href.split("#")[0] };
}

/** seb:// or sebs:// link that makes SEB download and open the sitting's .seb file. */
export function sebLink(configUrl: string): string {
  const abs = new URL(configUrl, location.origin);
  return (abs.protocol === "https:" ? "sebs://" : "seb://") + abs.host + abs.pathname;
}

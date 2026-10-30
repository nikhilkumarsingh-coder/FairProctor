// The only place that talks to the backend. JWT is sent as "Authorization: Bearer <token>".
import { sebHeaders } from "./seb";
import { store } from "./storage";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public extra: Record<string, unknown> = {}) {
    super(message);
  }
}
/** The request never reached the server (offline, DNS, CORS). The exam uploader retries these. */
export class NetworkError extends Error {}

const BASE = ((import.meta.env.VITE_API_URL as string | undefined) || "").replace(/\/$/, "");
// The candidate app and the staff app share one address, so each keeps its login under its own key: a reviewer
// logged in to the staff app is not "logged in" on the candidate pages of the same browser, and the other way round.
let TOKEN_KEY = "fp-token";
let token: string | null = store.get(TOKEN_KEY);

export function setTokenKey(key: string) { TOKEN_KEY = key; token = store.get(key); }
export function getToken() { return token; }
export function setToken(t: string | null) {
  token = t;
  store.set(TOKEN_KEY, t);
}

type Opts = { method?: string; body?: unknown; csv?: string; accept?: string; signal?: AbortSignal; raw?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...sebHeaders() };
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.csv !== undefined) { headers["Content-Type"] = "text/csv"; body = opts.csv; }
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  if (opts.accept) headers.Accept = opts.accept;
  let res: Response;
  try {
    res = await fetch(BASE + path, { method: opts.method || (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new NetworkError("No connection");
  }
  if (opts.raw && res.ok) return res as unknown as T;
  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await res.json().catch(() => null) : await res.text();
  if (!res.ok) {
    const err = (data && typeof data === "object" && (data as any).error) || {};
    if (res.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new CustomEvent("fp-unauthorized", { detail: err.code }));
    if (!err.code && res.status >= 500) {
      // No JSON error from FastAPI: the dev proxy could not reach the backend, or the backend crashed.
      console.warn(`FairProctor API ${path} → ${res.status}. Is the backend running? (dev: it should be on ${"VITE_PROXY_TARGET or http://127.0.0.1:8000"})`);
      throw new ApiError(res.status, "server_unreachable", "Could not reach the FairProctor server. Please try again in a minute.", err);
    }
    throw new ApiError(res.status, err.code || "http_error", err.message || `Request failed (${res.status})`, err);
  }
  return data as T;
}

export const errorText = (e: unknown) =>
  e instanceof NetworkError ? "No internet connection. Please try again." : e instanceof Error ? e.message : String(e);

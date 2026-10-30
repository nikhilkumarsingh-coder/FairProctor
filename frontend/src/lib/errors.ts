import { ApiError, NetworkError } from "./api";
import type { Key } from "./i18n";

const CODES: Record<string, Key> = {
  wrong_login: "errWrongLogin", locked: "errLocked", email_taken: "errEmailTaken",
  bad_join_code: "errBadJoin", sitting_closed: "errJoinClosed", not_live: "notLive", server_unreachable: "errServer",
  wrong_password: "errWrongPassword", same_password: "errSame", no_password: "codeLoginNote", session_expired: "errSessionExpired", name_locked: "nameLocked",
};

/** Candidate-facing error text in the chosen language (server text is the fallback). */
export function errorFor(e: unknown, t: (k: Key) => string) {
  if (e instanceof NetworkError) return t("errNetwork");
  if (e instanceof ApiError && CODES[e.code]) return t(CODES[e.code]);
  return e instanceof Error ? e.message : String(e);
}

/** 422 field problems from the backend → { field: problem }. */
export function fieldErrors(e: unknown): Record<string, string> {
  if (!(e instanceof ApiError) || e.code !== "invalid") return {};
  const out: Record<string, string> = {};
  for (const f of (e.extra.fields as { field: string; problem: string }[]) || []) out[f.field] = f.problem.replace(/^Value error, /, "");
  return out;
}

export const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, getToken, setToken } from "./api";
import { useT } from "./i18n";
import { navigate } from "./router";
import type { Me } from "./types";

type Ctx = {
  user: Me | null;
  ready: boolean;
  login: (body: Record<string, string>) => Promise<Me>;
  logout: () => Promise<void>;
  setUser: (me: Me) => void;
  setSession: (token: string) => void;
};
const AuthCtx = createContext<Ctx>(null as unknown as Ctx);

export const homeFor = (role?: string) => (role === "admin" ? "/admin" : role === "reviewer" ? "/review" : "/exam");

/** app: which frontend this is (the server refuses a login that belongs to the other one); loginPath: where to go
 *  when logged out. */
export function AuthProvider({ children, app = "candidate", loginPath = "/login" }: { children: ReactNode; app?: "candidate" | "staff"; loginPath?: string }) {
  const [user, setUser] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const { setLang } = useT();

  useEffect(() => {
    if (!getToken()) { setReady(true); return; }
    api<Me>("/api/me").then((me) => {
      // a login saved by the other app (e.g. an admin token from before the apps were split): start logged out here
      if ((app === "candidate") !== (me.role === "candidate")) { setToken(null); return; }
      setUser(me);
    }).catch(() => setToken(null)).finally(() => setReady(true));
  }, []);

  useEffect(() => {
    const on = (e: Event) => {
      setToken(null);
      setUser(null);
      navigate((e as CustomEvent).detail === "session_expired" ? `${loginPath}?expired=1` : loginPath, { replace: true });
    };
    window.addEventListener("fp-unauthorized", on);
    return () => window.removeEventListener("fp-unauthorized", on);
  }, []);

  const finish = async (r: { access_token: string }) => {
    setToken(r.access_token);
    const me = await api<Me>("/api/me");
    setUser(me);
    if (me.role === "candidate") setLang(me.language);     // the language saved in the candidate's profile
    return me;
  };
  const login = useCallback(async (body: Record<string, string>) => finish(await api("/api/auth/login", { body: { ...body, app } })), [app]);
  const logout = useCallback(async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch { /* token may already be invalid */ }
    setToken(null);
    setUser(null);
    navigate(loginPath, { replace: true });
  }, [loginPath]);

  const setSession = useCallback((t: string) => setToken(t), []);
  return <AuthCtx.Provider value={{ user, ready, login, logout, setUser, setSession }}>{children}</AuthCtx.Provider>;
}

export const useAuth = () => useContext(AuthCtx);

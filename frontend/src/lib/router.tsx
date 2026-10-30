// A tiny history router (no dependency): enough for ~15 routes with :params.
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

const Ctx = createContext<{ path: string; search: URLSearchParams }>({ path: "/", search: new URLSearchParams() });

export function navigate(to: string, opts: { replace?: boolean } = {}) {
  if (to === location.pathname + location.search) return;
  opts.replace ? history.replaceState(null, "", to) : history.pushState(null, "", to);
  window.dispatchEvent(new Event("fp-nav"));
  window.scrollTo({ top: 0 });
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const read = () => ({ path: location.pathname, search: new URLSearchParams(location.search) });
  const [loc, setLoc] = useState(read);
  useEffect(() => {
    const on = () => setLoc(read());
    window.addEventListener("popstate", on);
    window.addEventListener("fp-nav", on);
    return () => { window.removeEventListener("popstate", on); window.removeEventListener("fp-nav", on); };
  }, []);
  return <Ctx.Provider value={loc}>{children}</Ctx.Provider>;
}

export const useLocation = () => useContext(Ctx);

export function match(pattern: string, path: string): Record<string, string> | null {
  const p = pattern.split("/").filter(Boolean), s = path.split("/").filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(":")) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

export function Link({ to, className, children, ...rest }: { to: string; className?: string; children: ReactNode } & React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return (
    <a href={to} className={className} {...rest}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
      }}>
      {children}
    </a>
  );
}

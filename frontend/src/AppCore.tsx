// What both apps share: providers, the role-checked router, and the "no access" / "not found" pages.
import { useEffect, type ReactNode } from "react";
import { Loading } from "./components/Shell";
import { ToastProvider } from "./components/ui/toast";
import { AuthProvider, homeFor, useAuth } from "./lib/auth";
import { I18nProvider } from "./lib/i18n";
import { match, navigate, RouterProvider, useLocation } from "./lib/router";
import type { Role } from "./lib/types";

export type RouteDef = { path: string; roles?: Role[]; page: (p: Record<string, string>) => ReactNode };
export const CAND: Role[] = ["candidate"], REV: Role[] = ["reviewer", "admin"], ADMIN: Role[] = ["admin"];

type AppProps = { app: "candidate" | "staff"; routes: RouteDef[]; loginPath: string; roots: string[]; otherApp: { href: string; label: string } };

function Redirect({ to }: { to: string }) {
  useEffect(() => navigate(to, { replace: true }), [to]);
  return null;
}

const STAFF_PATH = /^\/(staff|admin|review)(\/|$)/;

function Router({ app, routes, loginPath, roots, otherApp }: AppProps) {
  const { path } = useLocation();
  const { user, ready } = useAuth();
  if (!ready) return <div className="mx-auto max-w-[480px] p-6"><Loading /></div>;
  if (roots.includes(path)) return <Redirect to={user ? homeFor(user.role) : loginPath} />;
  for (const r of routes) {
    const params = match(r.path, path);
    if (!params) continue;
    if (r.roles && !user) return <Redirect to={`${loginPath}?next=${encodeURIComponent(path)}`} />;
    if (r.roles && user && !r.roles.includes(user.role)) return <NoAccess otherApp={otherApp} />;
    if (!r.roles && user && r.path === loginPath) return <Redirect to={homeFor(user.role)} />;
    return <>{r.page(params)}</>;
  }
  // a page of the other app (a staff link opened in the candidate app, or the reverse): load that app
  if ((app === "candidate") === STAFF_PATH.test(path)) { window.location.replace(path); return null; }
  return <NotFound home={roots[0]} />;
}

function NoAccess({ otherApp }: { otherApp: AppProps["otherApp"] }) {
  return (
    <div className="mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-bold">You do not have access to this page</h1>
      <p className="mt-2 text-slate-500">This page is for a different role.</p>
      <a href={otherApp.href} className="mt-6 inline-block font-semibold text-pink-700 underline dark:text-pink-400">{otherApp.label}</a>
    </div>
  );
}

function NotFound({ home }: { home: string }) {
  return (
    <div className="mx-auto max-w-md p-8 text-center">
      <h1 className="text-2xl font-bold">Page not found</h1>
      <a href={home} className="mt-6 inline-block font-semibold text-pink-700 underline dark:text-pink-400">Go home</a>
    </div>
  );
}

export function AppCore({ app, ...rest }: AppProps) {
  return (
    <I18nProvider>
      <RouterProvider>
        <AuthProvider app={app} loginPath={rest.loginPath}>
          <ToastProvider>
            <Router app={app} {...rest} />
          </ToastProvider>
        </AuthProvider>
      </RouterProvider>
    </I18nProvider>
  );
}

import { useState, type ReactNode } from "react";
import { errorText } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { Link, useLocation } from "@/lib/router";
import { isDark, setDark } from "@/lib/theme";
import { useOnline } from "@/lib/useApi";
import { Icon } from "./Icon";
import { Button } from "./ui/button";
import { Alert, Skeleton } from "./ui/misc";

export function ThemeToggle({ className }: { className?: string }) {
  const [dark, set] = useState(isDark());
  return (
    <button onClick={() => { setDark(!dark); set(!dark); }} aria-label={dark ? "Light mode" : "Dark mode"}
      className={cn("rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800", className)}>
      <Icon name={dark ? "sun" : "moon"} size={18} />
    </button>
  );
}

export function LangToggle({ className }: { className?: string }) {
  const { lang, setLang } = useT();
  return (
    <div className={cn("flex overflow-hidden rounded-lg border border-slate-300 text-sm font-medium dark:border-slate-700", className)} role="group" aria-label="Language">
      <button onClick={() => setLang("en")} aria-pressed={lang === "en"} className={cn("px-2.5 py-1", lang === "en" ? "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>EN</button>
      <button onClick={() => setLang("hi")} aria-pressed={lang === "hi"} lang="hi" className={cn("px-2.5 py-1", lang === "hi" ? "bg-slate-800 text-white dark:bg-slate-200 dark:text-slate-900" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>हिं</button>
    </div>
  );
}

export function Brand({ small }: { small?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-tight text-slate-900 dark:text-slate-50", small ? "text-base" : "text-lg")}>
      <span className="grid h-7 w-7 place-items-center rounded-md bg-brand text-white dark:text-slate-950"><Icon name="shield" size={16} /></span>
      FairProctor
    </span>
  );
}

export function OfflineStrip() {
  const online = useOnline();
  const { t } = useT();
  if (online) return null;
  return (
    <div role="status" className="sticky top-0 z-40 flex items-center justify-center gap-2 bg-amber-100 px-4 py-2 text-sm font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
      <Icon name="wifiOff" size={16} /> {t("offlineStrip")}
    </div>
  );
}

/** Candidate pages: plain white top bar, centred column (480 px on phones, wider on laptops). */
export function CandidateShell({ children, bar, tools, wide, full }: { children: ReactNode; bar?: ReactNode; tools?: ReactNode; wide?: boolean; full?: boolean }) {
  const { user, logout } = useAuth();
  const { t } = useT();
  return (
    <div className="min-h-dvh">
      <OfflineStrip />
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className={cn("mx-auto flex items-center justify-between gap-3 px-4 py-3", full ? "max-w-[1400px]" : wide ? "max-w-3xl" : "max-w-[480px] lg:max-w-2xl")}>
          {bar ?? <Link to="/exam" className="rounded-lg"><Brand small /></Link>}
          <div className="flex items-center gap-1.5">
            {tools}
            <LangToggle />
            <ThemeToggle />
            {user && !bar && (
              <>
                <Link to="/account" className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label={t("account")} title={t("account")}>
                  <Icon name="user" size={18} />
                </Link>
                <button onClick={logout} className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" aria-label={t("logout")} title={t("logout")}>
                  <Icon name="logout" size={18} />
                </button>
              </>
            )}
          </div>
        </div>
      </header>
      <main className={cn("mx-auto px-4 py-6", full ? "max-w-[1400px]" : wide ? "max-w-3xl" : "max-w-[480px] lg:max-w-2xl")}>{children}</main>
    </div>
  );
}

/** Reviewer / admin pages: white top bar with navigation, full width. */
export function StaffShell({ children, title }: { children: ReactNode; title?: string }) {
  const { user, logout } = useAuth();
  const { path } = useLocation();
  const nav = user?.role === "admin"
    ? [{ to: "/admin", label: "Tests & sittings" }, { to: "/review/live", label: "Live monitor" }, { to: "/review/exams", label: "Exams" }, { to: "/review", label: "Review queue" }, { to: "/review/appeals", label: "Appeals" }]
    : [{ to: "/review/live", label: "Live monitor" }, { to: "/review/exams", label: "Exams" }, { to: "/review", label: "Review queue" }, { to: "/review/appeals", label: "Appeals" }];
  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link to={user?.role === "admin" ? "/admin" : "/review"} ><Brand small /></Link>
          <nav className="flex gap-1">
            {nav.map((n) => (
              <Link key={n.to} to={n.to}
                className={cn("rounded-md px-3 py-1.5 text-sm font-medium",
                  (n.to === "/review" ? path === "/review" || path.startsWith("/review/s/") : path.startsWith(n.to))
                    ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-50" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>
                {n.label}
              </Link>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2 text-sm">
            <Link to="/staff/account" title="My account"
              className={cn("inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
                path === "/staff/account" && "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-50")}>
              <Icon name="user" size={16} /><span className="hidden sm:inline">{user?.name} · {user?.role}</span>
            </Link>
            <ThemeToggle className="text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" />
            <Button variant="ghost" size="sm" onClick={logout}><Icon name="logout" size={16} /> Log out</Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">
        {title && <h1 className="mb-5 text-xl font-semibold tracking-tight text-slate-900 dark:text-slate-50">{title}</h1>}
        {children}
      </main>
    </div>
  );
}

export function Loading({ slow, lines = 3 }: { slow?: boolean; lines?: number }) {
  const { t } = useT();
  return (
    <div className="space-y-3" aria-busy="true" aria-label={t("loading")}>
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} className={i === 0 ? "h-28" : "h-16"} />)}
      {slow && <p className="text-sm text-slate-500">{t("slowLoading")}</p>}
    </div>
  );
}

export function ErrorBox({ error, retry }: { error: unknown; retry?: () => void }) {
  const { t } = useT();
  return (
    <Alert className="flex items-center justify-between gap-3">
      <span>{errorText(error)}</span>
      {retry && <Button size="sm" variant="outline" onClick={retry}><Icon name="refresh" size={16} />{t("tryAgain")}</Button>}
    </Alert>
  );
}

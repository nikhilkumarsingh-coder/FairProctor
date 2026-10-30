// "Try the demo" boxes: one-click logins for judges and testers, shown only when the backend is in demo mode
// (GET /api/demo: FP_DEMO=1, or local SQLite) and the demo accounts exist. The candidate login page shows the candidate
// buttons, the staff login page the admin and reviewer buttons.
import { useState, type ReactNode } from "react";
import { Icon, type IconName } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Alert } from "@/components/ui/misc";
import { api } from "@/lib/api";
import { homeFor, useAuth } from "@/lib/auth";
import { errorFor } from "@/lib/errors";
import { useT, type Key } from "@/lib/i18n";
import { navigate } from "@/lib/router";
import type { Demo, Me } from "@/lib/types";
import { useApi } from "@/lib/useApi";

function useDemo() {
  const { t } = useT();
  const { data } = useApi<Demo>("/api/demo");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function run(key: string, go: () => Promise<string>) {
    setBusy(key);
    setError(null);
    try { navigate(await go(), { replace: true }); }
    catch (e) { setError(errorFor(e, t)); }
    finally { setBusy(null); }
  }
  const b = (key: string, icon: IconName, label: string, onClick: () => void) => (
    <Button key={key} variant="outline" size="sm" className="h-auto min-h-9 justify-start py-2 text-left whitespace-normal" disabled={!!busy} onClick={onClick}>
      <Icon name={busy === key ? "refresh" : icon} size={16} className={busy === key ? "animate-spin" : undefined} />{label}
    </Button>
  );
  return { data, error, run, b };
}

function Box({ title, note, children, error }: { title: string; note: string; children: ReactNode; error: string | null }) {
  return (
    <Card className="border-dashed">
      <CardContent className="space-y-4 pt-5">
        <div>
          <p className="flex items-center gap-2 font-semibold"><Icon name="play" size={18} className="text-pink-600 dark:text-pink-400" />{title}</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">{note}</p>
        </div>
        {children}
        {error && <Alert>{error}</Alert>}
      </CardContent>
    </Card>
  );
}

/** Candidate app: a fresh candidate already in the demo test (made by the server, no sign-up), or a finished story. */
export function CandidateDemo() {
  const { t, lang } = useT();
  const { login, setSession, setUser } = useAuth();
  const { data, error, run, b } = useDemo();
  if (!data?.enabled) return null;
  const fresh = (kind: "mcq" | "coding") => run(kind, async () => {
    const r = await api<{ access_token: string }>("/api/demo/candidate", { body: { kind, language: lang } });
    setSession(r.access_token);
    setUser(await api<Me>("/api/me"));
    return "/exam";
  });
  const J = data.join_codes || {};
  return (
    <Box title={t("demoTitle")} note={t("demoNote")} error={error}>
      {(J.mcq || J.coding) && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("demoNew")}</p>
          <div className="grid grid-cols-2 gap-2">
            {J.mcq && b("mcq", "file", t("demoMcq"), () => fresh("mcq"))}
            {J.coding && b("coding", "code", t("demoCoding"), () => fresh("coding"))}
          </div>
          <p className="text-xs text-slate-500">{t("demoNewHelp")}</p>
        </div>
      )}
      {!!data.story?.length && (
        <div className="space-y-1.5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{t("demoStory")}</p>
          <div className="grid gap-2">
            {data.story.map((p) => b(p.key, "user", t(`demo_${p.key}` as Key),
              () => run(p.key, async () => { await login({ roll_no: p.roll_no, code: p.code }); return "/exam/result"; })))}
          </div>
        </div>
      )}
      <p className="text-xs text-slate-500">{t("demoStaffHere")} <a href="/staff/login" className="font-semibold text-pink-700 underline dark:text-pink-400">/staff/login</a></p>
    </Box>
  );
}

/** Staff app: the demo admin and reviewer. */
export function StaffDemo() {
  const { login } = useAuth();
  const { data, error, run, b } = useDemo();
  if (!data?.enabled || !data.staff?.length) return null;
  return (
    <Box title="Try the demo" note="Demo accounts for judges and testers (demo mode only)." error={error}>
      <div className="grid grid-cols-2 gap-2">
        {data.staff.map((s) => b(s.role, s.role === "admin" ? "shield" : "eye", s.role === "admin" ? "Admin" : "Reviewer",
          () => run(s.role, async () => homeFor((await login({ email: s.email, password: s.password })).role))))}
      </div>
    </Box>
  );
}

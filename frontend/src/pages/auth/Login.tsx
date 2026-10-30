// Candidate login (the candidate app at /): roll no. + login code from the test centre. No sign-up and no email
// login here: reviewers and admins use the staff app at /staff/login.
import { useState, type FormEvent } from "react";
import { CandidateDemo } from "@/components/DemoPanel";
import { CandidateShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { homeFor, useAuth } from "@/lib/auth";
import { errorFor } from "@/lib/errors";
import { useT } from "@/lib/i18n";
import { navigate, useLocation } from "@/lib/router";

export default function Login() {
  const { t } = useT();
  const { login } = useAuth();
  const { search } = useLocation();
  const [v, setV] = useState({ roll_no: "", code: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: "" }); };

  const validate = () => {
    const e: Record<string, string> = {};
    if (!v.roll_no.trim()) e.roll_no = t("errRequired");
    if (!v.code.trim()) e.code = t("errRequired");
    else if (!/^[A-Za-z0-9]{6}$/.test(v.code.trim())) e.code = t("errCode");
    setErrs(e);
    return !Object.keys(e).length;
  };

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    if (!validate()) return;
    setBusy(true);
    try {
      const me = await login({ roll_no: v.roll_no.trim().toUpperCase(), code: v.code.trim().toUpperCase() });
      const next = search.get("next");
      navigate(next && next.startsWith(homeFor(me.role)) ? next : homeFor(me.role), { replace: true });
    } catch (e) {
      setError(errorFor(e, t));
    } finally {
      setBusy(false);
    }
  }

  const aria = (k: string) => ({ "aria-invalid": !!errs[k], "aria-describedby": errs[k] ? `${k}-err` : undefined });

  return (
    <CandidateShell>
      <div className="animate-fade-in space-y-6">
        <div className="pt-2 text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-lg bg-brand text-white dark:text-slate-950">
            <Icon name="shield" size={28} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("loginTitle")}</h1>
          <p className="mt-2 text-slate-500 dark:text-slate-400">{t("appTagline")}</p>
        </div>

        {search.get("expired") && <Alert tone="info">{t("errSessionExpired")}</Alert>}
        <Card>
          <CardContent className="pt-5">
            <form onSubmit={submit} noValidate className="space-y-4">
              <Field id="roll_no" label={t("rollNo")} error={errs.roll_no}>
                <Input id="roll_no" autoComplete="username" autoCapitalize="characters" value={v.roll_no} onChange={set("roll_no")} {...aria("roll_no")} />
              </Field>
              <Field id="code" label={t("loginCode")} help={t("loginCodeHelp")} error={errs.code}>
                <Input id="code" autoComplete="one-time-code" autoCapitalize="characters" maxLength={6} className="font-mono tracking-[0.3em] uppercase"
                  value={v.code} onChange={set("code")} {...aria("code")} />
              </Field>
              {error && <Alert>{error}</Alert>}
              <Button type="submit" size="lg" className="w-full" disabled={busy}>
                {busy ? t("loggingIn") : t("logIn")} {!busy && <Icon name="arrowRight" size={18} />}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-sm text-slate-500 dark:text-slate-400">{t("noCodeHelp")}</p>
        <CandidateDemo />
      </div>
    </CandidateShell>
  );
}

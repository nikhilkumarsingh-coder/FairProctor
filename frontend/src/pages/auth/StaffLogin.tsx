// Staff login (the staff app at /staff/login): reviewers and admins, email + password. Accounts are made by an admin
// (reviewers) or with `python -m backend.scripts.create_admin` (admins); there is no sign-up.
import { useState, type FormEvent } from "react";
import { StaffDemo } from "@/components/DemoPanel";
import { Brand, ThemeToggle } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { homeFor, useAuth } from "@/lib/auth";
import { EMAIL_RE, errorFor } from "@/lib/errors";
import { useT } from "@/lib/i18n";
import { navigate, useLocation } from "@/lib/router";

export default function StaffLogin() {
  const { t } = useT();
  const { login } = useAuth();
  const { search } = useLocation();
  const [v, setV] = useState({ email: "", password: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => { setV({ ...v, [k]: e.target.value }); setErrs({ ...errs, [k]: "" }); };

  async function submit(ev: FormEvent) {
    ev.preventDefault();
    setError(null);
    const e: Record<string, string> = {};
    if (!EMAIL_RE.test(v.email.trim())) e.email = "Enter a valid email address.";
    if (!v.password) e.password = "Please fill this in.";
    setErrs(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    try {
      const me = await login({ email: v.email.trim(), password: v.password });
      const next = search.get("next");
      navigate(next && next.startsWith(homeFor(me.role)) ? next : homeFor(me.role), { replace: true });
    } catch (err) {
      setError(errorFor(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-dvh">
      <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <Brand small />
          <ThemeToggle />
        </div>
      </header>
      <main className="mx-auto max-w-md space-y-6 px-4 py-10">
        <div className="text-center">
          <div className="mx-auto mb-4 grid h-12 w-12 place-items-center rounded-lg bg-brand text-white dark:text-slate-950">
            <Icon name="lock" size={26} />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Staff login</h1>
          <p className="mt-2 text-slate-500 dark:text-slate-400">For reviewers and admins. Candidates log in on the test page.</p>
        </div>
        {search.get("expired") && <Alert tone="info">Your password was changed or your session ended. Please log in again.</Alert>}
        <Card>
          <CardContent className="pt-5">
            <form onSubmit={submit} noValidate className="space-y-4">
              <Field id="email" label="Email" error={errs.email}>
                <Input id="email" type="email" autoComplete="username" inputMode="email" value={v.email} onChange={set("email")} aria-invalid={!!errs.email} />
              </Field>
              <Field id="password" label="Password" error={errs.password}>
                <Input id="password" type="password" autoComplete="current-password" value={v.password} onChange={set("password")} aria-invalid={!!errs.password} />
              </Field>
              {error && <Alert>{error}</Alert>}
              <Button type="submit" size="lg" className="w-full" disabled={busy}>
                {busy ? "Logging in…" : "Log in"} {!busy && <Icon name="arrowRight" size={18} />}
              </Button>
            </form>
          </CardContent>
        </Card>
        <p className="text-center text-sm text-slate-500">No account? Ask your exam admin. <a href="/" className="font-semibold text-pink-700 hover:underline dark:text-pink-400">Candidate login</a></p>
        <StaffDemo />
      </main>
    </div>
  );
}

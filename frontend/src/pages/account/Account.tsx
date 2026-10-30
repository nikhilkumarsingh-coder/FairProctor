import { useState, type FormEvent } from "react";
import { CandidateShell, StaffShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardTitle } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { errorFor, fieldErrors } from "@/lib/errors";
import { dateTime } from "@/lib/format";
import { translate, useT, type Key, type Lang } from "@/lib/i18n";
import type { Me } from "@/lib/types";

/** Profile + password for every role. Candidates see it in their language; staff screens stay in English. */
export default function Account() {
  const { user, logout } = useAuth();
  const { lang } = useT();
  if (!user) return null;
  const staff = user.role !== "candidate";
  const L: Lang = staff ? "en" : lang;
  const t = (k: Key, v?: Record<string, string | number>) => translate(L, k, v);
  const roleKey: Key = user.role === "admin" ? "roleAdmin" : user.role === "reviewer" ? "roleReviewer" : "roleCandidate";
  const initials = user.name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");

  // one element tree, wrapped by the role's shell (a component defined here would remount the forms on every render)
  const body = (
      <div className={cn("animate-fade-in space-y-5", staff && "mx-auto max-w-2xl")}>
        <h1 className="text-2xl font-semibold tracking-tight">{t("account")}</h1>
        <Card className="overflow-hidden">
          <div className="h-16 border-b border-slate-200 bg-slate-100 dark:border-slate-800 dark:bg-slate-800" />
          <CardContent className="-mt-10 space-y-2 pt-0">
            <div className="grid h-20 w-20 place-items-center rounded-full border-4 border-slate-50 bg-white text-2xl font-semibold text-pink-700 shadow dark:border-slate-900 dark:bg-slate-800 dark:text-pink-300">
              {initials || <Icon name="user" size={28} />}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-xl font-semibold">{user.name}</p>
              <Badge tone="brand">{t(roleKey)}</Badge>
            </div>
            <p className="flex items-center gap-1.5 text-slate-600 dark:text-slate-300">
              <Icon name={user.email ? "mail" : "key"} size={16} />{user.email || `${t("rollNo")}: ${user.roll_no}`}
            </p>
            {user.created_at && <p className="text-sm text-slate-500">{t("accountCreated", { date: dateTime(user.created_at, L) })}</p>}
          </CardContent>
        </Card>
        <ProfileForm me={user} staff={staff} t={t} />
        <PasswordForm me={user} t={t} />
        <Button variant="outline" className="w-full" onClick={logout}><Icon name="logout" size={16} />{t("logout")}</Button>
      </div>
  );
  return staff ? <StaffShell>{body}</StaffShell> : <CandidateShell>{body}</CandidateShell>;
}

type T = (k: Key, v?: Record<string, string | number>) => string;

function ProfileForm({ me, staff, t }: { me: Me; staff: boolean; t: T }) {
  const { setUser } = useAuth();
  const { setLang } = useT();
  const toast = useToast();
  const [name, setName] = useState(me.name);
  const [language, setLanguage] = useState<Lang>(me.language);
  const [err, setErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function save(e: FormEvent) {
    e.preventDefault();
    const n = name.trim().replace(/\s+/g, " ");
    const locked = !!me.roll_no;
    if (n.length < 2) { setErr({ name: t("errName") }); return; }
    const body: Record<string, string> = {};
    if (n !== me.name && !locked) body.name = n;
    if (!staff && language !== me.language) body.language = language;
    if (!Object.keys(body).length) { toast(t("nothingChanged"), "info"); return; }
    setBusy(true); setErr({});
    try {
      const updated = await api<Me>("/api/me", { method: "PATCH", body });
      setUser(updated);
      setName(updated.name);
      if (!staff) setLang(updated.language);
      toast(staff ? t("profileSaved") : translate(updated.language, "profileSaved"));   // in the language just chosen
    } catch (e2) {
      const f = fieldErrors(e2);
      setErr(Object.keys(f).length ? f : { form: errorFor(e2, t) });
    } finally { setBusy(false); }
  }

  return (
    <Card>
      <CardContent className="pt-5">
        <CardTitle className="text-lg">{t("profileTitle")}</CardTitle>
        <form onSubmit={save} noValidate className="mt-4 space-y-4">
          <Field id="p-name" label={t("name")} error={err.name} help={me.roll_no ? t("nameLocked") : undefined}>
            <Input id="p-name" value={name} autoComplete="name" maxLength={120} readOnly={!!me.roll_no}
              className={me.roll_no ? "bg-slate-100 text-slate-600 dark:bg-slate-900 dark:text-slate-400" : undefined}
              onChange={(e) => { setName(e.target.value); setErr({}); }}
              aria-invalid={!!err.name} aria-describedby={err.name ? "p-name-err" : me.roll_no ? "p-name-help" : undefined} />
          </Field>
          {!staff && (
            <fieldset className="space-y-1.5">
              <legend className="text-sm font-semibold text-slate-700 dark:text-slate-300">{t("language")}</legend>
              <div className="grid grid-cols-2 gap-2" role="radiogroup">
                {(["en", "hi"] as Lang[]).map((l) => (
                  <button type="button" key={l} role="radio" aria-checked={language === l} onClick={() => setLanguage(l)} lang={l}
                    className={cn("h-12 rounded-xl border-2 font-semibold transition",
                      language === l ? "border-pink-500 bg-pink-50 text-pink-800 dark:bg-pink-950/40 dark:text-pink-200" : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950")}>
                    {t(l === "en" ? "english" : "hindi")}
                  </button>
                ))}
              </div>
              <p className="text-sm text-slate-500">{t("languageHelp")}</p>
            </fieldset>
          )}
          {err.form && <Alert>{err.form}</Alert>}
          <Button type="submit" disabled={busy}>{busy ? t("loading") : t("saveChanges")}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

const STRONG = (p: string) => p.length >= 8 && /[A-Za-z]/.test(p) && /\d/.test(p);

function PasswordForm({ me, t }: { me: Me; t: T }) {
  const { setSession } = useAuth();
  const toast = useToast();
  const [v, setV] = useState({ current: "", next: "", again: "" });
  const [show, setShow] = useState(false);
  const [err, setErr] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const set = (k: keyof typeof v) => (e: React.ChangeEvent<HTMLInputElement>) => { setV({ ...v, [k]: e.target.value }); setErr({}); };

  if (me.has_password === false) {
    return (
      <Card><CardContent className="pt-5">
        <CardTitle className="text-lg">{t("changePassword")}</CardTitle>
        <Alert tone="info" className="mt-3 flex gap-2"><Icon name="key" size={18} className="mt-0.5 shrink-0" />{t("codeLoginNote")}</Alert>
      </CardContent></Card>
    );
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!v.current) er.current = t("errRequired");
    if (!STRONG(v.next)) er.next = t("errPassword");
    else if (v.next === v.current) er.next = t("errSame");
    if (!er.next && v.again !== v.next) er.again = t("errMatch");
    setErr(er);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      const r = await api<{ access_token: string }>("/api/auth/change-password", { body: { current_password: v.current, new_password: v.next } });
      setSession(r.access_token);                     // this device stays logged in with a fresh token
      setV({ current: "", next: "", again: "" });
      toast(t("passwordChanged"));
    } catch (e2) {
      const msg = errorFor(e2, t);
      setErr(msg === t("errWrongPassword") ? { current: msg } : msg === t("errSame") ? { next: msg } : { form: msg });
    } finally { setBusy(false); }
  }
  const type = show ? "text" : "password";
  const aria = (k: string) => ({ "aria-invalid": !!err[k], "aria-describedby": err[k] ? `pw-${k}-err` : undefined });

  return (
    <Card>
      <CardContent className="pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-lg">{t("changePassword")}</CardTitle>
            <CardDescription className="text-sm">{t("passwordNote")}</CardDescription>
          </div>
          <Button type="button" variant="ghost" size="sm" onClick={() => setShow(!show)} aria-pressed={show}>
            <Icon name="eye" size={16} />{show ? t("hide") : t("show")}
          </Button>
        </div>
        <form onSubmit={submit} noValidate className="mt-4 space-y-4">
          <input type="text" name="username" autoComplete="username" value={me.email || ""} readOnly hidden />
          <Field id="pw-current" label={t("currentPassword")} error={err.current}>
            <Input id="pw-current" type={type} autoComplete="current-password" value={v.current} onChange={set("current")} {...aria("current")} />
          </Field>
          <Field id="pw-next" label={t("newPassword")} help={t("passwordHelp")} error={err.next}>
            <Input id="pw-next" type={type} autoComplete="new-password" value={v.next} onChange={set("next")} {...aria("next")} />
          </Field>
          <Field id="pw-again" label={t("confirmPassword")} error={err.again}>
            <Input id="pw-again" type={type} autoComplete="new-password" value={v.again} onChange={set("again")} {...aria("again")} />
          </Field>
          {err.form && <Alert>{err.form}</Alert>}
          <Button type="submit" disabled={busy}><Icon name="lock" size={16} />{busy ? t("loading") : t("changePassword")}</Button>
        </form>
      </CardContent>
    </Card>
  );
}

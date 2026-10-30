import { useState, type FormEvent } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { SittingStatus } from "@/components/admin";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { Alert, Dialog } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { api, errorText } from "@/lib/api";
import { fieldErrors } from "@/lib/errors";
import { dateTime } from "@/lib/format";
import { Link, navigate } from "@/lib/router";
import type { Sitting, Test } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function AdminHome() {
  const tests = useApi<Test[]>("/api/admin/tests");
  const sittings = useApi<Sitting[]>("/api/admin/sittings");
  const [newTest, setNewTest] = useState(false);
  const [newSitting, setNewSitting] = useState(false);
  return (
    <StaffShell>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Tests & sittings</h1>
          <p className="mt-1 text-sm text-slate-500">Make a test, add questions, then run it as a sitting and add its candidates (each gets a roll no. + login code).</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setNewTest(true)}><Icon name="file" size={16} />New test</Button>
          <Button onClick={() => setNewSitting(true)}><Icon name="play" size={16} />New sitting</Button>
        </div>
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold">Sittings</h2>
        {sittings.loading && !sittings.data ? <Loading lines={2} /> : sittings.error ? <ErrorBox error={sittings.error} retry={sittings.reload} /> : !sittings.data?.length ? (
          <Card className="p-8 text-center text-slate-500">No sittings yet.</Card>
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {sittings.data.map((s) => (
              <Link key={s.id} to={`/admin/sittings/${s.id}`} className="block rounded-2xl border border-slate-200 bg-white p-4 transition-colors hover:border-slate-400 dark:hover:border-slate-600 dark:border-slate-800 dark:bg-slate-900">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold">{s.title}</p>
                    <p className="truncate text-sm text-slate-500">{s.test_title}</p>
                  </div>
                  <SittingStatus status={s.status} />
                </div>
                <div className="mt-3 flex items-center justify-between text-sm">
                  <span className="font-mono font-semibold tracking-wider">{s.join_code}</span>
                  <span className="inline-flex items-center gap-1 text-slate-500"><Icon name="users" size={14} />{s.n_candidates}</span>
                </div>
                <p className="mt-2 text-xs text-slate-500">{dateTime(s.starts_at)} → {dateTime(s.ends_at)}</p>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section>
        <h2 className="mb-3 text-lg font-semibold">Tests</h2>
        {tests.loading && !tests.data ? <Loading lines={2} /> : tests.error ? <ErrorBox error={tests.error} retry={tests.reload} /> : !tests.data?.length ? (
          <Card className="p-8 text-center text-slate-500">No tests yet.</Card>
        ) : (
          <Card className="overflow-hidden bg-white dark:bg-slate-950">
            <table className="w-full text-sm">
              <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                <tr><th className="px-4 py-2.5">Title</th><th className="px-4 py-2.5">Duration</th><th className="px-4 py-2.5">Questions</th><th className="hidden px-4 py-2.5 sm:table-cell">Created</th></tr>
              </thead>
              <tbody>
                {tests.data.map((t) => (
                  <tr key={t.id} onClick={() => navigate(`/admin/tests/${t.id}`)} className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 dark:border-slate-900 dark:hover:bg-slate-900">
                    <td className="px-4 py-3 font-semibold"><Link to={`/admin/tests/${t.id}`}>{t.title}</Link>
                      {t.kind === "coding" && <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-pink-50 px-2 py-0.5 text-xs font-semibold text-pink-700 dark:bg-pink-950 dark:text-pink-300"><Icon name="code" size={12} />coding</span>}</td>
                    <td className="tabular px-4 py-3">{t.duration_min} min</td>
                    <td className="tabular px-4 py-3">{t.n_items ? `${t.n_items} ${t.kind === "coding" ? "problems" : "questions"}` : <span className="text-amber-600">none yet</span>}</td>
                    <td className="hidden px-4 py-3 text-slate-500 sm:table-cell">{dateTime(t.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Card>
        )}
      </section>

      <StaffAccounts />

      <NewTest open={newTest} onClose={() => setNewTest(false)} />
      <NewSitting open={newSitting} onClose={() => setNewSitting(false)} tests={tests.data || []} />
    </StaffShell>
  );
}

function NewTest({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [v, setV] = useState({ title: "", duration: "45", kind: "mcq" as "mcq" | "coding" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!v.title.trim()) er.title = "Give the test a title.";
    const d = Number(v.duration);
    if (!Number.isInteger(d) || d < 1 || d > 600) er.duration = "Between 1 and 600 minutes.";
    setErrs(er);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      const r = await api<{ id: number }>("/api/admin/tests", { body: { title: v.title.trim(), duration_min: d, kind: v.kind } });
      navigate(`/admin/tests/${r.id}`);
    } catch (e) { setErrs({ form: errorText(e), ...fieldErrors(e) }); } finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="New test">
      <form onSubmit={submit} noValidate className="space-y-4">
        <fieldset>
          <legend className="mb-1.5 text-sm font-semibold text-slate-700 dark:text-slate-300">Type</legend>
          <div className="grid grid-cols-2 gap-2" role="radiogroup">
            {([["mcq", "Question test", "MCQ + short answers (CSV)"], ["coding", "Coding test", "Programming problems (JSON)"]] as const).map(([k, l, h]) => (
              <button type="button" key={k} role="radio" aria-checked={v.kind === k} onClick={() => setV({ ...v, kind: k, duration: k === "coding" ? "60" : v.duration })}
                className={`rounded-xl border-2 p-2.5 text-left text-sm ${v.kind === k ? "border-pink-500 bg-pink-50 dark:bg-pink-950/40" : "border-slate-200 dark:border-slate-800"}`}>
                <b className="block">{l}</b><span className="text-xs text-slate-500">{h}</span>
              </button>
            ))}
          </div>
        </fieldset>
        <Field id="t-title" label="Title" error={errs.title}><Input id="t-title" value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} aria-invalid={!!errs.title} /></Field>
        <Field id="t-dur" label="Duration (minutes)" error={errs.duration || errs.duration_min}><Input id="t-dur" type="number" inputMode="numeric" min={1} max={600} value={v.duration} onChange={(e) => setV({ ...v, duration: e.target.value })} aria-invalid={!!errs.duration} /></Field>
        {errs.form && <Alert>{errs.form}</Alert>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating…" : "Create and add questions"}</Button>
      </form>
    </Dialog>
  );
}

const local = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16);

function NewSitting({ open, onClose, tests }: { open: boolean; onClose: () => void; tests: Test[] }) {
  const toast = useToast();
  const now = new Date();
  const [v, setV] = useState({ test_id: "", title: "", starts: local(now), ends: local(new Date(now.getTime() + 3 * 3600_000)) });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const ready = tests.filter((t) => t.n_items > 0);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const er: Record<string, string> = {};
    const tid = Number(v.test_id || ready[0]?.id);
    if (!tid) er.test_id = "Pick a test that has questions.";
    if (!v.title.trim()) er.title = "Give the sitting a title, e.g. 'Morning batch, 2 Nov'.";
    const s = new Date(v.starts), en = new Date(v.ends);
    if (isNaN(+s)) er.starts = "Pick a start time.";
    if (isNaN(+en) || en <= s) er.ends = "The end must be after the start.";
    setErrs(er);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      const r = await api<{ id: number; join_code: string }>("/api/admin/sittings", { body: { test_id: tid, title: v.title.trim(), starts_at: s.toISOString(), ends_at: en.toISOString() } });
      toast(`Sitting created · join code ${r.join_code}`);
      navigate(`/admin/sittings/${r.id}`);
    } catch (e) { setErrs({ form: errorText(e) }); } finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="New sitting">
      <form onSubmit={submit} noValidate className="space-y-4">
        <Field id="s-test" label="Test" error={errs.test_id}>
          <select id="s-test" value={v.test_id || ready[0]?.id || ""} onChange={(e) => setV({ ...v, test_id: e.target.value })}
            className="h-12 w-full rounded-xl border border-slate-300 bg-white px-3 dark:border-slate-700 dark:bg-slate-950">
            {ready.length === 0 && <option value="">No test has questions yet</option>}
            {ready.map((t) => <option key={t.id} value={t.id}>{t.title} ({t.n_items} {t.kind === "coding" ? "problems" : "q"}, {t.duration_min} min)</option>)}
          </select>
        </Field>
        <Field id="s-title" label="Sitting title" error={errs.title}><Input id="s-title" value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} aria-invalid={!!errs.title} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="s-start" label="Opens" error={errs.starts}><Input id="s-start" type="datetime-local" value={v.starts} onChange={(e) => setV({ ...v, starts: e.target.value })} /></Field>
          <Field id="s-end" label="Closes" error={errs.ends}><Input id="s-end" type="datetime-local" value={v.ends} onChange={(e) => setV({ ...v, ends: e.target.value })} aria-invalid={!!errs.ends} /></Field>
        </div>
        {errs.form && <Alert>{errs.form}</Alert>}
        <Button type="submit" className="w-full" disabled={busy}>{busy ? "Creating…" : "Create sitting"}</Button>
      </form>
    </Dialog>
  );
}

type StaffUser = { id: number; role: "admin" | "reviewer"; name: string; email: string; created_at: string };

/** Reviewers are added here; admins only with `python -m backend.scripts.create_admin` on the server. No sign-up. */
function StaffAccounts() {
  const reviewers = useApi<StaffUser[]>("/api/admin/users?role=reviewer");
  const admins = useApi<StaffUser[]>("/api/admin/users?role=admin");
  const [open, setOpen] = useState(false);
  const rows = [...(admins.data || []), ...(reviewers.data || [])];
  return (
    <section className="mt-8">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">Staff accounts</h2>
          <p className="text-sm text-slate-500">Reviewers log in at /staff/login. New admins are created on the server with <code className="rounded bg-slate-100 px-1 text-xs dark:bg-slate-800">python -m backend.scripts.create_admin</code>.</p>
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}><Icon name="userPlus" size={16} />Add reviewer</Button>
      </div>
      {(reviewers.loading || admins.loading) && !rows.length ? <Loading lines={1} /> : (
        <Card className="overflow-hidden bg-white dark:bg-slate-950">
          <table className="w-full text-sm">
            <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
              <tr><th className="px-4 py-2.5">Name</th><th className="px-4 py-2.5">Email</th><th className="px-4 py-2.5">Role</th><th className="hidden px-4 py-2.5 sm:table-cell">Added</th></tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id} className="border-b border-slate-100 dark:border-slate-900">
                  <td className="px-4 py-2.5 font-semibold">{u.name}</td>
                  <td className="px-4 py-2.5 text-slate-600 dark:text-slate-300">{u.email}</td>
                  <td className="px-4 py-2.5 capitalize">{u.role}</td>
                  <td className="hidden px-4 py-2.5 text-slate-500 sm:table-cell">{dateTime(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
      <NewReviewer open={open} onClose={() => setOpen(false)} onDone={() => reviewers.reload(true)} />
    </section>
  );
}

function NewReviewer({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const toast = useToast();
  const [v, setV] = useState({ name: "", email: "", password: "" });
  const [errs, setErrs] = useState<Record<string, string>>({});
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    const er: Record<string, string> = {};
    if (!v.name.trim()) er.name = "Enter the reviewer's name.";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v.email.trim())) er.email = "Enter a valid email address.";
    if (v.password.length < 8 || !/[A-Za-z]/.test(v.password) || !/\d/.test(v.password)) er.password = "Use at least 8 characters with letters and numbers.";
    setErrs(er); setErr(null);
    if (Object.keys(er).length) return;
    setBusy(true);
    try {
      await api("/api/admin/users", { body: { role: "reviewer", name: v.name.trim(), email: v.email.trim(), password: v.password } });
      toast("Reviewer added. Share the email and password with them privately.");
      setV({ name: "", email: "", password: "" }); onDone(); onClose();
    } catch (x) { setErrs(fieldErrors(x)); setErr(errorText(x)); }
    finally { setBusy(false); }
  }
  return (
    <Dialog open={open} onClose={onClose} title="Add a reviewer">
      <form onSubmit={submit} noValidate className="space-y-4">
        <Field id="r-name" label="Name" error={errs.name}><Input id="r-name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} /></Field>
        <Field id="r-email" label="Email" error={errs.email}><Input id="r-email" type="email" value={v.email} onChange={(e) => setV({ ...v, email: e.target.value })} /></Field>
        <Field id="r-password" label="First password" help="They can change it on their account page." error={errs.password}>
          <Input id="r-password" type="text" autoComplete="off" value={v.password} onChange={(e) => setV({ ...v, password: e.target.value })} />
        </Field>
        {err && <Alert>{err}</Alert>}
        <div className="flex gap-2">
          <Button type="button" variant="outline" className="flex-1" onClick={onClose}>Cancel</Button>
          <Button type="submit" className="flex-1" disabled={busy}>{busy ? "Adding…" : "Add reviewer"}</Button>
        </div>
      </form>
    </Dialog>
  );
}

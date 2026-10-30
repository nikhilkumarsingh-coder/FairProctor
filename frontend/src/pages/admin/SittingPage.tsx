import { useEffect, useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { CopyCode, CsvBox, downloadText, SittingStatus, type BadRow } from "@/components/admin";
import { Icon } from "@/components/Icon";
import { BAND_LABEL } from "@/components/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Alert, Dialog, Progress } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";
import { Link } from "@/lib/router";
import type { Band, Job } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Cand = { user_id: number; roll_no: string | null; email: string | null; name: string; session_id: string; status: string; started_at: string | null; submitted_at: string | null; device: string | null; bandwidth_class: string | null };
type Detail = {
  id: number; test_id: number; title: string; starts_at: string; ends_at: string; status: string; join_code: string; closed_at: string | null; scored_at: string | null;
  live: { not_started: number; in_progress: number; submitted: number; reference_sessions: number; bands: Partial<Record<Band, number>> };
  candidates: Cand[]; jobs: (Job & { finished_at?: string | null; created_at: string })[];
  seb?: Seb;
};
type Seb = { required: boolean; config_key_set: boolean; config_key_end: string; file_uploaded: boolean; config_url: string | null };
type Codes = { n: number; candidates: { roll_no: string; name: string; code: string }[]; csv: string };

const SAMPLE = "roll_no,name,language\nCS2026-001,Asha Kumari,hi\nCS2026-002,Rahul Verma,en\n";

export default function SittingPage({ id }: { id: number }) {
  const toast = useToast();
  const [poll, setPoll] = useState<number | undefined>(undefined);
  const { data, error, loading, reload } = useApi<Detail>(`/api/admin/sittings/${id}`, { poll });
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState<BadRow[]>([]);
  const [csvErr, setCsvErr] = useState<string | null>(null);
  const [codes, setCodes] = useState<Codes | null>(null);
  const [closing, setClosing] = useState(false);
  const [job, setJob] = useState<Job | null>(null);
  const [actErr, setActErr] = useState<string | null>(null);

  useEffect(() => { setPoll(data?.status === "live" || data?.status === "scoring" ? 5000 : undefined); }, [data?.status]);

  // follow a running scoring job
  useEffect(() => {
    const running = data?.jobs?.find((j) => j.status === "queued" || j.status === "running");
    if (running && !job) setJob(running);
  }, [data, job]);
  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const t = setTimeout(async () => {
      try {
        const j = await api<Job>(`/api/admin/jobs/${job.id}`);
        setJob(j);
        if (j.status === "done") { toast("Scoring finished"); reload(true); }
        if (j.status === "failed") reload(true);
      } catch { setJob({ ...job }); }
    }, 1000);
    return () => clearTimeout(t);
  }, [job]); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(path: string, after?: (r: any) => void) {
    setActErr(null);
    try { const r = await api(path, { method: "POST" }); after?.(r); reload(true); }
    catch (e) { setActErr(errorText(e)); }
  }
  async function upload(csv: string) {
    setBusy(true); setCsvErr(null); setRows([]);
    try {
      const r = await api<Codes>(`/api/admin/sittings/${id}/candidates`, { csv });
      setCodes(r);
      reload(true);
    } catch (e) {
      setCsvErr(errorText(e));
      if (e instanceof ApiError) setRows((e.extra.rows as BadRow[]) || []);
    } finally { setBusy(false); }
  }
  async function resetCode(c: Cand) {
    try {
      const r = await api<{ roll_no: string; code: string }>(`/api/admin/candidates/${c.user_id}/reset-code`, { method: "POST" });
      setCodes({ n: 1, candidates: [{ roll_no: r.roll_no, name: c.name, code: r.code }], csv: `roll_no,name,code\n${r.roll_no},${c.name},${r.code}\n` });
    } catch (e) { toast(errorText(e), "danger"); }
  }

  if (loading && !data) return <StaffShell><Loading /></StaffShell>;
  if (error || !data) return <StaffShell><ErrorBox error={error} retry={reload} /></StaffShell>;
  const L = data.live, bands = L.bands, scored = data.status === "scored";
  const total = L.not_started + L.in_progress + L.submitted;

  return (
    <StaffShell>
      <Link to="/admin" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />Tests & sittings</Link>
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1><SittingStatus status={data.status} /></div>
          <p className="mt-1 text-sm text-slate-500">{dateTime(data.starts_at)} → {dateTime(data.ends_at)} · <Link to={`/admin/tests/${data.test_id}`} className="underline">questions</Link></p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-right"><p className="text-xs text-slate-500">Join code</p><CopyCode code={data.join_code} big /></div>
          {data.status === "scheduled" && <Button onClick={() => act(`/api/admin/sittings/${id}/open`, () => toast("Sitting is live"))}><Icon name="play" size={16} />Open now</Button>}
          {data.status === "live" && <Link to={`/review/live/${id}`} className="inline-flex h-11 items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"><span className="h-2 w-2 animate-pulse rounded-full bg-rose-500" />Live monitor</Link>}
          {data.status === "live" && <Button variant="danger" onClick={() => setClosing(true)}><Icon name="lock" size={16} />Close & score</Button>}
          {scored && <Link to={`/admin/sittings/${id}/fairness`} className="inline-flex h-11 items-center gap-2 rounded-xl border border-slate-300 bg-white px-4 font-semibold hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:bg-slate-800"><Icon name="scale" size={16} />Fairness report</Link>}
          {scored && <Link to={`/review?sitting=${id}`} className="inline-flex h-11 items-center gap-2 rounded-lg bg-brand px-5 font-medium text-white hover:bg-brand-hover dark:text-slate-950">Open review queue <Icon name="arrowRight" size={16} /></Link>}
        </div>
      </div>
      {actErr && <Alert className="mb-4">{actErr}</Alert>}

      {data.status === "scoring" && !job && data.jobs?.[0]?.status === "failed" && (
        <Alert className="mb-5 flex flex-wrap items-center justify-between gap-3">
          <span><b>Scoring failed.</b> {data.jobs[0].message} Answers are safe; fix the cause (or update the server) and try again.</span>
          <Button variant="outline" size="sm" onClick={() => act(`/api/admin/sittings/${id}/close`, (r) => setJob({ id: r.job_id, status: "queued", progress: 0, message: "queued" }))}>
            <Icon name="refresh" size={16} />Retry scoring
          </Button>
        </Alert>
      )}

      {job && job.status !== "done" && (
        <Card className="mb-5 bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
          <div className="flex items-center justify-between text-sm"><b>{job.status === "failed" ? "Scoring failed" : "Scoring the sitting…"}</b><span className="tabular text-slate-500">{Math.round(job.progress * 100)}%</span></div>
          <Progress value={job.progress * 100} label="Scoring progress" />
          <p className="text-xs text-slate-500">{job.message}</p>
        </CardContent></Card>
      )}

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Count label="Not started" n={L.not_started} />
        <Count label="Writing now" n={L.in_progress} tone="text-sky-600" live={data.status === "live"} />
        <Count label="Submitted" n={L.submitted} tone="text-emerald-600" />
        <Count label="Reference sessions" n={L.reference_sessions} hint="calibration data scored with this sitting" />
      </div>

      {scored && (
        <Card className="mb-5 bg-white dark:bg-slate-950"><CardContent className="pt-5">
          <CardTitle className="text-base">Result of scoring</CardTitle>
          <div className="mt-3 grid grid-cols-3 gap-3">
            {(["review_first", "review", "clear"] as Band[]).map((b) => (
              <Link key={b} to={`/review?sitting=${id}&band=${b}`} className={cn("rounded-xl p-3 transition hover:brightness-95",
                b === "review_first" ? "bg-rose-50 dark:bg-rose-950/40" : b === "review" ? "bg-amber-50 dark:bg-amber-950/40" : "bg-emerald-50 dark:bg-emerald-950/40")}>
                <p className="text-xs font-semibold text-slate-600 dark:text-slate-300">{BAND_LABEL[b]}</p>
                <p className="tabular text-2xl font-semibold">{bands[b] || 0}</p>
              </Link>
            ))}
          </div>
        </CardContent></Card>
      )}

      {data.seb && <SebCard id={id} seb={data.seb} editable={data.status === "scheduled" || data.status === "live"} onSaved={() => reload(true)} />}

      <div className="grid gap-5 lg:grid-cols-[1fr_24rem]">
        <Card className="min-w-0 overflow-hidden bg-white dark:bg-slate-950">
          <div className="flex items-center justify-between px-4 pt-4"><CardTitle className="text-base">Candidates ({total})</CardTitle></div>
          {data.candidates.length === 0 ? <p className="p-6 text-sm text-slate-500">No candidates yet. Import a list, or share the join code so candidates can sign up and join.</p> : (
            <div className="overflow-x-auto">
              <table className="mt-3 w-full min-w-[640px] text-sm">
                <thead className="border-y border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500 dark:border-slate-800">
                  <tr><th className="px-4 py-2">Candidate</th><th className="px-4 py-2">Status</th><th className="px-4 py-2">Device</th><th className="px-4 py-2">Submitted</th><th className="px-4 py-2" /></tr>
                </thead>
                <tbody>
                  {data.candidates.map((c) => (
                    <tr key={c.session_id} className="border-b border-slate-100 dark:border-slate-900">
                      <td className="px-4 py-2.5"><p className="font-semibold">{c.name}</p><p className="text-xs text-slate-500">{c.roll_no || c.email}</p></td>
                      <td className="px-4 py-2.5"><Badge tone={c.status === "submitted" ? "success" : c.status === "in_progress" ? "info" : "neutral"}>{c.status.replace("_", " ")}</Badge></td>
                      <td className="px-4 py-2.5 text-slate-500">{c.device && c.status !== "not_started" ? `${c.device} · ${c.bandwidth_class}` : "—"}</td>
                      <td className="px-4 py-2.5 text-slate-500">{c.submitted_at ? dateTime(c.submitted_at) : "—"}</td>
                      <td className="px-4 py-2.5 text-right">
                        {c.roll_no && !scored && <Button variant="ghost" size="sm" onClick={() => resetCode(c)}><Icon name="key" size={14} />New code</Button>}
                        {scored && c.status === "submitted" && <Link to={`/review/s/${c.session_id}`} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm font-semibold text-pink-700 hover:bg-pink-50 dark:text-pink-300 dark:hover:bg-pink-950/40">Open evidence<Icon name="arrowRight" size={14} /></Link>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        {(data.status === "scheduled" || data.status === "live") && (
          <Card className="h-fit bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
            <CardTitle className="text-base">Import candidates</CardTitle>
            <p className="text-xs text-slate-500">Columns: roll_no, name, [language = en | hi]. Each candidate gets a login code, shown once.</p>
            <CsvBox label="Candidates CSV" sample={SAMPLE} busy={busy} onSubmit={upload} rows={rows} error={csvErr} />
          </CardContent></Card>
        )}
      </div>

      <Dialog open={closing} onClose={() => setClosing(false)} title="Close and score this sitting?">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Candidates still writing ({L.in_progress}) are submitted now. Answers sent after this are not accepted. Scoring runs in the background and puts sessions in the review queue.
        </p>
        <div className="mt-5 flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => setClosing(false)}>Cancel</Button>
          <Button variant="danger" className="flex-1" onClick={() => { setClosing(false); act(`/api/admin/sittings/${id}/close`, (r) => setJob({ id: r.job_id, status: "queued", progress: 0, message: "queued" })); }}>Close & score</Button>
        </div>
      </Dialog>

      <Dialog open={!!codes} onClose={() => setCodes(null)} title="Login codes — save them now">
        {codes && (
          <div className="space-y-4">
            <Alert tone="warning">Only a hash is stored, so these codes cannot be shown again. Download them before closing.</Alert>
            <div className="max-h-72 overflow-auto rounded-xl border border-slate-200 dark:border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs text-slate-500 dark:bg-slate-900"><tr><th className="px-3 py-2">Roll no.</th><th className="px-3 py-2">Name</th><th className="px-3 py-2">Code</th></tr></thead>
                <tbody>{codes.candidates.map((c) => <tr key={c.roll_no} className="border-t border-slate-100 dark:border-slate-800"><td className="px-3 py-1.5">{c.roll_no}</td><td className="px-3 py-1.5">{c.name}</td><td className="px-3 py-1.5 font-mono font-semibold">{c.code}</td></tr>)}</tbody>
              </table>
            </div>
            <Button className="w-full" onClick={() => downloadText(`sitting-${id}-codes.csv`, codes.csv)}><Icon name="download" size={16} />Download CSV</Button>
          </div>
        )}
      </Dialog>
    </StaffShell>
  );
}

function Count({ label, n, tone, hint, live }: { label: string; n: number; tone?: string; hint?: string; live?: boolean }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500" />}{label}</p>
      <p className={cn("tabular mt-1 text-3xl font-semibold", tone)}>{n}</p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
}

/** Optional Safe Exam Browser lock-down for laptop/iPad sittings: the Config Key the server checks and the .seb file. */
function SebCard({ id, seb, editable, onSaved }: { id: number; seb: Seb; editable: boolean; onSaved: () => void }) {
  const toast = useToast();
  const [required, setRequired] = useState(seb.required);
  const [key, setKey] = useState("");
  const [file, setFile] = useState<{ name: string; b64: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => setRequired(seb.required), [seb.required]);

  function pick(f: File | undefined) {
    if (!f) return;
    const r = new FileReader();
    r.onload = () => setFile({ name: f.name, b64: String(r.result).split(",").pop() || "" });
    r.readAsDataURL(f);
  }
  async function save() {
    setBusy(true); setErr(null);
    try {
      await api(`/api/admin/sittings/${id}/seb`, { method: "PUT", body: { required, config_key: key || null, file_base64: file?.b64 || null } });
      toast(required ? "Safe Exam Browser is now required" : "Safe Exam Browser settings saved");
      setKey(""); setFile(null); onSaved();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }
  return (
    <Card className="mb-5 bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base"><Icon name="lock" size={18} />Safe Exam Browser</CardTitle>
        <Badge tone={seb.required ? "warning" : "neutral"}>{seb.required ? "Required" : "Off"}</Badge>
      </div>
      <p className="text-sm text-slate-500">
        Optional lock-down for <b>laptops and desktops</b>: they can write the test only inside Safe Exam Browser with this
        sitting's settings. The device is decided automatically: <b>phones and tablets</b> (SEB does not run on Android) use the
        full-screen kiosk mode instead, and a browser that only pretends to be a phone gets a "device check" flag for the reviewer.
        The behaviour signals work either way.
      </p>
      <p className="text-sm">
        Config Key: {seb.config_key_set ? <span className="font-mono">…{seb.config_key_end}</span> : <span className="text-slate-500">not set</span>}
        {" · "}.seb file: {seb.file_uploaded ? <a className="font-semibold text-pink-700 underline dark:text-pink-400" href={seb.config_url || "#"}>uploaded (download)</a> : <span className="text-slate-500">not uploaded</span>}
      </p>
      {editable && (
        <div className="grid gap-3 md:grid-cols-[auto_1fr_1fr_auto] md:items-end">
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-medium">
            <input type="checkbox" className="h-4 w-4 accent-pink-600" checked={required} onChange={(e) => setRequired(e.target.checked)} />
            Require Safe Exam Browser on laptops
          </label>
          <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-500">Config Key (SEB Config Tool → Exam)</span>
            <input value={key} onChange={(e) => setKey(e.target.value.trim())} placeholder={seb.config_key_set ? "keep the current key" : "64 hexadecimal characters"}
              className="h-10 w-full rounded-lg border border-slate-300 bg-white px-3 font-mono text-xs dark:border-slate-700 dark:bg-slate-900" aria-label="Config Key" />
          </label>
          <label className="text-sm"><span className="mb-1 block text-xs font-semibold text-slate-500">.seb file for candidates</span>
            <input type="file" accept=".seb" onChange={(e) => pick(e.target.files?.[0])} aria-label=".seb file"
              className="block w-full text-xs file:mr-2 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 dark:file:bg-slate-800" />
            {file && <span className="text-xs text-slate-500">{file.name}</span>}
          </label>
          <Button onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
        </div>
      )}
      {err && <Alert>{err}</Alert>}
    </CardContent></Card>
  );
}

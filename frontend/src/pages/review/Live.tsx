import { useEffect, useRef, useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { BandBadge, FamilyChip, NetBadge, PriorityBar } from "@/components/review";
import { SnapshotGroups, type SnapshotRow } from "@/components/Snapshots";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, Textarea } from "@/components/ui/form";
import { Alert, Progress } from "@/components/ui/misc";
import { api, errorText } from "@/lib/api";
import { Card, CardContent, CardTitle } from "@/components/ui/card";

import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";
import { Link } from "@/lib/router";
import type { LiveAlert, LiveCandidate, LiveSitting, LiveSnapshot } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const ago = (iso?: string | null) => {
  if (!iso) return "—";
  const s = Math.round((Date.now() - Date.parse(iso)) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s} s ago`;
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  return dateTime(iso);
};

/** /review/live — sittings being written right now. */
export function LiveList() {
  const { data, error, loading, reload } = useApi<LiveSitting[]>("/api/review/live", { poll: 15000 });
  return (
    <StaffShell>
      <Header />
      {loading && !data ? <Loading /> : error || !data ? <ErrorBox error={error} retry={reload} /> : data.length === 0 ? (
        <Card className="p-10 text-center text-slate-500"><Icon name="inbox" size={32} className="mx-auto mb-2" />No sitting is live right now. An admin opens one from Tests & sittings.</Card>
      ) : (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.map((s) => (
            <Link key={s.id} to={`/review/live/${s.id}`} className="block rounded-2xl border border-slate-200 bg-white p-4 transition-colors hover:border-slate-400 dark:hover:border-slate-600 dark:border-slate-800 dark:bg-slate-900">
              <div className="flex items-center justify-between gap-2"><p className="font-semibold">{s.title}</p><LiveDot /></div>
              <p className="mt-1 text-sm text-slate-500">{dateTime(s.starts_at)} → {dateTime(s.ends_at)}</p>
              <p className="mt-3 text-sm"><b className="tabular text-sky-600">{s.writing}</b> writing now · <b className="tabular text-emerald-600">{s.submitted}</b> submitted</p>
            </Link>
          ))}
        </div>
      )}
    </StaffShell>
  );
}

function Header({ children }: { children?: React.ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">Live monitor <LiveDot /></h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">
          While a sitting is being written, the trained FairProctor model re-scores everyone's answers so far, and raw alerts
          show who left the test screen, pasted, or had a second person in view. It is an early signal for watching, not a
          decision: the full score is made when the sitting closes.
        </p>
      </div>
      {children}
    </div>
  );
}
const LiveDot = () => <span className="inline-flex items-center gap-1.5 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-semibold text-rose-700 dark:bg-rose-950 dark:text-rose-300"><span className="h-1.5 w-1.5 animate-pulse rounded-full bg-rose-500" />LIVE</span>;

/** /review/live/:id — candidates ranked by live risk, plus the alert feed. Refreshes every 10 s. */
export function LiveMonitor({ id }: { id: number }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<LiveSnapshot>(`/api/review/live/${id}`, { poll: 10000 });
  const [only, setOnly] = useState<string | null>(null);
  const seen = useRef<Set<string> | null>(null);
  const [, tick] = useState(0);
  useEffect(() => { const t = setInterval(() => tick((n) => n + 1), 5000); return () => clearInterval(t); }, []);

  // pop up alerts that arrived since the last refresh
  useEffect(() => {
    if (!data) return;
    const keys = data.alerts.map((a) => `${a.session_id}|${a.kind}|${a.at}`);
    if (seen.current) {
      const fresh = data.alerts.filter((a, i) => !seen.current!.has(keys[i]));
      fresh.slice(0, 3).forEach((a) => toast(`${label(a)} · ${a.who} ${a.text}`, a.kind === "second_person" ? "danger" : "info"));
    }
    seen.current = new Set(keys);
  }, [data]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !data) return <StaffShell><Header /><Loading /></StaffShell>;
  if (error || !data) return <StaffShell><Header /><ErrorBox error={error} retry={reload} /></StaffShell>;
  const m = data.model;
  const coding = data.kind === "coding";
  const cands = only ? data.candidates.filter((c) => c.session_id === only) : data.candidates;
  const alerts = only ? data.alerts.filter((a) => a.session_id === only) : data.alerts;
  const ended = data.candidates.filter((c) => c.terminated);

  return (
    <StaffShell>
      <Link to="/review/live" className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />Live sittings</Link>
      <Header />
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold">{data.sitting.title}</h2>
        {coding && <Badge tone="brand"><Icon name="code" size={12} />Coding</Badge>}
        <Badge tone={data.sitting.status === "live" ? "success" : "neutral"}>{data.sitting.status}</Badge>
        <span className="text-sm text-slate-500">join code <b className="font-mono">{data.sitting.join_code}</b></span>
      </div>
      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Writing now" n={data.counts.in_progress} tone="text-sky-600" />
        <Stat label="Submitted" n={data.counts.submitted} tone="text-emerald-600" />
        <Stat label="Not started" n={data.counts.not_started} />
        <div className="rounded-2xl border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Model</p>
          <p className="mt-1 font-semibold">{m.error ? "Model run failed" : m.ran_at ? `Last run ${ago(m.ran_at)}` : "Running…"}</p>
          <p className="text-xs text-slate-500">every {m.every_s} s · needs {m.min_answers}+ answers{m.version ? ` · v${m.version}` : ""}</p>
        </div>
      </div>
      {data.sitting.status === "live" && ended.length > 0 && (
        <Alert tone="warning" className="mb-5">
          <p className="font-semibold">{ended.length === 1 ? "1 test was" : `${ended.length} tests were`} ended by a rule and {ended.length === 1 ? "waits" : "wait"} for a reviewer</p>
          <p className="mt-0.5">Any reviewer can look at the snapshots and reopen it while this sitting is open. The candidate keeps the answers and gets the closed minutes back.</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {ended.map((c) => (
              <button key={c.session_id} onClick={() => setOnly(c.session_id)} id={`reopen-pick-${c.session_id}`}
                className={cn("rounded-full border px-3 py-1 text-xs font-semibold", only === c.session_id ? "border-amber-600 bg-amber-100 dark:bg-amber-900/60" : "border-amber-300 bg-white hover:bg-amber-100 dark:border-amber-800 dark:bg-slate-900")}>
                {c.who} · {(c.terminated || "").replace("_", " ")}
              </button>
            ))}
          </div>
        </Alert>
      )}
      {data.sitting.status !== "live" && (
        <Card className="mb-5 p-4 text-sm">This sitting is {data.sitting.status}. {data.sitting.status === "scored" && <Link to={`/review?sitting=${id}`} className="font-semibold text-pink-700 underline dark:text-pink-400">Open the review queue</Link>}</Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_24rem]">
        <div className="min-w-0 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Candidates by live risk</h3>
            {only && <button onClick={() => setOnly(null)} className="text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400">Show everyone</button>}
          </div>
          {cands.length === 0 ? <Card className="p-8 text-center text-slate-500">Nobody has started yet.</Card> : cands.map((c) => (
            <div key={c.session_id} className="space-y-2">
              <CandidateRow c={c} lines={data.priority_lines} minAnswers={coding ? 1 : m.min_answers} coding={coding} selected={only === c.session_id} canReopen={data.sitting.status === "live"}
                onSelect={() => setOnly(only === c.session_id ? null : c.session_id)} />
              {c.terminated && only === c.session_id && data.sitting.status === "live" && <ReopenPanel c={c} onDone={() => reload(true)} />}
            </div>
          ))}
        </div>
        <aside className="lg:sticky lg:top-20 lg:self-start">
          <Card className="bg-white dark:bg-slate-950"><CardContent className="pt-5">
            <CardTitle className="flex items-center gap-2 text-base"><Icon name="alert" size={18} className="text-rose-500" />Alerts {only && <span className="text-sm font-normal text-slate-500">· one candidate</span>}</CardTitle>
            <p className="mt-1 text-xs text-slate-500">Facts from the test screen and camera numbers. A single face check with two people (someone walking past) is not an alert.</p>
            {alerts.length === 0 ? <p className="mt-4 text-sm text-slate-500">No alerts.</p> : (
              <ol className="mt-3 max-h-[60vh] space-y-2 overflow-y-auto pr-1">
                {alerts.map((a, i) => <AlertItem key={i} a={a} onClick={() => setOnly(a.session_id)} />)}
              </ol>
            )}
          </CardContent></Card>
        </aside>
      </div>
    </StaffShell>
  );
}

const KIND: Record<LiveAlert["kind"], { icon: IconName; c: string; label: string }> = {
  left_tab: { icon: "window", c: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300", label: "Left screen" },
  paste: { icon: "paste", c: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300", label: "Paste" },
  second_person: { icon: "users", c: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300", label: "Second person" },
  phone: { icon: "phone", c: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300", label: "Phone" },
  terminated: { icon: "lock", c: "bg-rose-600 text-white", label: "Test ended" },
};
const label = (a: LiveAlert) => KIND[a.kind].label;

function AlertItem({ a, onClick }: { a: LiveAlert; onClick: () => void }) {
  const k = KIND[a.kind];
  return (
    <li>
      <button onClick={onClick} className="flex w-full gap-2.5 rounded-xl p-2 text-left hover:bg-slate-50 dark:hover:bg-slate-900">
        <span className={cn("mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full", k.c)}><Icon name={k.icon} size={14} /></span>
        <span className="min-w-0 text-sm"><b>{a.who}</b> {a.text}<span className="block text-xs text-slate-500">{ago(a.at)}</span></span>
      </button>
    </li>
  );
}

function CandidateRow({ c, lines, minAnswers, selected, onSelect, coding, canReopen }: { c: LiveCandidate; lines: LiveSnapshot["priority_lines"]; minAnswers: number; selected: boolean; onSelect: () => void; coding?: boolean; canReopen?: boolean }) {
  const s = c.signals;
  const chips: { icon: IconName; text: string; warn: boolean }[] = [
    { icon: "window", text: s.left_tab ? `Left screen ${s.left_tab}× · ${s.away_s} s` : "Stayed on screen", warn: s.left_tab > 0 },
    { icon: "paste", text: s.pastes ? `Pasted ${s.pastes}× · ${s.paste_chars} chars` : "No paste", warn: s.pastes > 0 },
    { icon: "users", text: s.frames ? (s.two_faces ? `2+ faces in ${s.two_faces} checks` : "One face") : "No camera numbers", warn: s.two_faces >= 2 },
  ];
  if (s.no_face_pct != null && s.no_face_pct >= 10) chips.push({ icon: "cameraOff", text: `Face not seen ${s.no_face_pct}%`, warn: false });
  if (s.pauses) chips.push({ icon: "pause", text: `${s.pauses} long pause${s.pauses > 1 ? "s" : ""}`, warn: false });
  const rc = c.rules?.counts;
  if (rc?.terminated) chips.unshift({ icon: "lock", text: `Test ended (${rc.terminated.replace("_", " ")})${canReopen && !selected ? " · select to review and reopen" : ""}`, warn: true });
  if (rc?.history?.length) chips.push({ icon: "refresh", text: `Reopened ${rc.history.length}× by a reviewer`, warn: false });
  if (rc?.phone) chips.push({ icon: "phone", text: `Phone seen ${rc.phone}×`, warn: true });
  if (rc?.multi_face) chips.push({ icon: "users", text: `2+ faces for 5 s: ${rc.multi_face}×`, warn: rc.multi_face > 0 });
  if (rc?.relogins) chips.push({ icon: "user", text: `Logged in again ${rc.relogins}×`, warn: rc.relogins >= 2 });
  if (rc?.disconnects) chips.push({ icon: "wifiOff", text: `Disconnected ${rc.disconnects}×`, warn: rc.disconnects > 5 });
  if (rc?.device?.mismatch) chips.push({ icon: "monitor", text: rc.device.seb_exempt ? "Device check: says phone, looks like a laptop (skipped SEB)" : "Device check: says phone, looks like a laptop", warn: true });
  if (rc?.fullscreen_exits) chips.push({ icon: "window", text: `Left full screen ${rc.fullscreen_exits}× · noted only`, warn: false });
  if (s.mic) chips.push({ icon: s.mic === "on" ? "mic" : "micOff", warn: false,
    text: s.speech ? `Speech-like sound ${s.speech}× · not counted alone` : s.mic === "on" ? "Mic on · no talking-like sound" : "Mic off" });
  return (
    <button onClick={onSelect} className={cn("block w-full rounded-2xl border bg-white p-4 text-left transition dark:bg-slate-950",
      selected ? "border-pink-500 ring-2 ring-pink-500/30" : "border-slate-200 hover:border-slate-300 dark:border-slate-800 dark:hover:border-slate-700")}>
      <div className="grid gap-3 md:grid-cols-[13rem_1fr]">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <p className="font-semibold">{c.name || c.who}</p>
            <span className={cn("h-2 w-2 rounded-full", c.status === "in_progress" ? "animate-pulse bg-sky-500" : "bg-emerald-500")} title={c.status} />
          </div>
          <p className="text-xs text-slate-500">{c.name ? `${c.roll_no || c.email || ""} · ${c.who}` : c.status === "in_progress" ? "writing" : "submitted"} · <NetBadge bandwidth={c.bandwidth} device={c.device} /></p>
          <Progress value={(c.answered / Math.max(1, c.n_items)) * 100} label="Answered" className="h-1.5" />
          <p className="text-xs text-slate-500"><span className="tabular">{c.answered}/{c.n_items}</span> {coding ? "solved" : "answered"} · seen {ago(c.last_seen)}</p>
        </div>
        <div className="min-w-0 space-y-2">
          {c.risk == null ? (
            <p className="text-sm text-slate-500">Live risk: too early (needs {coding ? "a first run or submit" : `${minAnswers}+ answers`})</p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <div className="w-56 max-w-full"><PriorityBar value={c.risk} band={c.band!} lines={lines} /></div>
              <BandBadge band={c.band!} />
              {c.trend ? <span className={cn("tabular text-xs font-semibold", c.trend > 0 ? "text-rose-600" : "text-emerald-600")}>{c.trend > 0 ? "▲" : "▼"} {Math.abs(c.trend)}</span> : null}
              <div className="flex flex-wrap gap-1">{c.families.map((f) => <FamilyChip key={f} family={f} />)}</div>
            </div>
          )}
          {c.headline && <p className="line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{c.headline}</p>}
          <div className="flex flex-wrap gap-1.5">
            {chips.map((ch, i) => (
              <span key={i} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
                ch.warn ? "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300")}>
                <Icon name={ch.icon} size={12} />{ch.text}
              </span>
            ))}
          </div>
        </div>
      </div>
    </button>
  );
}

function Stat({ label, n, tone }: { label: string; n: number; tone?: string }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("tabular mt-1 text-3xl font-semibold", tone)}>{n}</p>
    </div>
  );
}

const PHASE = { before: "Before", at: "At the moment", after: "5 s after" } as const;

/** A test a proctoring rule ended: any reviewer looks at the snapshots and the counts and can reopen it while the
 *  sitting is open. The candidate keeps the answers and gets the closed minutes back. */
function ReopenPanel({ c, onDone }: { c: LiveCandidate; onDone: () => void }) {
  const toast = useToast();
  const snaps = useApi<{ days: number; snapshots: SnapshotRow[] }>(`/api/review/sessions/${encodeURIComponent(c.session_id)}/snapshots`);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function reopen() {
    if (note.trim().length < 5) { setErr("Write a short reason (what you saw), at least 5 characters."); return; }
    setBusy(true); setErr(null);
    try {
      const r = await api<{ minutes_back: number }>(`/api/review/sessions/${encodeURIComponent(c.session_id)}/reinstate`, { body: { note: note.trim() } });
      toast(`Test reopened · ${r.minutes_back} min given back. The candidate sees a Continue button.`, "success");
      setNote(""); onDone();
    } catch (e) { setErr(errorText(e)); }
    finally { setBusy(false); }
  }
  return (
    <Card className="border-rose-200 bg-white dark:border-rose-900 dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <CardTitle className="flex items-center gap-2 text-base"><Icon name="lock" size={18} className="text-rose-600" />Ended by a rule: review and reopen</CardTitle>
      <ul className="space-y-1 text-sm text-slate-700 dark:text-slate-300">
        {(c.rules?.flags || []).map((f, i) => <li key={i} className="flex gap-2"><Icon name="info" size={14} className="mt-0.5 shrink-0 text-slate-400" />{f.text}</li>)}
      </ul>
      {snaps.data && snaps.data.snapshots.length > 0
        ? <SnapshotGroups rows={snaps.data.snapshots} reasonText={(_r, label) => label} phaseText={(p) => PHASE[p]} />
        : <p className="text-sm text-slate-500">No snapshots for this test.</p>}
      <Field id={`reopen-${c.session_id}`} label="Why reopen? (kept in the record)">
        <Textarea id={`reopen-${c.session_id}`} value={note} onChange={(e) => { setNote(e.target.value); setErr(null); }} placeholder="e.g. the photo shows a TV remote, not a phone" className="min-h-20" />
      </Field>
      {err && <Alert>{err}</Alert>}
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={reopen} disabled={busy}><Icon name="refresh" size={16} />{busy ? "Reopening…" : "Reopen the test"}</Button>
        <span className="text-xs text-slate-500">Answers are kept, the closed minutes are given back, and the rule that ended it counts from 0 again. Any reviewer can do this while the sitting is open.</span>
      </div>
    </CardContent></Card>
  );
}

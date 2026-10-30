import { useMemo, useRef, useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { CodePanel, CodingTimeline } from "@/components/CodeReview";
import { BandBadge, clock, FamilyChip, NetBadge, PriorityBar } from "@/components/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/form";
import { Alert } from "@/components/ui/misc";
import { SnapshotGroups, type SnapshotRow } from "@/components/Snapshots";
import { useToast } from "@/components/ui/toast";
import { api, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";
import { Link } from "@/lib/router";
import type { SessionDetail } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Session({ id }: { id: string }) {
  const { data, error, loading, slow, reload } = useApi<SessionDetail>(`/api/review/sessions/${encodeURIComponent(id)}`);
  const [at, setAt] = useState<number | null>(null);
  const tl = useRef<HTMLDivElement>(null);
  const jump = (t: number) => { setAt(t); tl.current?.scrollIntoView({ behavior: "smooth", block: "center" }); };

  return (
    <StaffShell>
      <Link to="/review" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />Review queue</Link>
      {loading && !data ? <Loading slow={slow} /> : error || !data ? <ErrorBox error={error} retry={reload} /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_22rem]">
          <div className="min-w-0 space-y-5">
            <Header d={data} />
            {data.also_viewing.length > 0 && <Alert tone="info">Also looking at this session now: {data.also_viewing.join(", ")}</Alert>}
            <Card className="bg-white dark:bg-slate-950"><CardContent className="pt-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">Summary</p>
              <p className="mt-1 text-lg leading-snug">{data.explanation.headline}</p>
            </CardContent></Card>
            {data.kind === "coding" && <CodePanel d={data} />}
            <div ref={tl}>{data.kind === "coding" ? <CodingTimeline d={data} at={at} onPick={setAt} /> : <Timeline d={data} at={at} onPick={setAt} />}</div>
            {data.rules && data.rules.flags.length > 0 && <RulesCard r={data.rules} />}
            <Reasons d={data} onMoment={jump} />
            <Snapshots id={id} reference={data.meta.reference} onMoment={jump} />
            {data.explanation.context.length > 0 && (
              <Card><CardContent className="pt-5">
                <CardTitle className="flex items-center gap-2 text-base"><Icon name="shield" size={18} className="text-emerald-600" />Not counted against this candidate</CardTitle>
                <ul className="mt-3 space-y-1.5 text-sm text-slate-600 dark:text-slate-300">
                  {data.explanation.context.map((c, i) => <li key={i} className="flex gap-2"><Icon name="check" size={15} className="mt-0.5 shrink-0 text-emerald-600" />{c}</li>)}
                </ul>
              </CardContent></Card>
            )}
          </div>
          <aside className="space-y-5 lg:sticky lg:top-20 lg:self-start">
            <Decision d={data} onDone={() => reload(true)} />
            {data.appeal && (
              <Card><CardContent className="space-y-2 pt-5">
                <div className="flex items-center justify-between"><CardTitle className="text-base">Candidate's explanation</CardTitle><Badge tone={data.appeal.status === "open" ? "warning" : "neutral"}>{data.appeal.status}</Badge></div>
                <p className="whitespace-pre-wrap text-sm">{data.appeal.text}</p>
                {data.appeal.status === "open" && <Link to="/review/appeals" className="text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400">Answer in Appeals →</Link>}
              </CardContent></Card>
            )}
            {data.reviews.length > 0 && (
              <Card><CardContent className="pt-5">
                <CardTitle className="text-base">History</CardTitle>
                <ol className="mt-3 space-y-3">
                  {data.reviews.map((r, i) => (
                    <li key={i} className="border-l-2 border-slate-300 pl-3 text-sm dark:border-slate-700">
                      <p className="font-semibold capitalize">{r.decision.replace("_", " ")} <span className="font-normal text-slate-500">· {r.reviewer} · {dateTime(r.at)}</span></p>
                      {r.note && <p className="text-slate-600 dark:text-slate-300">{r.note}</p>}
                    </li>
                  ))}
                </ol>
              </CardContent></Card>
            )}
          </aside>
        </div>
      )}
    </StaffShell>
  );
}

/** Proctoring rules: fixed limits next to the model's ranking (phone, multi-face, tab switches, logins, disconnects). */
function RulesCard({ r }: { r: NonNullable<SessionDetail["rules"]> }) {
  const tone = { high: "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200",
    medium: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
    info: "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300" };
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <CardTitle className="flex items-center gap-2 text-base"><Icon name="shield" size={18} />Proctoring rules</CardTitle>
      <ul className="space-y-1.5">
        {r.flags.map((f, i) => <li key={i} className={cn("rounded-lg border px-3 py-2 text-sm", tone[f.level])}>{f.text}</li>)}
      </ul>
      <p className="text-xs text-slate-500">Fixed limits checked on the device and again on the server. An ended test is not a finding: confirm or clear it below.</p>
    </CardContent></Card>
  );
}

const PHASE = { before: "Before", at: "At the moment", after: "5 s after" } as const;

/** Camera snapshots at flagged moments, loaded separately (each view is audited). */
function Snapshots({ id, reference, onMoment }: { id: string; reference: boolean; onMoment: (t: number) => void }) {
  const { data, error, loading } = useApi<{ days: number; snapshots: SnapshotRow[] }>(`/api/review/sessions/${encodeURIComponent(id)}/snapshots`);
  const title = <CardTitle className="flex items-center gap-2 text-base"><Icon name="camera" size={18} />Camera snapshots at flagged moments</CardTitle>;
  if (loading && !data) return null;
  if (error || !data || data.snapshots.length === 0) {
    const why = error ? "Could not load the snapshots. If the server was just updated, restart it so the new database table is created."
      : reference ? "None: this is a generated reference/demo session, not a test taken with a camera."
      : "None: nothing was flagged while the camera was on, or this test was taken before snapshots were turned on.";
    return (
      <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
        {title}
        <p className={cn("text-sm", error ? "text-amber-700 dark:text-amber-300" : "text-slate-500")}>{why}</p>
      </CardContent></Card>
    );
  }
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        {title}
        <Button variant="ghost" size="sm" onClick={() => onMoment(data.snapshots[0].t)}>Show on timeline</Button>
      </div>
      <p className="text-sm text-slate-500">Use them to tell someone walking past from someone helping. They are not used by the model,
        the candidate can see them, and they are deleted after {data.days} days.</p>
      <SnapshotGroups rows={data.snapshots} reasonText={(_r, label) => label} phaseText={(p) => PHASE[p]} />
    </CardContent></Card>
  );
}

function Header({ d }: { d: SessionDetail }) {
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-4 pt-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{d.pseudonym}</h1>
            <BandBadge band={d.score.band} />
            {d.meta.reference && <Badge tone="outline" title="From the reference data used to calibrate the sitting">Reference session</Badge>}
          </div>
          <p className="mt-1 text-sm text-slate-500">{d.sitting.title} · rank #{d.score.rank} · submitted {dateTime(d.meta.submitted_at)}</p>
        </div>
        <div className="text-right text-xs text-slate-500">model {d.score.model_version}<br />scored {dateTime(d.score.scored_at)}</div>
      </div>
      <PriorityBar value={d.score.priority} band={d.score.band} lines={d.priority_lines} big />
      <div className="flex flex-wrap gap-2 text-xs">
        <Badge><NetBadge bandwidth={d.meta.bandwidth_class} device={d.meta.device} /> {d.meta.device} · {d.meta.bandwidth_class} bandwidth</Badge>
        {d.kind === "coding" ? <Badge tone="brand"><Icon name="code" size={12} />Coding test</Badge> : <>
          <Badge>Pre-check light: {d.meta.precheck_light || "—"}</Badge>
          <Badge>Framing: {(d.meta.precheck_framing || "—").replace("_", " ")}</Badge></>}
      </div>
      {d.identity ? (
        <Alert tone="warning" className="flex items-center gap-2"><Icon name="user" size={16} />{d.identity.name}{d.identity.roll_no && <> · {d.identity.roll_no}</>}{d.identity.email && <> · {d.identity.email}</>}</Alert>
      ) : (
        <p className="flex items-center gap-1.5 text-xs text-slate-500"><Icon name="lock" size={13} />Name and roll no. are shown only after a reviewer confirms.</p>
      )}
    </CardContent></Card>
  );
}

type Span = { a: number; b: number };
function spans(events: SessionDetail["events"], start: string, end: string, D: number): Span[] {
  const out: Span[] = [];
  let open: number | null = null;
  for (const e of events) {
    if (e.type === start && open === null) open = e.t;
    if (e.type === end && open !== null) { out.push({ a: open, b: e.t }); open = null; }
  }
  if (open !== null) out.push({ a: open, b: D });
  return out;
}

function Timeline({ d, at, onPick }: { d: SessionDetail; at: number | null; onPick: (t: number) => void }) {
  const D = useMemo(() => Math.max(60, ...d.events.map((e) => e.t), ...d.frames.map((f) => f.t)), [d]);
  const pct = (t: number) => `${(Math.max(0, Math.min(D, t)) / D) * 100}%`;
  const answers = d.events.filter((e) => e.type === "answer");
  const focus = spans(d.events, "focus_lost", "focus_gained", D);
  const idle = spans(d.events, "idle_start", "idle_end", D);
  const pastes = d.events.filter((e) => e.type === "paste");
  const speech = d.events.filter((e) => e.type === "speech_like");
  const fullscreen = spans(d.events, "fullscreen_exit", "fullscreen_enter", D);
  const kiosk = d.events.some((e) => e.type === "fullscreen_exit" || e.type === "fullscreen_enter");
  const micUsed = d.events.some((e) => e.type === "mic_on" || e.type === "speech_like");
  const step = D > 3600 ? 600 : D > 1200 ? 300 : D > 300 ? 60 : 30;
  const ticks = Array.from({ length: Math.floor(D / step) + 1 }, (_, i) => i * step);
  const moments = d.explanation.moments;
  const sel = at === null ? null : moments.reduce<null | (typeof moments)[0]>((b, m) => (b && Math.abs(b.t - at) <= Math.abs(m.t - at) ? b : m), null);

  const Lane = ({ label, children }: { label: string; children: React.ReactNode }) => (
    <div className="grid grid-cols-[6.5rem_1fr] items-center gap-3">
      <span className="text-xs font-semibold text-slate-500">{label}</span>
      <div className="relative h-6 rounded-md bg-slate-100 dark:bg-slate-900">{children}</div>
    </div>
  );
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">Timeline</CardTitle>
        <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
          <Key c="bg-emerald-500" l="correct" /><Key c="bg-rose-500" l="wrong" /><Key c="bg-amber-400" l="left window" />
          <Key c="bg-violet-400" l="no input" /><Key c="bg-teal-500" l="paste" /><Key c="bg-sky-400" l="head down" /><Key c="bg-rose-600" l="2+ faces" /><Key c="bg-slate-400" l="no face" /><Key c="bg-orange-500" l="phone in view" />{micUsed && <Key c="bg-indigo-400" l="speech-like sound" />}{kiosk && <Key c="bg-slate-500" l="out of full screen" />}
        </div>
      </div>
      <div className="relative space-y-1.5">
        <Lane label="Answers">
          {answers.map((e) => (
            <span key={e.seq} title={`Q${e.item + 1} · ${e.option || "–"} · ${clock(e.t)}${e.correct === 1 ? " · correct" : e.correct === 0 ? " · wrong" : ""}`}
              className={cn("absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-white dark:ring-slate-950",
                e.correct === 1 ? "bg-emerald-500" : e.correct === 0 ? "bg-rose-500" : "bg-slate-400")} style={{ left: pct(e.t) }} />
          ))}
        </Lane>
        <Lane label="Left window">
          {focus.map((s, i) => <span key={i} title={`${clock(s.a)}–${clock(s.b)}`} className="absolute inset-y-1 rounded bg-amber-400" style={{ left: pct(s.a), width: `max(3px, ${((s.b - s.a) / D) * 100}%)` }} />)}
        </Lane>
        <Lane label="No input">
          {idle.map((s, i) => <span key={i} title={`${clock(s.a)}–${clock(s.b)} (${Math.round(s.b - s.a)} s)`} className="absolute inset-y-1 rounded bg-violet-400" style={{ left: pct(s.a), width: `max(3px, ${((s.b - s.a) / D) * 100}%)` }} />)}
        </Lane>
        <Lane label="Paste">
          {pastes.map((e) => <span key={e.seq} title={`${e.chars} chars · Q${e.item + 1} · ${clock(e.t)}`} className="absolute inset-y-0.5 w-1 -translate-x-1/2 rounded bg-teal-500" style={{ left: pct(e.t) }} />)}
        </Lane>
        <Lane label={`Camera (${d.frames.length})`}>
          {d.frames.map((f, i) => {
            const c = f.faces > 1 ? "bg-rose-600" : !f.face_visible ? "bg-slate-400" : f.gaze === "down" ? "bg-sky-400" : "bg-emerald-300/60 dark:bg-emerald-700/50";
            return <span key={i} title={`${clock(f.t)} · ${f.faces} face(s) · ${f.gaze}`} className={cn("absolute inset-y-1 w-[3px] -translate-x-1/2 rounded-sm", c)} style={{ left: pct(f.t) }} />;
          })}
        </Lane>
        {d.frames.some((f) => f.phone != null) && (
          <Lane label="Phone in view">
            {d.frames.filter((f) => (f.phone ?? 0) > 0).map((f, i) => (
              <span key={i} title={`${clock(f.t)} · phone seen in ${Math.round((f.phone ?? 0) * 100)}% of checks (on the candidate's device; no image)`}
                className="absolute inset-y-1 w-[3px] -translate-x-1/2 rounded-sm bg-orange-500" style={{ left: pct(f.t), opacity: 0.35 + 0.65 * (f.phone ?? 0) }} />
            ))}
          </Lane>
        )}
        {kiosk && (
          <Lane label={`Full screen (${fullscreen.length})`}>
            {fullscreen.map((s, i) => <span key={i} title={`${clock(s.a)}–${clock(s.b)} out of full screen (noted only, never a rule)`} className="absolute inset-y-1 rounded bg-slate-500" style={{ left: pct(s.a), width: `max(3px, ${((s.b - s.a) / D) * 100}%)` }} />)}
          </Lane>
        )}
        {micUsed && (
          <Lane label={`Sound (${speech.length})`}>
            {speech.map((e) => (
              <span key={e.seq} title={`${clock(Math.max(0, e.t - 5))}–${clock(e.t)} · speech-like sound, ${e.meta?.s ?? "?"} s of voice (on the candidate's phone; no audio). Never counted alone.`}
                className="absolute inset-y-1 rounded bg-indigo-400" style={{ left: pct(Math.max(0, e.t - 5)), width: `max(3px, ${(5 / D) * 100}%)` }} />
            ))}
          </Lane>
        )}
        <div className="pointer-events-none absolute inset-y-0 left-[7.25rem] right-0">
          {moments.map((m, i) => (
            <button key={i} onClick={() => onPick(m.t)} title={`${m.at} · ${m.label}`}
              className={cn("pointer-events-auto absolute -top-1 bottom-0 w-2 -translate-x-1/2 cursor-pointer", "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2",
                sel?.t === m.t ? "after:w-0.5 after:bg-pink-600" : "after:bg-pink-400/50")} style={{ left: pct(m.t) }} aria-label={`Moment ${m.at}: ${m.label}`} />
          ))}
        </div>
      </div>
      <div className="relative ml-[7.25rem] h-4 text-[10px] text-slate-400">
        {ticks.map((t) => <span key={t} className="absolute -translate-x-1/2 tabular" style={{ left: pct(t) }}>{clock(t)}</span>)}
      </div>
      {sel && (
        <p className="animate-fade-in rounded-lg bg-pink-50 px-3 py-2 text-sm text-pink-900 dark:bg-pink-950/40 dark:text-pink-200">
          <b className="tabular">{sel.at}</b> — {sel.label}
        </p>
      )}
    </CardContent></Card>
  );
}
const Key = ({ c, l }: { c: string; l: string }) => <span className="inline-flex items-center gap-1"><span className={cn("h-2.5 w-2.5 rounded-sm", c)} />{l}</span>;

function Reasons({ d, onMoment }: { d: SessionDetail; onMoment: (t: number) => void }) {
  const partners = d.explanation.partners || [];
  return (
    <div className="space-y-3">
      <h2 className="text-lg font-semibold">Why this session is in the queue</h2>
      {d.explanation.reasons.length === 0 && <Card className="p-5 text-sm text-slate-500">No reason stood out. This session is ranked for completeness.</Card>}
      {d.explanation.reasons.map((r, i) => (
        <Card key={i} className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2"><FamilyChip family={r.family} /><h3 className="font-semibold">{r.title}</h3></div>
            <div className="flex w-36 items-center gap-2 text-xs text-slate-500" title="Share of this session's priority that comes from this reason">
              <div className="h-1.5 flex-1 rounded-full bg-slate-200 dark:bg-slate-800"><div className="brand-bg h-full rounded-full" style={{ width: `${r.weight * 100}%` }} /></div>
              <span className="tabular">{Math.round(r.weight * 100)}%</span>
            </div>
          </div>
          {r.evidence.map((e, j) => <EvidenceBox key={j} e={e} onMoment={onMoment} />)}
          {!r.evidence.length && r.fallback && <p className="text-sm text-slate-600 dark:text-slate-300">{r.fallback}</p>}
          {r.family === "match" && partners.length > 0 && (
            <p className="text-sm text-slate-600 dark:text-slate-300">Matched with:{" "}
              {partners.map((p, k) => <span key={p.session_id}>{k > 0 && ", "}<Link to={`/review/s/${encodeURIComponent(p.session_id)}`} className="font-semibold text-pink-700 hover:underline dark:text-pink-400">{p.pseudonym}</Link></span>)}
            </p>
          )}
        </CardContent></Card>
      ))}
    </div>
  );
}

function EvidenceBox({ e, onMoment }: { e: SessionDetail["explanation"]["reasons"][0]["evidence"][0]; onMoment: (t: number) => void }) {
  const [all, setAll] = useState(false);
  const shown = all ? e.moments : e.moments.slice(0, 8);
  return (
    <div className="rounded-xl bg-slate-50 p-3 dark:bg-slate-900">
      <p className="text-sm leading-relaxed">{e.text}</p>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {shown.map((m, k) => (
          <button key={k} onClick={() => onMoment(m.t)} className="inline-flex items-center gap-1 rounded-full bg-pink-100 px-2 py-0.5 text-xs font-semibold text-pink-800 hover:bg-pink-200 dark:bg-pink-950 dark:text-pink-300">
            <Icon name="play" size={10} /><span className="tabular">{clock(m.t)}</span> {m.label}
          </button>
        ))}
        {e.moments.length > 8 && (
          <button onClick={() => setAll(!all)} className="rounded-full px-2 py-0.5 text-xs font-semibold text-slate-600 underline-offset-2 hover:underline dark:text-slate-300">
            {all ? "Show fewer" : `+${e.moments.length - 8} more`}
          </button>
        )}
      </div>
    </div>
  );
}

type Choice = "clear" | "need_more" | "confirm";
function Decision({ d, onDone }: { d: SessionDetail; onDone: () => void }) {
  const toast = useToast();
  const [choice, setChoice] = useState<Choice | null>(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const opts: { v: Choice; label: string; help: string; c: string }[] = [
    { v: "clear", label: "Clear", help: "Nothing wrong after looking", c: "peer-checked:border-emerald-500 peer-checked:bg-emerald-50 dark:peer-checked:bg-emerald-950/40" },
    { v: "need_more", label: "Need more information", help: "Keep open, ask the test centre", c: "peer-checked:border-amber-500 peer-checked:bg-amber-50 dark:peer-checked:bg-amber-950/40" },
    { v: "confirm", label: "Confirm", help: "The rules were broken (note required)", c: "peer-checked:border-rose-500 peer-checked:bg-rose-50 dark:peer-checked:bg-rose-950/40" },
  ];
  async function send() {
    if (!choice) { setErr("Choose a decision."); return; }
    if (choice === "confirm" && note.trim().length < 10) { setErr("Write what you saw (at least 10 characters) before confirming."); return; }
    setBusy(true); setErr(null);
    try {
      await api(`/api/review/sessions/${encodeURIComponent(d.session_id)}/decision`, { body: { decision: choice, note: note.trim() } });
      toast("Decision saved");
      setChoice(null); setNote("");
      onDone();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <CardTitle className="text-base">Your decision</CardTitle>
      <fieldset className="space-y-2">
        <legend className="sr-only">Decision</legend>
        {opts.map((o) => (
          <label key={o.v} className="block cursor-pointer">
            <input type="radio" name="decision" value={o.v} checked={choice === o.v} onChange={() => { setChoice(o.v); setErr(null); }} className="peer sr-only" />
            <span className={cn("block rounded-xl border-2 border-slate-200 p-3 transition peer-focus-visible:ring-2 peer-focus-visible:ring-pink-500 dark:border-slate-800", o.c)}>
              <span className="block font-semibold">{o.label}</span>
              <span className="block text-xs text-slate-500">{o.help}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <Field id="note" label={choice === "confirm" ? "Note (required)" : "Note (optional)"} error={err}>
        <Textarea id="note" value={note} maxLength={2000} onChange={(e) => { setNote(e.target.value); setErr(null); }} placeholder="What you saw, with times" className="min-h-24 text-sm" aria-invalid={!!err} />
      </Field>
      <Button className="w-full" disabled={busy} onClick={send}>{busy ? "Saving…" : "Save decision"}</Button>
      <p className="text-xs text-slate-500">The candidate sees the outcome and your note (on confirm) and can explain once.</p>
    </CardContent></Card>
  );
}

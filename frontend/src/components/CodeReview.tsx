// Reviewer views for coding sessions: the programs (with the matching program of another candidate side by side)
// and a timeline of runs, submits, typing, pastes and leaving the test window.
import { useState } from "react";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/router";
import type { SessionDetail } from "@/lib/types";
import { CodeBlock } from "./CodeEditor";
import { Icon } from "./Icon";
import { clock } from "./review";
import { Badge } from "./ui/badge";
import { Card, CardContent, CardTitle } from "./ui/card";

const VERDICT: Record<string, string> = { accepted: "Accepted", wrong_answer: "Wrong answer", compile_error: "Compile error",
  runtime_error: "Runtime error", time_limit: "Time limit", output_limit: "Output limit" };
const tone = (v: string) => (v === "accepted" ? "success" : v === "compile_error" || v === "time_limit" ? "warning" : "danger") as "success" | "warning" | "danger";
const LANG: Record<string, string> = { python: "Python", cpp: "C++", java: "Java", javascript: "JavaScript" };

export function CodePanel({ d }: { d: SessionDetail }) {
  const code = d.code || [];
  const [tab, setTab] = useState(Math.max(0, code.findIndex((c) => c.match)));
  if (!code.length) return <Card className="p-5 text-sm text-slate-500">No program was run or submitted.</Card>;
  const c = code[Math.min(tab, code.length - 1)];
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-4 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="flex items-center gap-2 text-base"><Icon name="code" size={18} />Programs</CardTitle>
        <div role="tablist" className="flex flex-wrap gap-1">
          {code.map((x, i) => (
            <button key={x.item} role="tab" aria-selected={i === tab} onClick={() => setTab(i)}
              className={cn("inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-sm font-semibold",
                i === tab ? "bg-pink-50 text-pink-800 dark:bg-pink-950/50 dark:text-pink-200" : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800")}>
              P{x.item + 1}{x.match && <span className="h-2 w-2 rounded-full bg-amber-500" title="matches another program" />}
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <b>P{c.item + 1} · {c.title}</b>
        <Badge tone={tone(c.verdict)}>{VERDICT[c.verdict] || c.verdict}</Badge>
        <span className="text-slate-500">{c.passed}/{c.total} hidden tests · {LANG[c.language] || c.language} · {c.attempts} submit{c.attempts === 1 ? "" : "s"}, {c.runs} run{c.runs === 1 ? "" : "s"} · final at {clock(c.t)}</span>
      </div>
      {c.match ? (
        <>
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            <b>{Math.round(c.match.similarity * 100)}% match</b> with{" "}
            <Link to={`/review/s/${encodeURIComponent(c.match.session_id)}`} className="font-semibold underline">{c.match.pseudonym}</Link>
            {" "}after renaming, spacing and comments are ignored. Matching lines are highlighted on both sides.
          </p>
          <div className="grid gap-3 xl:grid-cols-2">
            <div className="min-w-0"><p className="mb-1 text-xs font-semibold text-slate-500">This candidate</p>
              <CodeBlock code={c.code} language={c.language} marks={c.match.lines} className="max-h-[28rem]" /></div>
            <div className="min-w-0"><p className="mb-1 text-xs font-semibold text-slate-500">{c.match.pseudonym}</p>
              <CodeBlock code={c.match.code} language={c.match.language || c.language} marks={c.match.partner_lines} className="max-h-[28rem]" /></div>
          </div>
        </>
      ) : <CodeBlock code={c.code} language={c.language} className="max-h-[28rem]" />}
    </CardContent></Card>
  );
}

export function CodingTimeline({ d, at, onPick }: { d: SessionDetail; at: number | null; onPick: (t: number) => void }) {
  const typing = d.events.filter((e) => e.type === "code_typing");
  const runs = d.runs || [];
  const D = Math.max(60, ...d.events.map((e) => e.t), ...runs.map((r) => r.t), ...d.frames.map((f) => f.t));
  const pct = (t: number) => `${(Math.max(0, Math.min(D, t)) / D) * 100}%`;
  const pastes = d.events.filter((e) => e.type === "paste");
  const focus: { a: number; b: number }[] = [];
  let open: number | null = null;
  for (const e of d.events) {
    if (e.type === "focus_lost" && open === null) open = e.t;
    if (e.type === "focus_gained" && open !== null) { focus.push({ a: open, b: e.t }); open = null; }
  }
  const maxIns = Math.max(40, ...typing.map((e) => Number(e.meta?.ins || 0)));
  const step = D > 3600 ? 600 : D > 1200 ? 300 : D > 300 ? 60 : 30;
  const moments = d.explanation.moments;
  const sel = at === null ? null : moments.reduce<null | (typeof moments)[0]>((b, m) => (b && Math.abs(b.t - at) <= Math.abs(m.t - at) ? b : m), null);
  const Lane = ({ label, children, h = "h-6" }: { label: string; children: React.ReactNode; h?: string }) => (
    <div className="grid grid-cols-[6.5rem_1fr] items-center gap-3">
      <span className="text-xs font-semibold text-slate-500">{label}</span>
      <div className={cn("relative rounded-md bg-slate-100 dark:bg-slate-900", h)}>{children}</div>
    </div>
  );
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-base">Timeline</CardTitle>
        <div className="flex flex-wrap gap-3 text-[11px] text-slate-500">
          <K c="bg-emerald-500" l="accepted" /><K c="bg-rose-500" l="failed submit" /><K c="bg-slate-400" l="run" />
          <K c="bg-sky-400" l="typing" /><K c="bg-fuchsia-600" l="burst (not typed)" /><K c="bg-teal-500" l="paste" /><K c="bg-amber-400" l="left window" />
        </div>
      </div>
      <div className="relative space-y-1.5">
        <Lane label="Runs & submits">
          {runs.map((r, i) => (
            <span key={i} title={`P${r.item + 1} ${r.kind} · ${VERDICT[r.verdict] || r.verdict} ${r.passed}/${r.total} · ${clock(r.t)}`}
              className={cn("absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-1 ring-white dark:ring-slate-950",
                r.kind === "run" ? "h-2 w-2 bg-slate-400" : r.verdict === "accepted" ? "h-3 w-3 bg-emerald-500" : "h-3 w-3 bg-rose-500")} style={{ left: pct(r.t) }} />
          ))}
        </Lane>
        <Lane label="Typing" h="h-10">
          {typing.map((e) => {
            const ins = Number(e.meta?.ins || 0), burst = Number(e.meta?.max_ins || 0) >= 60 || ins - Number(e.meta?.dele || 0) >= 150;
            return <span key={e.seq} title={`${clock(e.t)} · P${e.item + 1} · +${ins} / −${e.meta?.dele || 0} chars`}
              className={cn("absolute bottom-0 w-[3px] -translate-x-1/2 rounded-t-sm", burst ? "bg-fuchsia-600" : "bg-sky-400")}
              style={{ left: pct(e.t), height: `${Math.max(8, Math.min(100, (ins / maxIns) * 100))}%` }} />;
          })}
        </Lane>
        <Lane label="Paste">
          {pastes.map((e) => <span key={e.seq} title={`${clock(e.t)} · P${e.item + 1} · ${e.chars} chars`}
            className={cn("absolute inset-y-0.5 -translate-x-1/2 rounded bg-teal-500", e.chars >= 120 ? "w-1.5" : "w-1 opacity-60")} style={{ left: pct(e.t) }} />)}
        </Lane>
        <Lane label="Left window">
          {focus.map((s, i) => <span key={i} title={`${clock(s.a)}–${clock(s.b)}`} className="absolute inset-y-1 rounded bg-amber-400" style={{ left: pct(s.a), width: `max(3px, ${((s.b - s.a) / D) * 100}%)` }} />)}
        </Lane>
        <div className="pointer-events-none absolute inset-y-0 left-[7.25rem] right-0">
          {moments.map((m, i) => (
            <button key={i} onClick={() => onPick(m.t)} title={`${m.at} · ${m.label}`} aria-label={`Moment ${m.at}: ${m.label}`}
              className={cn("pointer-events-auto absolute -top-1 bottom-0 w-2 -translate-x-1/2 cursor-pointer after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2",
                sel?.t === m.t ? "after:w-0.5 after:bg-pink-600" : "after:bg-pink-400/50")} style={{ left: pct(m.t) }} />
          ))}
        </div>
      </div>
      <div className="relative ml-[7.25rem] h-4 text-[10px] text-slate-400">
        {Array.from({ length: Math.floor(D / step) + 1 }, (_, i) => i * step).map((t) => <span key={t} className="tabular absolute -translate-x-1/2" style={{ left: pct(t) }}>{clock(t)}</span>)}
      </div>
      {sel && <p className="animate-fade-in rounded-lg bg-pink-50 px-3 py-2 text-sm text-pink-900 dark:bg-pink-950/40 dark:text-pink-200"><b className="tabular">{sel.at}</b> — {sel.label}</p>}
    </CardContent></Card>
  );
}
const K = ({ c, l }: { c: string; l: string }) => <span className="inline-flex items-center gap-1"><span className={cn("h-2.5 w-2.5 rounded-sm", c)} />{l}</span>;

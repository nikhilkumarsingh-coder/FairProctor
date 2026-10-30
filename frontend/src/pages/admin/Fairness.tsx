// Fairness report for one scored sitting: for each group of candidates (shared room, connection, light, device,
// framing; language for coding tests) the share sent to review by FairProctor and by the old rules given the same
// number of review slots. Equal bars mean equal treatment. Every value is also in the table under each chart.
import { useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs } from "@/components/ui/misc";
import { cn } from "@/lib/cn";
import { Link } from "@/lib/router";
import type { FairGap, FairGroup, FairLargest, FairRate, Fairness, FairView } from "@/lib/types";
import { useApi } from "@/lib/useApi";

type Level = "any" | "first";
type Pop = "honest" | "all";
type Sys = "ours" | "old";
const SYS: Record<Sys, { name: string; color: string }> = {
  ours: { name: "FairProctor", color: "var(--viz-ours)" },
  old: { name: "Old rules", color: "var(--viz-old)" },
};

export const pct = (r: number | null | undefined) =>
  r == null ? "—" : r > 0 && r < 0.095 ? `${(r * 100).toFixed(1)}%` : `${Math.round(r * 100)}%`;
const pts = (d: number | null | undefined) => {
  if (d == null) return "—";
  const v = Math.round(d * 100);
  return v === 0 ? "0 pts" : `${v > 0 ? "+" : "−"}${Math.abs(v)} pts`;
};
const ci = (lo: number | null | undefined, hi: number | null | undefined, unit: "pct" | "pts") =>
  lo == null || hi == null ? "" : unit === "pct" ? `95% CI ${pct(lo)}–${pct(hi)}` : `95% CI ${pts(lo).replace(" pts", "")} to ${pts(hi)}`;

const VERDICT: Record<FairGap["verdict"], { label: string; icon: IconName; tone: string }> = {
  higher: { label: "Flagged more often", icon: "alert", tone: "text-amber-700 dark:text-amber-400" },
  lower: { label: "Flagged less often", icon: "info", tone: "text-slate-600 dark:text-slate-300" },
  no_clear_difference: { label: "No clear difference", icon: "checkCircle", tone: "text-emerald-700 dark:text-emerald-400" },
  too_few: { label: "Too few to tell", icon: "info", tone: "text-slate-500" },
};

function niceMax(v: number) {
  for (const s of [0.05, 0.1, 0.2, 0.25, 0.4, 0.5, 0.6, 0.8, 1]) if (v <= s) return s;
  return 1;
}

export default function FairnessPage({ id }: { id: number }) {
  const { data, error, loading, reload } = useApi<Fairness>(`/api/admin/sittings/${id}/fairness`);
  const [level, setLevel] = useState<Level>("any");
  const [pop, setPop] = useState<Pop>("honest");

  if (loading && !data) return <StaffShell><Loading /></StaffShell>;
  if (error || !data) return <StaffShell><ErrorBox error={error} retry={reload} /></StaffShell>;
  const back = <Link to={`/admin/sittings/${id}`} className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />{data.sitting.title}</Link>;
  if (!data.ready || !data.views) {
    return (
      <StaffShell>
        {back}
        <h1 className="text-2xl font-semibold tracking-tight">Fairness report</h1>
        <Card className="mt-5 max-w-xl bg-white dark:bg-slate-950"><CardContent className="pt-5 text-sm text-slate-600 dark:text-slate-300">
          The report appears after the sitting is closed and scored. Press <b>Close & score</b> on the sitting page.
        </CardContent></Card>
      </StaffShell>
    );
  }
  const view = data.views[`${pop}.${level}`];
  const L = data.labels!, W = data.workload![level];
  const max = niceMax(Math.max(0.05, ...view.dimensions.flatMap((d) => d.groups.flatMap((g) => [g.ours.hi ?? 0, g.ours.rate ?? 0, g.old.rate ?? 0]))));
  const what = level === "any" ? "sent to review" : "put in Review first";
  const who = pop === "honest" ? "honest candidates" : "candidates";

  return (
    <StaffShell>
      {back}
      <div className="mb-5 max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Fairness report</h1>
        <p className="mt-2 text-slate-600 dark:text-slate-300">
          Does a shared room, a phone, dim light or a slow connection get {who} {what} more often? Each bar is the share of a
          group that was {what}. <b>Equal bars mean equal treatment.</b>
        </p>
      </div>

      <div className="viz mb-5 flex flex-wrap items-center gap-3">
        <Tabs<Level> value={level} onChange={setLevel} items={[{ value: "any", label: "Sent to review" }, { value: "first", label: "Review first" }]} />
        <Tabs<Pop> value={pop} onChange={setPop} items={[{ value: "honest", label: "Honest candidates" }, { value: "all", label: "Everyone" }]} />
        <div className="ml-auto flex items-center gap-4 text-sm text-slate-600 dark:text-slate-300" aria-label="Legend">
          {(Object.keys(SYS) as Sys[]).map((s) => (
            <span key={s} className="inline-flex items-center gap-2"><span className="h-2.5 w-4 rounded-r-[3px]" style={{ background: SYS[s].color }} />{s === "old" ? "Old rules, same workload" : SYS[s].name}</span>
          ))}
        </div>
      </div>

      <div className="mb-5 grid gap-3 md:grid-cols-3">
        <Largest title="Biggest extra flagging · FairProctor" g={view.largest.ours} />
        <Largest title="Biggest extra flagging · old rules" g={view.largest.old} />
        <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">In this report</p>
          <p className="mt-1 text-3xl font-semibold">{view.n} <span className="text-base font-semibold text-slate-500">{who}</span></p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
            {L.malpractice} malpractice{L.pending ? ` · ${L.pending} waiting for a decision` : ""}{L.reference ? ` · ${L.reference} reference sessions` : ""}
          </p>
          <p className="mt-1 text-xs text-slate-500">Review slots: {W.n} of {data.n} ({pct(W.share)}) for both systems</p>
        </div>
      </div>

      <p className="mb-5 flex max-w-3xl gap-2 text-sm text-slate-500"><Icon name="info" size={16} className="mt-0.5 shrink-0" />{data.old_rules}</p>

      <div className="viz space-y-5">
        {view.dimensions.map((d) => <DimensionCard key={d.key} d={d} max={max} />)}
      </div>
      {view.skipped.length > 0 && (
        <p className="mt-4 text-sm text-slate-500">Not shown: {view.skipped.map((s) => `${s.title} — ${s.reason}`).join(" ")}</p>
      )}

      <Card className="mt-6 max-w-3xl bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5 text-sm text-slate-600 dark:text-slate-300">
        <p className="font-semibold text-slate-900 dark:text-slate-100">How to read this</p>
        <p><b>Honest</b> means reference sessions without planted malpractice (their true labels are known), and real candidates a reviewer cleared or the model cleared. Confirmed cases are left out of the honest view, and so are flagged candidates still waiting for a decision.</p>
        <p>Each gap compares a group with the first group of its chart. The 95% interval (Newcombe) says how sure the gap is: if it crosses zero, the difference may be chance. Small groups give wide intervals.</p>
        {data.sitting.kind === "mcq" && <p>On the 5,000-session evaluation set, honest low-bandwidth candidates were sent to review 3 points more often than normal ones with FairProctor, and 44 points more often with the old rules at the same workload (<code>reports/RESULTS.md</code>).</p>}
        <p>Bandwidth and device are recorded for this report only. They are never inputs to the model.</p>
      </CardContent></Card>
    </StaffShell>
  );
}

function Largest({ title, g }: { title: string; g: FairLargest | null }) {
  const v = g ? VERDICT[g.verdict] : null;
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</p>
      {g && v ? (
        <>
          <p className="mt-1 text-3xl font-semibold">{pts(g.diff)}</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{g.group} vs {g.reference}</p>
          <p className={cn("mt-1 inline-flex items-center gap-1 text-xs font-semibold", v.tone)}><Icon name={v.icon} size={14} />{v.label}<span className="font-normal text-slate-500">· {ci(g.lo, g.hi, "pts")}</span></p>
        </>
      ) : (
        <>
          <p className="mt-1 text-3xl font-semibold">None</p>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">No group was flagged more often than its reference group.</p>
        </>
      )}
    </div>
  );
}

function DimensionCard({ d, max }: { d: FairView["dimensions"][number]; max: number }) {
  const ref = d.groups.find((g) => g.reference);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * max);
  return (
    <Card className="bg-white dark:bg-slate-950">
      <CardContent className="pt-5">
        <h2 className="text-base font-semibold">{d.title}</h2>
        <p className="text-sm text-slate-500">{d.note}</p>
        <div className="mt-3">
          {d.groups.map((g) => <Row key={g.key} g={g} max={max} ticks={ticks} refLabel={ref?.label || ""} dim={d.title} />)}
          <div className="grid sm:grid-cols-[13rem_1fr_15rem] sm:gap-x-4">
            <div className="hidden sm:block" />
            <div className="relative mr-12 h-5 text-[11px] text-slate-500 tabular">
              {ticks.map((t, i) => (
                <span key={i} className="absolute top-1 -translate-x-1/2" style={{ left: `${(t / max) * 100}%` }}>{pct(t)}</span>
              ))}
            </div>
          </div>
        </div>
        <details className="mt-3 text-sm">
          <summary className="cursor-pointer font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300">Show the numbers</summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[620px] text-left">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr><th className="py-1.5 pr-3">Group</th><th className="py-1.5 pr-3">Candidates</th><th className="py-1.5 pr-3">FairProctor</th><th className="py-1.5 pr-3">Old rules</th><th className="py-1.5 pr-3">Gap · FairProctor</th><th className="py-1.5">Gap · old rules</th></tr>
              </thead>
              <tbody className="tabular">
                {d.groups.map((g) => (
                  <tr key={g.key} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-1.5 pr-3 font-semibold">{g.label}{g.reference && <span className="font-normal text-slate-500"> (reference)</span>}</td>
                    <td className="py-1.5 pr-3">{g.n}</td>
                    <td className="py-1.5 pr-3">{pct(g.ours.rate)} <span className="text-slate-500">({g.ours.k} of {g.ours.n}; {ci(g.ours.lo, g.ours.hi, "pct")})</span></td>
                    <td className="py-1.5 pr-3">{pct(g.old.rate)} <span className="text-slate-500">({g.old.k} of {g.old.n})</span></td>
                    <td className="py-1.5 pr-3">{g.gap ? <>{pts(g.gap.ours.diff)} <span className="text-slate-500">({ci(g.gap.ours.lo, g.gap.ours.hi, "pts")})</span></> : "—"}</td>
                    <td className="py-1.5">{g.gap ? pts(g.gap.old.diff) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

function Row({ g, max, ticks, refLabel, dim }: { g: FairGroup; max: number; ticks: number[]; refLabel: string; dim: string }) {
  const v = g.gap ? VERDICT[g.gap.ours.verdict] : null;
  return (
    <div className="grid border-b border-slate-100 last:border-b-0 sm:grid-cols-[13rem_1fr_15rem] sm:gap-x-4 dark:border-slate-900">
      <div className="pt-3 sm:py-3">
        <p className="text-sm font-semibold">{g.label}</p>
        <p className="text-xs text-slate-500">{g.n} candidates</p>
      </div>
      <div className="relative mr-12 self-stretch py-3">
        {ticks.map((t, i) => (
          <span key={i} aria-hidden className="absolute inset-y-0 w-px" style={{ left: `${(t / max) * 100}%`, background: i === 0 ? "var(--viz-axis)" : "var(--viz-grid)" }} />
        ))}
        <div className="relative space-y-[3px]">
          <Bar sys="ours" r={g.ours} max={max} what={`${dim}: ${g.label}`} />
          <Bar sys="old" r={g.old} max={max} what={`${dim}: ${g.label}`} />
        </div>
      </div>
      <div className="pb-3 text-sm sm:py-3">
        {g.gap && v ? (
          <>
            <p><b className="tabular">{pts(g.gap.ours.diff)}</b> <span className="text-slate-500">vs {refLabel}</span></p>
            <p className={cn("inline-flex items-center gap-1 text-xs font-semibold", v.tone)}><Icon name={v.icon} size={13} />{v.label}</p>
            <p className="text-xs text-slate-500">{ci(g.gap.ours.lo, g.gap.ours.hi, "pts")} · old rules {pts(g.gap.old.diff)}</p>
          </>
        ) : <p className="text-xs text-slate-500">Reference group</p>}
      </div>
    </div>
  );
}

function Bar({ sys, r, max, what }: { sys: Sys; r: FairRate; max: number; what: string }) {
  const [tip, setTip] = useState(false);
  const w = r.rate == null ? 0 : Math.min(1, r.rate / max) * 100;
  const labelAt = sys === "ours" && r.hi != null && r.n > 0 ? Math.max(w, Math.min(1, r.hi / max) * 100) : w;   // after the whisker
  const text = `${SYS[sys].name}: ${pct(r.rate)} (${r.k} of ${r.n})${sys === "ours" ? `, ${ci(r.lo, r.hi, "pct")}` : ""}`;
  return (
    <div className="relative h-[11px] outline-none" tabIndex={0} aria-label={`${what}. ${text}`}
      onPointerEnter={() => setTip(true)} onPointerLeave={() => setTip(false)} onFocus={() => setTip(true)} onBlur={() => setTip(false)}>
      <div className={cn("h-full rounded-r-[4px] transition-[filter]", tip && "brightness-110")} style={{ width: `${w}%`, background: SYS[sys].color, minWidth: r.rate ? 2 : 0 }} />
      {sys === "ours" && r.lo != null && r.hi != null && r.n > 0 && (
        <span aria-hidden className="absolute top-1/2 h-px -translate-y-1/2 bg-slate-900/70 dark:bg-slate-100/70"
          style={{ left: `${Math.min(1, r.lo / max) * 100}%`, width: `${Math.max(0, Math.min(1, r.hi / max) - Math.min(1, r.lo / max)) * 100}%` }}>
          <span className="absolute -top-[3px] left-0 h-[7px] w-px bg-inherit" /><span className="absolute -top-[3px] right-0 h-[7px] w-px bg-inherit" />
        </span>
      )}
      <span className="tabular absolute top-1/2 -translate-y-1/2 pl-1.5 text-[11px] font-semibold text-slate-600 dark:text-slate-300" style={{ left: `${labelAt}%` }}>{pct(r.rate)}</span>
      {tip && (
        <div role="tooltip" className="pointer-events-none absolute bottom-full z-20 mb-1.5 w-max max-w-[16rem] -translate-x-1/2 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs shadow-lg dark:border-slate-700 dark:bg-slate-900"
          style={{ left: `${Math.max(12, Math.min(88, w))}%` }}>
          <p className="flex items-center gap-1.5"><span className="h-0.5 w-3 rounded" style={{ background: SYS[sys].color }} /><b className="text-sm">{pct(r.rate)}</b> <span className="text-slate-500">{SYS[sys].name}</span></p>
          <p className="text-slate-500">{r.k} of {r.n}{sys === "ours" && r.lo != null ? ` · ${ci(r.lo, r.hi, "pct")}` : " · same number of review slots"}</p>
        </div>
      )}
    </div>
  );
}

import { useEffect, useMemo, useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { BandBadge, FamilyChip, FAMILIES, NetBadge, PriorityBar, StatusBadge } from "@/components/review";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Tabs } from "@/components/ui/misc";
import { cn } from "@/lib/cn";
import { Link, navigate, useLocation } from "@/lib/router";
import { store } from "@/lib/storage";
import type { Queue as Q } from "@/lib/types";
import type { Exam } from "./Exams";
import { useApi } from "@/lib/useApi";

type Tab = "queue" | "review_first" | "review" | "clear" | "all";
const PAGE = 50;

export default function Queue() {
  const { search } = useLocation();
  const [tab, setTab] = useState<Tab>((search.get("band") as Tab) || "queue");
  const [family, setFamily] = useState(search.get("family") || "");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [hideRef, setHideRef] = useState(store.get("fp-hide-ref") === "1");
  const [limit, setLimit] = useState(PAGE);
  const [sel, setSel] = useState(0);
  const sitting = search.get("sitting") || "";

  useEffect(() => { const id = setTimeout(() => setQuery(q), 300); return () => clearTimeout(id); }, [q]);
  useEffect(() => { setLimit(PAGE); setSel(0); }, [tab, family, query, hideRef]);

  const path = useMemo(() => {
    const p = new URLSearchParams({ band: tab, limit: String(limit), include_reference: hideRef ? "0" : "1" });
    if (family) p.set("family", family);
    if (query) p.set("q", query);
    if (sitting) p.set("sitting_id", sitting);
    return "/api/review/queue?" + p;
  }, [tab, family, query, hideRef, limit, sitting]);
  const { data, error, loading, slow, reload } = useApi<Q>(path);
  const exams = useApi<Exam[]>("/api/review/exams").data || [];
  const exam = exams.find((e) => String(e.id) === sitting);
  const pickExam = (id: string) => navigate(id ? `/review?sitting=${id}` : "/review");
  const rows = data?.rows || [];

  // J / K to move, Enter to open (the reviewer's keyboard flow)
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.closest("input, textarea, select")) return;
      if (e.key === "j") setSel((s) => Math.min(rows.length - 1, s + 1));
      if (e.key === "k") setSel((s) => Math.max(0, s - 1));
      if (e.key === "Enter" && rows[sel]) navigate(`/review/s/${encodeURIComponent(rows[sel].session_id)}`);
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [rows, sel]);
  useEffect(() => { document.getElementById(`row-${sel}`)?.scrollIntoView({ block: "nearest" }); }, [sel]);

  const c = data?.counts || {};
  const needs = (c.review_first || 0) + (c.review || 0);
  const total = needs + (c.clear || 0);

  return (
    <StaffShell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Review queue</h1>
          <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
            Ranked by review priority (0–100). 50 is the review line. Priority is an order to look in, not a probability or a verdict.
          </p>
        </div>
        <p className="text-xs text-slate-500"><kbd className="rounded border px-1">J</kbd> / <kbd className="rounded border px-1">K</kbd> move · <kbd className="rounded border px-1">Enter</kbd> open</p>
      </div>

      <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Review first" value={c.review_first} tone="text-rose-600" hint={total ? `${Math.round(((c.review_first || 0) / total) * 100)}% of sessions` : ""} onClick={() => setTab("review_first")} />
        <Stat label="Review" value={c.review} tone="text-amber-600" onClick={() => setTab("review")} />
        <Stat label="Auto-cleared" value={c.clear} tone="text-emerald-600" onClick={() => setTab("clear")} />
        <Link to="/review/appeals" className="block"><Stat label="Open appeals" value={data?.open_appeals} tone="text-pink-600" /></Link>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label htmlFor="exam" className="text-xs font-semibold text-slate-500">Exam:</label>
        <select id="exam" value={sitting} onChange={(e) => pickExam(e.target.value)}
          className="h-9 max-w-full rounded-lg border border-slate-300 bg-white px-2 text-sm dark:border-slate-700 dark:bg-slate-900">
          <option value="">All exams</option>
          {exams.map((e) => <option key={e.id} value={e.id}>{e.title}{e.status === "scored" ? ` · ${e.flagged} flagged` : ` · ${e.status}`}</option>)}
        </select>
        {exam && <span className="text-sm text-slate-500">{exam.test_title} · reviewed {exam.reviewed} of {exam.flagged} flagged</span>}
        <Link to="/review/exams" className="ml-auto text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400">All exams →</Link>
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs<Tab> value={tab} onChange={setTab} items={[
          { value: "queue", label: <>Needs review <Count n={needs} /></> },
          { value: "review_first", label: <>Review first <Count n={c.review_first} /></> },
          { value: "review", label: <>Review <Count n={c.review} /></> },
          { value: "clear", label: <>Auto-cleared <Count n={c.clear} /></> },
          { value: "all", label: "All" },
        ]} />
        <div className="relative ml-auto w-full sm:w-64">
          <Icon name="search" size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pseudonym, roll no. or id" className="h-10 pl-9 text-sm" aria-label="Search" />
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold text-slate-500">Reason:</span>
        {Object.keys(FAMILIES).map((f) => <FamilyChip key={f} family={f} active={family === f} onClick={() => setFamily(family === f ? "" : f)} />)}
        <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
          <input type="checkbox" className="h-4 w-4 accent-pink-600" checked={hideRef} onChange={(e) => { setHideRef(e.target.checked); store.set("fp-hide-ref", e.target.checked ? "1" : null); }} />
          Hide reference sessions
        </label>
      </div>

      {loading && !data ? <Loading slow={slow} /> : error ? <ErrorBox error={error} retry={reload} /> : rows.length === 0 ? (
        <Card className="p-10 text-center text-slate-500"><Icon name="inbox" size={32} className="mx-auto mb-2" />Nothing here with these filters.</Card>
      ) : (
        <Card className="overflow-hidden bg-white dark:bg-slate-950">
          <div className="hidden grid-cols-[3rem_11rem_9rem_1fr_8rem] gap-4 border-b border-slate-200 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500 md:grid dark:border-slate-800">
            <span>Rank</span><span>Candidate</span><span>Priority</span><span>Why</span><span>Status</span>
          </div>
          <ul role="list">
            {rows.map((r, i) => (
              <li key={r.session_id} id={`row-${i}`}>
                <Link to={`/review/s/${encodeURIComponent(r.session_id)}`} onMouseEnter={() => setSel(i)}
                  className={cn("grid gap-x-4 gap-y-2 border-b border-slate-100 px-4 py-3 transition md:grid-cols-[3rem_11rem_9rem_1fr_8rem] md:items-center dark:border-slate-900",
                    i === sel ? "bg-pink-50/70 dark:bg-pink-950/20" : "hover:bg-slate-50 dark:hover:bg-slate-900")}>
                  <span className="tabular hidden text-sm text-slate-500 md:block">#{r.rank}</span>
                  <div className="flex items-center justify-between gap-2 md:block">
                    <p className="font-semibold">{r.pseudonym}</p>
                    <div className="flex items-center gap-2"><NetBadge bandwidth={r.bandwidth} device={r.device} />{r.reference && <span className="text-[11px] text-slate-400" title="Reference session from the scoring data, not a real candidate">ref</span>}</div>
                  </div>
                  <div className="space-y-1">
                    <PriorityBar value={r.priority} band={r.band} lines={data!.priority_lines} />
                    <BandBadge band={r.band} />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex flex-wrap gap-1">{r.families.map((f) => <FamilyChip key={f} family={f} />)}</div>
                    <p className="line-clamp-2 text-sm text-slate-600 dark:text-slate-300">{r.headline}</p>
                  </div>
                  <div><StatusBadge status={r.status} /></div>
                </Link>
              </li>
            ))}
          </ul>
          {data && data.total > rows.length && (
            <div className="p-3 text-center">
              <Button variant="outline" size="sm" onClick={() => setLimit(limit + PAGE)}>Show more ({data.total - rows.length} left)</Button>
            </div>
          )}
        </Card>
      )}
    </StaffShell>
  );
}

function Count({ n }: { n?: number }) {
  return <span className="tabular ml-1 rounded-full bg-slate-200 px-1.5 text-xs dark:bg-slate-700">{n ?? 0}</span>;
}

function Stat({ label, value, tone, hint, onClick }: { label: string; value?: number; tone: string; hint?: string; onClick?: () => void }) {
  const C = onClick ? "button" : "div";
  return (
    <C onClick={onClick} className="w-full rounded-2xl border border-slate-200 bg-white p-4 text-left transition-colors hover:border-slate-400 dark:border-slate-800 dark:bg-slate-900">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <p className={cn("tabular mt-1 text-3xl font-semibold", tone)}>{value ?? 0}</p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </C>
  );
}

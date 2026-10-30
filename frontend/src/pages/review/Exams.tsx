import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { FamilyChip } from "@/components/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/misc";
import { dateTime } from "@/lib/format";
import { Link, navigate } from "@/lib/router";
import { useApi } from "@/lib/useApi";

export type Exam = {
  id: number; title: string; test_title: string; kind: "mcq" | "coding"; status: string;
  starts_at: string; ends_at: string; scored_at: string | null;
  candidates: number; submitted: number; writing: number; reference: number;
  bands: { review_first: number; review: number; clear: number };
  flagged: number; reviewed: number; confirmed: number; reasons: Record<string, number>;
  open_appeals: number; snapshots: number; snapshot_sessions: number;
};

const STATUS: Record<string, { label: string; tone: "info" | "warning" | "success" | "neutral" }> = {
  scheduled: { label: "Scheduled", tone: "neutral" }, live: { label: "Live now", tone: "info" },
  closed: { label: "Closed", tone: "neutral" }, scoring: { label: "Scoring…", tone: "warning" }, scored: { label: "Scored", tone: "success" },
};

/** Reviewer home by exam: each sitting with what was flagged, how far review has got, the reasons, appeals and snapshots. */
export default function Exams() {
  const { data, error, loading, slow, reload } = useApi<Exam[]>("/api/review/exams", { poll: 30000 });
  return (
    <StaffShell>
      <div className="mb-5">
        <h1 className="text-2xl font-semibold tracking-tight">Exams</h1>
        <p className="mt-1 max-w-2xl text-sm text-slate-500 dark:text-slate-400">
          Flagged sessions grouped by exam. Open an exam to review only its flagged candidates, highest priority first.
        </p>
      </div>
      {loading && !data ? <Loading slow={slow} /> : error || !data ? <ErrorBox error={error} retry={reload} /> : data.length === 0 ? (
        <Card className="p-10 text-center text-slate-500"><Icon name="inbox" size={32} className="mx-auto mb-2" />No exams yet.</Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {data.map((e) => <ExamCard key={e.id} e={e} />)}
        </div>
      )}
    </StaffShell>
  );
}

function ExamCard({ e }: { e: Exam }) {
  const st = STATUS[e.status] || STATUS.closed;
  const scored = e.status === "scored";
  const left = e.flagged - e.reviewed;
  const open = (band = "queue") => navigate(`/review?sitting=${e.id}&band=${band}`);
  return (
    <Card className="min-w-0 bg-white dark:bg-slate-950"><CardContent className="space-y-4 pt-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-lg font-semibold">{e.title}</p>
          <p className="truncate text-sm text-slate-500">{e.test_title} · {e.kind === "coding" ? "Coding" : "MCQ"} · {dateTime(e.starts_at)}</p>
        </div>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>

      <p className="text-sm text-slate-600 dark:text-slate-300">
        {e.candidates} candidate{e.candidates === 1 ? "" : "s"} · {e.submitted} submitted{e.writing ? ` · ${e.writing} writing` : ""}
        {e.reference > 0 && <span className="text-slate-400"> · {e.reference} reference sessions</span>}
      </p>

      {scored ? (
        <>
          <div className="grid grid-cols-3 gap-2 text-center">
            <button onClick={() => open("review_first")} className="rounded-xl border border-slate-200 p-2.5 hover:border-slate-400 dark:border-slate-800">
              <p className="tabular text-2xl font-semibold text-rose-600">{e.bands.review_first}</p><p className="text-xs text-slate-500">Review first</p>
            </button>
            <button onClick={() => open("review")} className="rounded-xl border border-slate-200 p-2.5 hover:border-slate-400 dark:border-slate-800">
              <p className="tabular text-2xl font-semibold text-amber-600">{e.bands.review}</p><p className="text-xs text-slate-500">Review</p>
            </button>
            <button onClick={() => open("clear")} className="rounded-xl border border-slate-200 p-2.5 hover:border-slate-400 dark:border-slate-800">
              <p className="tabular text-2xl font-semibold text-emerald-600">{e.bands.clear}</p><p className="text-xs text-slate-500">Auto-cleared</p>
            </button>
          </div>
          <div className="space-y-1.5">
            <p className="text-sm font-semibold">{e.flagged ? `Reviewed ${e.reviewed} of ${e.flagged} flagged${e.confirmed ? ` · ${e.confirmed} confirmed` : ""}` : "Nothing flagged"}</p>
            <Progress value={e.flagged ? (e.reviewed / e.flagged) * 100 : 100} label="Review progress" />
          </div>
          {Object.keys(e.reasons).length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs font-semibold text-slate-500">Reasons:</span>
              {Object.entries(e.reasons).map(([f, n]) => (
                <Link key={f} to={`/review?sitting=${e.id}&family=${f}`} className="inline-flex items-center gap-1">
                  <FamilyChip family={f} /><span className="tabular text-xs text-slate-500">{n}</span>
                </Link>
              ))}
            </div>
          )}
          <div className="flex flex-wrap gap-2 text-sm">
            {e.open_appeals > 0 && <Link to="/review/appeals"><Badge tone="warning"><Icon name="send" size={12} />{e.open_appeals} open appeal{e.open_appeals === 1 ? "" : "s"}</Badge></Link>}
            {e.snapshots > 0 && <Badge tone="info"><Icon name="camera" size={12} />{e.snapshots} snapshots · {e.snapshot_sessions} candidate{e.snapshot_sessions === 1 ? "" : "s"}</Badge>}
          </div>
          <Button className="w-full" onClick={() => open()} disabled={!e.flagged}>
            {left > 0 ? `Review ${left} flagged` : e.flagged ? "Open flagged (all reviewed)" : "No flagged sessions"} <Icon name="arrowRight" size={16} />
          </Button>
        </>
      ) : e.status === "live" ? (
        <Button variant="outline" className="w-full" onClick={() => navigate(`/review/live/${e.id}`)}><Icon name="eye" size={16} />Open live monitor</Button>
      ) : (
        <p className="text-sm text-slate-500">{e.status === "scoring" ? "Scoring is running; flagged sessions appear here in a moment." : "Flagged sessions appear here once the exam is closed and scored."}</p>
      )}
    </CardContent></Card>
  );
}

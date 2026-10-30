import { useState } from "react";
import { CandidateShell, ErrorBox, Loading } from "@/components/Shell";
import { Icon, type IconName } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { Checkbox, Field, Textarea } from "@/components/ui/form";
import { Dialog } from "@/components/ui/misc";
import { SnapshotGroups, type SnapshotRow } from "@/components/Snapshots";
import { useToast } from "@/components/ui/toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { errorFor } from "@/lib/errors";
import { dateTime } from "@/lib/format";
import { useT, type Key } from "@/lib/i18n";
import { noteText, pointText, pointTitle } from "@/lib/serverText";
import { verdictKey, verdictTone } from "./Coding";
import type { ExamMe, Result as R, ResultState } from "@/lib/types";
import { useApi } from "@/lib/useApi";

const LOOK: Record<ResultState, { key: Key; icon: IconName; c: string }> = {
  pending: { key: "statePending", icon: "clock", c: "bg-sky-50 text-sky-900 ring-sky-200 dark:bg-sky-950/50 dark:text-sky-100 dark:ring-sky-900" },
  clear: { key: "stateClear", icon: "checkCircle", c: "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-100 dark:ring-emerald-900" },
  cleared_after_review: { key: "stateClearedReview", icon: "checkCircle", c: "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-100 dark:ring-emerald-900" },
  cleared_after_appeal: { key: "stateClearedAppeal", icon: "checkCircle", c: "bg-emerald-50 text-emerald-900 ring-emerald-200 dark:bg-emerald-950/50 dark:text-emerald-100 dark:ring-emerald-900" },
  under_review: { key: "stateReview", icon: "eye", c: "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-950/50 dark:text-amber-100 dark:ring-amber-900" },
  confirmed: { key: "stateConfirmed", icon: "alert", c: "bg-rose-50 text-rose-900 ring-rose-200 dark:bg-rose-950/50 dark:text-rose-100 dark:ring-rose-900" },
};

/** "06:34–09:32" → 394 (seconds into the test where the moment starts). */
const startSec = (when: string) => {
  const m = when.match(/(\d+):(\d{2})/);
  return m ? Number(m[1]) * 60 + Number(m[2]) : 0;
};

export default function Result() {
  const { t, lang } = useT();
  const { data, error, loading, slow, reload } = useApi<R>("/api/exam/result", { poll: 30000 });
  const snaps = useApi<{ days: number; snapshots: SnapshotRow[] }>("/api/exam/snapshots");
  const me = useApi<ExamMe>("/api/exam/me", { poll: 15000 });              // a reviewer may reopen a test a rule ended
  const reopened = me.data?.session?.status === "in_progress";
  const [appeal, setAppeal] = useState(false);
  const toast = useToast();

  if (loading && !data) return <CandidateShell><Loading slow={slow} /></CandidateShell>;
  if (error || !data) return <CandidateShell><ErrorBox error={error} retry={reload} /></CandidateShell>;
  const look = LOOK[data.state];
  const points = data.points || [];


  return (
    <CandidateShell>
      <div className="animate-fade-in space-y-4">
        <h1 className="text-2xl font-semibold tracking-tight">{t("resultTitle")}</h1>
        {!reopened && (
          <div className={cn("flex gap-3 rounded-2xl p-4 ring-1", look.c)} role="status">
            <Icon name={look.icon} size={26} className="mt-0.5 shrink-0" />
            <p className="text-lg font-semibold leading-snug">{t(look.key)}</p>
          </div>
        )}

        {reopened && (
          <Card className="border-emerald-300 dark:border-emerald-800"><CardContent className="space-y-3 pt-5">
            <CardTitle className="text-lg text-emerald-800 dark:text-emerald-200">{t("reopenedTitle")}</CardTitle>
            <p className="text-sm text-slate-700 dark:text-slate-300">{t("reopenedBody")}</p>
            <Button size="lg" className="w-full" onClick={() => window.location.assign("/exam/run")}>{t("reopenedContinue")} <Icon name="arrowRight" size={18} /></Button>
          </CardContent></Card>
        )}

        {data.terminated && !reopened && (
          <Card><CardContent className="space-y-2 pt-5">
            <CardTitle className="flex items-center gap-2 text-lg"><Icon name="lock" size={18} />{t("endedTitle")}</CardTitle>
            <p className="font-medium">{t(("ended_" + data.terminated.reason) as Key)}</p>
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("endedBody")}</p>
            <p className="text-xs text-slate-500">{t("endedMayReopen")}</p>
          </CardContent></Card>
        )}

        {data.coding && (
          <Card><CardContent className="space-y-3 pt-5">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-lg">{t("yourMarks")}</CardTitle>
              <span className="tabular text-lg font-semibold">{t("marksOf", { m: data.coding.marks, t: data.coding.out_of })}</span>
            </div>
            <ul className="space-y-2">
              {data.coding.problems.map((p) => (
                <li key={p.item} className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
                  <span className="font-semibold">P{p.item + 1} · {p.title}</span>
                  <Badge tone={verdictTone(p.verdict)}>{t(verdictKey(p.verdict))}</Badge>
                  {p.total > 0 && <span className="text-sm text-slate-500">{t("testsPassed", { p: p.passed, t: p.total })}</span>}
                  <span className="tabular ml-auto font-semibold">{p.marks}</span>
                </li>
              ))}
            </ul>
          </CardContent></Card>
        )}

        {snaps.data && snaps.data.snapshots.length > 0 && (
          <Card><CardContent className="space-y-3 pt-5">
            <CardTitle className="text-lg">{t("snapTitle")}</CardTitle>
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("snapNote", { days: snaps.data.days })}</p>
            <SnapshotGroups rows={snaps.data.snapshots} reasonText={(r) => t(("snap_" + r) as Key)}
              phaseText={(p) => t(p === "before" ? "snapBefore" : p === "at" ? "snapAt" : "snapAfter")} />
          </CardContent></Card>
        )}

        {data.reviewer_note && (
          <Card><CardContent className="pt-5">
            <p className="text-sm font-semibold text-slate-500">{t("reviewerNote")}</p>
            <p className="mt-1">{data.reviewer_note}</p>
          </CardContent></Card>
        )}

        {points.length > 0 && (
          <Card>
            <CardContent className="space-y-3 pt-5">
              <CardTitle className="text-lg">{t("noticed")}</CardTitle>
              <ul className="space-y-3">
                {points.map((p, i) => (
                  <li key={i} className="rounded-lg border border-slate-200 bg-slate-50 p-3.5 dark:border-slate-800 dark:bg-slate-950">
                    <p className="font-semibold">{pointTitle(p.title, lang)}</p>
                    <p className="mt-1 text-slate-600 dark:text-slate-300">{pointText(p.title, p.text, lang)}</p>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {p.when && <Badge tone="info"><Icon name="clock" size={12} />{t("atTime", { when: p.when })}</Badge>}
                      {p.questions.length > 0 && <Badge className="whitespace-normal">{data.test_kind === "coding"
                        ? t("problemList", { list: p.questions.map((q) => "P" + q).join(", ") })
                        : t("questionList", { list: p.questions.map((q) => "Q" + q).join(", ") })}</Badge>}
                    </div>
                  </li>
                ))}
              </ul>
              {data.can_appeal && <Button size="lg" className="w-full" onClick={() => setAppeal(true)}><Icon name="send" size={18} />{t("explainThis")}</Button>}
            </CardContent>
          </Card>
        )}

        {data.appeal && (
          <Card><CardContent className="space-y-3 pt-5">
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="text-lg">{t("yourExplanation")}</CardTitle>
              <Badge tone={data.appeal.status === "open" ? "warning" : data.appeal.outcome === "overturned" ? "success" : "neutral"}>
                {data.appeal.status === "open" ? t("appealOpen") : data.appeal.outcome === "overturned" ? t("appealOverturned") : t("appealUpheld")}
              </Badge>
            </div>
            <p className="whitespace-pre-wrap rounded-xl bg-white p-3 text-slate-700 dark:bg-slate-950 dark:text-slate-200">{data.appeal.text}</p>
            <p className="text-xs text-slate-500">{dateTime(data.appeal.at, lang)}</p>
            {data.appeal.response && (
              <div>
                <p className="text-sm font-semibold text-slate-500">{t("reviewerReply")}</p>
                <p className="mt-1">{data.appeal.response}</p>
              </div>
            )}
          </CardContent></Card>
        )}

        {(data.not_counted || []).length > 0 && (
          <Card><CardContent className="pt-5">
            <CardTitle className="flex items-center gap-2 text-lg"><Icon name="shield" size={18} className="text-emerald-600" />{t("notCounted")}</CardTitle>
            <ul className="mt-3 space-y-2 text-slate-600 dark:text-slate-300">
              {data.not_counted!.map((n, i) => <li key={i} className="flex gap-2"><Icon name="check" size={16} className="mt-1 shrink-0 text-emerald-600" />{noteText(n, lang)}</li>)}
            </ul>
          </CardContent></Card>
        )}

        <p className="px-1 text-sm text-slate-500 dark:text-slate-400">{t("retention", { days: data.retention_days })}</p>
      </div>

      <AppealSheet open={appeal} onClose={() => setAppeal(false)} points={points} onSent={() => { setAppeal(false); toast(t("appealSent")); reload(true); }} />
    </CandidateShell>
  );
}

function AppealSheet({ open, onClose, points, onSent }: { open: boolean; onClose: () => void; points: NonNullable<R["points"]>; onSent: () => void }) {
  const { t, lang } = useT();
  const [text, setText] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function send() {
    if (text.trim().length < 5) { setErr(t("appealTooShort")); return; }
    setBusy(true); setErr(null);
    try {
      await api("/api/exam/appeal", { body: { text: text.trim(), moments: picked.map((i) => startSec(points[i].when)) } });
      onSent();
    } catch (e) { setErr(errorFor(e, t)); } finally { setBusy(false); }
  }
  const withTime = points.map((p, i) => ({ p, i })).filter(({ p }) => p.when);
  return (
    <Dialog open={open} onClose={onClose} title={t("appealTitle")} side="bottom">
      <div className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-300">{t("appealHelp")}</p>
        {withTime.length > 0 && (
          <fieldset className="space-y-3">
            <legend className="mb-2 text-sm font-semibold">{t("appealMoments")}</legend>
            {withTime.map(({ p, i }) => (
              <Checkbox key={i} id={`m${i}`} checked={picked.includes(i)} onChange={(v) => setPicked(v ? [...picked, i] : picked.filter((x) => x !== i))}>
                <span className="text-sm"><b className="tabular">{p.when}</b> — {pointTitle(p.title, lang)}</span>
              </Checkbox>
            ))}
          </fieldset>
        )}
        <Field id="appeal" label={t("yourExplanation")} error={err}>
          <Textarea id="appeal" value={text} maxLength={4000} placeholder={t("appealPlaceholder")} onChange={(e) => { setText(e.target.value); setErr(null); }}
            aria-invalid={!!err} aria-describedby={err ? "appeal-err" : undefined} />
        </Field>
        <Button size="lg" className="w-full" disabled={busy} onClick={send}><Icon name="send" size={18} />{busy ? t("loading") : t("send")}</Button>
      </div>
    </Dialog>
  );
}

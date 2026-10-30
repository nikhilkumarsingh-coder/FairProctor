import { useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { BandBadge, clock } from "@/components/review";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Textarea } from "@/components/ui/form";
import { Tabs } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { api, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { dateTime } from "@/lib/format";
import { Link } from "@/lib/router";
import type { Appeal } from "@/lib/types";
import { useApi } from "@/lib/useApi";

export default function Appeals() {
  const [status, setStatus] = useState<"open" | "decided">("open");
  const { data, error, loading, slow, reload } = useApi<Appeal[]>(`/api/review/appeals?status=${status}`);
  return (
    <StaffShell>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Appeals</h1>
          <p className="mt-1 text-sm text-slate-500">Candidates' own explanations. Read them with the session evidence before deciding.</p>
        </div>
        <Tabs value={status} onChange={setStatus} items={[{ value: "open", label: "Open" }, { value: "decided", label: "Decided" }]} />
      </div>
      {loading && !data ? <Loading slow={slow} /> : error || !data ? <ErrorBox error={error} retry={reload} /> : data.length === 0 ? (
        <Card className="p-10 text-center text-slate-500"><Icon name="inbox" size={32} className="mx-auto mb-2" />No {status} appeals.</Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {data.map((a) => <AppealCard key={a.id} a={a} onDone={() => reload(true)} />)}
        </div>
      )}
    </StaffShell>
  );
}

function AppealCard({ a, onDone }: { a: Appeal; onDone: () => void }) {
  const toast = useToast();
  const [outcome, setOutcome] = useState<"upheld" | "overturned" | null>(null);
  const [response, setResponse] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function send() {
    if (!outcome) { setErr("Choose an outcome."); return; }
    if (response.trim().length < 5) { setErr("Write a short reply to the candidate (at least 5 characters)."); return; }
    setBusy(true); setErr(null);
    try {
      await api(`/api/review/appeals/${a.id}/decide`, { body: { outcome, response: response.trim() } });
      toast("Reply sent to the candidate");
      onDone();
    } catch (e) { setErr(errorText(e)); } finally { setBusy(false); }
  }
  return (
    <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Link to={`/review/s/${encodeURIComponent(a.session_id)}`} className="font-semibold text-pink-700 hover:underline dark:text-pink-400">{a.pseudonym}</Link>
          {a.band && <BandBadge band={a.band} />}
          {a.priority != null && <span className="tabular text-sm text-slate-500">priority {a.priority}</span>}
        </div>
        <span className="text-xs text-slate-500">{dateTime(a.at)}</span>
      </div>
      <blockquote className="whitespace-pre-wrap rounded-xl border-l-4 border-pink-400 bg-slate-50 p-3 dark:bg-slate-900">{a.text}</blockquote>
      {a.moments.length > 0 && (
        <div className="flex flex-wrap gap-1.5 text-xs">
          <span className="text-slate-500">About:</span>
          {a.moments.map((m, i) => <Badge key={i} tone="info"><span className="tabular">{clock(m)}</span></Badge>)}
        </div>
      )}
      {a.status === "decided" ? (
        <div className="rounded-xl bg-slate-50 p-3 text-sm dark:bg-slate-900">
          <Badge tone={a.outcome === "overturned" ? "success" : "neutral"}>{a.outcome === "overturned" ? "Overturned — candidate cleared" : "Decision upheld"}</Badge>
          <p className="mt-2">{a.response}</p>
        </div>
      ) : (
        <div className="space-y-3 border-t border-slate-200 pt-3 dark:border-slate-800">
          <div className="grid grid-cols-2 gap-2">
            {(["overturned", "upheld"] as const).map((o) => (
              <button key={o} onClick={() => { setOutcome(o); setErr(null); }} aria-pressed={outcome === o}
                className={cn("rounded-xl border-2 p-2.5 text-left text-sm transition", outcome === o
                  ? o === "overturned" ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-950/40" : "border-rose-500 bg-rose-50 dark:bg-rose-950/40"
                  : "border-slate-200 dark:border-slate-800")}>
                <b className="block">{o === "overturned" ? "Accept explanation" : "Uphold decision"}</b>
                <span className="text-xs text-slate-500">{o === "overturned" ? "Candidate is cleared" : "Finding stays"}</span>
              </button>
            ))}
          </div>
          <Field id={`r${a.id}`} label="Reply to the candidate" error={err}>
            <Textarea id={`r${a.id}`} value={response} onChange={(e) => { setResponse(e.target.value); setErr(null); }} className="min-h-20 text-sm" maxLength={4000} />
          </Field>
          <Button className="w-full" disabled={busy} onClick={send}>{busy ? "Sending…" : "Send reply"}</Button>
        </div>
      )}
    </CardContent></Card>
  );
}

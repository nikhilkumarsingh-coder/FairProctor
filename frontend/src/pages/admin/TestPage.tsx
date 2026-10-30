import { useState } from "react";
import { ErrorBox, Loading, StaffShell } from "@/components/Shell";
import { CsvBox, type BadRow } from "@/components/admin";
import { Icon } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, errorText } from "@/lib/api";
import { Link } from "@/lib/router";
import { useApi } from "@/lib/useApi";
import { CodeBlock } from "@/components/CodeEditor";
import { Statement } from "@/pages/exam/Coding";

type Problem = { item: number; title: string; statement: string; languages: string[]; time_limit: number; starter: Record<string, string>;
  samples: { input: string; output: string }[]; hidden: { input: string; output: string }[] };
type Detail = { id: number; title: string; duration_min: number; kind?: "mcq" | "coding"; problems?: Problem[];
  items: { position: number; kind: string; text: string; options: Record<string, string>; correct_option: string }[] };

const SAMPLE_JSON = JSON.stringify({ problems: [{
  title: "Double it", statement: "Read an integer n and print 2n.\n\nInput\nOne integer n (|n| <= 10^9).\n\nOutput\nOne integer.",
  languages: ["python", "cpp", "java", "javascript"], time_limit: 2,
  starter: { python: "n = int(input())\n# print 2n\n" },
  samples: [{ input: "3\n", output: "6\n" }],
  tests: [{ input: "5\n", output: "10\n" }, { input: "-7\n", output: "-14\n" }, { input: "1000000000\n", output: "2000000000\n" }],
  solution: { language: "python", code: "print(2 * int(input()))\n" },
}] }, null, 2);

const SAMPLE = `text,option_a,option_b,option_c,option_d,correct,kind
What is 32 × 8?,248,266,256,288,C,mcq
Next number: 2 5 8 11 ?,13,14,15,16,B,mcq
What is 15% of 200?,,,,,30,short
`;

export default function TestPage({ id }: { id: number }) {
  const toast = useToast();
  const { data, error, loading, reload } = useApi<Detail>(`/api/admin/tests/${id}`);
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState<BadRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  async function upload(csv: string) {
    setBusy(true); setErr(null); setRows([]);
    try {
      const r = await api<{ n_items: number }>(`/api/admin/tests/${id}/items`, { csv });
      toast(`${r.n_items} questions saved`);
      reload(true);
    } catch (e) {
      setErr(errorText(e));
      if (e instanceof ApiError) setRows((e.extra.rows as BadRow[]) || []);
    } finally { setBusy(false); }
  }
  if (data?.kind === "coding") return <CodingTest data={data} reload={() => reload(true)} />;
  return (
    <StaffShell>
      <Link to="/admin" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />Tests & sittings</Link>
      {loading && !data ? <Loading /> : error || !data ? <ErrorBox error={error} retry={reload} /> : (
        <div className="grid gap-5 lg:grid-cols-[1fr_24rem]">
          <div className="min-w-0 space-y-4">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
              <p className="text-sm text-slate-500">{data.duration_min} min · {data.items.length} questions</p>
            </div>
            {data.items.length === 0 ? <Card className="p-8 text-center text-slate-500">No questions yet. Upload a CSV.</Card> : (
              <ol className="space-y-2">
                {data.items.map((it) => (
                  <li key={it.position} className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-950">
                    <div className="flex items-start gap-3">
                      <span className="tabular grid h-7 w-7 shrink-0 place-items-center rounded-full bg-slate-100 text-xs font-semibold dark:bg-slate-800">{it.position + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="font-medium">{it.text} {it.kind === "short" && <Badge tone="info">short answer</Badge>}</p>
                        {it.kind === "short" ? <p className="mt-1 text-sm text-emerald-700 dark:text-emerald-300">Answer: {it.correct_option}</p> : (
                          <div className="mt-1.5 flex flex-wrap gap-1.5 text-sm">
                            {Object.entries(it.options).map(([k, v]) => (
                              <span key={k} className={k === it.correct_option ? "rounded-md bg-emerald-100 px-2 py-0.5 font-semibold text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "rounded-md bg-slate-100 px-2 py-0.5 dark:bg-slate-800"}>{k}. {v}</span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <Card className="h-fit bg-white lg:sticky lg:top-20 dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
            <CardTitle className="text-base">{data.items.length ? "Replace questions" : "Add questions"}</CardTitle>
            <p className="text-xs text-slate-500">Columns: text, option_a, option_b, …, correct, [difficulty], [kind = mcq | short]. A short-answer row leaves the options empty and puts the answer in <i>correct</i>. Uploading replaces all questions.</p>
            <CsvBox label="Questions CSV" sample={SAMPLE} busy={busy} onSubmit={upload} rows={rows} error={err} />
          </CardContent></Card>
        </div>
      )}
    </StaffShell>
  );
}

function CodingTest({ data, reload }: { data: Detail; reload: () => void }) {
  const toast = useToast();
  const langs = useApi<{ key: string; label: string; available: boolean }[]>("/api/code/languages");
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState<BadRow[]>([]);
  const [rowLabel, setRowLabel] = useState("Problem");
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState<number | null>(null);
  async function upload(text: string) {
    setErr(null); setRows([]);
    let body: unknown;
    try { body = JSON.parse(text); } catch (e) { setErr(`Not valid JSON: ${(e as Error).message}`); return; }
    setBusy(true);
    try {
      const r = await api<{ n_items: number; checked: number }>(`/api/admin/tests/${data.id}/problems`, { body });
      toast(`${r.n_items} problems saved${r.checked ? ` · ${r.checked} reference solution${r.checked > 1 ? "s" : ""} passed every test` : ""}`);
      reload();
    } catch (e) {
      setErr(errorText(e));
      if (e instanceof ApiError && e.code === "bad_rows") { setRowLabel("Problem"); setRows((e.extra.rows as BadRow[]) || []); }
      if (e instanceof ApiError && e.code === "invalid") {
        setRowLabel("Field");
        setRows(((e.extra.fields as { field: string; problem: string }[]) || []).map((f) => ({ line: f.field as unknown as number, problem: f.problem })));
      }
    } finally { setBusy(false); }
  }
  const problems = data.problems || [];
  return (
    <StaffShell>
      <Link to="/admin" className="mb-4 inline-flex items-center gap-1 text-sm font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-300"><Icon name="left" size={16} />Tests & sittings</Link>
      <div className="grid gap-5 lg:grid-cols-[1fr_26rem]">
        <div className="min-w-0 space-y-4">
          <div>
            <div className="flex items-center gap-2"><h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1><Badge tone="brand"><Icon name="code" size={12} />Coding test</Badge></div>
            <p className="text-sm text-slate-500">{data.duration_min} min · {problems.length} problems</p>
          </div>
          {problems.length === 0 ? <Card className="p-8 text-center text-slate-500">No problems yet. Upload them as JSON.</Card> : problems.map((p) => (
            <Card key={p.item} className="bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="tabular grid h-7 w-7 place-items-center rounded-full bg-slate-100 text-xs font-semibold dark:bg-slate-800">{p.item + 1}</span>
                <b>{p.title}</b>
                <Badge>{p.time_limit} s</Badge>
                {p.languages.map((l) => <Badge key={l} tone="outline">{l}</Badge>)}
                <span className="ml-auto text-sm text-slate-500">{p.samples.length} sample · {p.hidden.length} hidden tests</span>
              </div>
              <Statement text={p.statement} className="space-y-2 text-sm text-slate-600 dark:text-slate-300" />
              <button onClick={() => setOpen(open === p.item ? null : p.item)} className="text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400">
                {open === p.item ? "Hide tests and starter code" : "Show tests and starter code"}
              </button>
              {open === p.item && (
                <div className="space-y-3">
                  {[...p.samples.map((c, i) => ({ c, label: `Sample ${i + 1}` })), ...p.hidden.map((c, i) => ({ c, label: `Hidden ${i + 1}` }))].slice(0, 12).map(({ c, label }) => (
                    <div key={label} className="grid gap-2 text-xs md:grid-cols-2">
                      <div><p className="mb-1 font-semibold text-slate-500">{label} · input ({c.input.length} chars)</p><pre className="max-h-28 overflow-auto rounded-lg bg-slate-50 p-2 font-mono dark:bg-slate-900">{c.input.slice(0, 600)}{c.input.length > 600 ? " …" : ""}</pre></div>
                      <div><p className="mb-1 font-semibold text-slate-500">expected</p><pre className="max-h-28 overflow-auto rounded-lg bg-slate-50 p-2 font-mono dark:bg-slate-900">{c.output.slice(0, 600)}</pre></div>
                    </div>
                  ))}
                  {Object.entries(p.starter).map(([l, code]) => <div key={l}><p className="mb-1 text-xs font-semibold text-slate-500">Starter · {l}</p><CodeBlock code={code} language={l} className="max-h-48" /></div>)}
                </div>
              )}
            </CardContent></Card>
          ))}
        </div>
        <div className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
            <CardTitle className="text-base">Languages on this server</CardTitle>
            <div className="flex flex-wrap gap-1.5">
              {(langs.data || []).map((l) => <Badge key={l.key} tone={l.available ? "success" : "neutral"}>{l.available ? "✓" : "✗"} {l.label}</Badge>)}
            </div>
            <p className="text-xs text-slate-500">A language that is not installed is hidden from candidates.</p>
          </CardContent></Card>
          <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-5">
            <CardTitle className="text-base">{problems.length ? "Replace problems" : "Add problems"}</CardTitle>
            <p className="text-xs text-slate-500">JSON: problems → title, statement, languages, time_limit, starter, samples (shown), tests (hidden), and an optional
              reference solution that must pass every test before the upload is accepted. Uploading replaces all problems.</p>
            <CsvBox kind="json" rowLabel={rowLabel} label="Problems JSON" sample={SAMPLE_JSON} busy={busy} onSubmit={upload} rows={rows} error={err} />
          </CardContent></Card>
        </div>
      </div>
    </StaffShell>
  );
}

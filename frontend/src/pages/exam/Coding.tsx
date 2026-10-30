// The coding test screen: problem tabs, statement + samples, the code editor, Run / Submit and results.
// Code is kept on this device (IndexedDB) as you type, so a reload or a lost connection never loses it.
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CodeEditor, type Typing } from "@/components/CodeEditor";
import { Icon } from "@/components/Icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/form";
import { Alert, Dialog } from "@/components/ui/misc";
import { api, ApiError, NetworkError } from "@/lib/api";
import { cn } from "@/lib/cn";
import { errorFor } from "@/lib/errors";
import { local, type ExamEngine } from "@/lib/examEngine";
import { useT, type Key } from "@/lib/i18n";
import type { CodeState, Item, RunResult, SubmitResult } from "@/lib/types";

type Draft = { language: string; codes: Record<string, string> };
type Best = { verdict: string; passed: number; total: number };

export const verdictKey = (v: string) => (`v_${v}` as Key);
export const verdictTone = (v: string): "success" | "danger" | "warning" | "neutral" =>
  v === "accepted" || v === "passed" ? "success" : v === "compile_error" || v === "time_limit" ? "warning" : v === "not_submitted" ? "neutral" : "danger";

/** Statement text with **bold**, `code`, and "Input" / "Output" lines as small headings. */
export function Statement({ text, className }: { text: string; className?: string }) {
  const inline = (s: string) => s.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((p, i) =>
    p.startsWith("**") ? <strong key={i}>{p.slice(2, -2)}</strong> : p.startsWith("`") ? <code key={i} className="rounded bg-slate-100 px-1 font-mono text-[0.9em] dark:bg-slate-800">{p.slice(1, -1)}</code> : p);
  return (
    <div className={cn("space-y-3 leading-relaxed text-slate-700 dark:text-slate-200", className)}>
      {text.split(/\n\s*\n/).map((para, i) => {
        const [first, ...rest] = para.split("\n");
        if (/^(Input|Output|Note|Example)s?$/i.test(first.trim())) {
          return <div key={i}><h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-slate-500">{first.trim()}</h3><p className="whitespace-pre-line">{inline(rest.join("\n"))}</p></div>;
        }
        return <p key={i} className="whitespace-pre-line">{inline(para)}</p>;
      })}
    </div>
  );
}

function Pre({ label, text, tone }: { label: string; text: string; tone?: "bad" | "good" }) {
  return (
    <div className="min-w-0">
      <p className="mb-1 text-xs font-semibold text-slate-500">{label}</p>
      <pre className={cn("max-h-48 overflow-auto rounded-lg border px-3 py-2 font-mono text-[13px] leading-snug",
        tone === "bad" ? "border-rose-200 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40" : tone === "good" ? "border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40"
          : "border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900")}>{text === "" ? " " : text}</pre>
    </div>
  );
}

export function CodingView({ items, idx, go, engine, session, codeState, onAccepted, onFinish }: {
  items: Item[]; idx: number; go: (i: number) => void; engine: ExamEngine; session: string; codeState: CodeState;
  onAccepted: (item: number) => void; onFinish: () => void;
}) {
  const { t } = useT();
  const item = items[idx];
  const P = item.code!;
  const [drafts, setDrafts] = useState<Record<number, Draft>>({});
  const [best, setBest] = useState<Record<number, Best | null>>(() =>
    Object.fromEntries(Object.entries(codeState).map(([k, v]) => [Number(k), v.best])));
  const [results, setResults] = useState<Record<number, { run?: RunResult; submit?: SubmitResult; error?: string }>>({});
  const [busy, setBusy] = useState<null | "run" | "submit">(null);
  const [custom, setCustom] = useState<Record<number, string | null>>({});
  const [reset, setReset] = useState(false);
  const [ready, setReady] = useState(false);
  const acc = useRef<Required<Typing> & { item: number; lang: string }>({ ins: 0, dele: 0, keys: 0, max_ins: 0, clear: 0, item: item.item, lang: "" });

  // restore: this device's draft first, else the last code the server has, else the starter code
  useEffect(() => {
    (async () => {
      const out: Record<number, Draft> = {};
      for (const it of items) {
        const saved = await local.get<Draft>(session, `code${it.item}`);
        const cs = codeState[String(it.item)];
        const langs = it.code!.languages.map((l) => l.key);
        const lang = saved?.language && langs.includes(saved.language) ? saved.language : cs && langs.includes(cs.language) ? cs.language : langs[0];
        const codes: Record<string, string> = {};
        for (const l of langs) codes[l] = saved?.codes?.[l] ?? (cs?.language === l ? cs.code : it.code!.starter[l] ?? "");
        out[it.item] = { language: lang, codes };
      }
      setDrafts(out);
      setReady(true);
    })();
  }, [items, session]); // eslint-disable-line react-hooks/exhaustive-deps

  const d = drafts[item.item];
  const lang = d?.language || P.languages[0]?.key || "python";
  const code = d?.codes[lang] ?? "";

  // typing statistics, sent every 5 s while the editor is used
  const flush = () => {
    const a = acc.current;
    if (a.ins + a.dele + a.keys > 0) {
      engine.event("code_typing", a.item, a.lang, 0, engine.now(), { ins: a.ins, dele: a.dele, keys: a.keys, max_ins: a.max_ins, clear: a.clear,
        len: (drafts[a.item]?.codes[a.lang] ?? "").length });
    }
    acc.current = { ins: 0, dele: 0, keys: 0, max_ins: 0, clear: 0, item: item.item, lang };
  };
  const flushRef = useRef(flush);
  flushRef.current = flush;
  useEffect(() => { const id = setInterval(() => flushRef.current(), 5000); return () => { clearInterval(id); flushRef.current(); }; }, []);
  useEffect(() => { flushRef.current(); }, [idx, lang]);

  const save = useRef<ReturnType<typeof setTimeout> | null>(null);
  const update = (next: Draft) => {
    setDrafts((all) => ({ ...all, [item.item]: next }));
    if (save.current) clearTimeout(save.current);
    save.current = setTimeout(() => local.set(session, `code${item.item}`, next), 600);
  };
  const onType = (ty: Typing) => {
    const a = acc.current;
    a.item = item.item; a.lang = lang;
    a.ins += ty.ins; a.dele += ty.dele; a.keys += ty.keys; a.max_ins = Math.max(a.max_ins, ty.max_ins); a.clear += ty.clear || 0;
  };

  async function run(useCustom: boolean) {
    flush();
    setBusy("run");
    setResults((r) => ({ ...r, [item.item]: { ...r[item.item], error: undefined } }));
    try {
      const body: Record<string, unknown> = { item: item.item, language: lang, code, t: engine.now() };
      if (useCustom) body.input = custom[item.item] ?? "";
      const res = await api<RunResult>("/api/exam/code/run", { body });
      setResults((r) => ({ ...r, [item.item]: { ...r[item.item], run: res } }));
      engine.event("code_run", item.item, useCustom ? "custom" : "samples");
    } catch (e) {
      setResults((r) => ({ ...r, [item.item]: { ...r[item.item], error: e instanceof NetworkError ? t("codeKeptOffline") : errorFor(e, t) } }));
    } finally { setBusy(null); }
  }

  async function submit() {
    flush();
    setBusy("submit");
    setResults((r) => ({ ...r, [item.item]: { ...r[item.item], error: undefined } }));
    try {
      const res = await api<SubmitResult>("/api/exam/code/submit", { body: { item: item.item, language: lang, code, t: engine.now() } });
      setResults((r) => ({ ...r, [item.item]: { ...r[item.item], submit: res } }));
      setBest((b) => { const old = b[item.item]; return { ...b, [item.item]: !old || res.passed >= old.passed ? { verdict: res.verdict, passed: res.passed, total: res.total } : old }; });
      engine.event("code_submit", item.item, res.verdict, 0, engine.now(), { passed: res.passed, total: res.total });
      if (res.verdict === "accepted") onAccepted(item.item);
    } catch (e) {
      const msg = e instanceof NetworkError ? t("codeKeptOffline") : e instanceof ApiError && e.code === "busy" ? e.message : errorFor(e, t);
      setResults((r) => ({ ...r, [item.item]: { ...r[item.item], error: msg } }));
    } finally { setBusy(null); }
  }

  const res = results[item.item];
  const solved = useMemo(() => items.filter((it) => best[it.item]?.verdict === "accepted").length, [best, items]);

  return (
    <div className="space-y-4 pb-10">
      <div className="flex flex-wrap items-center gap-2">
        <div role="tablist" aria-label={t("problemsLabel")} className="flex flex-wrap gap-1.5">
          {items.map((it, i) => {
            const b = best[it.item];
            return (
              <button key={it.item} role="tab" aria-selected={i === idx} onClick={() => go(i)}
                className={cn("inline-flex items-center gap-1.5 rounded-xl border-2 px-3 py-1.5 text-sm font-semibold transition",
                  i === idx ? "border-pink-500 bg-pink-50 text-pink-800 dark:bg-pink-950/40 dark:text-pink-200" : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900")}>
                {b?.verdict === "accepted" ? <Icon name="checkCircle" size={15} className="text-emerald-600" /> : b ? <span className="tabular text-xs text-slate-500">{b.passed}/{b.total}</span> : null}
                P{i + 1} <span className="hidden font-normal text-slate-500 md:inline">· {it.code!.title}</span>
              </button>
            );
          })}
        </div>
        <span className="ml-auto text-sm text-slate-500">{solved}/{items.length} {t("v_accepted").toLowerCase()}</span>
        <Button size="sm" onClick={() => { flush(); onFinish(); }}><Icon name="send" size={15} />{t("finishTest")}</Button>
      </div>
      <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-900 md:hidden dark:bg-amber-950/50 dark:text-amber-200">{t("useLaptop")}</p>

      <div className="grid gap-4 lg:grid-cols-[5fr_7fr]">
        <Card className="h-fit bg-white lg:sticky lg:top-4 lg:max-h-[calc(100dvh-7rem)] lg:overflow-y-auto dark:bg-slate-950">
          <CardContent className="space-y-4 pt-5">
            <div>
              <p className="text-sm font-semibold text-pink-700 dark:text-pink-400">{t("problemN", { n: idx + 1 })}</p>
              <h1 className="text-2xl font-semibold tracking-tight">{P.title}</h1>
              <div className="mt-2 flex flex-wrap gap-1.5">
                <Badge><Icon name="timer" size={12} />{t("timeLimitS", { s: P.time_limit })}</Badge>
                <Badge tone="info"><Icon name="lock" size={12} />{t("hiddenTests", { n: P.hidden_tests })}</Badge>
                {best[item.item] && <Badge tone={verdictTone(best[item.item]!.verdict)}>{t("bestSoFar", { p: best[item.item]!.passed, t: best[item.item]!.total })}</Badge>}
              </div>
            </div>
            <Statement text={item.text} />
            <div className="space-y-3">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-500">{t("sampleTests")}</h3>
              {P.samples.map((s, i) => (
                <div key={i} className="grid gap-2 sm:grid-cols-2">
                  <Pre label={`${t("sampleN", { n: i + 1 })} · ${t("inputLabel")}`} text={s.input} />
                  <Pre label={t("expectedOutput")} text={s.output} />
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm font-semibold" htmlFor="lang">{t("languageLabel")}</label>
            <select id="lang" value={lang} disabled={!ready} onChange={(e) => d && update({ ...d, language: e.target.value })}
              className="h-9 rounded-lg border border-slate-300 bg-white px-2 text-sm font-semibold dark:border-slate-700 dark:bg-slate-900">
              {P.languages.map((l) => <option key={l.key} value={l.key}>{l.label}</option>)}
            </select>
            <Button variant="ghost" size="sm" onClick={() => setReset(true)} disabled={!ready}><Icon name="refresh" size={14} />{t("resetCode")}</Button>
            <span className="ml-auto hidden text-xs text-slate-500 sm:inline">{t("runHint")}</span>
          </div>
          {ready ? (
            <CodeEditor key={`${item.item}-${lang}`} value={code} language={lang} label={`${P.title} · ${lang}`} minHeight={380}
              className="max-h-[60dvh]" onChange={(v) => d && update({ ...d, codes: { ...d.codes, [lang]: v } })}
              events={{ onType, onRun: () => !busy && run(false), onDropInsert: (n) => engine.event("paste", item.item, "drop", n) }} />
          ) : <div className="h-96 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-900" />}
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" onClick={() => run(false)} disabled={!!busy || !ready}><Icon name="play" size={16} />{busy === "run" ? t("running") : t("runSamples")}</Button>
            <Button variant="ghost" onClick={() => setCustom((c) => ({ ...c, [item.item]: c[item.item] == null ? (P.samples[0]?.input ?? "") : null }))}>
              <Icon name="terminal" size={16} />{t("runCustom")}
            </Button>
            <Button className="ml-auto" onClick={submit} disabled={!!busy || !ready}><Icon name="send" size={16} />{busy === "submit" ? t("judging") : t("submitCode")}</Button>
          </div>
          {custom[item.item] != null && (
            <Card className="bg-white dark:bg-slate-950"><CardContent className="space-y-2 pt-4">
              <label htmlFor="custom" className="text-sm font-semibold">{t("customInput")}</label>
              <Textarea id="custom" value={custom[item.item]!} onChange={(e) => setCustom((c) => ({ ...c, [item.item]: e.target.value }))} className="min-h-24 font-mono text-sm" spellCheck={false} />
              <Button size="sm" variant="secondary" onClick={() => run(true)} disabled={!!busy}><Icon name="play" size={14} />{busy === "run" ? t("running") : t("runCustom")}</Button>
            </CardContent></Card>
          )}
          {res?.error && <Alert>{res.error}</Alert>}
          {res?.submit && <SubmitPanel r={res.submit} />}
          {res?.run && <RunPanel r={res.run} />}
        </div>
      </div>

      <Dialog open={reset} onClose={() => setReset(false)} title={t("resetCode")}>
        <p className="text-slate-600 dark:text-slate-300">{t("resetConfirm")}</p>
        <div className="mt-5 flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => setReset(false)}>{t("cancel")}</Button>
          <Button variant="danger" className="flex-1" onClick={() => { d && update({ ...d, codes: { ...d.codes, [lang]: P.starter[lang] ?? "" } }); setReset(false); }}>{t("resetCode")}</Button>
        </div>
      </Dialog>
    </div>
  );
}

function Panel({ title, children, tone }: { title: ReactNode; children: ReactNode; tone: string }) {
  return (
    <Card className="animate-fade-in bg-white dark:bg-slate-950"><CardContent className="space-y-3 pt-4">
      <div className={cn("flex flex-wrap items-center gap-2 text-sm font-semibold", tone)}>{title}</div>
      {children}
    </CardContent></Card>
  );
}

function SubmitPanel({ r }: { r: SubmitResult }) {
  const { t } = useT();
  return (
    <Panel tone="" title={<>
      <Badge tone={verdictTone(r.verdict)} className="text-sm">{t(verdictKey(r.verdict))}</Badge>
      <span>{t("testsPassed", { p: r.passed, t: r.total })}</span><span className="font-normal text-slate-500">· {r.seconds}s</span></>}>
      {r.compile_output ? <Pre label={t("errorOutput")} text={r.compile_output} tone="bad" /> : (
        <div className="flex flex-wrap gap-1.5">
          {r.tests.map((x) => (
            <span key={x.n} title={t(verdictKey(x.status))} className={cn("tabular inline-flex h-7 min-w-9 items-center justify-center gap-0.5 rounded-lg px-1.5 text-xs font-semibold",
              x.status === "passed" ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" : "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300")}>
              <Icon name={x.status === "passed" ? "check" : "x"} size={12} />{x.n}
            </span>
          ))}
        </div>
      )}
    </Panel>
  );
}

function RunPanel({ r }: { r: RunResult }) {
  const { t } = useT();
  if (r.mode === "custom") {
    return (
      <Panel tone="" title={<><Icon name="terminal" size={16} />{t("runCustom")} <Badge tone={r.status === "ok" ? "success" : "danger"}>{t(verdictKey(r.status))}</Badge></>}>
        {r.compile_output ? <Pre label={t("errorOutput")} text={r.compile_output} tone="bad" /> : <>
          <Pre label={t("yourOutput")} text={r.output ?? ""} />
          {r.stderr && <Pre label={t("errorOutput")} text={r.stderr} tone="bad" />}
        </>}
      </Panel>
    );
  }
  return (
    <Panel tone="" title={<><Icon name="play" size={16} />{t("sampleTests")} <Badge tone={verdictTone(r.verdict)}>{t(verdictKey(r.verdict))}</Badge>
      <span className="font-normal">{t("testsPassed", { p: r.passed, t: r.total })}</span></>}>
      {r.compile_output ? <Pre label={t("errorOutput")} text={r.compile_output} tone="bad" /> : r.tests.map((x) => (
        <details key={x.n} open={x.status !== "passed"} className="rounded-xl border border-slate-200 p-3 dark:border-slate-800">
          <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
            <Icon name={x.status === "passed" ? "checkCircle" : "alert"} size={16} className={x.status === "passed" ? "text-emerald-600" : "text-rose-600"} />
            {t("sampleN", { n: x.n })} · {t(verdictKey(x.status))} <span className="font-normal text-slate-500">{x.seconds}s</span>
          </summary>
          <div className="mt-3 grid gap-2 md:grid-cols-3">
            <Pre label={t("inputLabel")} text={x.input} />
            <Pre label={t("expectedOutput")} text={x.expected} tone="good" />
            <Pre label={t("yourOutput")} text={x.output} tone={x.status === "passed" ? "good" : "bad"} />
          </div>
          {x.stderr && <div className="mt-2"><Pre label={t("errorOutput")} text={x.stderr} tone="bad" /></div>}
        </details>
      ))}
    </Panel>
  );
}

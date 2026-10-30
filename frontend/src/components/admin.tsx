import { useState } from "react";
import { Icon } from "./Icon";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Textarea } from "./ui/form";
import { Alert } from "./ui/misc";
import { useToast } from "./ui/toast";

export function SittingStatus({ status }: { status: string }) {
  const tone = status === "live" ? "success" : status === "scheduled" ? "info" : status === "scoring" ? "warning" : "neutral";
  return <Badge tone={tone}>{status === "live" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />}{status}</Badge>;
}

export function CopyCode({ code, big }: { code: string; big?: boolean }) {
  const toast = useToast();
  return (
    <button onClick={() => navigator.clipboard?.writeText(code).then(() => toast("Copied " + code), () => {})} title="Copy"
      className={`inline-flex items-center gap-1.5 rounded-lg bg-slate-100 font-mono font-semibold tracking-wider hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 ${big ? "px-3 py-1.5 text-lg" : "px-2 py-0.5 text-sm"}`}>
      {code}<Icon name="file" size={big ? 16 : 13} className="opacity-60" />
    </button>
  );
}

export type BadRow = { line: number; problem: string };

/** Paste CSV or pick a file; shows the backend's row problems (bad_rows) next to the box. */
export function CsvBox({ label, sample, busy, onSubmit, rows, error, kind = "csv", rowLabel = "Line" }: {
  label: string; sample: string; busy: boolean; onSubmit: (csv: string) => void; rows?: BadRow[]; error?: string | null;
  kind?: "csv" | "json"; rowLabel?: string;
}) {
  const [text, setText] = useState("");
  const pick = async (f?: File) => { if (f) setText(await f.text()); };
  const sampleUrl = `data:${kind === "json" ? "application/json" : "text/csv"};charset=utf-8,` + encodeURIComponent(sample);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <label htmlFor="csv" className="text-sm font-semibold">{label}</label>
        <div className="flex gap-2">
          <a href={sampleUrl} download={`sample.${kind}`} className="inline-flex items-center gap-1 text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400"><Icon name="download" size={14} />Sample</a>
          <label className="inline-flex cursor-pointer items-center gap-1 text-sm font-semibold text-pink-700 hover:underline dark:text-pink-400">
            <Icon name="upload" size={14} />Choose file
            <input type="file" accept={kind === "json" ? ".json,application/json" : ".csv,text/csv"} className="sr-only" onChange={(e) => pick(e.target.files?.[0])} />
          </label>
        </div>
      </div>
      <Textarea id="csv" value={text} onChange={(e) => setText(e.target.value)} placeholder={sample.split("\n").slice(0, 2).join("\n")} className="min-h-32 font-mono text-xs" spellCheck={false} />
      {error && <Alert>{error}</Alert>}
      {rows && rows.length > 0 && (
        <div className="max-h-48 overflow-auto rounded-xl border border-rose-200 dark:border-rose-900">
          <table className="w-full text-sm">
            <thead className="bg-rose-50 text-left text-xs text-rose-800 dark:bg-rose-950 dark:text-rose-200"><tr><th className="px-3 py-1.5">{rowLabel}</th><th className="px-3 py-1.5">Problem</th></tr></thead>
            <tbody>{rows.map((r, i) => <tr key={i} className="border-t border-rose-100 dark:border-rose-900"><td className="tabular px-3 py-1.5">{r.line}</td><td className="px-3 py-1.5">{r.problem}</td></tr>)}</tbody>
          </table>
        </div>
      )}
      <Button disabled={busy || !text.trim()} onClick={() => onSubmit(text)}><Icon name="upload" size={16} />{busy ? "Uploading…" : "Upload"}</Button>
    </div>
  );
}

export function downloadText(name: string, text: string, type = "text/csv") {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = Object.assign(document.createElement("a"), { href: url, download: name });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

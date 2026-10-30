import { useState } from "react";
import { Dialog } from "@/components/ui/misc";
import { mmss } from "@/lib/format";

export type SnapshotRow = { id: number; t: number; reason: string; label: string; phase: "before" | "at" | "after"; image: string; taken_at: string };

/** Snapshots grouped by flagged moment (before / at / after), shown as small thumbnails; a click opens the larger one. */
export function SnapshotGroups({ rows, reasonText, phaseText }: {
  rows: SnapshotRow[];
  reasonText: (reason: string, fallback: string) => string;
  phaseText: (phase: SnapshotRow["phase"]) => string;
}) {
  const [open, setOpen] = useState<SnapshotRow | null>(null);
  const groups: SnapshotRow[][] = [];
  for (const r of [...rows].sort((a, b) => a.t - b.t)) {
    const g = groups.find((x) => x[0].reason === r.reason && Math.abs(x[0].t - r.t) <= 15);
    if (g) g.push(r); else groups.push([r]);
  }
  const order = { before: 0, at: 1, after: 2 };
  return (
    <>
      <ul className="space-y-3">
        {groups.map((g) => {
          g.sort((a, b) => order[a.phase] - order[b.phase]);
          const at = g.find((x) => x.phase === "at") || g[0];
          return (
            <li key={at.id} className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-950">
              <p className="text-sm font-semibold"><span className="tabular text-slate-500">{mmss(at.t)}</span> · {reasonText(at.reason, at.label)}</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {g.map((x) => (
                  <button key={x.id} type="button" onClick={() => setOpen(x)} className="group text-left">
                    <img src={x.image} alt={`${reasonText(x.reason, x.label)} · ${phaseText(x.phase)}`} loading="lazy"
                      className="h-20 w-[6.7rem] rounded-md object-cover ring-1 ring-slate-300 transition group-hover:ring-2 group-hover:ring-pink-600 dark:ring-slate-700" />
                    <span className="mt-0.5 block text-xs text-slate-500">{phaseText(x.phase)} · {mmss(x.t)}</span>
                  </button>
                ))}
              </div>
            </li>
          );
        })}
      </ul>
      <Dialog open={!!open} onClose={() => setOpen(null)} title={open ? `${mmss(open.t)} · ${reasonText(open.reason, open.label)} · ${phaseText(open.phase)}` : ""}>
        {open && <img src={open.image} alt="" className="w-full rounded-lg" style={{ imageRendering: "auto" }} />}
      </Dialog>
    </>
  );
}

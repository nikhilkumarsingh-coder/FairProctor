import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export const Skeleton = ({ className }: { className?: string }) => (
  <div className={cn("animate-pulse rounded-lg bg-slate-200 dark:bg-slate-800", className)} />
);

export const Progress = ({ value, className, label }: { value: number; className?: string; label?: string }) => (
  <div role="progressbar" aria-label={label} aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)}
    className={cn("h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800", className)}>
    <div className="brand-bg h-full rounded-full transition-[width] duration-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
  </div>
);

export function Alert({ tone = "danger", children, className }: { tone?: "danger" | "warning" | "success" | "info"; children: ReactNode; className?: string }) {
  const tones = {
    danger: "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/60 dark:text-rose-200",
    warning: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/60 dark:text-amber-200",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200",
    info: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-900 dark:bg-sky-950/60 dark:text-sky-200",
  };
  return <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-lg border px-4 py-3 text-sm", tones[tone], className)}>{children}</div>;
}

/** Modal dialog on the native <dialog> element (focus trap and Esc for free). side="bottom" = mobile sheet. */
export function Dialog({ open, onClose, title, children, side = "center", className }: {
  open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; side?: "center" | "bottom"; className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog ref={ref} onClose={onClose} onClick={(e) => e.target === ref.current && onClose()}
      className={cn(
        "m-auto w-[min(100%-2rem,32rem)] rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-lg backdrop:bg-slate-950/50 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-50",
        side === "bottom" && "mb-0 w-full max-w-lg rounded-b-none sm:mb-auto sm:rounded-xl",
        className,
      )}>
      {open && (
        <div className="animate-fade-in p-5">
          <div className="mb-3 flex items-start justify-between gap-4">
            <h2 className="text-lg font-semibold">{title}</h2>
            <button onClick={onClose} aria-label="Close" className="-m-2 rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800">✕</button>
          </div>
          {children}
        </div>
      )}
    </dialog>
  );
}

export function Tabs<T extends string>({ value, onChange, items, className }: {
  value: T; onChange: (v: T) => void; items: { value: T; label: ReactNode }[]; className?: string;
}) {
  return (
    <div role="tablist" className={cn("inline-flex flex-wrap gap-0 border-b border-slate-200 dark:border-slate-800", className)}>
      {items.map((it) => (
        <button key={it.value} role="tab" aria-selected={value === it.value} onClick={() => onChange(it.value)}
          className={cn("-mb-px border-b-2 px-3.5 py-2 text-sm font-medium transition-colors",
            value === it.value ? "border-pink-600 text-slate-900 dark:border-pink-400 dark:text-slate-50" : "border-transparent text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100")}>
          {it.label}
        </button>
      ))}
    </div>
  );
}

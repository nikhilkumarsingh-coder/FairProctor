import { forwardRef, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const field = "w-full rounded-lg border border-slate-300 bg-white px-3.5 text-base text-slate-900 placeholder:text-slate-400 transition-colors focus:border-pink-600 focus:outline-none focus:ring-3 focus:ring-pink-600/15 aria-[invalid=true]:border-rose-600 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-50";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(({ className, ...p }, ref) => (
  <input ref={ref} className={cn(field, "h-11", className)} {...p} />
));
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(({ className, ...p }, ref) => (
  <textarea ref={ref} className={cn(field, "min-h-28 py-3", className)} {...p} />
));
Textarea.displayName = "Textarea";

/** Label + control + help/error text, wired for screen readers. */
export function Field({ id, label, help, error, children }: { id: string; label: ReactNode; help?: ReactNode; error?: string | null; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-slate-700 dark:text-slate-300">{label}</label>
      {children}
      {error ? <p id={`${id}-err`} role="alert" className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
        : help ? <p id={`${id}-help`} className="text-sm text-slate-500 dark:text-slate-400">{help}</p> : null}
    </div>
  );
}

export function Checkbox({ id, checked, onChange, children }: { id: string; checked: boolean; onChange: (v: boolean) => void; children: ReactNode }) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-start gap-3 rounded-lg p-2 -m-2 hover:bg-slate-100 dark:hover:bg-slate-800/60">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 h-5 w-5 shrink-0 cursor-pointer rounded accent-pink-600" />
      <span className="text-base leading-snug">{children}</span>
    </label>
  );
}

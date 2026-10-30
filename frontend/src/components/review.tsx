// Small pieces shared by the reviewer and admin screens.
import { cn } from "@/lib/cn";
import type { Band } from "@/lib/types";
import { Icon, type IconName } from "./Icon";
import { Badge } from "./ui/badge";

export const FAMILIES: Record<string, { label: string; icon: IconName; c: string }> = {
  match: { label: "Answer match", icon: "match", c: "bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-950 dark:text-fuchsia-300" },
  timing: { label: "Timing", icon: "timer", c: "bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300" },
  pause: { label: "Silent pause", icon: "pause", c: "bg-violet-100 text-violet-800 dark:bg-violet-950 dark:text-violet-300" },
  focus: { label: "Left window", icon: "window", c: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300" },
  paste: { label: "Paste", icon: "paste", c: "bg-teal-100 text-teal-800 dark:bg-teal-950 dark:text-teal-300" },
  person: { label: "Another person", icon: "users", c: "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-300" },
  phone: { label: "Phone in view", icon: "phone", c: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300" },
  code_match: { label: "Code match", icon: "code", c: "bg-fuchsia-100 text-fuchsia-800 dark:bg-fuchsia-950 dark:text-fuchsia-300" },
  typing: { label: "Typing", icon: "key", c: "bg-indigo-100 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-300" },
  terminated: { label: "Test ended", icon: "lock", c: "bg-rose-600 text-white dark:bg-rose-700" },
  relogin: { label: "Logged in again", icon: "user", c: "bg-slate-200 text-slate-800 dark:bg-slate-800 dark:text-slate-200" },
  disconnect: { label: "Disconnects", icon: "wifiOff", c: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
  device_check: { label: "Device check", icon: "monitor", c: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" },
};

export function FamilyChip({ family, active, onClick }: { family: string; active?: boolean; onClick?: () => void }) {
  const f = FAMILIES[family] || { label: family, icon: "info" as IconName, c: "bg-slate-100 text-slate-700" };
  const Tag = onClick ? "button" : "span";
  return (
    <Tag onClick={onClick} aria-pressed={onClick ? !!active : undefined}
      className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold whitespace-nowrap", f.c,
        onClick && "cursor-pointer ring-offset-1 hover:brightness-95", active && "ring-2 ring-pink-500 dark:ring-offset-slate-950")}>
      <Icon name={f.icon} size={12} />{f.label}
    </Tag>
  );
}

export const BAND_LABEL: Record<Band, string> = { review_first: "Review first", review: "Review", clear: "Auto-cleared" };

export function BandBadge({ band }: { band: Band }) {
  return <Badge tone={band === "review_first" ? "danger" : band === "review" ? "warning" : "success"}>{BAND_LABEL[band]}</Badge>;
}

const STATUS: Record<string, { label: string; tone: "neutral" | "success" | "warning" | "danger" | "info" | "outline" }> = {
  new: { label: "New", tone: "info" },
  auto_cleared: { label: "Auto-cleared", tone: "outline" },
  confirmed: { label: "Confirmed", tone: "danger" },
  cleared: { label: "Cleared", tone: "success" },
  need_more: { label: "Needs more info", tone: "warning" },
  appeal_open: { label: "Appeal open", tone: "warning" },
};
export function StatusBadge({ status }: { status: string }) {
  const s = STATUS[status] || { label: status, tone: "neutral" as const };
  return <Badge tone={s.tone}>{s.label}</Badge>;
}

/** 0–100 priority with the review line (50) and the review-first line marked. Not a probability. */
export function PriorityBar({ value, band, lines, big }: { value: number; band: Band; lines?: { review: number; review_first: number | null }; big?: boolean }) {
  const c = band === "review_first" ? "bg-rose-500" : band === "review" ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className={cn("flex items-center gap-2", big && "gap-3")}>
      <span className={cn("tabular font-semibold", big ? "w-12 text-3xl" : "w-7 text-sm")}>{Math.round(value)}</span>
      <div className={cn("relative flex-1 rounded-full bg-slate-200 dark:bg-slate-800", big ? "h-3" : "h-1.5")} role="meter"
        aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value)} aria-label="Review priority">
        <div className={cn("h-full rounded-full", c)} style={{ width: `${Math.max(2, Math.min(100, value))}%` }} />
        {lines && <Mark at={lines.review} big={big} label="review line" />}
        {lines?.review_first != null && <Mark at={lines.review_first} big={big} label="review first" />}
      </div>
    </div>
  );
}
function Mark({ at, big, label }: { at: number; big?: boolean; label: string }) {
  return (
    <span title={`${label} (${Math.round(at)})`} className={cn("absolute top-1/2 w-0.5 -translate-y-1/2 rounded bg-slate-900/70 dark:bg-white/70", big ? "h-5" : "h-3")}
      style={{ left: `${at}%` }} />
  );
}

export function NetBadge({ bandwidth, device }: { bandwidth?: string; device?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
      <span className="inline-flex items-center gap-0.5" title={device === "phone" ? "Phone" : "Desktop"}><Icon name={device === "phone" ? "phone" : "monitor"} size={13} /></span>
      {bandwidth === "low" && <span className="inline-flex items-center gap-0.5 rounded bg-slate-100 px-1 font-semibold dark:bg-slate-800" title="Low bandwidth (2G)"><Icon name="wifiOff" size={12} />2G</span>}
    </span>
  );
}

export const clock = (t: number) => `${String(Math.floor(t / 60)).padStart(2, "0")}:${String(Math.floor(t % 60)).padStart(2, "0")}`;

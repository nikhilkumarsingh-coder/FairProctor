import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { Icon } from "./Icon";

/** A small calculator for the exam top bar: one icon that drops down a basic calculator (+ − × ÷, brackets, %).
 *  It is evaluated with a tiny parser (never eval), works with the mouse, touch or keyboard, and sends nothing. */
export function CalculatorButton() {
  const { t } = useT();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const btn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const away = (e: PointerEvent) => { if (!wrap.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);

  return (
    <div ref={wrap} className="relative">
      <button ref={btn} onClick={() => setOpen((o) => !o)} aria-expanded={open} aria-haspopup="dialog"
        aria-label={t("calculator")} title={t("calculator")}
        className={cn("rounded-lg p-2 text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
          open && "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-50")}>
        <Icon name="calculator" size={18} />
      </button>
      {open && <CalculatorPanel onClose={() => { setOpen(false); btn.current?.focus(); }} />}
    </div>
  );
}

const OPS = "+−×÷";

function CalculatorPanel({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const [expr, setExpr] = useState("");
  const [last, setLast] = useState<{ expr: string; value: string } | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  const screen = useRef<HTMLDivElement>(null);

  useEffect(() => { panel.current?.focus(); }, []);
  useEffect(() => { screen.current?.scrollTo({ left: screen.current.scrollWidth }); }, [expr]);

  const preview = expr && /[+−×÷%(]/.test(expr) ? format(evaluate(expr)) : "";

  function next(e: string, k: string): string {
    const prev = e.slice(-1);
    const fromResult = !!last && last.value !== "error" && e === last.value.replace("-", "−");
    if (OPS.includes(k)) {
      if (!e) return k === "−" ? "−" : e;
      if (OPS.includes(prev)) return e.length === 1 && k !== "−" ? e : e.slice(0, -1) + k;   // replace the operator
      if (prev === "(" && k !== "−") return e;
      if (prev === ".") return e.slice(0, -1) + k;
      return e + k;
    }
    if (k === ".") {
      if (fromResult) return "0.";
      const num = e.split(/[+−×÷()%]/).pop() || "";
      if (num.includes(".")) return e;
      return e + (num === "" ? "0." : ".");
    }
    if (k === "%") return e && /[0-9)]/.test(prev) ? e + "%" : e;
    if (k === ")") {
      const open = (e.match(/\(/g) || []).length - (e.match(/\)/g) || []).length;
      return open > 0 && /[0-9)%]/.test(prev) ? e + ")" : e;
    }
    if (k === "(") return fromResult ? "(" : /[0-9.)%]/.test(prev) ? e + "×(" : e + "(";
    if (fromResult) return k;                                         // a digit after "=" starts a new sum
    return e.length < 40 ? e + k : e;
  }

  function press(k: string) {
    if (k === "C") { setExpr(""); setLast(null); return; }
    if (k === "⌫") { setExpr(expr.slice(0, -1)); return; }
    if (k === "=") {
      if (!expr) return;
      const v = format(evaluate(expr));
      if (v === "") return;                                           // unfinished, e.g. "5×"
      setLast({ expr, value: v });
      setExpr(v === "error" ? "" : v.replace("-", "−"));
      return;
    }
    setExpr(next(expr, k));
  }

  function onKey(e: React.KeyboardEvent) {
    const map: Record<string, string> = { "*": "×", x: "×", X: "×", "/": "÷", "-": "−", "+": "+", Enter: "=", "=": "=",
      Backspace: "⌫", Delete: "C", c: "C", C: "C", ".": ".", ",": ".", "%": "%", "(": "(", ")": ")" };
    if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
    const k = /^[0-9]$/.test(e.key) ? e.key : map[e.key];
    if (k) { e.preventDefault(); press(k); }   // (not stopped: typing here still counts as activity, not a silent pause)
  }

  const keys: { k: string; label?: string; tone?: "op" | "eq" | "fn" }[][] = [
    [{ k: "C", tone: "fn" }, { k: "(", tone: "fn" }, { k: ")", tone: "fn" }, { k: "÷", tone: "op" }],
    [{ k: "7" }, { k: "8" }, { k: "9" }, { k: "×", tone: "op" }],
    [{ k: "4" }, { k: "5" }, { k: "6" }, { k: "−", tone: "op" }],
    [{ k: "1" }, { k: "2" }, { k: "3" }, { k: "+", tone: "op" }],
    [{ k: "%", tone: "fn" }, { k: "0" }, { k: "." }, { k: "=", tone: "eq" }],
  ];
  const aria: Record<string, string> = { C: t("calcClearAria"), "÷": "divide", "×": "multiply", "−": "minus", "+": "plus", "=": "equals", "%": "percent", ".": "point" };

  return (
    <div ref={panel} role="dialog" aria-label={t("calculator")} tabIndex={-1} onKeyDown={onKey}
      className="animate-fade-in absolute right-0 top-full z-50 mt-2 w-64 rounded-2xl border border-slate-200 bg-white p-3 shadow-xl outline-none dark:border-slate-700 dark:bg-slate-900">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500">{t("calculator")}</span>
        <button onClick={onClose} aria-label={t("calcClose")} className="rounded-md p-1 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"><Icon name="x" size={14} /></button>
      </div>
      <div className="mb-3 rounded-xl bg-slate-50 px-3 py-2 text-right dark:bg-slate-950" aria-live="polite">
        <p className="h-4 truncate text-xs text-slate-400 tabular">{last ? `${last.expr} =` : ""}</p>
        <div className="flex items-center gap-2">
          <div ref={screen} dir="ltr" className="tabular flex-1 overflow-x-auto whitespace-nowrap text-2xl font-semibold text-slate-900 [scrollbar-width:none] dark:text-slate-50">
            {expr || (last?.value === "error" ? <span className="text-base text-rose-600">{t("calcError")}</span> : "0")}
          </div>
          <button onClick={() => press("⌫")} aria-label={t("calcBack")} className="rounded-md p-1 text-slate-500 hover:bg-slate-200 dark:hover:bg-slate-800">
            <Icon name="left" size={16} />
          </button>
        </div>
        <p className="h-4 truncate text-xs text-slate-500 tabular">{preview && preview !== "error" ? `= ${preview}` : ""}</p>
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {keys.flat().map(({ k, label, tone }) => (
          <button key={k} onClick={() => press(k)} aria-label={aria[k] || label || k}
            className={cn("tabular h-11 rounded-lg text-lg font-medium transition-colors active:scale-95",
              tone === "eq" ? "bg-brand text-white hover:bg-brand-hover dark:text-slate-950"
                : tone === "op" ? "bg-pink-50 text-pink-800 hover:bg-pink-100 dark:bg-pink-950/50 dark:text-pink-200 dark:hover:bg-pink-950"
                  : tone === "fn" ? "bg-slate-100 text-slate-700 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
                    : "border border-slate-200 bg-white text-slate-900 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-50 dark:hover:bg-slate-800")}>
            {label || k}
          </button>
        ))}
      </div>
    </div>
  );
}

/** Number shown on the screen: up to 12 significant digits, no float noise (0.1 + 0.2 = 0.3). */
export function format(v: number | null): string {
  if (v === null) return "";
  if (!Number.isFinite(v)) return "error";
  const r = Number(v.toPrecision(12));
  return Math.abs(r) >= 1e15 || (r !== 0 && Math.abs(r) < 1e-9) ? r.toExponential() : String(r);
}

/** + − × ÷ with the usual precedence, brackets (unclosed ones close at the end), unary minus, postfix % (= ÷ 100).
 *  null when the expression is unfinished (e.g. ends with an operator). */
export function evaluate(src: string): number | null {
  const s = src.replace(/−/g, "-").replace(/×/g, "*").replace(/÷/g, "/");
  let i = 0;
  const peek = () => s[i];
  function number(): number | null {
    const m = /^(\d+\.?\d*|\.\d+)/.exec(s.slice(i));
    if (!m) return null;
    i += m[0].length;
    return parseFloat(m[0]);
  }
  function primary(): number | null {
    if (peek() === "(") {
      i++;
      const v = expr();
      if (peek() === ")") i++;
      return v;
    }
    return number();
  }
  function factor(): number | null {
    if (peek() === "-") { i++; const v = factor(); return v === null ? null : -v; }
    if (peek() === "+") { i++; return factor(); }
    let v = primary();
    while (v !== null && peek() === "%") { i++; v = v / 100; }
    return v;
  }
  function term(): number | null {
    let v = factor();
    while (v !== null && (peek() === "*" || peek() === "/" || peek() === "(")) {
      const op = peek() === "(" ? "*" : s[i++];
      const r = factor();
      if (r === null) return null;
      v = op === "*" ? v * r : v / r;
    }
    return v;
  }
  function expr(): number | null {
    let v = term();
    while (v !== null && (peek() === "+" || peek() === "-")) {
      const op = s[i++];
      const r = term();
      if (r === null) return null;
      v = op === "+" ? v + r : v - r;
    }
    return v;
  }
  if (!s) return null;
  const v = expr();
  return i === s.length ? v : null;
}

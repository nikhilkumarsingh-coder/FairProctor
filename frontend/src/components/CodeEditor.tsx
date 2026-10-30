// A small code editor: a transparent <textarea> over highlighted code (highlight.js), with line numbers,
// Tab / Shift+Tab indentation, auto-indent on Enter and Ctrl+Enter to run. It also reports typing statistics
// (inserted, deleted, the largest single non-paste insertion) for the coding integrity signals.
import hljs from "highlight.js/lib/core";
import cpp from "highlight.js/lib/languages/cpp";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import python from "highlight.js/lib/languages/python";
import { useMemo, useRef, type KeyboardEvent } from "react";
import { cn } from "@/lib/cn";

hljs.registerLanguage("python", python);
hljs.registerLanguage("cpp", cpp);
hljs.registerLanguage("java", java);
hljs.registerLanguage("javascript", javascript);

export type Typing = { ins: number; dele: number; keys: number; max_ins: number; clear?: number };
export type EditorEvents = { onType?: (t: Typing) => void; onDropInsert?: (chars: number) => void; onRun?: () => void };

const highlight = (code: string, lang: string) => {
  try { return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value; } catch { return escape(code); }
};
const escape = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const INDENT = "    ";
const FONT = "font-mono text-[13.5px] leading-[1.6]";

/** Read-only highlighted code with line numbers; `marks` highlights lines (e.g. lines that match another program). */
export function CodeBlock({ code, language, marks, className }: { code: string; language: string; marks?: number[]; className?: string }) {
  const html = useMemo(() => highlight(code, language).split("\n"), [code, language]);
  const set = new Set(marks || []);
  return (
    <div className={cn("hljs-theme overflow-auto rounded-xl border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950", className)}>
      <table className={cn("w-full border-collapse", FONT)}>
        <tbody>
          {html.map((line, i) => (
            <tr key={i} className={set.has(i + 1) ? "bg-amber-100/80 dark:bg-amber-900/30" : undefined}>
              <td className="w-10 select-none border-r border-slate-200 px-2 text-right align-top text-slate-400 dark:border-slate-800">{i + 1}</td>
              <td className="whitespace-pre px-3" dangerouslySetInnerHTML={{ __html: line || " " }} />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CodeEditor({ value, onChange, language, events, label, className, minHeight = 320 }: {
  value: string; onChange: (v: string) => void; language: string; events?: EditorEvents; label: string; className?: string; minHeight?: number;
}) {
  const ta = useRef<HTMLTextAreaElement>(null);
  const prev = useRef(value);
  const pasting = useRef(false);
  const html = useMemo(() => highlight(value, language) + "\n", [value, language]);
  const lines = value.split("\n").length;

  /** Replace the selection keeping the browser's undo history where possible. */
  function insert(text: string, selectStart?: number, selectEnd?: number) {
    const el = ta.current!;
    el.focus();
    if (selectStart !== undefined) el.setSelectionRange(selectStart, selectEnd ?? selectStart);
    // execCommand keeps Ctrl+Z working in a textarea; setRangeText is the fallback
    if (!document.execCommand?.("insertText", false, text)) {
      el.setRangeText(text, el.selectionStart, el.selectionEnd, "end");
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    const el = e.currentTarget;
    const { selectionStart: s, selectionEnd: en, value: v } = el;
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); events?.onRun?.(); return; }
    if (e.key === "Tab") {
      e.preventDefault();
      const ls = v.lastIndexOf("\n", s - 1) + 1;
      if (s === en && !e.shiftKey) { insert(INDENT); return; }
      // indent or dedent every selected line
      const le = en;
      const block = v.slice(ls, le);
      const changed = e.shiftKey ? block.replace(/^( {1,4}|\t)/gm, "") : block.replace(/^/gm, INDENT);
      insert(changed, ls, le);
      el.setSelectionRange(ls, ls + changed.length);
      return;
    }
    if (e.key === "Enter" && !e.shiftKey && !e.altKey) {
      e.preventDefault();
      const ls = v.lastIndexOf("\n", s - 1) + 1;
      const line = v.slice(ls, s);
      let indent = line.match(/^\s*/)![0];
      const t = line.trimEnd();
      if (t.endsWith(":") || t.endsWith("{") || t.endsWith("(") || t.endsWith("[")) indent += INDENT;
      const after = v.slice(en, en + 1);
      if (t.endsWith("{") && after === "}") {                      // {|} → opens a block
        insert("\n" + indent + "\n" + indent.slice(INDENT.length));
        el.setSelectionRange(s + 1 + indent.length, s + 1 + indent.length);
        return;
      }
      insert("\n" + indent);
      return;
    }
    if (e.key === "}" && s === en) {                                // dedent a closing brace on an empty line
      const ls = v.lastIndexOf("\n", s - 1) + 1;
      const before = v.slice(ls, s);
      if (/^\s+$/.test(before) && before.length >= INDENT.length) {
        e.preventDefault();
        insert(before.slice(INDENT.length) + "}", ls, s);
      }
    }
  }

  function onInput(next: string, inputType?: string) {
    const old = prev.current;
    prev.current = next;
    const delta = next.length - old.length;
    if (inputType === "insertFromPaste" || pasting.current) { pasting.current = false; return; }   // counted as a paste event
    if (inputType === "insertFromDrop" && delta > 0) { events?.onDropInsert?.(delta); return; }
    const ins = Math.max(0, delta), dele = Math.max(0, -delta);
    if (dele >= 40) { events?.onType?.({ ins: 0, dele: 0, keys: 1, max_ins: 0, clear: dele }); return; }   // clearing a block (e.g. the starter code)
    events?.onType?.({ ins, dele, keys: 1, max_ins: ins });
  }

  return (
    <div className={cn("relative overflow-auto rounded-xl border border-slate-300 bg-white focus-within:border-pink-600 focus-within:ring-3 focus-within:ring-pink-600/15 dark:border-slate-700 dark:bg-slate-950", className)}
      style={{ minHeight }}>
      <div className="hljs-theme flex min-h-full">
        <div aria-hidden className={cn("sticky left-0 z-10 select-none border-r border-slate-200 bg-slate-50 py-3 pl-2 pr-2 text-right text-slate-400 dark:border-slate-800 dark:bg-slate-900", FONT)}>
          {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
        </div>
        <div className="relative min-w-0 flex-1">
          <pre aria-hidden className={cn("pointer-events-none m-0 w-max min-w-full whitespace-pre px-3 py-3", FONT)} dangerouslySetInnerHTML={{ __html: html }} />
          <textarea ref={ta} value={value} spellCheck={false} autoCapitalize="off" autoComplete="off" autoCorrect="off" aria-label={label}
            onChange={(e) => { onChange(e.target.value); onInput(e.target.value, (e.nativeEvent as InputEvent).inputType); }}
            onPaste={() => { pasting.current = true; }}
            onKeyDown={onKeyDown}
            className={cn("absolute inset-0 h-full w-full resize-none overflow-hidden whitespace-pre bg-transparent px-3 py-3 text-transparent caret-slate-900 outline-none selection:bg-pink-300/40 dark:caret-white", FONT)}
            style={{ WebkitTextFillColor: "transparent" }} />
        </div>
      </div>
    </div>
  );
}

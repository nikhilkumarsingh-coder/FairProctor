// The exam recorder + uploader. Every event gets a sequence number and goes to IndexedDB first, then to the
// server in batches every 10 s. The server stores each (session, seq) once, so resending after a 2G drop is safe.
import { api, ApiError, NetworkError } from "./api";
import { kv, queue } from "./idb";
import type { StartRes } from "./types";

export type Sync = "saved" | "sending" | "offline" | "closed";
type Ev = { k: "e"; seq: number; t: number; type: string; item: number; option: string; chars: number; meta?: Record<string, number> };
type Fr = { k: "f"; seq: number; t: number; faces: number; face_visible: boolean; gaze: string; brightness?: number; blur?: number; phone?: number };
type Rec = Ev | Fr;

const BATCH = 300, EVERY = 10_000;

export class ExamEngine {
  readonly session: string;
  private seq = 0;
  private t0 = performance.now();
  private base: number;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private busy = false;
  private backoff = EVERY;
  private stopped = false;
  sync: Sync = "saved";
  pending = 0;
  /** set when the server ended the test by a proctoring rule (it also checks its own counts) */
  terminated: string | null = null;
  onChange: () => void = () => {};

  constructor(start: StartRes) {
    this.session = start.session_id;
    this.base = start.elapsed_s;
    this.seq = start.last_seq;
  }

  async init() {
    const local = (await kv.get<number>(`seq:${this.session}`)) || 0;
    this.seq = Math.max(this.seq, local);
    this.pending = await queue.count(this.session);
    this.schedule(1000);
    window.addEventListener("online", this.kick);
  }

  stop() {
    this.stopped = true;
    if (this.timer) clearTimeout(this.timer);
    window.removeEventListener("online", this.kick);
  }

  /** Seconds since the test started (server clock at start + monotonic clock since). */
  now() { return Math.round((this.base + (performance.now() - this.t0) / 1000) * 100) / 100; }

  private async put(r: Rec) {
    await queue.push(this.session, r.seq, r);
    await kv.set(`seq:${this.session}`, r.seq);
    this.pending++;
    this.onChange();
  }

  event(type: string, item: number, option = "", chars = 0, t = this.now(), meta?: Record<string, number>) {
    return this.put({ k: "e", seq: ++this.seq, t, type, item, option: option.slice(0, 40), chars, ...(meta ? { meta } : {}) });
  }

  frame(f: Omit<Fr, "k" | "seq" | "t">) {
    return this.put({ k: "f", seq: ++this.seq, t: this.now(), ...f });
  }

  private kick = () => { this.backoff = EVERY; this.schedule(0); };

  private schedule(ms: number) {
    if (this.stopped) return;
    if (this.timer) clearTimeout(this.timer);
    this.timer = setTimeout(() => this.flush().catch(() => {}), ms);
  }

  private set(s: Sync) { if (this.sync !== s) { this.sync = s; this.onChange(); } }

  /** Send everything queued. Returns true when the queue is empty. */
  async flush(): Promise<boolean> {
    if (this.busy || this.sync === "closed") return this.pending === 0;
    this.busy = true;
    try {
      for (;;) {
        const recs = await queue.oldest<Rec>(this.session, BATCH);
        this.pending = await queue.count(this.session);
        if (!recs.length) { this.set("saved"); this.backoff = EVERY; return true; }
        this.set("sending");
        const top = recs[recs.length - 1].seq;
        try {
          const res = await api<{ terminated?: string }>("/api/exam/events", {
            body: {
              events: recs.filter((r): r is Ev => r.k === "e").map(({ k, ...e }) => e),
              frames: recs.filter((r): r is Fr => r.k === "f").map(({ k, ...f }) => f),
            },
          });
          if (res?.terminated && !this.terminated) { this.terminated = res.terminated; this.onChange(); }
        } catch (e) {
          if (e instanceof ApiError && e.code === "sitting_closed") {
            await queue.dropUpTo(this.session, 999999999);
            this.pending = 0;
            this.set("closed");
            this.stop();
            return true;
          }
          if (e instanceof ApiError && e.status === 422) {
            console.warn("dropping a batch the server rejected", e);   // never let one bad record block the queue
          } else {
            throw e;
          }
        }
        await queue.dropUpTo(this.session, top);
        this.pending = await queue.count(this.session);
        this.onChange();
      }
    } catch (e) {
      this.set(e instanceof NetworkError ? "offline" : "sending");
      this.backoff = Math.min(this.backoff * 2, 60_000);
      return false;
    } finally {
      this.busy = false;
      if (!this.stopped) this.schedule(this.sync === "saved" ? EVERY : this.backoff);
    }
  }
}

/** Try hard to send everything before submitting: up to `ms`, false if still offline. */
export async function drain(engine: ExamEngine, ms = 15000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (await engine.flush()) return true;
    if (engine.sync === "offline") return false;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/** Answers, marks and position are kept on the phone too, so a reload offline loses nothing. */
export const local = {
  get: <T,>(session: string, k: string) => kv.get<T>(`${k}:${session}`),
  set: (session: string, k: string, v: unknown) => kv.set(`${k}:${session}`, v),
};

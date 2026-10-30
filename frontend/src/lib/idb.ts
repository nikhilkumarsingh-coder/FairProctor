// Minimal IndexedDB wrapper for the exam queue (falls back to memory if IndexedDB is unavailable).
const DB = "fairproctor", VER = 1;
let dbp: Promise<IDBDatabase | null> | null = null;
const mem = { kv: new Map<string, unknown>(), q: new Map<string, unknown>() };

function open(): Promise<IDBDatabase | null> {
  if (!dbp) {
    dbp = new Promise((resolve) => {
      try {
        const r = indexedDB.open(DB, VER);
        r.onupgradeneeded = () => {
          r.result.createObjectStore("kv");
          r.result.createObjectStore("q");
        };
        r.onsuccess = () => resolve(r.result);
        r.onerror = () => resolve(null);
      } catch {
        resolve(null);
      }
    });
  }
  return dbp;
}

function req<T>(r: IDBRequest<T>) {
  return new Promise<T>((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
}

async function tx(store: "kv" | "q", mode: IDBTransactionMode) {
  const db = await open();
  return db ? db.transaction(store, mode).objectStore(store) : null;
}

export const kv = {
  async get<T>(key: string): Promise<T | undefined> {
    const s = await tx("kv", "readonly");
    return s ? ((await req(s.get(key))) as T | undefined) : (mem.kv.get(key) as T | undefined);
  },
  async set(key: string, value: unknown) {
    const s = await tx("kv", "readwrite");
    s ? await req(s.put(value, key)) : mem.kv.set(key, value);
  },
};

// Queue records are keyed "<session>:<seq padded>", so a key range returns them oldest first.
const qkey = (session: string, seq: number) => `${session}:${String(seq).padStart(9, "0")}`;
const range = (session: string, upto = 999999999) => IDBKeyRange.bound(qkey(session, 0), qkey(session, upto));

export const queue = {
  async push(session: string, seq: number, rec: unknown) {
    const s = await tx("q", "readwrite");
    s ? await req(s.put(rec, qkey(session, seq))) : mem.q.set(qkey(session, seq), rec);
  },
  async oldest<T>(session: string, n: number): Promise<T[]> {
    const s = await tx("q", "readonly");
    if (!s) return [...mem.q.entries()].filter(([k]) => k.startsWith(session + ":")).sort().slice(0, n).map(([, v]) => v as T);
    return (await req(s.getAll(range(session), n))) as T[];
  },
  async count(session: string): Promise<number> {
    const s = await tx("q", "readonly");
    if (!s) return [...mem.q.keys()].filter((k) => k.startsWith(session + ":")).length;
    return req(s.count(range(session)));
  },
  async dropUpTo(session: string, seq: number) {
    const s = await tx("q", "readwrite");
    if (!s) { for (const k of [...mem.q.keys()]) if (k.startsWith(session + ":") && k <= qkey(session, seq)) mem.q.delete(k); return; }
    await req(s.delete(range(session, seq)));
  },
};

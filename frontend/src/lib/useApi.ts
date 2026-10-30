import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

/** GET a path; reload() to refresh; `slow` turns true after 10 s (2G). Pass null to skip. */
export function useApi<T>(path: string | null, opts: { poll?: number } = {}) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(!!path);
  const [slow, setSlow] = useState(false);
  const seq = useRef(0);
  const load = useCallback(async (quiet = false) => {
    if (!path) return;
    const my = ++seq.current;
    if (!quiet) { setLoading(true); setSlow(false); }
    const timer = setTimeout(() => my === seq.current && setSlow(true), 10000);
    try {
      const d = await api<T>(path);
      if (my === seq.current) { setData(d); setError(null); }
    } catch (e) {
      if (my === seq.current && !quiet) setError(e);
    } finally {
      clearTimeout(timer);
      if (my === seq.current) setLoading(false);
    }
  }, [path]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!opts.poll || !path) return;
    const id = setInterval(() => load(true), opts.poll);
    return () => clearInterval(id);
  }, [opts.poll, path, load]);
  return { data, error, loading, slow, reload: load, setData };
}

export function useOnline() {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true), off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => { window.removeEventListener("online", on); window.removeEventListener("offline", off); };
  }, []);
  return online;
}

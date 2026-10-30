import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CalculatorButton } from "@/components/Calculator";
import { CameraBubble, type Snap } from "@/components/CameraBubble";
import { DEFAULT_LIMITS, FaceRule, PhoneRule, tabSwitchEnds } from "@/lib/proctorRules";
import { CodingView } from "./Coding";
import { CandidateShell, ErrorBox, Loading } from "@/components/Shell";
import { Icon } from "@/components/Icon";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/form";
import { Dialog, Progress } from "@/components/ui/misc";
import { useToast } from "@/components/ui/toast";
import { api, ApiError, NetworkError } from "@/lib/api";
import { closeCamera } from "@/lib/camera";
import { listen, openMic } from "@/lib/mic";
import { canFullscreen, enterKiosk, exitKiosk, isFullscreen, keepScreenOn, onFullscreenChange, signals } from "@/lib/kiosk";
import { inSeb } from "@/lib/seb";
import { cn } from "@/lib/cn";
import { drain, ExamEngine, local, type Sync } from "@/lib/examEngine";
import { mmss } from "@/lib/format";
import { kv } from "@/lib/idb";
import { useT, type Key } from "@/lib/i18n";
import { navigate } from "@/lib/router";
import { store } from "@/lib/storage";
import type { Item, StartRes } from "@/lib/types";
import { useAuth } from "@/lib/auth";

const IDLE_S = 20;   // a pause counts as "no input" after 20 s (same as the scoring data)

type Load = { state: "loading" } | { state: "error"; error: unknown } | { state: "ready"; start: StartRes; engine: ExamEngine; offset: number };

export default function Exam() {
  const { user } = useAuth();
  const [load, setLoad] = useState<Load>({ state: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let engine: ExamEngine | null = null, alive = true;
    (async () => {
      const cacheKey = `start:${user?.id}`;
      let start: StartRes;
      try {
        const meta = JSON.parse(store.get("fp-precheck") || "null") || undefined;
        start = await api<StartRes>("/api/exam/start", { body: { ...(meta || {}), signals: signals() } });
        await kv.set(cacheKey, { ...start, cached_at: Date.now() });
      } catch (e) {
        const cached = e instanceof NetworkError ? await kv.get<StartRes & { cached_at: number }>(cacheKey) : undefined;
        if (!cached) {
          if (e instanceof ApiError && e.code === "already_submitted") return navigate("/exam/done", { replace: true });
          if (e instanceof ApiError && e.code === "no_consent") return navigate("/exam/consent", { replace: true });
          return alive && setLoad({ state: "error", error: e });
        }
        const gone = (Date.now() - cached.cached_at) / 1000;    // offline reload: continue from the copy on the phone
        start = { ...cached, elapsed_s: cached.elapsed_s + gone, server_now: new Date(Date.parse(cached.server_now) + gone * 1000).toISOString() };
      }
      engine = new ExamEngine(start);
      await engine.init();
      if (alive) setLoad({ state: "ready", start, engine, offset: Date.parse(start.server_now) - Date.now() });
    })();
    return () => { alive = false; engine?.stop(); };
  }, [attempt, user?.id]);

  if (load.state === "loading") return <CandidateShell><Loading /></CandidateShell>;
  if (load.state === "error") {
    return (
      <CandidateShell>
        <div className="space-y-4">
          <ErrorBox error={load.error} retry={() => { setLoad({ state: "loading" }); setAttempt(attempt + 1); }} />
          <BackHome />
        </div>
      </CandidateShell>
    );
  }
  return <Runner start={load.start} engine={load.engine} offset={load.offset} />;
}

function BackHome() {
  const { t } = useT();
  return <Button variant="outline" className="w-full" onClick={() => navigate("/exam")}><Icon name="left" size={18} />{t("backHome")}</Button>;
}

function Runner({ start, engine, offset }: { start: StartRes; engine: ExamEngine; offset: number }) {
  const { t } = useT();
  const toast = useToast();
  const items = start.items;
  const total = items.length;
  const S = start.session_id;
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>(start.answers || {});
  const [marked, setMarked] = useState<number[]>([]);
  const [sync, setSync] = useState<Sync>(engine.sync);
  const [pending, setPending] = useState(engine.pending);
  const [left, setLeft] = useState(() => Date.parse(start.deadline) - (Date.now() + offset));
  const [grid, setGrid] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [submitting, setSubmitting] = useState<null | "online" | "offline">(null);
  const [ready, setReady] = useState(false);
  // the camera is required: while it is off the questions are covered (answers stay saved, the timer keeps running)
  const [camOn, setCamOn] = useState<boolean | null>(null);
  const [camAttempt, setCamAttempt] = useState(0);
  // live notices for the candidate: they say what was recorded, never accuse, and add nothing to the score
  const [leftNotice, setLeftNotice] = useState<number | null>(null);
  const [banner, setBanner] = useState<null | "face" | "people">(null);
  // proctoring rules (lib/proctorRules.ts; the server enforces the same limits): counts continue after a refresh
  const limits = start.rules?.limits || DEFAULT_LIMITS;
  const leftCount = useRef(start.rules?.tab_switch || 0);
  const faceRule = useRef(new FaceRule(start.rules?.multi_face || 0, limits.multi_face));
  const phoneRule = useRef(new PhoneRule(start.rules?.phone || 0, limits.phone_warnings));
  const [peopleCount, setPeopleCount] = useState(start.rules?.multi_face || 0);
  const [phoneWarn, setPhoneWarn] = useState(false);
  const [ended, setEnded] = useState<null | { reason: string; sent: boolean }>(null);
  const [reopened, setReopened] = useState(false);
  useEffect(() => {                                    // ended by a rule: a reviewer may reopen it while the window is open
    if (!ended?.sent || reopened) return;
    const id = setInterval(async () => {
      try {
        const me = await api<{ session: { status: string } | null }>("/api/exam/me");
        if (me.session?.status === "in_progress") setReopened(true);
      } catch { /* offline: try again */ }
    }, 10000);
    return () => clearInterval(id);
  }, [ended?.sent, reopened]);
  const endedRef = useRef(false);
  // snapshots only at flagged moments (before / at / 5 s after), at most once a minute per reason; the candidate is told
  const snapRef = useRef<(() => Snap) | null>(null);
  const snapLast = useRef<Record<string, number>>({});
  const snapQueue = useRef<{ t: number; reason: string; phase: string; image: string }[]>([]);
  const snapSent = useRef(0);
  const sendSnaps = useRef(async () => {});
  sendSnaps.current = async () => {
    while (snapQueue.current.length) {
      try {
        await api("/api/exam/snapshot", { body: snapQueue.current[0] });
      } catch (e) {
        if (e instanceof NetworkError) return;              // offline: try again later
      }
      snapQueue.current.shift();
    }
  };
  useEffect(() => { const id = setInterval(() => sendSnaps.current(), 15000); return () => clearInterval(id); }, []);
  const flag = useRef((_reason: string, _rule?: boolean) => {});
  flag.current = (reason: string, rule = false) => {
    const now = Date.now();
    // a proctoring-rule event (phone seen, a multi-face episode) always gets its photos; other moments once a minute
    if (snapSent.current >= 24 || (!rule && now - (snapLast.current[reason] || 0) < 60000) || !snapRef.current) return;
    const s = snapRef.current();
    if (!s.at) return;
    snapLast.current[reason] = now;
    const t0 = engine.now();
    if (s.before) snapQueue.current.push({ t: Math.max(0, t0 - 5), reason, phase: "before", image: s.before });
    snapQueue.current.push({ t: t0, reason, phase: "at", image: s.at });
    snapSent.current += 3;
    setTimeout(() => {
      const a = snapRef.current?.();
      if (a?.at) snapQueue.current.push({ t: engine.now(), reason, phase: "after", image: a.at });
      sendSnaps.current();
    }, 5000);
    sendSnaps.current();
    toast(t("snapTaken"), "info");
  };
  const onBack = useRef(() => {});
  onBack.current = () => {
    leftCount.current += 1;
    if (tabSwitchEnds(leftCount.current, limits)) { endTest.current("tab_switch"); return; }
    setLeftNotice(leftCount.current);
    setTimeout(() => flag.current("tab_return"), 1200);     // the camera needs a moment after coming back
  };
  // the test is ended by a rule: photos and answers go first, then the server checks its own counts and ends it
  const endTest = useRef(async (_reason: string) => {});
  endTest.current = async (reason: string) => {
    if (endedRef.current) return;
    endedRef.current = true;
    setEnded({ reason, sent: false }); setPhoneWarn(false); setLeftNotice(null);
    for (let tries = 0; ; tries++) {
      await drain(engine);
      await sendSnaps.current();
      try {
        await api("/api/exam/terminate", { method: "POST" });
        break;
      } catch (e) {
        if (e instanceof ApiError && e.code !== "no_limit_passed") break;          // already submitted, closed…
        if (e instanceof ApiError && tries >= 5) { await api("/api/exam/submit", { method: "POST" }).catch(() => {}); break; }
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
    engine.stop();
    closeCamera();
    exitKiosk();
    setEnded({ reason, sent: true });
  };
  const onCheck = (faces: number | null) => {
    if (endedRef.current) return;
    const r = faceRule.current.check(faces);
    setBanner(r.people ? "people" : r.noFace ? "face" : null);
    if (r.episode) {
      setPeopleCount(faceRule.current.episodes);
      engine.event("multi_face", cur.current);
      flag.current("two_people", true);
      if (r.end) endTest.current("multiple_faces");
    } else if (r.noFace && faces === 0 && !noFaceShown.current) {
      noFaceShown.current = true;
      flag.current("no_face");
    }
    if (!r.noFace) noFaceShown.current = false;
  };
  const noFaceShown = useRef(false);
  const onPhone = (seen: boolean | null) => {
    if (endedRef.current) return;
    const r = phoneRule.current.check(seen, engine.now());
    if (!r.seen) return;
    engine.event("phone_seen", cur.current);
    flag.current("phone", true);
    if (r.end) endTest.current("phone");
    else setPhoneWarn(true);
  };
  const onPaste = useRef(() => {});
  onPaste.current = () => toast(t("noticePaste"), "info");
  const onFrame = (f: { faces: number; face_visible: boolean; gaze: string; brightness?: number; blur?: number; phone?: number }) => {
    engine.frame(f);                                   // banners and rules come from the 1-second checks (onCheck)
  };
  const item = items[idx];

  // restore what is on the phone (answers not yet sent, marks, position)
  useEffect(() => {
    (async () => {
      const [a, m, i] = await Promise.all([local.get<Record<string, string>>(S, "ans"), local.get<number[]>(S, "mark"), local.get<number>(S, "idx")]);
      if (a) setAnswers((s) => ({ ...s, ...a }));
      if (m) setMarked(m);
      if (typeof i === "number" && i >= 0 && i < total) setIdx(i);
      setReady(true);
    })();
  }, [S, total]);

  useEffect(() => {
    engine.onChange = () => {
      setSync(engine.sync); setPending(engine.pending);
      if (engine.terminated) endTest.current(engine.terminated);   // the server ended it (its own counts)
      if (engine.sync === "offline") wentOffline.current(); else if (engine.sync === "saved") cameOnline.current();
    };
    return () => { engine.onChange = () => {}; };
  }, [engine]);

  // disconnects: each offline episode is recorded (start and end) and queued on the phone until it is back online
  const offSince = useRef<number | null>(null);
  const wentOffline = useRef(() => {});
  const cameOnline = useRef(() => {});
  wentOffline.current = () => { if (offSince.current === null && !endedRef.current) { offSince.current = engine.now(); engine.event("offline_start", cur.current); } };
  cameOnline.current = () => { if (offSince.current !== null) { offSince.current = null; engine.event("offline_end", cur.current); } };
  useEffect(() => {
    const off = () => wentOffline.current(), on = () => cameOnline.current();
    window.addEventListener("offline", off);
    window.addEventListener("online", on);
    return () => { window.removeEventListener("offline", off); window.removeEventListener("online", on); };
  }, []);

  // item_shown whenever the question on screen changes
  const shown = useRef(-1);
  useEffect(() => {
    if (!ready || shown.current === idx) return;
    shown.current = idx;
    engine.event("item_shown", item.item);
    local.set(S, "idx", idx);
  }, [idx, ready]); // eslint-disable-line react-hooks/exhaustive-deps

  // focus, paste and idle (no mouse, touch or keyboard input) tracking
  const cur = useRef(item.item);

  // microphone (when allowed): every 5 s this phone decides "speech-like or not"; only a "yes" and its seconds are
  // sent. It is never evidence on its own (backend/services/audio.py), so a missing or slow mic changes nothing.
  const [micOn, setMicOn] = useState(false);
  const isEnded = !!ended;
  useEffect(() => {
    if (isEnded || start.mic === "off" || (start.mic !== "required" && store.get("fp-mic") !== "on")) return;
    let alive = true, stop = () => {};
    openMic().then(() => {
      if (!alive) return;
      stop = listen({
        onWindow: (w) => {
          if (w.speech) engine.event("speech_like", cur.current, "", 0, engine.now(), { s: Math.round(w.voiced_s * 10) / 10, a: Math.round(w.active_s * 10) / 10 });
        },
        onStop: (why) => { if (alive) { setMicOn(false); engine.event("mic_off", cur.current, why); } },
      });
      setMicOn(true);
      engine.event("mic_on", cur.current);
    }).catch(() => { if (alive) engine.event("mic_off", cur.current, "blocked"); });
    return () => { alive = false; stop(); setMicOn(false); };
  }, [isEnded]); // eslint-disable-line react-hooks/exhaustive-deps

  // kiosk mode (not inside SEB): screen kept on, full screen; leaving it is noted, never a rule
  const [fsOff, setFsOff] = useState(false);
  useEffect(() => {
    if (start.kiosk === false || inSeb() || isEnded) return;
    const stopWake = keepScreenOn();
    if (!canFullscreen()) return stopWake;               // iPhone: no full screen for web pages
    let was = isFullscreen();
    setFsOff(!was);                                      // e.g. after a refresh: offer to go back
    const stop = onFullscreenChange((on) => {
      setFsOff(!on);
      if (on !== was) engine.event(on ? "fullscreen_enter" : "fullscreen_exit", cur.current);
      was = on;
    });
    return () => { stop(); stopWake(); };
  }, [isEnded]); // eslint-disable-line react-hooks/exhaustive-deps
  cur.current = item.item;
  useEffect(() => {
    let focused = !document.hidden && document.hasFocus();
    let lastInput = engine.now(), idle = false;
    const focus = () => {
      const now = !document.hidden && document.hasFocus();
      if (now === focused) return;
      focused = now;
      if (!now && idle) { idle = false; engine.event("idle_end", cur.current); }
      engine.event(now ? "focus_gained" : "focus_lost", cur.current);
      if (now) onBack.current();
      lastInput = engine.now();
    };
    const activity = () => {
      lastInput = engine.now();
      if (idle) { idle = false; engine.event("idle_end", cur.current); }
    };
    let lastMove = 0;
    const move = () => { const n = performance.now(); if (n - lastMove > 500) { lastMove = n; activity(); } };
    const paste = (e: ClipboardEvent) => {
      engine.event("paste", cur.current, "", e.clipboardData?.getData("text")?.length || 0);
      onPaste.current();
    };
    const tick = setInterval(() => {
      if (!idle && focused && engine.now() - lastInput >= IDLE_S) { idle = true; engine.event("idle_start", cur.current, "", 0, lastInput); }
    }, 1000);
    const evs = ["pointerdown", "keydown", "touchstart", "wheel", "input"] as const;
    evs.forEach((n) => window.addEventListener(n, activity, { passive: true }));
    window.addEventListener("pointermove", move, { passive: true });
    window.addEventListener("scroll", move, { passive: true });
    document.addEventListener("visibilitychange", focus);
    window.addEventListener("blur", focus);
    window.addEventListener("focus", focus);
    document.addEventListener("paste", paste);
    return () => {
      clearInterval(tick);
      evs.forEach((n) => window.removeEventListener(n, activity));
      window.removeEventListener("pointermove", move);
      window.removeEventListener("scroll", move);
      document.removeEventListener("visibilitychange", focus);
      window.removeEventListener("blur", focus);
      window.removeEventListener("focus", focus);
      document.removeEventListener("paste", paste);
    };
  }, [engine]);

  const submit = useCallback(async () => {
    if (endedRef.current) return;                          // ended by a rule: already submitted
    setConfirm(false); setGrid(false);
    setSubmitting("online");
    for (;;) {
      const sent = await drain(engine);
      await sendSnaps.current();                              // photos are accepted only while the test is open
      if (engine.sync === "closed") break;
      if (sent) {
        try { await api("/api/exam/submit", { method: "POST" }); break; }
        catch (e) { if (!(e instanceof NetworkError)) break; }
      }
      setSubmitting("offline");                       // keep trying until the phone is back online
      await new Promise((r) => setTimeout(r, 5000));
    }
    engine.stop();
    closeCamera();
    exitKiosk();
    navigate("/exam/done", { replace: true });
  }, [engine]);

  // timer: from the server's deadline, corrected for this phone's clock
  const warned = useRef(false), timeUp = useRef(false);
  useEffect(() => {
    const id = setInterval(() => {
      const l = Date.parse(start.deadline) - (Date.now() + offset);
      setLeft(l);
      if (l <= 5 * 60_000 && l > 0 && !warned.current) { warned.current = true; toast(t("timeLeft5"), "info"); }
      if (l <= 0 && !timeUp.current) { timeUp.current = true; toast(t("timeUp"), "info"); submit(); }
    }, 1000);
    return () => clearInterval(id);
  }, [start.deadline, offset, submit]); // eslint-disable-line react-hooks/exhaustive-deps

  const answer = (option: string) => {
    const k = String(item.item);
    if (answers[k] === option) return;
    const next = { ...answers, [k]: option };
    setAnswers(next);
    local.set(S, "ans", next);
    engine.event("answer", item.item, option);
  };
  const toggleMark = () => {
    const next = marked.includes(item.item) ? marked.filter((m) => m !== item.item) : [...marked, item.item];
    setMarked(next);
    local.set(S, "mark", next);
  };
  const go = (i: number) => { if (i >= 0 && i < total) { setIdx(i); setGrid(false); } };

  const coding = start.test_kind === "coding";
  const [acceptedSet, setAcceptedSet] = useState<number[]>(() =>
    Object.entries(start.code_state || {}).filter(([, v]) => v.best?.verdict === "accepted").map(([k]) => Number(k)));
  const answeredN = useMemo(() => coding ? acceptedSet.length : items.filter((it) => (answers[String(it.item)] ?? "") !== "").length,
    [answers, items, coding, acceptedSet]);

  if (sync === "closed") {
    return (
      <CandidateShell>
        <Card><CardContent className="space-y-4 pt-5 text-center">
          <Icon name="lock" size={32} className="mx-auto text-slate-500" />
          <p className="text-lg font-semibold">{t("sittingClosed")}</p>
          <Button className="w-full" onClick={() => { closeCamera(); navigate("/exam"); }}>{t("backHome")}</Button>
        </CardContent></Card>
      </CandidateShell>
    );
  }

  const low = left <= 5 * 60_000;
  const bar = (
    <div className="flex items-center gap-2">
      <span className={cn("tabular inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 font-mono text-sm font-semibold", low ? "border-rose-300 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300" : "border-slate-300 bg-slate-50 text-slate-800 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100")}
        role="timer" aria-label={t("timeLeft")}>
        <Icon name="clock" size={15} />{mmss(left / 1000)}
      </span>
      <span className="text-sm font-medium text-slate-600 dark:text-slate-300">{coding ? `${t("codingTest")} · P${idx + 1}/${total}` : t("qOf", { n: idx + 1, total })}</span>
    </div>
  );

  return (
    <CandidateShell bar={bar} tools={<CalculatorButton />} wide={!coding} full={coding}>
      {coding ? (
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Progress value={(answeredN / total) * 100} label={t("answered")} className="flex-1" />
            <SyncChip sync={sync} pending={pending} />
          </div>
          <CodingView items={items} idx={idx} go={go} engine={engine} session={S} codeState={start.code_state || {}}
            onAccepted={(it) => setAcceptedSet((a) => (a.includes(it) ? a : [...a, it]))} onFinish={() => setConfirm(true)} />
        </div>
      ) : (
      <div className="mx-auto max-w-2xl space-y-4 pb-28">
        <div className="flex items-center gap-3">
          <Progress value={(answeredN / total) * 100} label={t("answered")} className="flex-1" />
          <SyncChip sync={sync} pending={pending} />
        </div>

        <Card key={item.item} className="animate-fade-in">
          <CardContent className="space-y-5 pt-5">
            <div className="flex items-start justify-between gap-3">
              <p className="text-sm font-semibold text-pink-700 dark:text-pink-400">{t("questionN", { n: idx + 1 })}</p>
              <Button variant="ghost" size="sm" onClick={toggleMark} aria-pressed={marked.includes(item.item)}
                className={cn(marked.includes(item.item) && "text-amber-700 dark:text-amber-300")}>
                <Icon name="bookmark" size={16} fill={marked.includes(item.item) ? "currentColor" : "none"} />
                {marked.includes(item.item) ? t("marked") : t("mark")}
              </Button>
            </div>
            <h1 className="text-xl font-semibold leading-snug sm:text-2xl">{item.text}</h1>
            {item.kind === "short"
              ? <ShortAnswer key={item.item} value={answers[String(item.item)] || ""} onSave={answer} />
              : <Options item={item} value={answers[String(item.item)]} onPick={answer} />}
          </CardContent>
        </Card>
        <p className="text-center text-xs text-slate-500">{t("changeAnswer")}</p>
      </div>
      )}

      <CameraBubble enabled={!ended} mic={micOn} attempt={camAttempt} onCamera={setCamOn} onFrame={onFrame} onCheck={onCheck} onPhone={onPhone} snapRef={snapRef} />

      {camOn === false && !submitting && !ended && (
        <div role="alertdialog" aria-modal="true" aria-labelledby="camlock" className="fixed inset-0 z-50 grid place-items-center bg-slate-950/85 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 text-center shadow-xl dark:bg-slate-900">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"><Icon name="cameraOff" size={26} /></div>
            <h2 id="camlock" className="text-lg font-semibold">{t("camLockTitle")}</h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("camLockBody")}</p>
            <p className="text-sm text-slate-500">{t("cameraFix")}</p>
            <Button size="lg" className="w-full" onClick={() => { closeCamera(); setCamOn(null); setCamAttempt((n) => n + 1); }}>
              <Icon name="camera" size={18} />{t("tryAgain")}
            </Button>
          </div>
        </div>
      )}

      {fsOff && !banner && !submitting && !ended && (
        <div role="status" id="kiosk-off" className="animate-fade-in fixed inset-x-3 top-16 z-40 mx-auto flex max-w-2xl items-center gap-3 rounded-2xl bg-slate-900 px-4 py-3 text-sm text-white shadow-lg dark:bg-slate-800">
          <Icon name="window" size={18} className="shrink-0" />
          <span className="min-w-0 flex-1"><b>{t("kioskOff")}</b> <span className="opacity-80">{t("kioskOffNote")}</span></span>
          <Button size="sm" className="shrink-0" onClick={() => enterKiosk()}>{t("kioskBack")}</Button>
        </div>
      )}

      {banner && !submitting && (
        <div role="status" className={cn("animate-fade-in fixed inset-x-3 top-16 z-40 mx-auto flex max-w-2xl items-start gap-2 rounded-2xl px-4 py-3 text-sm font-semibold shadow-lg",
          banner === "people" ? "bg-rose-600 text-white" : "bg-amber-400 text-amber-950")}>
          <Icon name={banner === "people" ? "users" : "cameraOff"} size={18} className="mt-0.5 shrink-0" />
          <span>{t(banner === "people" ? "noticePeople" : "noticeFace")}
            {banner === "people" && <span className="mt-1 block font-normal opacity-90">{t("noticePeopleCount", { n: peopleCount, max: limits.multi_face })}</span>}</span>
        </div>
      )}

      <Dialog open={phoneWarn && !ended} onClose={() => setPhoneWarn(false)} title={t("phoneWarnTitle")}>
        <div className="space-y-3">
          <div className="flex gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300"><Icon name="phone" size={20} /></span>
            <p className="text-slate-700 dark:text-slate-200">{t("phoneWarnBody")}</p>
          </div>
          <Button className="w-full" onClick={() => setPhoneWarn(false)}>{t("phoneWarnOk")}</Button>
        </div>
      </Dialog>

      {ended && (
        <div role="alertdialog" aria-modal="true" aria-labelledby="ended" className="fixed inset-0 z-[60] grid place-items-center bg-slate-950/85 p-4 backdrop-blur-sm">
          <div className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-6 text-center shadow-xl dark:bg-slate-900">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300"><Icon name="lock" size={26} /></div>
            <h2 id="ended" className="text-lg font-semibold">{t("endedTitle")}</h2>
            <p className="font-medium text-slate-800 dark:text-slate-100">{t(("ended_" + ended.reason) as Key)}</p>
            <p className="text-sm text-slate-600 dark:text-slate-300">{t("endedBody")}</p>
            {reopened ? (
              <div className="space-y-3 rounded-xl bg-emerald-50 p-3 text-left dark:bg-emerald-950/40">
                <p className="font-semibold text-emerald-800 dark:text-emerald-200">{t("reopenedTitle")}</p>
                <p className="text-sm text-emerald-900 dark:text-emerald-200">{t("reopenedBody")}</p>
                <Button size="lg" className="w-full" onClick={() => window.location.assign("/exam/run")}>{t("reopenedContinue")} <Icon name="arrowRight" size={18} /></Button>
              </div>
            ) : ended.sent ? (
              <>
                <p className="text-xs text-slate-500">{t("endedMayReopen")}</p>
                <Button size="lg" variant="outline" className="w-full" onClick={() => navigate("/exam/result", { replace: true })}>{t("seeResult")} <Icon name="arrowRight" size={18} /></Button>
              </>
            ) : <p className="text-sm text-slate-500">{t("endedSending")}</p>}
          </div>
        </div>
      )}

      <Dialog open={leftNotice !== null && !submitting} onClose={() => setLeftNotice(null)} title={t("noticeLeftTitle")}>
        <div className="space-y-3">
          <div className="flex gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"><Icon name="window" size={20} /></span>
            <p className="text-slate-700 dark:text-slate-200">{t("noticeLeftBody")}</p>
          </div>
          <p className="text-sm text-slate-500">{t("noticeLeftCount", { n: leftNotice ?? 0, max: limits.tab_switch })}</p>
          <Button className="w-full" onClick={() => setLeftNotice(null)}>{t("noticeContinue")}</Button>
        </div>
      </Dialog>

      {!coding && <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95">
        <div className="mx-auto flex max-w-2xl items-center gap-2 px-4 py-3">
          <Button variant="outline" size="lg" className="px-4" onClick={() => go(idx - 1)} disabled={idx === 0} aria-label={t("prev")}>
            <Icon name="left" size={20} /><span className="hidden sm:inline">{t("prev")}</span>
          </Button>
          <Button variant="secondary" size="lg" className="px-4" onClick={() => setGrid(true)} aria-label={t("allQuestions")}>
            <Icon name="grid" size={20} /><span className="tabular text-sm">{answeredN}/{total}</span>
          </Button>
          {idx < total - 1
            ? <Button size="lg" className="flex-1" onClick={() => go(idx + 1)}>{t("next")}<Icon name="right" size={20} /></Button>
            : <Button size="lg" className="flex-1" onClick={() => setConfirm(true)}>{t("reviewSubmit")}<Icon name="send" size={18} /></Button>}
        </div>
      </nav>}

      <Dialog open={grid} onClose={() => setGrid(false)} title={t("allQuestions")} side="bottom">
        <div className="mb-3 flex flex-wrap gap-3 text-xs text-slate-600 dark:text-slate-300">
          <Legend className="bg-emerald-500" label={t("answered")} />
          <Legend className="bg-white ring-1 ring-slate-300 dark:bg-slate-800 dark:ring-slate-600" label={t("notAnswered")} />
          <Legend className="bg-amber-400" label={t("markedCount")} />
          <Legend className="ring-2 ring-pink-500" label={t("current")} />
        </div>
        <div className="grid max-h-[50dvh] grid-cols-6 gap-2 overflow-y-auto p-1 sm:grid-cols-8">
          {items.map((it, i) => {
            const done = (answers[String(it.item)] ?? "") !== "", mk = marked.includes(it.item);
            return (
              <button key={it.item} onClick={() => go(i)} aria-label={`${t("questionN", { n: i + 1 })}${done ? ", " + t("answered") : ""}${mk ? ", " + t("marked") : ""}`}
                className={cn("tabular relative h-11 rounded-xl text-sm font-semibold",
                  done ? "bg-emerald-500 text-white" : "bg-white ring-1 ring-slate-300 dark:bg-slate-800 dark:ring-slate-600",
                  i === idx && "ring-2 ring-pink-500 ring-offset-2 dark:ring-offset-slate-900")}>
                {i + 1}
                {mk && <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full bg-amber-400 ring-2 ring-white dark:ring-slate-900" />}
              </button>
            );
          })}
        </div>
        <Button size="lg" className="mt-4 w-full" onClick={() => { setGrid(false); setConfirm(true); }}>{t("reviewSubmit")}</Button>
      </Dialog>

      <Dialog open={confirm} onClose={() => setConfirm(false)} title={coding ? t("finishTest") : t("submitTitle")}>
        <p className="text-slate-600 dark:text-slate-300">
          {coding ? (total - answeredN ? t("finishBody", { n: total - answeredN }) : t("finishAll"))
            : total - answeredN ? t("submitEmpty", { n: total - answeredN }) : t("submitAll")}
          {marked.length > 0 && <> · {t("markedCount")}: {marked.length}</>}
        </p>
        <div className="mt-5 flex gap-2">
          <Button variant="outline" className="flex-1" onClick={() => setConfirm(false)}>{t("submitNo")}</Button>
          <Button className="flex-1" onClick={submit}>{t("submit")}</Button>
        </div>
      </Dialog>

      {submitting && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-white/90 p-6 text-center backdrop-blur dark:bg-slate-950/90" role="alertdialog" aria-live="assertive">
          <div className="space-y-4">
            <div className="brand-bg mx-auto h-12 w-12 animate-spin rounded-full [mask:radial-gradient(farthest-side,transparent_60%,#000_61%)]" />
            <p className="text-lg font-semibold">{submitting === "offline" ? t("submittingOffline") : t("submitting")}</p>
          </div>
        </div>
      )}
    </CandidateShell>
  );
}

function Legend({ className, label }: { className: string; label: string }) {
  return <span className="inline-flex items-center gap-1.5"><span className={cn("h-3.5 w-3.5 rounded", className)} />{label}</span>;
}

function SyncChip({ sync, pending }: { sync: Sync; pending: number }) {
  const { t } = useT();
  const s = sync === "offline"
    ? { icon: "wifiOff" as const, text: t("offline"), c: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200" }
    : sync === "sending"
      ? { icon: "refresh" as const, text: t("sending"), c: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200" }
      : { icon: "check" as const, text: t("saved"), c: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300" };
  return (
    <span role="status" className={cn("inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold", s.c)}
      title={pending ? t("pendingSend", { n: pending }) : undefined}>
      <Icon name={s.icon} size={13} />{s.text}
    </span>
  );
}

function Options({ item, value, onPick }: { item: Item; value?: string; onPick: (o: string) => void }) {
  const { t } = useT();
  return (
    <div role="radiogroup" aria-label={t("chooseOne")} className="space-y-2.5">
      {Object.entries(item.options).map(([k, text]) => {
        const on = value === k;
        return (
          <button key={k} role="radio" aria-checked={on} onClick={() => onPick(k)}
            className={cn("flex w-full items-center gap-3 rounded-lg border p-3.5 text-left text-base transition-colors",
              on ? "border-pink-600 bg-pink-50 ring-1 ring-pink-600 dark:border-pink-400 dark:bg-pink-950/40 dark:ring-pink-400" : "border-slate-200 bg-white hover:border-slate-300 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-slate-700")}>
            <span className={cn("grid h-8 w-8 shrink-0 place-items-center rounded-md border text-sm font-semibold",
              on ? "border-transparent bg-brand text-white dark:text-slate-950" : "border-slate-300 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300")}>{k}</span>
            <span className="flex-1 font-medium">{text}</span>
            {on && <Icon name="checkCircle" size={22} className="text-pink-600 dark:text-pink-400" />}
          </button>
        );
      })}
    </div>
  );
}

function ShortAnswer({ value, onSave }: { value: string; onSave: (v: string) => void }) {
  const { t } = useT();
  const [v, setV] = useState(value);
  const dirty = v.trim() !== value;
  const save = () => { if (v.trim() && dirty) onSave(v.trim()); };
  return (
    <form onSubmit={(e) => { e.preventDefault(); save(); }} className="space-y-3">
      <label htmlFor="short" className="sr-only">{t("typeAnswer")}</label>
      <Input id="short" value={v} maxLength={40} placeholder={t("typeAnswer")} autoComplete="off" onChange={(e) => setV(e.target.value)} onBlur={save} className="h-14 text-lg" />
      <div className="flex items-center gap-3">
        <Button type="submit" variant="secondary" disabled={!v.trim() || !dirty}>{t("saveAnswer")}</Button>
        {!dirty && value && <span className="inline-flex items-center gap-1 text-sm text-emerald-700 dark:text-emerald-300"><Icon name="check" size={16} />{t("answerSaved")}</span>}
      </div>
    </form>
  );
}

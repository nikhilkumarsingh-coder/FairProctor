"""Microphone "speech-like sound" check: support only, never evidence on its own.

The candidate's phone (frontend/src/lib/speech.ts) decides every 5 s whether the sound was speech-like and sends only
a "yes" with the voiced seconds. The detector catches about 87% of talking but also marks about a quarter of ordinary
home sounds (rooster, dog, laughing) and any TV as talking (reports/ESC50_NOISE_CHECK.md, MUSAN_SPEECH_CHECK.md,
BROWSER_SPEECH_CHECK.md). In a shared home that is exactly the noise this project must not punish, so:

* it never changes the score, the band or the queue order;
* when the score already shows silent pauses followed by correct answers on hard questions, speech-like sound during
  those pauses is added to that reason as a supporting line, for the reviewer to weigh;
* otherwise the candidate and the reviewer see it under "not counted".
"""
from __future__ import annotations

import json

from .. import db

IDLE_MIN_S = 20          # a pause with no input (same bar as the scoring features)
ANSWER_AFTER_S = 60      # the answer that ends the pause comes within this many seconds
WINDOW_S = 5             # one verdict covers the 5 s before its time


def for_sitting(con, sitting_id: int) -> dict[str, dict]:
    """session_id -> {windows: [(t, voiced_s)], mic_on: bool, stopped: [reason]} for submitted sessions."""
    rows = db.all_(con, """SELECT e.session_id, e.t, e.type, e.option, e.meta FROM events e
                           JOIN sessions s ON s.id = e.session_id
                           WHERE s.sitting_id = ? AND s.status = 'submitted' AND e.type IN ('speech_like', 'mic_on', 'mic_off')
                           ORDER BY e.session_id, e.t""", sitting_id)
    out: dict[str, dict] = {}
    for r in rows:
        a = out.setdefault(r["session_id"], dict(windows=[], mic_on=False, stopped=[]))
        if r["type"] == "speech_like":
            m = json.loads(r["meta"]) if r.get("meta") else {}
            a["windows"].append((float(r["t"]), float(m.get("s") or 0)))
        elif r["type"] == "mic_on":
            a["mic_on"] = True
        elif r["option"]:
            a["stopped"].append(r["option"])
    return out


def silent_pauses(ev) -> list[tuple[float, float, int]]:
    """(start, end, question) of pauses with no input of 20 s or more that ended in a correct answer."""
    if ev is None or len(ev) == 0:
        return []
    ev = ev.sort_values("t")
    out, start = [], None
    answers = ev[ev.type == "answer"]
    for r in ev[ev.type.isin(["idle_start", "idle_end"])].itertuples():
        if r.type == "idle_start":
            start = r.t
        elif start is not None:
            if r.t - start >= IDLE_MIN_S:
                a = answers[(answers.t >= r.t) & (answers.t <= r.t + ANSWER_AFTER_S)]
                if len(a) and int(a.correct.iloc[0]) == 1:
                    out.append((float(start), float(r.t), int(a.item.iloc[0])))
            start = None
    return out


def _secs(windows) -> float:
    return sum(s for _, s in windows)


def annotate(e: dict, audio: dict | None, ev) -> dict:
    """Add the microphone facts to an explanation. Never touches score, band, rank or weights."""
    if not audio:
        return e
    wins = audio["windows"]
    pauses = silent_pauses(ev)
    hit = [(a, b, q) for a, b, q in pauses if any(t - WINDOW_S < b and t > a for t, _ in wins)]
    pause_reason = next((r for r in e.get("reasons", []) if r.get("family") == "pause"), None)
    e["audio"] = dict(measured=bool(audio.get("mic_on") or wins), windows=len(wins), voiced_s=round(_secs(wins), 1),
                      supporting=bool(pause_reason and hit), pauses_with_speech=len(hit), stopped=audio.get("stopped", []))
    if pause_reason is not None and hit:
        moments = [dict(t=round(t, 1), label="speech-like sound") for t, _ in wins if any(t - WINDOW_S < b and t > a for a, b, _ in hit)]
        n, m = len(hit), len(pauses)
        pause_reason["evidence"].append(dict(
            key="speech_in_pause", t0=round(min(a for a, _, _ in hit), 1), t1=round(max(b for _, b, _ in hit), 1),
            items=sorted({q for _, _, q in hit}), strength=0, supporting=True, moments=moments[:12],
            text=(f"Speech-like sound was picked up during {n} of these {m} silent pause{'s' if m > 1 else ''} "
                  "(the phone's on-device check; no sound was recorded or sent). Supporting only: it does not change the "
                  "score, and a TV or family talking sounds the same."),
            candidate_text="Talking-like sound was picked up by your phone during some of these pauses. No sound was recorded."))
        known = {(x["t"], x["label"]) for x in e.get("moments", [])}
        from fairproctor.features import mmss
        for mo in moments:
            if (mo["t"], mo["label"]) not in known:
                e.setdefault("moments", []).append(dict(t=mo["t"], at=mmss(mo["t"]), label=mo["label"]))
        e["moments"] = sorted(e.get("moments", []), key=lambda x: x["t"])
    elif wins:
        e.setdefault("context", []).append(
            f"Speech-like sound was picked up {len(wins)} time{'s' if len(wins) > 1 else ''} (about {_secs(wins):.0f} s of voice). "
            "Not counted: a TV, family talking or animals sound the same to the phone.")
    stopped = [w for w in audio.get("stopped", []) if w in ("slow", "ended", "error")]
    if stopped:
        e.setdefault("context", []).append("The microphone check stopped during the test"
                                           + (" (this phone was too slow for it)" if "slow" in stopped else "") + ". Not counted.")
    return e

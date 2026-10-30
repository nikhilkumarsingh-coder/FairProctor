"""Live monitor: the trained model run on a sitting while candidates are still writing, plus the raw signals.

The final, fair score is still made when the sitting closes (services/scoring.py). The live risk is an early
signal on partial answers, recomputed at most once every EVERY_S seconds per sitting. The alerts (left the
test screen, pasted, a second person in view) are plain facts from the event stream, not model output.
"""
from __future__ import annotations

import datetime as dt
import logging
import threading
import time

import pandas as pd

from .. import db
from .scoring import _live_note, choose_stats, model_bundle

log = logging.getLogger("fairproctor.live")
EVERY_S = 45          # model run at most this often per sitting
MIN_ANSWERS = 3       # fewer answers than this: too early to say anything
_cache: dict[int, tuple[float, dict]] = {}
_busy: set[int] = set()
_lock = threading.Lock()


def _pseudonym(sid: str) -> str:
    from fairproctor.display import pseudonym
    return pseudonym(sid)


def _coding_run(sitting_id: int) -> dict:
    """Coding sittings: the coding model on the programs, pastes and typing so far."""
    from .coding_score import bundle, export, score_frame
    from ..routes.review import mask_ids
    with db.tx() as con:
        sit, sess, ev, runs, items, starters, titles = export(con, sitting_id, statuses=("in_progress", "submitted"))
    live = [s for s, syn in zip(sess.session_id, sess.is_synthetic) if not syn and (runs.session_id == s).any()]
    if not live:
        return dict(risks={}, ran_at=db.now(), version=bundle()["version"])
    res = score_frame(sess, ev, runs, items, starters, titles, ids=live)
    return dict(risks={s: dict(risk=r["priority"], band=r["band"], families=r["families"],
                               headline=mask_ids(r["explanation"]["headline"] if r["families"] else ""),
                               not_counted=r["explanation"]["context"]) for s, r in res.items()},
                ran_at=db.now(), version=bundle()["version"])


def _model_run(sitting_id: int) -> dict:
    """Features + trained model on everyone who has answered enough so far (reference sessions give the context)."""
    from fairproctor.explain import explain, phone_band
    from fairproctor.features import build
    with db.tx() as con:
        kind = db.one(con, "SELECT t.kind FROM sittings s JOIN tests t ON t.id = s.test_id WHERE s.id = ?", sitting_id)["kind"]
    if kind == "coding":
        return _coding_run(sitting_id)
    B = model_bundle()
    with db.tx() as con:
        sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id)
        sess = pd.DataFrame(db.all_(con, """SELECT id session_id, sitting_id window_id, device, bandwidth_class,
                                                   precheck_light, precheck_framing, is_synthetic
                                            FROM sessions WHERE sitting_id = ? AND status IN ('in_progress', 'submitted')""",
                                    sitting_id))
        ev = pd.DataFrame(db.all_(con, """SELECT e.session_id, e.t, e.type, e.item, e.option, e.correct, e.chars
                                          FROM events e JOIN sessions s ON s.id = e.session_id
                                          WHERE s.sitting_id = ? AND s.status IN ('in_progress', 'submitted')
                                          ORDER BY e.session_id, e.t, e.seq""", sitting_id),
                          columns=["session_id", "t", "type", "item", "option", "correct", "chars"])
        fr = pd.DataFrame(db.all_(con, """SELECT f.session_id, f.t, f.faces, f.face_visible, f.gaze, f.brightness, f.blur, f.phone
                                          FROM frame_stats f JOIN sessions s ON s.id = f.session_id
                                          WHERE s.sitting_id = ? AND s.status IN ('in_progress', 'submitted')
                                          ORDER BY f.session_id, f.t""", sitting_id),
                          columns=["session_id", "t", "faces", "face_visible", "gaze", "brightness", "blur", "phone"])
        items = pd.DataFrame(db.all_(con, "SELECT position item, kind FROM items WHERE test_id = ? ORDER BY position",
                                     sit["test_id"]))
    if sess.empty or ev.empty:
        return dict(risks={}, ran_at=db.now(), version=B["version"])
    from fairproctor.features import one_answer_per_item
    ev = one_answer_per_item(ev)
    n_ans = ev[ev.type == "answer"].groupby("session_id").item.nunique()
    live = [s for s, syn in zip(sess.session_id, sess.is_synthetic) if not syn and n_ans.get(s, 0) >= MIN_ANSWERS]
    if not live:
        return dict(risks={}, ran_at=db.now(), version=B["version"])
    keep = set(live) | set(sess.session_id[sess.is_synthetic.astype(bool)])
    sess = sess[sess.session_id.isin(keep)]
    ev, fr = ev[ev.session_id.isin(keep)], fr[fr.session_id.isin(keep)]
    st, _ = choose_stats(ev, items, len(sess), B)
    X, evid, st = build(sess, ev, fr, items, stats=st)
    XL = X.loc[live]
    M = B["model"]
    raw = M.raw(XL)
    prob = M.iso.predict(raw)
    contrib = M.contributions(XL)
    ev_by = {k: g for k, g in ev.groupby("session_id")}
    meta_by = sess.set_index("session_id").to_dict("index")
    risks = {}
    for i, sid in enumerate(live):
        band = "review_first" if raw[i] >= B["H"] else ("review" if raw[i] >= B["T"] else "clear")
        band = phone_band(band, X.loc[sid].to_dict())
        e = explain(sid, XL.loc[sid].to_dict(), contrib.loc[sid].to_dict(), evid[sid], dict(meta_by[sid], session_id=sid),
                    round(100 * float(prob[i]), 1), band, events=ev_by.get(sid), stats=st)
        from ..routes.review import mask_ids
        headline = mask_ids(e["headline"] if e["reasons"] else "")   # other candidates only by pseudonym
        risks[sid] = dict(risk=B["priority"](raw[i]), band=band, families=[r["family"] for r in e["reasons"]],
                          headline=headline,
                          not_counted=[_live_note(n) for n in e["context"]])
    return dict(risks=risks, ran_at=db.now(), version=B["version"])


def model_snapshot(sitting_id: int) -> dict:
    """Cached model run, refreshed when older than EVERY_S: the first view waits for it, later refreshes run in the
    background so the monitor answers at once. A failure never breaks the monitor."""
    now = time.time()
    with _lock:
        hit = _cache.get(sitting_id)
        if (hit and now - hit[0] < EVERY_S) or sitting_id in _busy:
            return hit[1] if hit else dict(risks={}, ran_at=None, pending=True)
        _busy.add(sitting_id)
    if hit:
        threading.Thread(target=_refresh, args=(sitting_id,), daemon=True).start()
        return hit[1]
    return _refresh(sitting_id)


def _refresh(sitting_id: int) -> dict:
    try:
        snap = _model_run(sitting_id)
    except Exception as e:                                   # noqa: BLE001 - the signals still show
        log.exception("live model run failed for sitting %s", sitting_id)
        snap = dict(risks={}, ran_at=db.now(), error=str(e)[:200])
    with _lock:
        old = _cache.get(sitting_id)
        snap["trend"] = {s: r["risk"] - old[1]["risks"][s]["risk"] for s, r in snap["risks"].items()
                         if old and s in old[1].get("risks", {})}
        _cache[sitting_id] = (time.time(), snap)
        _busy.discard(sitting_id)
    return snap


def _wall(started_at: str | None, t: float) -> str | None:
    s = db.parse_ts(started_at)
    return (s + dt.timedelta(seconds=float(t))).strftime("%Y-%m-%dT%H:%M:%SZ") if s else None


def _clock(t: float) -> str:
    return f"{int(t) // 60:02d}:{int(t) % 60:02d}"


def snapshot(sitting_id: int, show_names: bool) -> dict:
    from .scoring import model_bundle as _mb
    with db.tx() as con:
        sit = db.one(con, "SELECT id, test_id, title, status, starts_at, ends_at, join_code FROM sittings WHERE id = ?", sitting_id)
        if not sit:
            return {}
        n_items = db.one(con, "SELECT COUNT(*) n FROM items WHERE test_id = ?", sit["test_id"])["n"]
        rows = db.all_(con, """SELECT s.id, s.status, s.started_at, s.submitted_at, s.device, s.bandwidth_class,
                                      s.relogins, s.terminated_reason, s.terminated_at, s.rules_reset, s.rule_history, s.device_info, u.name, u.roll_no, u.email
                               FROM sessions s LEFT JOIN users u ON u.id = s.user_id
                               WHERE s.sitting_id = ? AND s.is_synthetic = 0""", sitting_id)
        ids = [r["id"] for r in rows if r["status"] != "not_started"]
        marks = ",".join("?" * len(ids)) or "''"
        ev = db.all_(con, f"""SELECT session_id, t, type, item, chars FROM events
                              WHERE session_id IN ({marks}) AND type IN ('answer', 'focus_lost', 'focus_gained', 'paste', 'idle_start',
                                                                         'phone_seen', 'multi_face', 'offline_start', 'offline_end',
                                                                         'speech_like', 'mic_on', 'mic_off',
                                                                         'fullscreen_exit', 'fullscreen_enter')
                              ORDER BY session_id, t, seq""", *ids)
        coding = db.one(con, "SELECT kind FROM tests WHERE id = ?", sit["test_id"])["kind"] == "coding"
        subs = db.all_(con, f"""SELECT session_id, item, verdict, passed, total FROM code_runs
                                WHERE session_id IN ({marks}) AND kind = 'submit'""", *ids) if coding else []
        fr = db.all_(con, f"""SELECT session_id, t, faces, face_visible FROM frame_stats
                              WHERE session_id IN ({marks}) ORDER BY session_id, t""", *ids)
    counts = {k: sum(1 for r in rows if r["status"] == k) for k in ("not_started", "in_progress", "submitted")}
    model = model_snapshot(sitting_id) if ids and sit["status"] == "live" else dict(risks={}, ran_at=None)
    ev_by: dict[str, list] = {}
    for e in ev:
        ev_by.setdefault(e["session_id"], []).append(e)
    fr_by: dict[str, list] = {}
    for f in fr:
        fr_by.setdefault(f["session_id"], []).append(f)

    cands, alerts = [], []
    for r in rows:
        if r["status"] == "not_started":
            continue
        sid, es, fs = r["id"], ev_by.get(r["id"], []), fr_by.get(r["id"], [])
        who = _pseudonym(sid)
        answered = (len({x["item"] for x in subs if x["session_id"] == sid and x["verdict"] == "accepted"}) if coding
                    else len({e["item"] for e in es if e["type"] == "answer"}))
        # left the test screen: each focus_lost until the next focus_gained
        left, away, open_at = 0, 0.0, None
        for e in es:
            if e["type"] == "focus_lost":
                left, open_at = left + 1, e["t"]
            elif e["type"] == "focus_gained" and open_at is not None:
                gone = e["t"] - open_at
                away += gone
                alerts.append(dict(at=_wall(r["started_at"], open_at), session_id=sid, who=who, kind="left_tab",
                                   text=f"left the test screen for {gone:.0f} s (Q{e['item'] + 1}, at {_clock(open_at)})"))
                open_at = None
        if open_at is not None:
            alerts.append(dict(at=_wall(r["started_at"], open_at), session_id=sid, who=who, kind="left_tab",
                               text=f"left the test screen at {_clock(open_at)} and has not come back yet"))
        pastes = [e for e in es if e["type"] == "paste"]
        for p in pastes:
            if coding and p["chars"] < 80:            # moving one's own lines in the editor is normal
                continue
            alerts.append(dict(at=_wall(r["started_at"], p["t"]), session_id=sid, who=who, kind="paste",
                               text=f"pasted {p['chars']} characters into {'P' if coding else 'Q'}{p['item'] + 1} (at {_clock(p['t'])})"))
        # a second person: two or more camera checks in a row with 2+ faces (one alone is usually someone walking past)
        two, run = 0, []
        for f in fs + [None]:
            if f is not None and f["faces"] >= 2:
                two += 1
                run.append(f)
                continue
            if len(run) >= 2:
                alerts.append(dict(at=_wall(r["started_at"], run[0]["t"]), session_id=sid, who=who, kind="second_person",
                                   text=f"a second person was in view for about {run[-1]['t'] - run[0]['t'] + 5:.0f} s (from {_clock(run[0]['t'])})"))
            run = []
        from .rules import REASONS, counts_from, flags as rule_flags
        rc = counts_from(es, r.get("relogins") or 0, r.get("terminated_reason"), r.get("rules_reset"), r.get("rule_history"),
                         r.get("device_info"))
        for e in es:
            if e["type"] == "phone_seen":
                alerts.append(dict(at=_wall(r["started_at"], e["t"]), session_id=sid, who=who, kind="phone",
                                   text=f"phone seen on camera (at {_clock(e['t'])})"))
            elif e["type"] == "multi_face":
                alerts.append(dict(at=_wall(r["started_at"], e["t"]), session_id=sid, who=who, kind="second_person",
                                   text=f"more than one face for 5 s (at {_clock(e['t'])})"))
        if r.get("terminated_reason"):
            alerts.append(dict(at=r.get("terminated_at"), session_id=sid, who=who, kind="terminated",
                               text=f"test ended: {REASONS.get(r['terminated_reason'], r['terminated_reason'])}"))
        last_t = max([e["t"] for e in es] + [f["t"] for f in fs] + [0])
        m = model["risks"].get(sid)
        c = dict(session_id=sid, who=who, status=r["status"], answered=answered, n_items=n_items,
                 device=r["device"], bandwidth=r["bandwidth_class"], last_seen=_wall(r["started_at"], last_t),
                 signals=dict(left_tab=left, away_s=round(away), pastes=len(pastes),
                              paste_chars=sum(p["chars"] for p in pastes), two_faces=two, frames=len(fs),
                              no_face_pct=round(100 * sum(1 for f in fs if not f["face_visible"]) / len(fs)) if fs else None,
                              face_now=(bool(fs[-1]["face_visible"]), fs[-1]["faces"]) if fs else None,
                              pauses=sum(1 for e in es if e["type"] == "idle_start"),
                              speech=sum(1 for e in es if e["type"] == "speech_like"),
                              mic=_mic_state(es)),
                 risk=m["risk"] if m else None, band=m["band"] if m else None, families=m["families"] if m else [],
                 headline=m["headline"] if m else "", trend=model.get("trend", {}).get(sid),
                 rules=dict(counts=rc, flags=rule_flags(rc)), terminated=r.get("terminated_reason"))
        if show_names:
            c.update(name=r["name"], roll_no=r["roll_no"], email=r["email"])
        cands.append(c)
    cands.sort(key=lambda c: (c["risk"] is None, -(c["risk"] or 0), c["who"]))
    alerts = sorted([a for a in alerts if a["at"]], key=lambda a: a["at"], reverse=True)[:60]
    try:
        lines = dict(review=50, review_first=_mb()["priority"].review_first_line)
    except Exception:       # noqa: BLE001
        lines = dict(review=50, review_first=None)
    if coding:
        try:
            from .coding_score import bundle as cb
            lines = dict(review=50, review_first=cb()["priority"].review_first_line)
        except Exception:       # noqa: BLE001
            pass
    return dict(sitting=sit, counts=counts, n_items=n_items, candidates=cands, alerts=alerts, priority_lines=lines, kind="coding" if coding else "mcq",
                model=dict(ran_at=model.get("ran_at"), every_s=EVERY_S, min_answers=MIN_ANSWERS,
                           version=model.get("version"), error=model.get("error"), pending=model.get("pending", False)))


def _mic_state(es) -> str | None:
    """'on' while the speech-like sound check is listening, 'off' after it stopped or was refused, None if never asked."""
    st = None
    for e in es:
        if e["type"] == "mic_on":
            st = "on"
        elif e["type"] == "mic_off":
            st = "off"
    return st

"""Close-of-sitting scoring: database -> fairproctor engine -> scores table.

The engine is used exactly as in the research pipeline (fairproctor/features.py, model.py, explain.py).
Collusion needs the whole sitting at once, which is why scoring runs when a sitting closes.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import pickle
import threading

import numpy as np
import pandas as pd

from .. import config, db
from ..jobs import worker

log = logging.getLogger("fairproctor.scoring")
_model_lock = threading.Lock()
_MODEL: dict | None = None


def model_bundle() -> dict:
    """Loads artifacts/model.pkl once. The priority scale is fixed from the training scores so 50/92 mean the same everywhere."""
    global _MODEL
    with _model_lock:
        if _MODEL is None:
            from fairproctor.display import PriorityScale
            art = config.artifacts_dir()
            path = os.path.join(art, "model.pkl")
            if not os.path.exists(path):
                raise RuntimeError(f"model.pkl not found in {art}: it ships in backend/model; or run "
                                   "`python data/generate.py` and `python -m fairproctor.pipeline`.")
            with open(path, "rb") as fh:
                b = pickle.load(fh)
            cache = os.path.join(art, "priority_raws.npy")
            if os.path.exists(cache):
                raws = np.load(cache)
            else:
                with open(os.path.join(art, "store.pkl"), "rb") as fh:
                    raws = np.array([d["raw"] for d in pickle.load(fh).values()])
                np.save(cache, raws)
            with open(path, "rb") as fh:
                version = hashlib.sha1(fh.read()).hexdigest()[:10]
            _MODEL = dict(model=b["model"], stats=b["stats"], T=float(b["T"]), H=float(b["H"]), version=version,
                          priority=PriorityScale(raws, b["T"], b["H"]))
    return _MODEL


def export(con, sitting_id: int):
    """The four tables fairproctor.features.build() expects, read from the database."""
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id)
    sess = pd.DataFrame(db.all_(con, """SELECT id session_id, sitting_id window_id, device, bandwidth_class,
                                               precheck_light, precheck_framing, is_synthetic, relogins, terminated_reason,
                                               rules_reset, rule_history, device_info
                                        FROM sessions WHERE sitting_id = ? AND status = 'submitted'""", sitting_id))
    ev = pd.DataFrame(db.all_(con, """SELECT e.session_id, e.t, e.type, e.item, e.option, e.correct, e.chars
                                      FROM events e JOIN sessions s ON s.id = e.session_id
                                      WHERE s.sitting_id = ? AND s.status = 'submitted' ORDER BY e.session_id, e.t, e.seq""",
                              sitting_id), columns=["session_id", "t", "type", "item", "option", "correct", "chars"])
    fr = pd.DataFrame(db.all_(con, """SELECT f.session_id, f.t, f.faces, f.face_visible, f.gaze, f.brightness, f.blur, f.phone
                                      FROM frame_stats f JOIN sessions s ON s.id = f.session_id
                                      WHERE s.sitting_id = ? AND s.status = 'submitted' ORDER BY f.session_id, f.t""",
                              sitting_id), columns=["session_id", "t", "faces", "face_visible", "gaze", "brightness", "blur", "phone"])
    fr["brightness"] = fr["brightness"].fillna(np.nan)
    items = pd.DataFrame(db.all_(con, "SELECT position item, kind FROM items WHERE test_id = ? ORDER BY position",
                                 sit["test_id"]))
    return sit, sess, ev, fr, items


def choose_stats(ev, items, n_sessions, bundle):
    """Typical time and difficulty of each question. A small sitting (e.g. a demo) borrows the trained paper's statistics."""
    from fairproctor.features import ItemStats
    st = bundle["stats"]
    same_paper = st.b.size == len(items) and list(st.kind) == list(items.kind)
    if n_sessions >= config.MIN_SITTING_FOR_OWN_STATS or not same_paper:
        note = "" if n_sessions >= config.MIN_SITTING_FOR_OWN_STATS else (
            f"only {n_sessions} sessions: question statistics are rough until about {config.MIN_SITTING_FOR_OWN_STATS}")
        return ItemStats.fit(ev, items), note
    return st, "question statistics from the reference paper"


def score_sitting(job_id: int, sitting_id) -> dict:
    from fairproctor.explain import explain, phone_band
    from fairproctor.features import build

    from . import audio, rules

    sitting_id = int(sitting_id)
    with db.tx() as con:
        kind = db.one(con, """SELECT t.kind FROM sittings s JOIN tests t ON t.id = s.test_id WHERE s.id = ?""", sitting_id)["kind"]
    if kind == "coding":                                   # programs, pastes and typing: the coding model
        from .coding_score import score_coding_sitting
        return score_coding_sitting(job_id, sitting_id)
    B = model_bundle()
    with db.tx() as con:
        sit, sess, ev, fr, items = export(con, sitting_id)
        sound = audio.for_sitting(con, sitting_id)
    from fairproctor.features import one_answer_per_item
    ev = one_answer_per_item(ev)                         # answers changed on review: the final one counts
    if sess.empty:
        with db.tx() as con:
            con.execute("UPDATE sittings SET status = 'scored', scored_at = ? WHERE id = ?", (db.now(), sitting_id))
        worker.progress(job_id, 1, "no submitted sessions")
        return dict(n=0)
    worker.progress(job_id, 0.1, f"building features for {len(sess)} sessions")
    st, note = choose_stats(ev, items, len(sess), B)
    X, evid, st = build(sess, ev, fr, items, stats=st)
    worker.progress(job_id, 0.6, "scoring")
    M = B["model"]
    raw = M.raw(X)
    prob = M.iso.predict(raw)
    contrib = M.contributions(X)
    order = np.argsort(-raw)
    rank = np.empty(len(raw), int)
    rank[order] = np.arange(1, len(raw) + 1)
    ev_by = {k: g for k, g in ev.groupby("session_id")}
    meta_by = sess.set_index("session_id").to_dict("index")
    rows = []
    for i, sid in enumerate(X.index):
        band = "review_first" if raw[i] >= B["H"] else ("review" if raw[i] >= B["T"] else "clear")
        band = phone_band(band, X.loc[sid].to_dict())
        tr = meta_by[sid].get("terminated_reason")
        rc = rules.counts_from(ev_by.get(sid, ev.iloc[:0]), int(meta_by[sid].get("relogins") or 0),
                               tr if isinstance(tr, str) else None, meta_by[sid].get("rules_reset"),
                               meta_by[sid].get("rule_history"), meta_by[sid].get("device_info"))
        band = rules.band_floor(band, rc)                    # ended tests, repeated logins, disconnect flag: a person looks
        e = explain(sid, X.loc[sid].to_dict(), contrib.loc[sid].to_dict(), evid[sid], dict(meta_by[sid], session_id=sid),
                    round(100 * float(prob[i]), 1), band, events=ev_by.get(sid), stats=st)
        e["rules"] = dict(counts=rc, flags=rules.flags(rc))
        audio.annotate(e, sound.get(sid), ev_by.get(sid))      # microphone: a supporting line or "not counted", never score
        e["rank"] = int(rank[i])
        if not meta_by[sid].get("is_synthetic"):
            e["context"] = [_live_note(n) for n in e["context"]]
        pr = B["priority"](raw[i])
        rows.append((sid, sitting_id, float(raw[i]), float(prob[i]), pr, band, int(rank[i]),
                     json.dumps([r["family"] for r in e["reasons"]] + rules.chips(rc)), json.dumps(_jsonable(e)), B["version"]))
        if i % 25 == 0:
            worker.progress(job_id, 0.6 + 0.35 * i / len(X), f"explaining {i}/{len(X)}")
    with db.tx() as con:
        con.execute("DELETE FROM scores WHERE sitting_id = ?", (sitting_id,))
        con.executemany("""INSERT INTO scores (session_id, sitting_id, raw, prob, priority, band, rank, families, explanation,
                                               model_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        con.execute("UPDATE sittings SET status = 'scored', scored_at = ? WHERE id = ?", (db.now(), sitting_id))
        bands = {b: sum(1 for r in rows if r[5] == b) for b in ("review_first", "review", "clear")}
        db.audit(con, None, "sitting_scored", sitting_id, n=len(rows), note=note, **bands)
    worker.progress(job_id, 1, f"scored {len(rows)} sessions" + (f"; {note}" if note else ""))
    return dict(n=len(rows))


def _live_note(note: str) -> str:
    """Live sessions send camera numbers every ~5 s by design (battery and data), so that is not 'low bandwidth'."""
    import re
    m = re.match(r"Low-bandwidth video: about one analysed frame every (\d+) s", note)
    if m and int(m.group(1)) <= 6:
        return ("Camera checks run on the device about every 5 s to save data and battery; "
                "video-based checks were weighted accordingly.")
    return note


def _jsonable(o):
    from ..http import clean
    return clean(o)


@worker.handler("score_sitting")
def _job(job_id, target):
    score_sitting(job_id, target)

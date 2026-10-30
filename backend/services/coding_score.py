"""Scoring coding sittings with the coding integrity model (fairproctor/coding.py).

Used when a coding sitting closes (all submitted sessions) and by the live monitor (answers so far).
The output has the same shape as question tests, so the queue, the session page and the candidate's result
work unchanged; the session page also shows the programs and, for a match, the other candidate's program.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import threading

import numpy as np
import pandas as pd

from .. import config, db

_lock = threading.Lock()
_B: dict | None = None


def bundle() -> dict:
    global _B
    with _lock:
        if _B is None:
            from fairproctor.display import PriorityScale
            path = os.path.join(config.artifacts_dir(), "coding_model.pkl")
            if not os.path.exists(path):
                raise RuntimeError("coding_model.pkl not found: run `python -m fairproctor.coding_pipeline --out backend/model`.")
            with open(path, "rb") as fh:
                raw_bytes = fh.read()
            b = pickle.loads(raw_bytes)
            _B = dict(model=b["model"], stats=b["stats"], T=float(b["T"]), H=float(b["H"]),
                      priority=PriorityScale(b["raws"], b["T"], b["H"]),
                      version="code-" + hashlib.sha1(raw_bytes).hexdigest()[:8])
    return _B


def export(con, sitting_id: int, statuses=("submitted",)):
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id)
    marks = ",".join("?" * len(statuses))
    sess = pd.DataFrame(db.all_(con, f"""SELECT id session_id, sitting_id window_id, device, bandwidth_class, is_synthetic
                                         FROM sessions WHERE sitting_id = ? AND status IN ({marks})""", sitting_id, *statuses),
                        columns=["session_id", "window_id", "device", "bandwidth_class", "is_synthetic"])
    ev = pd.DataFrame(db.all_(con, f"""SELECT e.session_id, e.t, e.type, e.item, e.chars, e.meta
                                       FROM events e JOIN sessions s ON s.id = e.session_id
                                       WHERE s.sitting_id = ? AND s.status IN ({marks})
                                         AND e.type IN ('item_shown', 'code_typing', 'paste', 'focus_lost', 'focus_gained')
                                       ORDER BY e.session_id, e.t, e.seq""", sitting_id, *statuses),
                      columns=["session_id", "t", "type", "item", "chars", "meta"])
    ev["meta"] = [json.loads(m) if isinstance(m, str) and m else None for m in ev.meta]
    runs = pd.DataFrame(db.all_(con, f"""SELECT r.session_id, r.item, r.kind, r.language, r.code, r.verdict, r.passed, r.total,
                                                COALESCE(r.t, 0) t
                                         FROM code_runs r JOIN sessions s ON s.id = r.session_id
                                         WHERE s.sitting_id = ? AND s.status IN ({marks}) ORDER BY r.id""", sitting_id, *statuses),
                        columns=["session_id", "item", "kind", "language", "code", "verdict", "passed", "total", "t"])
    items = db.all_(con, "SELECT position, options FROM items WHERE test_id = ? AND kind = 'code' ORDER BY position", sit["test_id"])
    starters = {r["position"]: json.loads(r["options"]).get("starter", {}) for r in items}
    titles = [json.loads(r["options"]).get("title", "") for r in items]
    return sit, sess, ev, runs, [r["position"] for r in items], starters, titles


DEMO_TITLES = ["Second largest", "Balanced brackets", "Pairs with sum k"]


def _stats(ev, runs, items, titles, B):
    from fairproctor.coding import CodingStats
    st = CodingStats.fit(ev, runs, items)
    tta = runs[(runs.kind == "submit") & (runs.verdict == "accepted")].groupby("item").session_id.nunique().to_dict()
    for it in items:
        if tta.get(it, 0) < 5:          # too few solvers here to know what is typical
            st.typical[it] = B["stats"].typical.get(it, 600.0) if titles == DEMO_TITLES else 600.0
    return st


def score_frame(sess, ev, runs, items, starters, titles, ids=None):
    """Model run on the given sessions; returns {session_id: dict(raw, prob, priority, band, explanation, families)}."""
    from fairproctor import coding
    B = bundle()
    st = _stats(ev, runs, items, titles, B)
    X, evid, _ = coding.build(sess, ev, runs, items, stats=st, starters=starters)
    ids = [s for s in (ids or list(X.index)) if s in X.index]
    if not ids:
        return {}
    XL = X.loc[ids]
    M = B["model"]
    raw = M.raw(XL)
    prob = M.iso.predict(raw)
    contrib = M.contributions(XL)
    out = {}
    for i, sid in enumerate(ids):
        band = "review_first" if raw[i] >= B["H"] else ("review" if raw[i] >= B["T"] else "clear")
        e = coding.explain(sid, XL.loc[sid].to_dict(), contrib.loc[sid].to_dict(), evid[sid], round(100 * float(prob[i]), 1), band)
        out[sid] = dict(raw=float(raw[i]), prob=float(prob[i]), priority=B["priority"](raw[i]), band=band, explanation=e,
                        families=[r["family"] for r in e["reasons"]])
    return out


def score_coding_sitting(job_id: int, sitting_id: int) -> dict:
    from ..jobs import worker
    from .scoring import _jsonable
    B = bundle()
    with db.tx() as con:
        sit, sess, ev, runs, items, starters, titles = export(con, sitting_id)
    if sess.empty:
        with db.tx() as con:
            con.execute("UPDATE sittings SET status = 'scored', scored_at = ? WHERE id = ?", (db.now(), sitting_id))
        worker.progress(job_id, 1, "no submitted sessions")
        return dict(n=0)
    worker.progress(job_id, 0.15, f"comparing programs and typing for {len(sess)} sessions")
    res = score_frame(sess, ev, runs, items, starters, titles)
    worker.progress(job_id, 0.85, "saving")
    order = sorted(res, key=lambda s: -res[s]["raw"])
    rank = {s: i + 1 for i, s in enumerate(order)}
    from . import rules
    with db.tx() as con:                                     # proctoring rules (ended tests, logins, disconnects)
        rc_by = {sid: rules.counts(con, sid) for sid in res}
    rows = []
    for sid, r in res.items():
        r["explanation"]["rank"] = rank[sid]
        rc = rc_by[sid]
        r["band"] = rules.band_floor(r["band"], rc)
        r["explanation"]["band"] = r["band"]
        r["explanation"]["rules"] = dict(counts=rc, flags=rules.flags(rc))
        r["families"] = r["families"] + rules.chips(rc)
        rows.append((sid, sitting_id, r["raw"], r["prob"], r["priority"], r["band"], rank[sid], json.dumps(r["families"]),
                     json.dumps(_jsonable(r["explanation"])), B["version"]))
    with db.tx() as con:
        con.execute("DELETE FROM scores WHERE sitting_id = ?", (sitting_id,))
        con.executemany("""INSERT INTO scores (session_id, sitting_id, raw, prob, priority, band, rank, families, explanation,
                                               model_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", rows)
        con.execute("UPDATE sittings SET status = 'scored', scored_at = ? WHERE id = ?", (db.now(), sitting_id))
        bands = {b: sum(1 for r in rows if r[5] == b) for b in ("review_first", "review", "clear")}
        db.audit(con, None, "sitting_scored", sitting_id, n=len(rows), kind="coding", **bands)
    worker.progress(job_id, 1, f"scored {len(rows)} coding sessions")
    return dict(n=len(rows))


def session_code(con, session_id: str, explanation: dict) -> list[dict]:
    """For the reviewer: each problem's final program, and the matching program of the other candidate."""
    from fairproctor.coding import final_codes
    from fairproctor.display import pseudonym
    runs = pd.DataFrame(db.all_(con, """SELECT session_id, item, kind, language, code, verdict, passed, total, COALESCE(t, 0) t
                                        FROM code_runs WHERE session_id = ? ORDER BY id""", session_id),
                        columns=["session_id", "item", "kind", "language", "code", "verdict", "passed", "total", "t"])
    if runs.empty:
        return []
    fin = final_codes(runs)
    titles = {r["position"]: json.loads(r["options"]).get("title", "") for r in db.all_(
        con, """SELECT i.position, i.options FROM items i JOIN sittings s ON s.test_id = i.test_id
                JOIN sessions x ON x.sitting_id = s.id WHERE x.id = ? AND i.kind = 'code'""", session_id)}
    matches = {}
    for r in explanation.get("reasons", []):
        for e in r.get("evidence", []):
            if e.get("key") in ("code_sim", "code_sim_partial") and e.get("partner"):
                matches.setdefault(e["item"], e)
    out = []
    for (sid, item), f in sorted(fin.items(), key=lambda x: x[0][1]):
        row = dict(item=item, title=titles.get(item, ""), language=f["language"], code=f["code"], verdict=f["verdict"],
                   passed=f["passed"], total=f["total"], t=f["t"],
                   attempts=int(((runs.item == item) & (runs.kind == "submit")).sum()),
                   runs=int(((runs.item == item) & (runs.kind == "run")).sum()))
        m = matches.get(item)
        if m:
            other = db.all_(con, """SELECT session_id, item, kind, language, code, verdict, passed, total, COALESCE(t, 0) t
                                    FROM code_runs WHERE session_id = ? AND item = ? ORDER BY id""", m["partner"], item)
            of = final_codes(pd.DataFrame(other)).get((m["partner"], item)) if other else None
            row["match"] = dict(session_id=m["partner"], pseudonym=pseudonym(m["partner"]), similarity=round(m["strength"], 2),
                                lines=m.get("lines", []), partner_lines=m.get("partner_lines", []),
                                code=of["code"] if of else "", language=of["language"] if of else "")
        out.append(row)
    return out

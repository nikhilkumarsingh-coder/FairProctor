"""Deletion on request and automatic retention (DPDP). Audit rows keep no personal data."""
from __future__ import annotations

import datetime as dt

from .. import config, db
from ..jobs.worker import handler


def delete_session(con, session_id: str, actor_id=None, reason: str = "") -> bool:
    s = db.one(con, "SELECT * FROM sessions WHERE id = ?", session_id)
    if not s:
        return False
    counts = {t: db.one(con, f"SELECT COUNT(*) n FROM {t} WHERE session_id = ?", session_id)["n"]
              for t in ("events", "frame_stats", "snapshots")}
    # events, frame_stats, snapshots, code_runs, consents, precheck_results, scores, reviews, appeals cascade with the session
    con.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
    if s["user_id"] and not db.one(con, "SELECT 1 FROM sessions WHERE user_id = ?", s["user_id"]):
        # the candidate's personal data (name, roll no., email) goes with their last session
        con.execute("DELETE FROM users WHERE id = ? AND role = 'candidate'", (s["user_id"],))
    db.audit(con, actor_id, "session_deleted", session_id, reason=reason, **counts)
    return True


def expired_sessions(con, days: int | None = None) -> list[str]:
    days = config.retention_days() if days is None else days
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return [r["id"] for r in db.all_(con, """SELECT x.id FROM sessions x JOIN sittings s ON s.id = x.sitting_id
                                             WHERE x.is_synthetic = 0 AND COALESCE(x.submitted_at, s.closed_at) < ?""", cutoff)]


@handler("retention")
def run_retention(job_id, target):
    with db.tx() as con:
        ids = expired_sessions(con)
        for sid in ids:
            delete_session(con, sid, reason=f"retention {config.retention_days()} days")
        from .snapshots import expire
        photos = expire(con)                           # snapshots go sooner than the rest of the record
        con.execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (db.now(),))
        db.audit(con, None, "retention_run", "", deleted=len(ids), snapshots_deleted=photos)

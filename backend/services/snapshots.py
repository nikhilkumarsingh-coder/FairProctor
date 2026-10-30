"""Camera snapshots at flagged moments.

The page takes a small photo only when something is flagged (a second person stays, no face for a while, a phone in
view, coming back to the test tab): one from just before, one at the moment, one a few seconds after. Reviewers see
them next to the evidence so they can tell a sibling walking past from a helper; the candidate sees their own on the
result page. They are never a model input and are deleted after config.snapshot_days().
"""
from __future__ import annotations

import base64
import binascii
import datetime as dt

from .. import config, db
from ..http import ApiError

LABELS = {"two_people": "A second person in view", "no_face": "Face not seen", "phone": "Phone in view",
          "tab_return": "Back from another tab or app"}


GRACE_S = 90      # a test a rule just ended still takes the photos of that moment (the "after" one, a 2G retry):
                  # they are what a reviewer looks at before reopening it


def _just_ended(session: dict) -> bool:
    if session["status"] != "submitted" or not session.get("terminated_reason") or not session.get("terminated_at"):
        return False
    at = db.parse_ts(session["terminated_at"])
    return bool(at) and (dt.datetime.now(dt.timezone.utc) - at).total_seconds() <= GRACE_S


def store(con, session: dict, sitting: dict, t: float, reason: str, phase: str, image: str) -> dict:
    if sitting["status"] != "live":
        return dict(stored=False, reason="sitting_closed")        # a late upload (2G) after the sitting closed: dropped
    if session["status"] != "in_progress" and not _just_ended(session):
        raise ApiError(409, "not_writing", "Snapshots are taken only while the test is being written.")
    raw = image.split(",", 1)[1] if image.startswith("data:") else image
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ApiError(422, "bad_image", "The snapshot is not a valid image.")
    if not data.startswith(b"\xff\xd8\xff") or len(data) > config.SNAPSHOT_MAX_BYTES:
        raise ApiError(422, "bad_image", "Snapshots must be small JPEG images.")
    n = db.one(con, "SELECT COUNT(*) n FROM snapshots WHERE session_id = ?", session["id"])["n"]
    if n >= config.SNAPSHOT_MAX_PER_SESSION:
        return dict(stored=False, reason="limit")
    if db.one(con, "SELECT 1 FROM snapshots WHERE session_id = ? AND reason = ? AND phase = ? AND abs(t - ?) < 1",
              session["id"], reason, phase, t):
        return dict(stored=False, reason="duplicate")            # a 2G retry
    con.execute("""INSERT INTO snapshots (session_id, t, reason, phase, image, bytes, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""", (session["id"], t, reason, phase, raw, len(data), db.now()))
    return dict(stored=True)


def listing(con, session_id: str) -> list[dict]:
    rows = db.all_(con, "SELECT id, t, reason, phase, image, created_at FROM snapshots WHERE session_id = ? ORDER BY t, id",
                   session_id)
    return [dict(id=r["id"], t=r["t"], reason=r["reason"], label=LABELS.get(r["reason"], r["reason"]), phase=r["phase"],
                 image="data:image/jpeg;base64," + r["image"], taken_at=r["created_at"]) for r in rows]


def expire(con, days: int | None = None) -> int:
    days = config.snapshot_days() if days is None else days
    cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = db.one(con, "SELECT COUNT(*) n FROM snapshots WHERE created_at < ?", cutoff)["n"]
    con.execute("DELETE FROM snapshots WHERE created_at < ?", (cutoff,))
    return n

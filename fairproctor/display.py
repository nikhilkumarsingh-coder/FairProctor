"""Display fields shared by the live API and the demo fixtures, so the frontend sees one contract.

priority  0-100 review priority. 50 = the review line, higher = review sooner. NOT a probability of cheating.
pseudonym stable, non-identifying label derived from the session id.
sitting   label and start time for the sitting (synthetic schedule for the demo sample).
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib

import numpy as np

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
SLOTS = [(10, 0), (13, 30), (16, 30)]
EXAM = "Campus Hiring Assessment 2026 — Aptitude & Reasoning"


class PriorityScale:
    def __init__(self, raws, review_raw: float, review_first_raw: float):
        self.T = float(review_raw)
        self.spread = float((np.quantile(np.asarray(raws), 0.999) - self.T) / 4.5)
        self.review_first_line = self(review_first_raw)

    def __call__(self, raw: float) -> int:
        return int(round(100 / (1 + np.exp(-(raw - self.T) / self.spread))))


def _h(sid: str, salt: str) -> bytes:
    return hashlib.sha1(f"samata:{salt}:{sid}".encode()).digest()  # fixed salt prefix; changing it renames every demo pseudonym


def pseudonym(sid: str) -> str:
    return "Candidate " + base64.b32encode(_h(sid, "p")).decode()[:4]


def sitting(w: int) -> dict:
    day = dt.date(2026, 10, 6) + dt.timedelta(days=int(w) // 3)
    hh, mm = SLOTS[int(w) % 3]
    start = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=IST)
    return dict(id=f"SIT-{int(w) + 1:02d}", label=f"Sitting {int(w) + 1} · {start:%d %b, %H:%M} IST",
                startsAt=start.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"))


def started_at(sid: str, w: int) -> str:
    base = dt.datetime.fromisoformat(sitting(w)["startsAt"].replace("Z", "+00:00"))
    t = base + dt.timedelta(seconds=int.from_bytes(_h(sid, "t")[:2], "big") % 240)
    return t.isoformat().replace("+00:00", "Z")


def demo_status(sid: str, band: str, verdict: str) -> str:
    """Demo review statuses; 'confirmed_by_reviewer' only ever comes from a reviewer verdict in the sample."""
    if band == "clear":
        return "auto_cleared"
    r = int.from_bytes(_h(sid, "s")[:2], "big") / 65535
    if r < 0.22:
        return "confirmed_by_reviewer" if verdict == "confirmed" else "cleared_after_review"
    if r < 0.28:
        return "under_investigation"
    if r < 0.31:
        return "needs_further_investigation"
    return "high_priority" if band == "review_first" else "needs_review"

"""Which device a candidate writes on, decided automatically, and what that means for the lock-down.

    inside Safe Exam Browser          SEB (the page skips its own kiosk mode)
    phone or tablet browser           kiosk mode: full screen, screen kept on, leaving full screen noted
                                      (SEB does not exist on Android, so a sitting that requires SEB lets phones in)
    laptop / desktop browser          SEB when the sitting requires it, otherwise kiosk mode

The device is read from the request (User-Agent, the Sec-CH-UA-Mobile client hint) and checked against what the page
measures (touch points, screen size, pointer). A browser can be told to pretend to be a phone, so a laptop could try
that to avoid SEB: when the request says "phone" but the page looks like a laptop, the session gets a "device check"
flag for the reviewer. It never ends a test.
"""
from __future__ import annotations

import json
import re

from .. import db

MOBILE_UA = re.compile(r"Mobi|Android|iPhone|iPad|iPod|Windows Phone", re.I)
IOS_UA = re.compile(r"iPhone|iPad|iPod", re.I)


def from_request(request) -> dict:
    ua = request.headers.get("user-agent", "")
    ch = request.headers.get("sec-ch-ua-mobile")
    return dict(ua_mobile=bool(MOBILE_UA.search(ua)), ch_mobile=None if ch is None else ch.strip() == "?1",
                ios=bool(IOS_UA.search(ua)))


def is_mobile(request) -> bool:
    d = from_request(request)
    return d["ua_mobile"] or d["ch_mobile"] is True


def looks_like_laptop(signals: dict | None) -> bool | None:
    """From the page's own measurements: no touch, a fine pointer and a wide screen. None when not measured."""
    if not signals:
        return None
    touch = signals.get("touch")
    w, h = signals.get("w") or 0, signals.get("h") or 0
    if touch is None or not w:
        return None
    return touch == 0 and not signals.get("coarse") and max(w, h) >= 1100 and min(w, h) >= 700


def record(con, session_id: str, request, signals: dict | None, seb_required: bool, in_seb: bool) -> dict:
    """Store what was seen at the start of the test (merged on a resume; a mismatch, once seen, stays)."""
    s = db.one(con, "SELECT device_info FROM sessions WHERE id = ?", session_id) or {}
    old = json.loads(s["device_info"]) if s.get("device_info") else {}
    d = from_request(request)
    mobile = d["ua_mobile"] or d["ch_mobile"] is True
    laptop = looks_like_laptop(signals)
    mismatch = bool(mobile and laptop)
    info = dict(old, **d, signals=signals or old.get("signals"), mobile=mobile,
                mode="seb" if in_seb else "kiosk",
                seb_exempt=bool(seb_required and mobile and not in_seb) or bool(old.get("seb_exempt")),
                mismatch=mismatch or bool(old.get("mismatch")))
    if info["mismatch"]:
        info["note"] = "The browser says phone, but the screen and input look like a laptop or desktop."
    con.execute("UPDATE sessions SET device_info = ? WHERE id = ?", (json.dumps(info), session_id))
    return info


def parse(v) -> dict:
    if isinstance(v, dict):
        return v
    try:
        return json.loads(v) if isinstance(v, str) and v else {}
    except ValueError:
        return {}

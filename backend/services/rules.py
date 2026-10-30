"""Proctoring rules: clear counts with fixed limits, next to the trained model (which only ranks).

    phone seen (2 of 5 seconds)       1st: warning + snapshot      2nd: test ended
    2+ faces for 5 seconds            each: warning + snapshot     6th: test ended
    leaving the test tab or app       each: warning with count     6th: test ended
    logging in again during the test  counted, never ends it       2+: sent to review
    disconnects (offline episodes)    counted                      6+ with answers right after reconnecting: flag

The device reports the episodes; the server stores them, ends the test when a limit is passed (also if the device
did not), keeps the reason, and makes sure a person reviews every ended test. Ending a test never decides
malpractice: the reviewer confirms or clears it, and the candidate can reply.
"""
from __future__ import annotations

import datetime as dt
import json

import pandas as pd

from .. import config, db
from ..http import ApiError

EVENT_FOR = {"phone": "phone_seen", "multiple_faces": "multi_face", "tab_switch": "focus_lost"}
REASONS = {
    "phone": "A phone was seen on camera a second time after a warning.",
    "multiple_faces": f"More than one face was seen on camera more than {config.MULTI_FACE_MAX} times.",
    "tab_switch": f"The test tab or app was left more than {config.TAB_SWITCH_MAX} times.",
}


def _json(v, default):
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v) if isinstance(v, str) and v else default
    except ValueError:
        return default


def counts_from(ev: pd.DataFrame | list[dict], relogins: int = 0, terminated: str | None = None,
                reset: dict | str | None = None, history: list | str | None = None, device=None) -> dict:
    df = ev if isinstance(ev, pd.DataFrame) else pd.DataFrame(ev, columns=["t", "type", "item", "correct"])
    reset = _json(reset, {})
    if len(df) and reset:                      # a reopened test: the rule that ended it starts counting again from 0
        drop = pd.Series(False, index=df.index)
        for etype, upto in reset.items():
            drop |= (df["type"] == etype) & (df["t"].astype(float) <= float(upto))
        df = df[~drop]
    t = df["type"] if len(df) else pd.Series([], dtype=str)
    ends = df[t == "offline_end"]["t"].astype(float).tolist() if len(df) else []
    answers = df[t == "answer"]["t"].astype(float).tolist() if len(df) else []
    quick = sum(1 for e in ends if any(0 <= a - e <= config.RECONNECT_ANSWER_S for a in answers))
    dev = _json(device, {})
    return dict(phone=int((t == "phone_seen").sum()), multi_face=int((t == "multi_face").sum()),
                tab_switch=int((t == "focus_lost").sum()), disconnects=int((t == "offline_start").sum()),
                answered_after_reconnect=quick, relogins=int(relogins or 0), terminated=terminated or None,
                history=_json(history, []), fullscreen_exits=int((t == "fullscreen_exit").sum()),
                device=dict(mode=dev.get("mode"), mobile=dev.get("mobile"), seb_exempt=bool(dev.get("seb_exempt")),
                            mismatch=bool(dev.get("mismatch")), note=dev.get("note")) if dev else None)


def counts(con, session_id: str) -> dict:
    s = db.one(con, "SELECT relogins, terminated_reason, rules_reset, rule_history, device_info FROM sessions WHERE id = ?",
               session_id) or {}
    ev = db.all_(con, """SELECT t, type, item, correct FROM events WHERE session_id = ?
                         AND type IN ('phone_seen', 'multi_face', 'focus_lost', 'offline_start', 'offline_end', 'answer',
                                      'fullscreen_exit')
                         ORDER BY t""", session_id)
    return counts_from(ev, s.get("relogins", 0), s.get("terminated_reason"), s.get("rules_reset"), s.get("rule_history"),
                       s.get("device_info"))


def limit_passed(c: dict) -> str | None:
    if c["phone"] > config.PHONE_WARNINGS:
        return "phone"
    if c["multi_face"] > config.MULTI_FACE_MAX:
        return "multiple_faces"
    if c["tab_switch"] > config.TAB_SWITCH_MAX:
        return "tab_switch"
    return None


def disconnect_flag(c: dict) -> bool:
    return c["disconnects"] > config.DISCONNECT_MAX and c["answered_after_reconnect"] > 0


def terminate(con, session: dict, reason: str, actor_id=None) -> bool:
    """End a running test: it is submitted as it stands and the reason is kept for the reviewer and the candidate."""
    if session["status"] != "in_progress":
        return False
    now = db.now()
    con.execute("""UPDATE sessions SET status = 'submitted', submitted_at = ?, terminated_reason = ?, terminated_at = ?
                   WHERE id = ? AND status = 'in_progress'""", (now, reason, now, session["id"]))
    db.audit(con, actor_id, "exam_terminated", session["id"], reason=reason)
    return True


def enforce(con, session: dict) -> str | None:
    """After new events are stored: end the test if a limit has been passed. Returns the reason, if ended."""
    if session["status"] != "in_progress":
        return None
    reason = limit_passed(counts(con, session["id"]))
    if reason and terminate(con, session, reason):
        return reason
    return None


def reinstate(con, session_id: str, reviewer: dict, note: str) -> dict:
    """A reviewer reopens a test a rule ended, while the sitting is open: answers stay, the minutes it stood ended are
    given back (never past the sitting's end), and the rule that ended it counts from 0 again. Any reviewer can do it;
    the first one wins if two press at once."""
    s = db.one(con, "SELECT * FROM sessions WHERE id = ?", session_id)
    if not s:
        raise ApiError(404, "not_found", "No session with this id.")
    if not s.get("terminated_reason") or s["status"] != "submitted":
        raise ApiError(409, "not_ended_by_rule", "Only a test ended by a proctoring rule can be reopened (it may already be reopened).")
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", s["sitting_id"])
    now = dt.datetime.now(dt.timezone.utc)
    if sit["status"] != "live" or now >= db.parse_ts(sit["ends_at"]):
        raise ApiError(409, "window_closed", "The sitting's time window is over, so the test cannot be reopened. Clear it in the review instead.")
    ended_at = db.parse_ts(s["terminated_at"]) or now
    gap = max(0.0, (now - ended_at).total_seconds())
    t_now = (now - db.parse_ts(s["started_at"])).total_seconds()          # the exam clock the device uses
    reset = _json(s.get("rules_reset"), {})
    etype = EVENT_FOR.get(s["terminated_reason"], s["terminated_reason"])
    last = db.one(con, "SELECT MAX(t) m FROM events WHERE session_id = ? AND type = ?", session_id, etype)["m"]
    reset[etype] = max(t_now, float(last or 0))          # every earlier event of this rule, even if the device clock ran ahead
    hist = _json(s.get("rule_history"), [])
    hist.append(dict(reason=s["terminated_reason"], ended_at=s["terminated_at"], reopened_at=db.now(),
                     by=reviewer.get("name") or reviewer.get("email") or str(reviewer["id"]), note=note,
                     minutes_back=round(gap / 60, 1)))
    cur = con.execute("""UPDATE sessions SET status = 'in_progress', submitted_at = NULL, terminated_reason = NULL,
                         terminated_at = NULL, extra_seconds = COALESCE(extra_seconds, 0) + ?, rules_reset = ?, rule_history = ?
                         WHERE id = ? AND status = 'submitted' AND terminated_reason IS NOT NULL""",
                      (gap, json.dumps(reset), json.dumps(hist), session_id))
    if cur.rowcount != 1:
        raise ApiError(409, "not_ended_by_rule", "Another reviewer has just reopened this test.")
    db.audit(con, reviewer["id"], "exam_reinstated", session_id, reason=hist[-1]["reason"], seconds_back=round(gap))
    from .exam import deadline, sitting_and_test
    _, test, _ = sitting_and_test(con, s["sitting_id"])
    dl = deadline(db.one(con, "SELECT * FROM sessions WHERE id = ?", session_id), sit, test)
    return dict(status="in_progress", minutes_back=hist[-1]["minutes_back"], deadline=dl.isoformat() if dl else None)


def flags(c: dict) -> list[dict]:
    """What the reviewer sees in the 'Proctoring rules' card and the queue chips."""
    out = []
    for h in c.get("history") or []:
        out.append(dict(key="reinstated", level="info",
                        text=f"Ended by a rule ({REASONS.get(h.get('reason'), h.get('reason'))}) and reopened by {h.get('by')}"
                             f" — {h.get('minutes_back', 0)} min given back. Note: {h.get('note') or '—'}"))
    if c.get("terminated"):
        out.append(dict(key="terminated", level="high", text=f"Test ended by a rule: {REASONS.get(c['terminated'], c['terminated'])}"))
    if c["phone"]:
        out.append(dict(key="phone_rule", level="high" if c["phone"] > config.PHONE_WARNINGS else "info",
                        text=f"Phone seen on camera {c['phone']} time{'s' if c['phone'] > 1 else ''} (1st = warning, 2nd ends the test)."))
    if c["multi_face"]:
        out.append(dict(key="multi_face", level="high" if c["multi_face"] > config.MULTI_FACE_MAX else "info",
                        text=f"More than one face for 5 s or longer: {c['multi_face']} time{'s' if c['multi_face'] > 1 else ''} (limit {config.MULTI_FACE_MAX})."))
    if c["tab_switch"]:
        out.append(dict(key="tab_switch", level="high" if c["tab_switch"] > config.TAB_SWITCH_MAX else "info",
                        text=f"Left the test tab or app {c['tab_switch']} time{'s' if c['tab_switch'] > 1 else ''} (limit {config.TAB_SWITCH_MAX})."))
    if c["relogins"]:
        out.append(dict(key="relogin", level="medium" if c["relogins"] >= config.RELOGIN_REVIEW else "info",
                        text=f"Logged in again during the test {c['relogins']} time{'s' if c['relogins'] > 1 else ''} (counted; the test was not ended)."))
    if c.get("fullscreen_exits"):
        out.append(dict(key="fullscreen", level="info",
                        text=f"Left full screen {c['fullscreen_exits']} time{'s' if c['fullscreen_exits'] > 1 else ''} "
                             "(noted only: on a phone a swipe, a notification or a call does this; never a rule)."))
    d = c.get("device") or {}
    if d.get("mismatch"):
        out.append(dict(key="device_check", level="medium" if d.get("seb_exempt") else "info",
                        text="Device check: the browser said phone, but the screen and input looked like a laptop or desktop"
                             + (" — this let it skip Safe Exam Browser, which the sitting requires on laptops." if d.get("seb_exempt") else ".")))
    if c["disconnects"]:
        flagged = disconnect_flag(c)
        out.append(dict(key="disconnect", level="medium" if flagged else "info",
                        text=f"Disconnected {c['disconnects']} time{'s' if c['disconnects'] > 1 else ''}"
                             + (f"; answered within {config.RECONNECT_ANSWER_S} s of reconnecting {c['answered_after_reconnect']} time"
                                f"{'s' if c['answered_after_reconnect'] > 1 else ''}." if flagged else ".")))
    return out


def chips(c: dict) -> list[str]:
    """Queue chips (families) added by the rules."""
    out = []
    if c.get("terminated"):
        out.append("terminated")
    if c["relogins"] >= config.RELOGIN_REVIEW:
        out.append("relogin")
    if disconnect_flag(c):
        out.append("disconnect")
    d = c.get("device") or {}
    if d.get("mismatch") and d.get("seb_exempt"):             # may have avoided SEB by pretending to be a phone
        out.append("device_check")
    return out


def band_floor(band: str, c: dict) -> str:
    """A person looks at every test ended by a rule, repeated logins and the disconnect flag (never 'review first' by
    itself, and a band is never lowered)."""
    if band == "clear" and chips(c):
        return "review"
    return band

"""Candidate side: session lookup, start/resume, event ingestion, submit, result, appeal."""
from __future__ import annotations

import datetime as dt
import json

from .. import config, db
from ..http import ApiError


def latest_session(con, user: dict) -> dict | None:
    return db.one(con, "SELECT * FROM sessions WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1", user["id"])


def my_session(con, user: dict) -> dict:
    s = latest_session(con, user)
    if not s:
        raise ApiError(404, "no_session", "No test yet. Enter the join code from your test centre.")
    return s


def join(con, user: dict, code: str) -> dict:
    """A candidate who signed up joins a sitting with its join code (imported candidates are already in theirs)."""
    from ..security import new_session_id
    sit = db.one(con, "SELECT * FROM sittings WHERE upper(join_code) = upper(?)", code.strip())
    if not sit:
        raise ApiError(404, "bad_join_code", "This join code is not correct.")
    if sit["status"] not in ("scheduled", "live"):
        raise ApiError(409, "sitting_closed", "This test is already closed.")
    s = db.one(con, "SELECT * FROM sessions WHERE sitting_id = ? AND user_id = ?", sit["id"], user["id"])
    if not s:
        con.execute("INSERT INTO sessions (id, sitting_id, user_id) VALUES (?, ?, ?)",
                    (new_session_id(), sit["id"], user["id"]))
        db.audit(con, user["id"], "joined_sitting", sit["id"])
    return overview(con, user)


def sitting_and_test(con, sitting_id: int):
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", sitting_id)
    test = db.one(con, "SELECT * FROM tests WHERE id = ?", sit["test_id"])
    n = db.one(con, "SELECT COUNT(*) n FROM items WHERE test_id = ?", test["id"])["n"]
    return sit, test, n


def deadline(sess: dict, sit: dict, test: dict) -> dt.datetime | None:
    if not sess["started_at"]:
        return None
    own = db.parse_ts(sess["started_at"]) + dt.timedelta(minutes=test["duration_min"], seconds=float(sess.get("extra_seconds") or 0))
    return min(own, db.parse_ts(sit["ends_at"]))           # time given back after a reopen never runs past the sitting


def has_consent(con, session_id: str) -> dict | None:
    return db.one(con, "SELECT * FROM consents WHERE session_id = ? ORDER BY id DESC LIMIT 1", session_id)


def consent_current(c: dict | None, s: dict) -> bool:
    """A test not yet started needs consent to the current text; one already being written keeps the consent it began with."""
    return bool(c) and (c["version"] == config.CONSENT_VERSION or s["status"] != "not_started")


def overview(con, user: dict) -> dict:
    s = latest_session(con, user)
    if not s:
        return dict(session=None, join_needed=True, consent=dict(given=False, version_needed=config.CONSENT_VERSION),
                    can_start=False, result_ready=False, retention_days=config.retention_days(),
                    server_now=dt.datetime.now(dt.timezone.utc).isoformat())
    sit, test, n = sitting_and_test(con, s["sitting_id"])
    c = has_consent(con, s["id"])
    now = dt.datetime.now(dt.timezone.utc)
    dl = deadline(s, sit, test)
    can_start = (sit["status"] == "live" and s["status"] != "submitted" and now < db.parse_ts(sit["ends_at"])
                 and (dl is None or now < dl))
    return dict(join_needed=False, session=dict(id=s["id"], status=s["status"], started_at=s["started_at"], submitted_at=s["submitted_at"],
                             deadline=dl.isoformat() if dl else None, reopened=bool(s.get("rule_history"))),
                sitting=dict(id=sit["id"], title=sit["title"], starts_at=sit["starts_at"], ends_at=sit["ends_at"],
                             status=sit["status"]),
                test=dict(title=test["title"], duration_min=test["duration_min"], n_items=n, kind=test["kind"]),
                consent=dict(given=consent_current(c, s), version_needed=config.CONSENT_VERSION,
                             camera_ok=bool(c and c["camera_ok"]), precheck_share_ok=bool(c and c["precheck_share_ok"])),
                can_start=can_start, result_ready=sit["status"] == "scored",
                retention_days=config.retention_days(), server_now=now.isoformat(), mic=config.MIC_MODE)


def start(con, user: dict, meta: dict) -> dict:
    s = my_session(con, user)
    sit, test, n = sitting_and_test(con, s["sitting_id"])
    if not consent_current(has_consent(con, s["id"]), s):
        raise ApiError(409, "no_consent", "Please read and accept the consent screen first.")
    if s["status"] == "submitted":
        raise ApiError(409, "already_submitted", "This test has already been submitted.")
    if sit["status"] != "live":
        raise ApiError(409, "not_live", "The test has not started yet." if sit["status"] == "scheduled"
                       else "This sitting is closed.")
    now = dt.datetime.now(dt.timezone.utc)
    if now >= db.parse_ts(sit["ends_at"]):
        raise ApiError(409, "window_over", "The time window for this test is over.")
    if s["status"] == "not_started":
        con.execute("""UPDATE sessions SET status = 'in_progress', started_at = ?, device = ?, bandwidth_class = ?,
                       precheck_light = ?, precheck_framing = ? WHERE id = ?""",
                    (db.now(), meta["device"], meta["bandwidth_class"], meta["precheck_light"], meta["precheck_framing"],
                     s["id"]))
        db.audit(con, user["id"], "exam_started", s["id"])
        s = db.one(con, "SELECT * FROM sessions WHERE id = ?", s["id"])
    from . import coding
    items = [coding.problem_payload(con, test["id"], r) if r["kind"] == "code" else
             dict(item=r["position"], kind=r["kind"], text=r["text"], options=json.loads(r["options"]))
             for r in db.all_(con, "SELECT position, kind, text, options FROM items WHERE test_id = ? ORDER BY position",
                              test["id"])]  # correct_option and hidden tests are never sent to the browser
    if test["kind"] != "coding":
        items = shuffled(items, s["id"])                     # every candidate sees their own order (same on resume)
    answers = {r["item"]: r["option"] for r in db.all_(con, """SELECT item, option FROM events WHERE session_id = ? AND type = 'answer'
                                                              ORDER BY seq""", s["id"])}
    dl = deadline(s, sit, test)
    return dict(session_id=s["id"], started_at=s["started_at"], deadline=dl.isoformat(), server_now=now.isoformat(),
                elapsed_s=(now - db.parse_ts(s["started_at"])).total_seconds(), last_seq=s["last_seq"],
                items=items, answers=answers, test_kind=test["kind"], rules=_rule_state(con, s["id"]), mic=config.MIC_MODE,
                code_state=coding.code_state(con, s["id"]) if test["kind"] == "coding" else {})


def _rule_state(con, session_id: str) -> dict:
    """Counts so far (so a refresh or a new login continues them) and the limits the page enforces."""
    from . import rules
    c = rules.counts(con, session_id)
    return dict(phone=c["phone"], multi_face=c["multi_face"], tab_switch=c["tab_switch"],
                limits=dict(phone_warnings=config.PHONE_WARNINGS, multi_face=config.MULTI_FACE_MAX, tab_switch=config.TAB_SWITCH_MAX))


def shuffled(items: list, session_id: str) -> list:
    """The question order for one candidate: a fixed shuffle seeded by the session, so a refresh or a new login shows
    the same order. Questions keep their numbers inside the system (answers, scoring, review), only the order changes."""
    import hashlib
    import random
    out = list(items)
    random.Random(int(hashlib.sha256(session_id.encode()).hexdigest()[:16], 16)).shuffle(out)
    return out


def ingest(con, user: dict, batch) -> dict:
    """Idempotent: a batch sent twice (2G retries) is stored once, keyed by (session_id, seq)."""
    s = my_session(con, user)
    sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", s["sitting_id"])
    if s["status"] == "not_started":
        raise ApiError(409, "not_started", "Start the test first.")
    if sit["status"] in ("scoring", "scored"):
        raise ApiError(409, "sitting_closed", "This sitting is closed; late data was not accepted.")
    key = {r["position"]: (r["correct_option"], set(json.loads(r["options"])), r["kind"]) for r in
           db.all_(con, "SELECT position, correct_option, options, kind FROM items WHERE test_id = ?", sit["test_id"])}
    saved = dup = rejected = 0
    for e in batch.events:
        if e.type not in config.EVENT_TYPES or (e.item != -1 and e.item not in key):
            rejected += 1
            continue
        correct, option = -1, ""
        if e.type == "answer":
            if e.item not in key:
                rejected += 1
                continue
            right, opts, kind = key[e.item]
            if kind == "short":                      # typed answer: compared without spaces or case
                option = e.option.strip()[:40]
                correct = int(_norm(option) == _norm(right))
            elif e.option.upper() in opts:
                option = e.option.upper()
                correct = int(option == right)
            else:
                rejected += 1
                continue
        if e.type in ("code_typing", "code_run", "code_submit", "mic_off"):
            option = e.option[:40]
        cur = con.execute("""INSERT INTO events (session_id, seq, t, type, item, option, correct, chars, meta)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                          (s["id"], e.seq, e.t, e.type, e.item, option, correct, e.chars if e.type == "paste" else 0,
                           json.dumps(e.meta) if e.meta else None))
        saved += cur.rowcount
        dup += 1 - cur.rowcount
    for f in batch.frames:
        cur = con.execute("""INSERT INTO frame_stats (session_id, seq, t, faces, face_visible, gaze, brightness, blur, phone)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING""",
                          (s["id"], f.seq, f.t, f.faces, int(f.face_visible), f.gaze if f.gaze in config.GAZE else "unknown",
                           f.brightness, f.blur, f.phone))
        saved += cur.rowcount
        dup += 1 - cur.rowcount
    top = max([e.seq for e in batch.events] + [f.seq for f in batch.frames] + [s["last_seq"]])
    con.execute("UPDATE sessions SET last_seq = ? WHERE id = ?", (top, s["id"]))
    out = dict(saved=saved, duplicates=dup, rejected=rejected, saved_upto=top)
    if any(e.type in ("phone_seen", "multi_face", "focus_lost") for e in batch.events):
        from . import rules
        reason = rules.enforce(con, db.one(con, "SELECT * FROM sessions WHERE id = ?", s["id"]))
        if reason:
            out["terminated"] = reason                       # also when the device did not end it itself
    return out


def _norm(v: str) -> str:
    v = "".join(str(v).lower().split())
    try:
        return repr(float(v))                         # "12", "12.0" and "12.00" are the same answer
    except ValueError:
        return v


def submit(con, user: dict) -> dict:
    s = my_session(con, user)
    if s["status"] == "submitted":
        return dict(status="submitted", submitted_at=s["submitted_at"], already=True)
    if s["status"] == "not_started":
        raise ApiError(409, "not_started", "The test was never started.")
    con.execute("UPDATE sessions SET status = 'submitted', submitted_at = ? WHERE id = ?", (db.now(), s["id"]))
    db.audit(con, user["id"], "exam_submitted", s["id"])
    return dict(status="submitted", submitted_at=db.now())


def candidate_state(con, session_id: str) -> tuple[str, dict | None, dict | None, dict | None]:
    sc = db.one(con, "SELECT * FROM scores WHERE session_id = ?", session_id)
    rv = db.one(con, "SELECT * FROM reviews WHERE session_id = ? ORDER BY id DESC LIMIT 1", session_id)
    ap = db.one(con, "SELECT * FROM appeals WHERE session_id = ?", session_id)
    if not sc:
        return "pending", sc, rv, ap
    if ap and ap["status"] == "decided":
        return ("cleared_after_appeal" if ap["outcome"] == "overturned" else "confirmed"), sc, rv, ap
    if rv and rv["decision"] == "clear":
        return "cleared_after_review", sc, rv, ap
    if rv and rv["decision"] == "confirm":
        return "confirmed", sc, rv, ap
    return ("clear" if sc["band"] == "clear" else "under_review"), sc, rv, ap


MESSAGES = {
    "pending": "Your test is submitted. Results will appear here after the sitting is checked.",
    "clear": "Your test was checked and no issues were found.",
    "under_review": "A few moments of your test are being looked at again by a person. This is not a finding of malpractice.",
    "cleared_after_review": "A reviewer looked at your test and found no malpractice.",
    "confirmed": "A reviewer found that some moments of your test did not follow the test rules.",
    "cleared_after_appeal": "Thank you for your explanation. The reviewer accepted it and your test is cleared.",
}


def result(con, user: dict) -> dict:
    s = my_session(con, user)
    state, sc, rv, ap = candidate_state(con, s["id"])
    out = dict(state=state, message=MESSAGES[state], retention_days=config.retention_days(),
               can_appeal=False, appeal=None)
    sit, test, _ = sitting_and_test(con, s["sitting_id"])
    out["test_kind"] = test["kind"]
    if s.get("terminated_reason"):
        from .rules import REASONS
        out["terminated"] = dict(reason=s["terminated_reason"], text=REASONS.get(s["terminated_reason"], ""), at=s["terminated_at"])
    if test["kind"] == "coding":
        from .coding import marks
        out["coding"] = marks(con, s["id"], test["id"])
    if sc:
        e = json.loads(sc["explanation"])
        cand = e.get("candidate", {})
        out["not_counted"] = e.get("context", [])            # what was discounted (2G, people passing, phone held low)
        if state != "clear":
            out["summary"] = cand.get("summary")
            out["points"] = cand.get("points", [])          # title, text, when (mm:ss), questions; no other candidate's id
        if rv and rv["decision"] == "confirm" and rv["note"]:
            out["reviewer_note"] = rv["note"]
        open_since = db.parse_ts((rv or {}).get("at") or sc["scored_at"])
        out["can_appeal"] = (state in ("under_review", "confirmed") and not ap and
                             dt.datetime.now(dt.timezone.utc) - open_since < dt.timedelta(days=config.APPEAL_DAYS))
    if ap:
        out["appeal"] = dict(text=ap["text"], status=ap["status"], outcome=ap["outcome"], response=ap["response"],
                             at=ap["at"], decided_at=ap["decided_at"])
    return out


def appeal(con, user: dict, body) -> dict:
    s = my_session(con, user)
    r = result(con, user)
    if not r["can_appeal"]:
        raise ApiError(409, "cannot_appeal", "An appeal is not open for this test (already sent, cleared, or past 7 days).")
    con.execute("INSERT INTO appeals (session_id, text, moments) VALUES (?, ?, ?)",
                (s["id"], body.text, json.dumps(body.moments)))
    db.audit(con, user["id"], "appeal_sent", s["id"])
    return dict(ok=True, message="Your explanation has been sent to the reviewer with your test record.")

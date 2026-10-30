"""Reviewer API: ranked queue, session detail with evidence, decisions, appeals."""
import datetime as dt
import json
import re

from fastapi import APIRouter, Depends, Query

from .. import db
from ..http import ApiError, require
from ..schemas import AppealDecisionIn, DecisionIn, ReinstateIn
from ..services.exam import candidate_state

router = APIRouter(prefix="/api/review", tags=["reviewer"])
REV = Depends(require("reviewer", "admin"))
BANDS = ("review_first", "review", "clear")


def pseudonym(sid: str) -> str:
    from fairproctor.display import pseudonym as p
    return p(sid)


SESSION_ID = re.compile(r"\b(?:[RC]\d+-S\d{5}|L-[0-9A-F]{10})\b")


def mask_ids(text: str, keep: str = "") -> str:
    """Any other session's id in free text becomes that candidate's pseudonym (ids could be traced to people)."""
    return SESSION_ID.sub(lambda m: m.group(0) if m.group(0) == keep else pseudonym(m.group(0)), text)


def masked(explanation_json: str) -> dict:
    """Explanation with every other session id (partners, closest matches) replaced by a pseudonym."""
    raw = json.loads(explanation_json)
    partners, own = raw.get("partners", []), raw.get("session_id", "")
    e = json.loads(mask_ids(explanation_json, keep=own))
    e["partners"] = [dict(session_id=p, pseudonym=pseudonym(p)) for p in partners]
    return e


def _status(con, sid, band):
    _, _, rv, ap = candidate_state(con, sid)
    if ap and ap["status"] == "open":
        return "appeal_open"
    if rv:
        return {"confirm": "confirmed", "clear": "cleared", "need_more": "need_more"}[rv["decision"]]
    return "auto_cleared" if band == "clear" else "new"


def _review_first_line():
    from ..services.scoring import model_bundle
    return model_bundle()["priority"].review_first_line


@router.get("/live", summary="Sittings that are being written right now")
def live_sittings(me: dict = REV):
    with db.tx() as con:
        rows = db.all_(con, """SELECT s.id, s.title, s.status, s.starts_at, s.ends_at,
                                      (SELECT COUNT(*) FROM sessions x WHERE x.sitting_id = s.id AND x.is_synthetic = 0
                                       AND x.status = 'in_progress') writing,
                                      (SELECT COUNT(*) FROM sessions x WHERE x.sitting_id = s.id AND x.is_synthetic = 0
                                       AND x.status = 'submitted') submitted
                               FROM sittings s WHERE s.status = 'live' ORDER BY s.starts_at""")
    return rows


@router.get("/live/{sitting_id}", summary="Live monitor: trained model on partial answers (every 45 s) + raw alerts")
def live_monitor(sitting_id: int, me: dict = REV):
    from ..services.live import snapshot
    out = snapshot(sitting_id, show_names=me["role"] == "admin")
    if not out:
        raise ApiError(404, "not_found", "Sitting not found.")
    return out


@router.get("/exams", summary="Every exam (sitting) with its flagged sessions, review progress, reasons, appeals and snapshots")
def exams(me: dict = REV):
    with db.tx() as con:
        sits = db.all_(con, """SELECT s.id, s.title, s.status, s.starts_at, s.ends_at, s.scored_at, t.title test_title, t.kind
                               FROM sittings s JOIN tests t ON t.id = s.test_id ORDER BY s.starts_at DESC, s.id DESC""")
        out = []
        for st in sits:
            sid = st["id"]
            n = db.one(con, """SELECT COUNT(*) n, SUM(CASE WHEN status = 'submitted' THEN 1 ELSE 0 END) submitted,
                                      SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) writing
                               FROM sessions WHERE sitting_id = ? AND is_synthetic = 0""", sid)
            ref = db.one(con, "SELECT COUNT(*) n FROM sessions WHERE sitting_id = ? AND is_synthetic = 1", sid)["n"]
            scored = db.all_(con, "SELECT session_id, band, families FROM scores WHERE sitting_id = ?", sid)
            bands = {b: sum(1 for r in scored if r["band"] == b) for b in BANDS}
            flagged = [r for r in scored if r["band"] != "clear"]
            reasons: dict[str, int] = {}
            for r in flagged:
                for f in json.loads(r["families"] or "[]"):
                    reasons[f] = reasons.get(f, 0) + 1
            decided = db.one(con, """SELECT COUNT(DISTINCT r.session_id) n FROM reviews r JOIN scores c ON c.session_id = r.session_id
                                     WHERE c.sitting_id = ? AND c.band <> 'clear'""", sid)["n"]
            confirmed = db.one(con, """SELECT COUNT(*) n FROM scores c WHERE c.sitting_id = ? AND (SELECT decision FROM reviews r
                                       WHERE r.session_id = c.session_id ORDER BY r.id DESC LIMIT 1) = 'confirm'""", sid)["n"]
            appeals_open = db.one(con, """SELECT COUNT(*) n FROM appeals a JOIN sessions x ON x.id = a.session_id
                                          WHERE x.sitting_id = ? AND a.status = 'open'""", sid)["n"]
            snaps = db.one(con, """SELECT COUNT(*) n, COUNT(DISTINCT p.session_id) sessions FROM snapshots p
                                   JOIN sessions x ON x.id = p.session_id WHERE x.sitting_id = ?""", sid)
            out.append(dict(id=sid, title=st["title"], test_title=st["test_title"], kind=st["kind"], status=st["status"],
                            starts_at=st["starts_at"], ends_at=st["ends_at"], scored_at=st["scored_at"],
                            candidates=n["n"] or 0, submitted=n["submitted"] or 0, writing=n["writing"] or 0, reference=ref,
                            bands=bands, flagged=len(flagged), reviewed=decided, confirmed=confirmed,
                            reasons=dict(sorted(reasons.items(), key=lambda kv: -kv[1])), open_appeals=appeals_open,
                            snapshots=snaps["n"], snapshot_sessions=snaps["sessions"]))
    return out


@router.get("/queue", summary="Sessions ranked by review priority (0-100; 50 = review line). Not a probability.")
def queue(band: str = "queue", family: str = "", q: str = "", sitting_id: int | None = None,
          bandwidth: str | None = None, include_reference: int = 1,
          limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0), me: dict = REV):
    where, args = ["1 = 1"], []
    if sitting_id:
        where.append("c.sitting_id = ?")
        args.append(sitting_id)
    if band == "queue":
        where.append("c.band <> 'clear'")
    elif band in BANDS:
        where.append("c.band = ?")
        args.append(band)
    if family:
        where.append("c.families LIKE ?")
        args.append(f'%"{family}"%')
    if bandwidth in ("low", "normal"):
        where.append("x.bandwidth_class = ?")
        args.append(bandwidth)
    if not include_reference:
        where.append("x.is_synthetic = 0")
    q = q.strip().upper()
    with db.tx() as con:
        rows = db.all_(con, f"""SELECT c.session_id, c.sitting_id, c.priority, c.band, c.rank, c.families, c.explanation,
                                       x.bandwidth_class, x.device, x.is_synthetic, x.submitted_at, u.roll_no
                                FROM scores c JOIN sessions x ON x.id = c.session_id LEFT JOIN users u ON u.id = x.user_id
                                WHERE {' AND '.join(where)} ORDER BY c.priority DESC, c.rank""", *args)
        if q:
            rows = [r for r in rows if q in r["session_id"].upper() or q in (r["roll_no"] or "").upper()
                    or q in pseudonym(r["session_id"]).upper()]
        counts = {r["band"]: r["n"] for r in db.all_(
            con, "SELECT band, COUNT(*) n FROM scores" + (" WHERE sitting_id = ?" if sitting_id else "") + " GROUP BY band",
            *([sitting_id] if sitting_id else []))}
        open_appeals = db.one(con, "SELECT COUNT(*) n FROM appeals WHERE status = 'open'")["n"]
        out = [dict(session_id=r["session_id"], pseudonym=pseudonym(r["session_id"]), sitting_id=r["sitting_id"],
                    priority=r["priority"], band=r["band"], rank=r["rank"], families=json.loads(r["families"]),
                    headline=masked(r["explanation"])["headline"], status=_status(con, r["session_id"], r["band"]),
                    bandwidth=r["bandwidth_class"], device=r["device"], reference=bool(r["is_synthetic"]),
                    submitted_at=r["submitted_at"]) for r in rows[offset:offset + limit]]
    lines = dict(review=50, review_first=_review_first_line()) if rows or counts else dict(review=50, review_first=None)
    return dict(total=len(rows), counts=counts, open_appeals=open_appeals, rows=out, priority_lines=lines)


@router.get("/sessions/{session_id}", summary="Evidence for one session (other candidates only as pseudonyms)")
def session_detail(session_id: str, me: dict = REV):
    sid = session_id
    with db.tx() as con:
        x = db.one(con, "SELECT * FROM sessions WHERE id = ?", sid)
        sc = db.one(con, "SELECT * FROM scores WHERE session_id = ?", sid)
        if not x or not sc:
            raise ApiError(404, "not_found", "No scored session with this id.")
        e = masked(sc["explanation"])
        events = db.all_(con, "SELECT seq, t, type, item, option, correct, chars, meta FROM events WHERE session_id = ? ORDER BY t, seq", sid)
        for ev_ in events:
            ev_["meta"] = json.loads(ev_["meta"]) if ev_.get("meta") else None
        kind = db.one(con, """SELECT t.kind FROM sittings s JOIN tests t ON t.id = s.test_id WHERE s.id = ?""", x["sitting_id"])["kind"]
        code = []
        if kind == "coding":
            from ..services.coding_score import session_code
            code = session_code(con, sid, json.loads(sc["explanation"]))   # real ids to find the partner's program;
                                                                            # the page shows the partner by pseudonym
            runs = db.all_(con, "SELECT item, kind, verdict, passed, total, COALESCE(t, 0) t FROM code_runs WHERE session_id = ? ORDER BY id", sid)
        else:
            runs = []
        frames = db.all_(con, "SELECT t, faces, face_visible, gaze, phone FROM frame_stats WHERE session_id = ? ORDER BY t", sid)
        from ..services import rules as _rules
        rc = _rules.counts(con, sid)
        rules_out = dict(counts=rc, flags=_rules.flags(rc))
        reviews = db.all_(con, """SELECT r.decision, r.note, r.at, u.name reviewer FROM reviews r
                                  LEFT JOIN users u ON u.id = r.reviewer_id WHERE r.session_id = ? ORDER BY r.id""", sid)
        appeal = db.one(con, "SELECT * FROM appeals WHERE session_id = ?", sid)
        con.execute("""INSERT INTO session_views (session_id, reviewer_id, at) VALUES (?, ?, ?)
                       ON CONFLICT (session_id, reviewer_id) DO UPDATE SET at = excluded.at""", (sid, me["id"], db.now()))
        cutoff = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        others = db.all_(con, """SELECT u.name FROM session_views v JOIN users u ON u.id = v.reviewer_id
                                 WHERE v.session_id = ? AND v.reviewer_id <> ? AND v.at > ?""", sid, me["id"], cutoff)
        identity = None
        if reviews and reviews[-1]["decision"] == "confirm" and x["user_id"]:   # real identity only after a confirmation
            identity = db.one(con, "SELECT name, roll_no, email FROM users WHERE id = ?", x["user_id"])
        sit = db.one(con, "SELECT id, title FROM sittings WHERE id = ?", x["sitting_id"])
    if appeal:
        appeal["moments"] = json.loads(appeal["moments"])
    return dict(session_id=sid, pseudonym=pseudonym(sid), identity=identity, sitting=sit,
                meta=dict(device=x["device"], bandwidth_class=x["bandwidth_class"], precheck_light=x["precheck_light"],
                          precheck_framing=x["precheck_framing"], reference=bool(x["is_synthetic"]),
                          started_at=x["started_at"], submitted_at=x["submitted_at"]),
                score=dict(priority=sc["priority"], band=sc["band"], rank=sc["rank"], model_version=sc["model_version"],
                           scored_at=sc["scored_at"]),
                explanation=e, events=events, frames=frames, reviews=reviews, appeal=appeal, rules=rules_out,
                also_viewing=[o["name"] for o in others], kind=kind, code=code, runs=runs,
                priority_lines=dict(review=50, review_first=_review_first_line()))


@router.get("/sessions/{session_id}/snapshots", summary="Camera snapshots at flagged moments (every view is audited)")
def session_snapshots(session_id: str, me: dict = REV):
    from .. import config
    from ..services import snapshots
    with db.tx() as con:
        if not db.one(con, "SELECT 1 FROM sessions WHERE id = ?", session_id):
            raise ApiError(404, "not_found", "No session with this id.")
        rows = snapshots.listing(con, session_id)
        if rows:
            db.audit(con, me["id"], "snapshots_viewed", session_id, n=len(rows))
    return dict(days=config.snapshot_days(), snapshots=rows)


@router.post("/sessions/{session_id}/reinstate", summary="Reopen a test a proctoring rule ended (while the sitting is open); time is given back")
def reinstate(session_id: str, b: ReinstateIn, me: dict = REV):
    from ..services import rules
    with db.tx() as con:
        return rules.reinstate(con, session_id, me, b.note.strip())


@router.post("/sessions/{session_id}/decision", status_code=201)
def decide(session_id: str, b: DecisionIn, me: dict = REV):
    if b.decision == "confirm" and len(b.note) < 10:
        raise ApiError(422, "note_needed", "Please write a short note (what you saw) before confirming.")
    with db.tx() as con:
        if not db.one(con, "SELECT 1 FROM scores WHERE session_id = ?", session_id):
            raise ApiError(404, "not_found", "No scored session with this id.")
        con.execute("INSERT INTO reviews (session_id, reviewer_id, decision, note) VALUES (?, ?, ?, ?)",
                    (session_id, me["id"], b.decision, b.note))
        db.audit(con, me["id"], "review_" + b.decision, session_id)
    return dict(ok=True, decision=b.decision)


@router.get("/appeals")
def appeals(status: str = "open", me: dict = REV):
    with db.tx() as con:
        rows = db.all_(con, """SELECT a.*, c.band, c.priority FROM appeals a LEFT JOIN scores c ON c.session_id = a.session_id
                               WHERE a.status = ? ORDER BY a.id""", status)
    return [dict(r, moments=json.loads(r["moments"]), pseudonym=pseudonym(r["session_id"])) for r in rows]


@router.post("/appeals/{appeal_id}/decide")
def decide_appeal(appeal_id: int, b: AppealDecisionIn, me: dict = REV):
    with db.tx() as con:
        a = db.one(con, "SELECT * FROM appeals WHERE id = ?", appeal_id)
        if not a:
            raise ApiError(404, "not_found", "Appeal not found.")
        if a["status"] != "open":
            raise ApiError(409, "already_decided", "This appeal already has a decision.")
        con.execute("""UPDATE appeals SET status = 'decided', outcome = ?, response = ?, reviewer_id = ?, decided_at = ?
                       WHERE id = ?""", (b.outcome, b.response, me["id"], db.now(), appeal_id))
        db.audit(con, me["id"], "appeal_" + b.outcome, a["session_id"])
    return dict(ok=True)

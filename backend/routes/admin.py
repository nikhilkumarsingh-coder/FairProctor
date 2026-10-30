"""Admin API: staff users, tests, questions, sittings, candidates, live view, close & score, deletion."""
import json

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from .. import db
from ..http import ApiError, csv_body, require
from ..jobs import worker
from ..schemas import ProblemSetIn, SebIn, SittingIn, TestIn, UserIn
from ..security import hash_secret, new_login_code
from ..services import admin as svc
from ..services import privacy

router = APIRouter(prefix="/api/admin", tags=["admin"])
ADMIN = Depends(require("admin"))
CSV_DOC = {"requestBody": {"content": {"text/csv": {"schema": {"type": "string"}}}, "required": True}}


def _get(con, table, id_, what):
    row = db.one(con, f"SELECT * FROM {table} WHERE id = ?", id_)
    if not row:
        raise ApiError(404, "not_found", f"{what} not found.")
    return row


# ---------------------------------------------------------------- staff users
@router.post("/users", status_code=201, summary="Create an admin or reviewer account")
def create_user(b: UserIn, me: dict = ADMIN):
    with db.tx() as con:
        if db.one(con, "SELECT 1 FROM users WHERE lower(email) = lower(?)", b.email):
            raise ApiError(409, "email_taken", "A user with this email already exists.")
        uid = con.insert("INSERT INTO users (role, name, email, secret_hash) VALUES (?, ?, ?, ?)",
                         (b.role, b.name, b.email, hash_secret(b.password)))
        db.audit(con, me["id"], "user_created", uid, role=b.role)
    return dict(id=uid)


@router.get("/users", summary="All accounts (no passwords)")
def list_users(role: str | None = None, me: dict = ADMIN):
    with db.tx() as con:
        sql = "SELECT id, role, name, email, roll_no, sitting_id, language, created_at FROM users"
        return db.all_(con, sql + (" WHERE role = ? ORDER BY id" if role else " ORDER BY id"), *([role] if role else []))


# ---------------------------------------------------------------- tests and questions
@router.get("/tests")
def list_tests(me: dict = ADMIN):
    with db.tx() as con:
        return db.all_(con, """SELECT t.*, (SELECT COUNT(*) FROM items i WHERE i.test_id = t.id) n_items
                               FROM tests t ORDER BY t.id DESC""")


@router.post("/tests", status_code=201)
def create_test(b: TestIn, me: dict = ADMIN):
    with db.tx() as con:
        tid = con.insert("INSERT INTO tests (title, duration_min, created_by, kind) VALUES (?, ?, ?, ?)",
                         (b.title, b.duration_min, me["id"], b.kind))
        db.audit(con, me["id"], "test_created", tid, kind=b.kind)
    return dict(id=tid)


@router.get("/tests/{test_id}")
def test_detail(test_id: int, me: dict = ADMIN):
    with db.tx() as con:
        t = _get(con, "tests", test_id, "Test")
        if t["kind"] == "coding":
            from ..services.coding import admin_problems
            t["items"], t["problems"] = [], admin_problems(con, test_id)
        else:
            t["items"] = [dict(r, options=json.loads(r["options"])) for r in
                          db.all_(con, "SELECT * FROM items WHERE test_id = ? ORDER BY position", test_id)]
    return t


@router.post("/tests/{test_id}/problems", summary="Replace the problems of a coding test (JSON); reference solutions are run first")
def upload_problems(test_id: int, b: ProblemSetIn, me: dict = ADMIN):
    from ..services import coding
    with db.tx() as con:
        t = _get(con, "tests", test_id, "Test")
        if t["kind"] != "coding":
            raise ApiError(409, "not_coding", "This is a question test. Upload questions as CSV, or create a coding test.")
    bad = coding.check_solutions(b.problems)            # slow (compiles and runs), so outside the transaction
    if bad:
        raise ApiError(400, "bad_rows", f"{len(bad)} problem(s) need fixing.", rows=bad)
    with db.tx() as con:
        n = coding.replace_problems(con, test_id, b.problems)
        db.audit(con, me["id"], "problems_uploaded", test_id, n=n)
    return dict(n_items=n, checked=sum(1 for p in b.problems if p.solution))


@router.post("/tests/{test_id}/items", openapi_extra=CSV_DOC,
             summary="Replace all questions (CSV: text, option_a..option_d, correct, [difficulty], [kind])")
async def upload_items(test_id: int, request: Request, me: dict = ADMIN):
    items = svc.parse_items_csv(await csv_body(request))

    def work():
        with db.tx() as con:
            if _get(con, "tests", test_id, "Test")["kind"] == "coding":
                raise ApiError(409, "coding_test", "This is a coding test: upload its problems as JSON.")
            n = svc.replace_items(con, test_id, items)
            db.audit(con, me["id"], "items_uploaded", test_id, n=n)
        return dict(n_items=n)
    return await run_in_threadpool(work)


# ---------------------------------------------------------------- sittings
@router.get("/sittings")
def list_sittings(me: dict = ADMIN):
    with db.tx() as con:
        rows = db.all_(con, """SELECT s.*, t.title test_title,
                                      (SELECT COUNT(*) FROM sessions x WHERE x.sitting_id = s.id AND x.is_synthetic = 0) n_candidates
                               FROM sittings s JOIN tests t ON t.id = s.test_id ORDER BY s.id DESC""")
    for r in rows:
        r["seb_required"] = bool(r.get("seb_required"))
        for k in ("seb_file", "seb_config_key", "seb_token"):
            r.pop(k, None)
    return rows


@router.post("/sittings", status_code=201, summary="Create a sitting; candidates join with its join_code")
def create_sitting(b: SittingIn, me: dict = ADMIN):
    s0, s1 = db.parse_ts(b.starts_at), db.parse_ts(b.ends_at)
    if not s0 or not s1 or s1 <= s0:
        raise ApiError(422, "bad_time", "ends_at must be after starts_at (ISO 8601 with time zone).")
    with db.tx() as con:
        t = _get(con, "tests", b.test_id, "Test")
        if not db.one(con, "SELECT 1 FROM items WHERE test_id = ?", t["id"]):
            raise ApiError(409, "no_questions", "Upload questions to the test first.")
        sid = svc.create_sitting(con, b.test_id, b.title, s0.isoformat(), s1.isoformat())
        db.audit(con, me["id"], "sitting_created", sid)
        code = db.one(con, "SELECT join_code FROM sittings WHERE id = ?", sid)["join_code"]
    return dict(id=sid, join_code=code)


@router.get("/sittings/{sitting_id}")
def sitting_detail(sitting_id: int, me: dict = ADMIN):
    with db.tx() as con:
        s = _get(con, "sittings", sitting_id, "Sitting")
        s["live"] = svc.sitting_live(con, sitting_id)
        s["candidates"] = db.all_(con, """SELECT u.id user_id, u.roll_no, u.email, u.name, x.id session_id, x.status,
                                                 x.started_at, x.submitted_at, x.device, x.bandwidth_class
                                          FROM sessions x JOIN users u ON u.id = x.user_id
                                          WHERE x.sitting_id = ? ORDER BY u.roll_no, u.name""", sitting_id)
        s["jobs"] = db.all_(con, "SELECT * FROM jobs WHERE target = ? AND kind = 'score_sitting' ORDER BY id DESC LIMIT 5",
                            str(sitting_id))
    from ..services.seb import summary
    s["seb"] = summary(s)
    for k in ("seb_file", "seb_config_key", "seb_token", "seb_required"):
        s.pop(k, None)
    return s


@router.put("/sittings/{sitting_id}/seb", summary="Require Safe Exam Browser for this sitting (laptop/iPad only), with its Config Key and .seb file")
def sitting_seb(sitting_id: int, b: SebIn, me: dict = ADMIN):
    from ..services import seb
    with db.tx() as con:
        out = seb.configure(con, sitting_id, b.required, b.config_key, b.file_base64, b.clear_file)
        db.audit(con, me["id"], "seb_configured", sitting_id, required=b.required, file=out["file_uploaded"])
    return out


@router.get("/sittings/{sitting_id}/fairness",
            summary="Fairness report: share of each group sent to review, FairProctor vs the old rules at the same workload")
def sitting_fairness(sitting_id: int, me: dict = ADMIN):
    from ..services.fairness import report
    with db.tx() as con:
        return report(con, sitting_id)


@router.post("/sittings/{sitting_id}/candidates", status_code=201, openapi_extra=CSV_DOC,
             summary="Import candidates (CSV: roll_no, name, [language]); login codes are returned ONCE")
async def upload_candidates(sitting_id: int, request: Request, me: dict = ADMIN):
    cands = svc.parse_candidates_csv(await csv_body(request))

    def work():
        with db.tx() as con:
            s = _get(con, "sittings", sitting_id, "Sitting")
            if s["status"] not in ("scheduled", "live"):
                raise ApiError(409, "sitting_closed", "This sitting is already closed.")
            rows = svc.add_candidates(con, sitting_id, cands)
            db.audit(con, me["id"], "candidates_added", sitting_id, n=len(rows))
        return rows
    rows = await run_in_threadpool(work)
    if "text/csv" in request.headers.get("accept", ""):
        return Response(svc.codes_csv(rows), media_type="text/csv", status_code=201,
                        headers={"Content-Disposition": f'attachment; filename="sitting-{sitting_id}-codes.csv"'})
    return dict(n=len(rows), candidates=rows, csv=svc.codes_csv(rows),
                note="Save these codes now. Only a hash is stored, so they cannot be shown again.")


@router.post("/candidates/{user_id}/reset-code")
def reset_code(user_id: int, me: dict = ADMIN):
    code = new_login_code()
    with db.tx() as con:
        u = _get(con, "users", user_id, "Candidate")
        if u["role"] != "candidate" or not u["roll_no"]:
            raise ApiError(400, "not_imported", "Only imported candidates (roll no. + code) have a login code.")
        con.execute("""UPDATE users SET secret_hash = ?, failed_logins = 0, locked_until = NULL, password_changed_at = ?,
                       token_version = token_version + 1 WHERE id = ?""", (hash_secret(code), db.now(), user_id))
        db.audit(con, me["id"], "code_reset", user_id)
    return dict(roll_no=u["roll_no"], code=code)


@router.post("/sittings/{sitting_id}/open")
def open_sitting(sitting_id: int, me: dict = ADMIN):
    with db.tx() as con:
        s = _get(con, "sittings", sitting_id, "Sitting")
        if s["status"] != "scheduled":
            raise ApiError(409, "bad_state", f"Sitting is {s['status']}.")
        con.execute("UPDATE sittings SET status = 'live' WHERE id = ?", (sitting_id,))
        db.audit(con, me["id"], "sitting_opened", sitting_id)
    return dict(status="live")


@router.post("/sittings/{sitting_id}/close", status_code=202,
             summary="Auto-submit, close and score the whole sitting (background job)")
def close_sitting(sitting_id: int, me: dict = ADMIN):
    with db.tx() as con:
        s = _get(con, "sittings", sitting_id, "Sitting")
        if s["status"] == "scored":
            raise ApiError(409, "already_scored", "This sitting has already been closed and scored.")
        if s["status"] == "scoring":                       # retry only when the last scoring run failed or died
            last = db.one(con, "SELECT status FROM jobs WHERE kind = 'score_sitting' AND target = ? ORDER BY id DESC LIMIT 1",
                          str(sitting_id))
            if last and last["status"] in ("queued", "running"):
                raise ApiError(409, "already_scoring", "This sitting is being scored right now.")
        n_auto = con.execute("""UPDATE sessions SET status = 'submitted', submitted_at = ?
                                WHERE sitting_id = ? AND status = 'in_progress'""", (db.now(), sitting_id)).rowcount
        con.execute("UPDATE sittings SET status = 'scoring', closed_at = ? WHERE id = ?", (db.now(), sitting_id))
        job = worker.enqueue(con, "score_sitting", sitting_id)
        db.audit(con, me["id"], "sitting_closed", sitting_id, auto_submitted=n_auto, job=job)
    return dict(job_id=job, auto_submitted=n_auto)


@router.get("/jobs/{job_id}")
def job_status(job_id: int, me: dict = ADMIN):
    with db.tx() as con:
        return _get(con, "jobs", job_id, "Job")


# ---------------------------------------------------------------- privacy
@router.get("/deletion-requests")
def deletion_requests(me: dict = ADMIN):
    with db.tx() as con:
        return db.all_(con, """SELECT d.*, u.roll_no, u.name, u.email FROM deletion_requests d
                               JOIN sessions s ON s.id = d.session_id LEFT JOIN users u ON u.id = s.user_id
                               WHERE d.status = 'open' ORDER BY d.id""")


@router.delete("/sessions/{session_id}", summary="Delete a session's data (and the candidate account if it was their last)")
def delete_session(session_id: str, me: dict = ADMIN):
    with db.tx() as con:
        existed = privacy.delete_session(con, session_id, actor_id=me["id"], reason="admin")
    if not existed:
        raise ApiError(404, "not_found", "Session not found.")
    return dict(deleted=True)


@router.get("/audit")
def audit_log(limit: int = Query(100, ge=1, le=1000), me: dict = ADMIN):
    with db.tx() as con:
        rows = db.all_(con, "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", limit)
    return [dict(r, detail=json.loads(r["detail"])) for r in rows]

"""Candidate API: overview, join, consent, pre-check numbers, start/resume, event batches, submit, result, appeal."""
import json
import secrets

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from .. import config, db
from ..http import ApiError, require
from ..schemas import AppealIn, CodeRunIn, CodeSubmitIn, ConsentIn, EventBatchIn, JoinIn, PrecheckIn, SnapshotIn, StartIn
from ..services import exam as svc

router = APIRouter(prefix="/api/exam", tags=["candidate"])
probe = APIRouter(prefix="/api/precheck", tags=["candidate"])
seb_files = APIRouter(prefix="/api/seb", tags=["candidate"])


@seb_files.get("/{token}.seb", summary="The sitting's Safe Exam Browser configuration file (opened by SEB itself, so no login)")
def seb_file(token: str):
    import base64
    with db.tx() as con:
        sit = db.one(con, "SELECT seb_file FROM sittings WHERE seb_token = ? AND seb_file IS NOT NULL", token)
    if not sit:
        raise ApiError(404, "not_found", "No Safe Exam Browser file here.")
    return Response(base64.b64decode(sit["seb_file"]), media_type="application/seb",
                    headers={"Content-Disposition": 'attachment; filename="fairproctor-exam.seb"', "Cache-Control": "no-store"})
code = APIRouter(prefix="/api/code", tags=["coding"])
CAND = Depends(require("candidate"))


@router.get("/me", summary="The candidate's current test, consent and what they can do next")
def me(request: Request, user: dict = CAND):
    from ..services import seb
    with db.tx() as con:
        out = svc.overview(con, user)
        s = svc.latest_session(con, user)
        if s:
            out["seb"] = seb.info(db.one(con, "SELECT * FROM sittings WHERE id = ?", s["sitting_id"]), request)
        out["kiosk"] = config.KIOSK and not seb.in_seb(request)
        return out


def _seb(con, request, user):
    from ..services import seb
    seb.guard(con, request, svc.my_session(con, user))


@router.post("/join", summary="Join a sitting with its join code (for candidates who signed up)")
def join(b: JoinIn, user: dict = CAND):
    if not config.allow_signup():
        raise ApiError(410, "signup_disabled", "Your test centre adds you to the test. Log in with their roll no. and code.")
    with db.tx() as con:
        return svc.join(con, user, b.join_code)


@router.post("/consent")
def consent(b: ConsentIn, user: dict = CAND):
    if b.version != config.CONSENT_VERSION:
        raise ApiError(409, "old_consent", "The consent text has changed. Please reload the page.",
                       version_needed=config.CONSENT_VERSION)
    if not b.understood:
        raise ApiError(422, "not_understood", "Please tick that you have read and understood.")
    if not b.camera_ok:                                   # the camera is a condition of taking the test
        raise ApiError(422, "camera_required", "The camera must be on to take this test.")
    with db.tx() as con:
        s = svc.my_session(con, user)
        con.execute("INSERT INTO consents (session_id, version, camera_ok, precheck_share_ok) VALUES (?, ?, ?, ?)",
                    (s["id"], b.version, int(b.camera_ok), int(b.precheck_share_ok)))
        db.audit(con, user["id"], "consent", s["id"], version=b.version, camera_ok=b.camera_ok)
    return dict(ok=True)


@router.post("/precheck", summary="Pre-check numbers (never images); stored only if the candidate allowed it")
def precheck(b: PrecheckIn, user: dict = CAND):
    with db.tx() as con:
        s = svc.my_session(con, user)
        c = svc.has_consent(con, s["id"])
        if not c or not c["precheck_share_ok"]:
            return dict(stored=False)
        con.execute("INSERT INTO precheck_results (session_id, data) VALUES (?, ?)",
                    (s["id"], json.dumps(b.model_dump(exclude_none=True))))
    return dict(stored=True)


@router.post("/start", summary="Start or resume the test; returns questions without answers")
def start(request: Request, b: StartIn | None = None, user: dict = CAND):
    from ..services import device, seb
    b = b or StartIn()
    with db.tx() as con:
        _seb(con, request, user)
        out = svc.start(con, user, b.model_dump(exclude={"signals"}))
        sit = db.one(con, "SELECT seb_required FROM sittings s JOIN sessions x ON x.sitting_id = s.id WHERE x.id = ?", out["session_id"])
        dev = device.record(con, out["session_id"], request, b.signals.model_dump() if b.signals else None,
                            bool(sit and sit["seb_required"]), seb.in_seb(request))
        out["kiosk"] = config.KIOSK and dev["mode"] != "seb"
        return out


@router.post("/events", summary="A batch of events and camera numbers; idempotent by seq")
def events(request: Request, b: EventBatchIn, user: dict = CAND):
    with db.tx() as con:
        _seb(con, request, user)
        return svc.ingest(con, user, b)


@router.post("/code/run", summary="Run code on the sample tests, or once on your own input")
def code_run(request: Request, b: CodeRunIn, user: dict = CAND):
    from ..services import coding
    with db.tx() as con:
        _seb(con, request, user)
    return coding.run(user, b)


@router.post("/code/submit", summary="Judge code on the hidden tests (only pass/fail per test comes back)")
def code_submit(request: Request, b: CodeSubmitIn, user: dict = CAND):
    from ..services import coding
    with db.tx() as con:
        _seb(con, request, user)
    return coding.submit(user, b)


@router.post("/snapshot", summary="A small camera snapshot at a flagged moment (reviewers and the candidate only; not a model input)")
def snapshot(request: Request, b: SnapshotIn, user: dict = CAND):
    from ..services import snapshots
    with db.tx() as con:
        _seb(con, request, user)
        s = svc.my_session(con, user)
        sit = db.one(con, "SELECT * FROM sittings WHERE id = ?", s["sitting_id"])
        return snapshots.store(con, s, sit, b.t, b.reason, b.phase, b.image)


@router.get("/snapshots", summary="The candidate's own snapshots")
def my_snapshots(user: dict = CAND):
    from ..services import snapshots
    with db.tx() as con:
        s = svc.my_session(con, user)
        return dict(days=config.snapshot_days(), snapshots=snapshots.listing(con, s["id"]))


@router.post("/terminate", summary="The device reports that a proctoring limit was passed; the server checks its own counts and ends the test")
def terminate(request: Request, user: dict = CAND):
    from ..services import rules
    with db.tx() as con:
        s = svc.my_session(con, user)
        if s.get("terminated_reason"):
            return dict(status="submitted", terminated=s["terminated_reason"])
        reason = rules.limit_passed(rules.counts(con, s["id"]))
        if not reason:
            raise ApiError(409, "no_limit_passed", "No proctoring limit has been passed.")
        rules.terminate(con, s, reason, user["id"])
        return dict(status="submitted", terminated=reason)


@router.post("/submit")
def submit(request: Request, user: dict = CAND):
    with db.tx() as con:
        _seb(con, request, user)
        return svc.submit(con, user)


@router.get("/result")
def result(user: dict = CAND):
    with db.tx() as con:
        return svc.result(con, user)


@router.post("/appeal", status_code=201)
def appeal(b: AppealIn, user: dict = CAND):
    with db.tx() as con:
        return svc.appeal(con, user, b)


@router.post("/delete-request")
def delete_request(user: dict = CAND):
    with db.tx() as con:
        s = svc.my_session(con, user)
        if not db.one(con, "SELECT 1 FROM deletion_requests WHERE session_id = ? AND status = 'open'", s["id"]):
            con.execute("INSERT INTO deletion_requests (session_id) VALUES (?)", (s["id"],))
            db.audit(con, user["id"], "deletion_requested", s["id"])
    return dict(ok=True, message="Your request is recorded. The test team will delete your data and confirm.")


@code.get("/languages", summary="Programming languages this server can run")
def languages():
    from ..services.runner import languages as langs
    return langs()


@probe.get("/probe", summary="Speed test: download random bytes")
def probe_down(kb: int = Query(200, ge=1, le=2000)):
    return Response(secrets.token_bytes(kb * 1024), media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


@probe.post("/probe", summary="Speed test: upload any bytes")
async def probe_up(request: Request):
    return {"bytes": len(await request.body())}

"""Auth: login (JWT) for the candidate app and the staff app, logout, me. Accounts are made by the admin (candidates,
reviewers) or `python -m backend.scripts.create_admin` (admins); self sign-up is off unless ALLOW_SIGNUP=1."""
import datetime as dt

from fastapi import APIRouter, Depends, Request, Response

from .. import config, db
from ..http import COOKIE, ApiError, current_user, exp_iso
from ..schemas import ChangePasswordIn, DemoCandidateIn, LoginIn, ProfileIn, SignupIn
from ..security import hash_secret, make_jwt, verify_secret

router = APIRouter(prefix="/api", tags=["auth"])


def _issue(user: dict, request: Request, response: Response) -> dict:
    token, jti, exp = make_jwt(user, config.jwt_secret(), config.token_hours())
    # The token is returned for the frontend to send as "Authorization: Bearer <token>".
    # A same-origin HttpOnly cookie is also set, for pages served by this server.
    response.set_cookie(COOKIE, token, max_age=config.token_hours() * 3600, httponly=True,
                        secure=request.url.scheme == "https", samesite="lax", path="/")
    return dict(access_token=token, token_type="bearer", expires_at=exp,
                user=dict(id=user["id"], role=user["role"], name=user["name"], language=user["language"]))


def _locked(u) -> bool:
    lock = db.parse_ts(u["locked_until"])
    return bool(lock and lock > dt.datetime.now(dt.timezone.utc))


@router.post("/auth/signup", status_code=201, summary="Create a candidate account (role: candidate)")
def signup(body: SignupIn, request: Request, response: Response):
    if not config.allow_signup():
        raise ApiError(410, "signup_disabled", "Accounts are created by your test centre. Log in with the roll no. "
                                               "and login code they gave you.")
    with db.tx() as con:
        if db.one(con, "SELECT 1 FROM users WHERE lower(email) = ?", body.email):
            raise ApiError(409, "email_taken", "An account with this email already exists. Please log in.")
        uid = con.insert("INSERT INTO users (role, name, email, secret_hash, language) VALUES ('candidate', ?, ?, ?, ?)",
                         (body.name, body.email, hash_secret(body.password), body.language))
        db.audit(con, uid, "signup")
        user = db.one(con, "SELECT * FROM users WHERE id = ?", uid)
    return _issue(user, request, response)


@router.post("/auth/login", summary="Log in with email + password, or roll no. + login code")
def login(body: LoginIn, request: Request, response: Response):
    with db.tx() as con:
        if body.email:
            cands = db.all_(con, "SELECT * FROM users WHERE lower(email) = lower(?)", body.email)
            secret = body.password
        else:
            cands = db.all_(con, "SELECT * FROM users WHERE roll_no = ? AND role = 'candidate' ORDER BY id DESC",
                            body.roll_no)
            secret = body.code.upper().replace(" ", "")
        if any(_locked(u) for u in cands):
            raise ApiError(429, "locked", f"Too many wrong tries. Try again after {config.LOCK_MINUTES} minutes.")
        user = next((u for u in cands if verify_secret(secret, u["secret_hash"])), None)
        if not user:
            for u in cands:
                n = u["failed_logins"] + 1
                lock = None
                if n >= config.MAX_LOGIN_FAILS:
                    lock = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=config.LOCK_MINUTES)
                            ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    n = 0
                con.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?", (n, lock, u["id"]))
                db.audit(con, u["id"], "login_failed")
        else:
            con.execute("UPDATE users SET failed_logins = 0, locked_until = NULL WHERE id = ?", (user["id"],))
            db.audit(con, user["id"], "login")
            if user["role"] == "candidate":                  # logging in again during a running test: counted, never ended
                running = db.one(con, "SELECT id FROM sessions WHERE user_id = ? AND status = 'in_progress'", user["id"])
                if running:
                    con.execute("UPDATE sessions SET relogins = relogins + 1 WHERE id = ?", (running["id"],))
                    db.audit(con, user["id"], "relogin_during_test", running["id"])
    if not user:   # raised after the transaction so the failed-try counter is saved
        raise ApiError(401, "wrong_login", "Login details are not correct.")
    if body.app == "candidate" and user["role"] != "candidate":
        raise ApiError(403, "wrong_app", "Reviewers and admins log in at /staff/login.", app="staff")
    if body.app == "staff" and user["role"] == "candidate":
        raise ApiError(403, "wrong_app", "Candidates log in on the main page with their roll no. and login code.", app="candidate")
    return _issue(user, request, response)


@router.post("/auth/logout", summary="Revoke this token")
def logout(response: Response, user: dict = Depends(current_user)):
    with db.tx() as con:
        con.execute("INSERT INTO revoked_tokens (jti, expires_at) VALUES (?, ?) ON CONFLICT DO NOTHING",
                    (user["jti"], exp_iso(user["exp"])))
    response.delete_cookie(COOKIE, path="/")
    return dict(ok=True)


def _me(user: dict) -> dict:
    out = {k: user[k] for k in ("id", "role", "name", "email", "roll_no", "sitting_id", "language", "created_at")}
    out["has_password"] = bool(user["email"])      # roll no. + code candidates have no password of their own
    return out


@router.get("/me", summary="The logged-in user")
def me(user: dict = Depends(current_user)):
    return _me(user)


@router.patch("/me", summary="Change my name or language")
def update_me(body: ProfileIn, user: dict = Depends(current_user)):
    changes = body.model_dump(exclude_none=True)
    if user["roll_no"] and "name" in changes and changes["name"] != user["name"]:
        raise ApiError(400, "name_locked", "Your name comes from your test centre's list. Ask them to correct it.")
    if changes:
        with db.tx() as con:
            con.execute(f"UPDATE users SET {', '.join(k + ' = ?' for k in changes)} WHERE id = ?",
                        (*changes.values(), user["id"]))
            db.audit(con, user["id"], "profile_updated", fields=sorted(changes))
        user = {**user, **changes}
    return _me(user)


@router.post("/auth/change-password", summary="Change my password; other devices are logged out")
def change_password(body: ChangePasswordIn, request: Request, response: Response, user: dict = Depends(current_user)):
    if not user["email"]:
        raise ApiError(400, "no_password", "You log in with a roll no. and a code from your test centre. "
                                           "Ask them if you need a new code.")
    with db.tx() as con:
        u = db.one(con, "SELECT * FROM users WHERE id = ?", user["id"])
        if _locked(u):
            raise ApiError(429, "locked", f"Too many wrong tries. Try again after {config.LOCK_MINUTES} minutes.")
        ok = verify_secret(body.current_password, u["secret_hash"])
        if not ok:                                   # counts like a wrong login, so it cannot be used to guess
            n, lock = u["failed_logins"] + 1, None
            if n >= config.MAX_LOGIN_FAILS:
                lock = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=config.LOCK_MINUTES)
                        ).strftime("%Y-%m-%dT%H:%M:%SZ")
                n = 0
            con.execute("UPDATE users SET failed_logins = ?, locked_until = ? WHERE id = ?", (n, lock, u["id"]))
            db.audit(con, u["id"], "password_change_failed")
        elif body.new_password == body.current_password:
            raise ApiError(422, "same_password", "The new password must be different from the current one.")
        else:
            con.execute("""UPDATE users SET secret_hash = ?, password_changed_at = ?, token_version = token_version + 1,
                           failed_logins = 0, locked_until = NULL WHERE id = ?""",
                        (hash_secret(body.new_password), db.now(), u["id"]))
            u = db.one(con, "SELECT * FROM users WHERE id = ?", u["id"])
            con.execute("INSERT INTO revoked_tokens (jti, expires_at) VALUES (?, ?) ON CONFLICT DO NOTHING",
                        (user["jti"], exp_iso(user["exp"])))
            db.audit(con, u["id"], "password_changed")
    if not ok:      # raised after the transaction so the failed-try counter is saved
        raise ApiError(400, "wrong_password", "Your current password is not correct.")
    return _issue(u, request, response)          # a fresh token for this device


@router.post("/demo/candidate", status_code=201, summary="Demo mode only: a fresh candidate in the demo sitting (one-click demo)")
def demo_candidate(body: DemoCandidateIn, request: Request, response: Response):
    if not config.demo_mode():
        raise ApiError(404, "not_found", "Not found.")
    from ..scripts.seed_demo import CODE_JOIN, JOIN_CODE
    from ..services.admin import add_candidates
    import secrets
    code = JOIN_CODE if body.kind == "mcq" else CODE_JOIN
    with db.tx() as con:
        sit = db.one(con, "SELECT id FROM sittings WHERE join_code = ? AND status = 'live'", code)
        if not sit:
            raise ApiError(409, "demo_closed", "The demo test is not open right now.")
        made = add_candidates(con, sit["id"], [dict(roll_no="DEMO" + secrets.token_hex(3).upper(), name="Demo candidate",
                                                     language=body.language)])[0]
        user = db.one(con, "SELECT * FROM users WHERE roll_no = ? AND sitting_id = ?", made["roll_no"], sit["id"])
        db.audit(con, user["id"], "demo_candidate")
    return _issue(user, request, response)


@router.get("/demo", summary="Public demo logins for the login page (only in demo mode: FP_DEMO=1, or local SQLite)")
def demo():
    if not config.demo_mode():
        return dict(enabled=False)
    from ..scripts.seed_demo import ADMIN, CODE_JOIN, JOIN_CODE, REVIEWER, story_logins
    with db.tx() as con:
        staff = [dict(role=role, email=email, password=pw) for role, (email, pw) in (("admin", ADMIN), ("reviewer", REVIEWER))
                 if db.one(con, "SELECT 1 FROM users WHERE email = ? AND role = ?", email, role)]
        story = [dict(key=p["key"], roll_no=p["roll_no"], code=p["code"], name=p["name"]) for p in story_logins()
                 if db.one(con, "SELECT 1 FROM users WHERE roll_no = ? AND role = 'candidate'", p["roll_no"])]
        live = {r["join_code"] for r in db.all_(con, "SELECT join_code FROM sittings WHERE status = 'live' AND join_code IN (?, ?)",
                                                 JOIN_CODE, CODE_JOIN)}
    if not staff:
        return dict(enabled=False)
    return dict(enabled=True, staff=staff, story=story,
                join_codes={k: c for k, c in (("mcq", JOIN_CODE), ("coding", CODE_JOIN)) if c in live})

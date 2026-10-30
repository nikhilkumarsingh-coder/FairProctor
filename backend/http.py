"""Shared FastAPI plumbing: one error format, JWT auth dependencies, role checks, CSV bodies."""
from __future__ import annotations

import datetime as dt
import math

import numpy as np
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import config, db
from .security import read_jwt

COOKIE = "fp_token"
bearer = HTTPBearer(auto_error=False, description="JWT from POST /api/auth/login or /api/auth/signup")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, **extra):
        self.status, self.code, self.message, self.extra = status, code, message, extra


def clean(o):
    """Make numpy / NaN values JSON-safe."""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def install_error_handlers(app: FastAPI) -> None:
    """Every error, ours or FastAPI's, comes back as {"error": {"code", "message", ...}}."""

    @app.exception_handler(ApiError)
    async def _api(request, e: ApiError):
        return JSONResponse({"error": dict(code=e.code, message=e.message, **e.extra)}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request, e: RequestValidationError):
        fields = [dict(field=".".join(str(p) for p in er["loc"] if p != "body"), problem=er["msg"]) for er in e.errors()]
        return JSONResponse({"error": dict(code="invalid", message="Some fields are missing or wrong.", fields=fields)},
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request, e: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(e.status_code, "http_error")
        return JSONResponse({"error": dict(code=code, message=str(e.detail))}, status_code=e.status_code)


async def csv_body(request: Request, max_bytes: int = 2_000_000) -> str:
    raw = await request.body()
    if len(raw) > max_bytes:
        raise ApiError(413, "too_large", "File is too large.")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ApiError(400, "bad_encoding", "Please upload the CSV as UTF-8.")


def _token(request: Request, cred: HTTPAuthorizationCredentials | None) -> str | None:
    if cred and cred.scheme.lower() == "bearer":
        return cred.credentials
    return request.cookies.get(COOKIE)        # same-origin convenience; cross-site frontends send the header


def current_user(request: Request, cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict:
    tok = _token(request, cred)
    claims = read_jwt(tok, config.jwt_secret()) if tok else None
    if not claims:
        raise ApiError(401, "not_logged_in", "Please log in.")
    with db.tx() as con:
        if db.one(con, "SELECT 1 FROM revoked_tokens WHERE jti = ?", claims["jti"]):
            raise ApiError(401, "not_logged_in", "You have logged out. Please log in again.")
        u = db.one(con, """SELECT id, role, name, email, roll_no, sitting_id, language, created_at, token_version
                           FROM users WHERE id = ?""", int(claims["sub"]))
    if not u:
        raise ApiError(401, "not_logged_in", "This account no longer exists.")
    if int(claims.get("tv", 0)) != u.pop("token_version"):           # issued before the password changed
        raise ApiError(401, "session_expired", "Your password was changed. Please log in again.")
    u["jti"], u["exp"] = claims["jti"], claims["exp"]
    return u


def require(*roles: str):
    """Dependency: the logged-in user must have one of these roles."""
    def dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in roles:
            raise ApiError(403, "not_allowed", "You do not have access to this page.")
        return user
    return dep


def exp_iso(exp: int) -> str:
    return dt.datetime.fromtimestamp(exp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

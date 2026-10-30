"""FairProctor web backend (FastAPI).

    python -m uvicorn backend.app:app --port 8000            # from the project root

Interactive API docs: http://127.0.0.1:8000/docs  ·  reference: docs/API.md
Database: PostgreSQL when DATABASE_URL is set (production), otherwise a local SQLite file.
"""
from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config, db

sys.path.insert(0, config.ROOT)   # so `fairproctor` (the scoring engine) imports from the project root

from .http import ApiError, install_error_handlers  # noqa: E402
from .jobs import worker  # noqa: E402
from .routes import admin, auth, exam, review  # noqa: E402
from .security import hash_secret  # noqa: E402
from .services import privacy, scoring  # noqa: E402,F401  (registers job handlers)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("fairproctor")


def bootstrap_admin() -> None:
    """On a fresh deployment, FP_ADMIN_EMAIL + FP_ADMIN_PASSWORD create the first admin."""
    email, pw = config.get("FP_ADMIN_EMAIL").lower(), config.get("FP_ADMIN_PASSWORD")
    if not email or not pw:
        return
    with db.tx() as con:
        if not db.one(con, "SELECT 1 FROM users WHERE lower(email) = ?", email):
            uid = con.insert("INSERT INTO users (role, name, email, secret_hash) VALUES ('admin', 'Admin', ?, ?)",
                             (email, hash_secret(pw)))
            db.audit(con, uid, "admin_bootstrapped")
            log.info("created admin %s", email)


def _daily_retention():
    try:
        with db.tx() as con:
            worker.enqueue(con, "retention", "daily")
    finally:
        t = threading.Timer(24 * 3600, _daily_retention)
        t.daemon = True
        t.start()


@contextlib.asynccontextmanager
async def lifespan(app):
    db.migrate()
    bootstrap_admin()
    worker.ensure_running()
    if os.environ.get("FP_RETENTION", "1") == "1":
        _daily_retention()
    yield


app = FastAPI(title="FairProctor API", version="1.0",
              description="Proctoring that does not punish a shared room. Log in at POST /api/auth/login, then "
                          "send `Authorization: Bearer <access_token>`. Errors are always "
                          '`{"error": {"code", "message"}}`.',
              lifespan=lifespan)
install_error_handlers(app)

if config.cors_origins():   # the deployed frontend (e.g. https://fairproctor.vercel.app)
    app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["Authorization", "Content-Type", "Accept", "X-SEB-Config-Key-Hash", "X-SEB-Page-Url", "X-SEB-Page-Url-Now"])


@app.get("/api/health", tags=["meta"])
def health():
    with db.tx() as con:
        n = db.one(con, "SELECT COUNT(*) n FROM sittings")["n"]
    return dict(ok=True, database="postgresql" if config.is_postgres() else "sqlite", sittings=n,
                model_ready=os.path.exists(os.path.join(config.artifacts_dir(), "model.pkl")))


for r in (auth.router, admin.router, exam.router, exam.probe, exam.code, exam.seb_files, review.router):
    app.include_router(r)


# ---------------------------------------------------------------- the React app, when it is built into frontend/dist
_dist = config.frontend_dist()
if os.path.isdir(os.path.join(_dist, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_dist, "assets")), name="assets")


@app.get("/", include_in_schema=False)
def root():
    index = os.path.join(_dist, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return dict(ok=True, message="FairProctor API is running. Docs: /docs")


STAFF_PREFIXES = ("staff", "admin", "review")     # the staff app (reviewers, admins); everything else: the candidate app


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    """Two apps from one build: /staff, /admin and /review get the staff app, every other page the candidate app, so
    each router works on refresh and candidates never download the staff screens."""
    index = os.path.join(_dist, "index.html")
    if path.startswith("api/") or not os.path.exists(index):
        raise ApiError(404, "not_found", "Not found.")
    file = os.path.join(_dist, path)
    if os.path.isfile(file) and os.path.abspath(file).startswith(os.path.abspath(_dist)):
        return FileResponse(file)
    staff = os.path.join(_dist, "staff", "index.html")
    if path.split("/", 1)[0] in STAFF_PREFIXES and os.path.exists(staff):
        return FileResponse(staff)
    return FileResponse(index)

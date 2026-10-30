"""A tiny in-process job queue (jobs table + one worker thread). Enough for one server; swap for RQ/Celery later."""
from __future__ import annotations

import logging
import threading
import time
import traceback

from .. import db

log = logging.getLogger("fairproctor.jobs")
_wake = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()
HANDLERS: dict = {}


def handler(kind: str):
    def deco(fn):
        HANDLERS[kind] = fn
        return fn
    return deco


def enqueue(con, kind: str, target) -> int:
    job_id = con.insert("INSERT INTO jobs (kind, target) VALUES (?, ?)", (kind, str(target)))
    ensure_running()
    _wake.set()
    return job_id


def progress(job_id: int, frac: float, message: str = "") -> None:
    with db.tx() as con:
        con.execute("UPDATE jobs SET progress = ?, message = ? WHERE id = ?", (round(float(frac), 3), message, job_id))


def _next():
    with db.tx() as con:
        j = db.one(con, "SELECT * FROM jobs WHERE status = 'queued' ORDER BY id LIMIT 1")
        if j:
            con.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (j["id"],))
    return j


def run_one() -> bool:
    j = _next()
    if not j:
        return False
    try:
        HANDLERS[j["kind"]](j["id"], j["target"])
        with db.tx() as con:
            con.execute("UPDATE jobs SET status = 'done', progress = 1, finished_at = ? WHERE id = ?", (db.now(), j["id"]))
    except Exception as e:  # keep the worker alive; the job row carries the error
        log.error("job %s failed: %s", j["id"], traceback.format_exc())
        with db.tx() as con:
            con.execute("UPDATE jobs SET status = 'failed', message = ?, finished_at = ? WHERE id = ?",
                        (f"{type(e).__name__}: {e}"[:500], db.now(), j["id"]))
    return True


def _loop():
    while True:
        try:
            while run_one():
                pass
        except Exception:
            log.error("worker loop: %s", traceback.format_exc())
        _wake.wait(timeout=2)   # short: a job enqueued inside a transaction is only visible after its commit
        _wake.clear()


def ensure_running() -> None:
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=_loop, name="fairproctor-jobs", daemon=True)
            _thread.start()


def wait_for(job_id: int, timeout: float = 600) -> dict:
    """For scripts and tests: block until a job finishes."""
    end = time.time() + timeout
    while time.time() < end:
        with db.tx() as con:
            j = db.one(con, "SELECT * FROM jobs WHERE id = ?", job_id)
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.2)
    raise TimeoutError(f"job {job_id} still running")

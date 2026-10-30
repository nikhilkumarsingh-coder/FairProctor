"""Database access for PostgreSQL (production) and SQLite (local development / tests).

All SQL in the app is written once with `?` placeholders and portable syntax
(ON CONFLICT ... DO NOTHING / DO UPDATE, RETURNING). The connection wrapper converts
placeholders for PostgreSQL. One short-lived connection per unit of work.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import glob
import json
import os
import sqlite3
import threading

from . import config

_lock = threading.Lock()
_migrated: set[str] = set()


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)


class Con:
    """A thin wrapper so the same code runs on sqlite3 and psycopg."""

    def __init__(self, raw, pg: bool):
        self.raw, self.pg = raw, pg

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.pg else sql

    def execute(self, sql: str, args=()):
        return self.raw.execute(self._sql(sql), tuple(args))

    def executemany(self, sql: str, rows):
        rows = list(rows)
        if not rows:
            return
        if self.pg:
            with self.raw.cursor() as cur:
                cur.executemany(self._sql(sql), rows)
        else:
            self.raw.executemany(sql, rows)

    def insert(self, sql: str, args=()) -> int:
        """INSERT ... and return the new row's id."""
        row = self.raw.execute(self._sql(sql + " RETURNING id"), tuple(args)).fetchone()
        return int(row["id"])

    def copy(self, table: str, cols: list[str], rows) -> None:
        """Fast bulk load (PostgreSQL COPY; executemany on SQLite)."""
        rows = list(rows)
        if not rows:
            return
        if self.pg:
            with self.raw.cursor() as cur:
                with cur.copy(f"COPY {table} ({', '.join(cols)}) FROM STDIN") as cp:
                    for r in rows:
                        cp.write_row(r)
        else:
            self.raw.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", rows)


def _sqlite(path: str):
    config.private_dir(os.path.dirname(os.path.abspath(path)))
    new = not os.path.exists(path)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False, isolation_level=None)
    if new:
        config._private(path, 0o600)             # SQLite gives the -wal / -shm files the same permissions
    con.row_factory = lambda cur, row: {d[0]: v for d, v in zip(cur.description, row)}
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def _postgres(url: str):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(url, row_factory=dict_row, autocommit=False, connect_timeout=15)


def _statements(sql: str):
    for stmt in sql.replace("\r\n", "\n").split(";\n"):
        body = "\n".join(ln for ln in stmt.splitlines() if not ln.strip().startswith("--")).strip()
        if body:
            yield body


def migrate(url: str | None = None) -> None:
    url = url or config.database_url()
    with _lock:
        if url in _migrated:
            return
        pg = url.startswith("postgresql://")
        here = os.path.join(os.path.dirname(__file__), "migrations", "postgres" if pg else "sqlite")
        raw = _postgres(url) if pg else _sqlite(url[len("sqlite:///"):])
        con = Con(raw, pg)
        try:
            if not pg:
                raw.execute("BEGIN")
            con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, at TEXT NOT NULL)")
            done = {r["name"] for r in con.execute("SELECT name FROM schema_migrations").fetchall()}
            for f in sorted(glob.glob(os.path.join(here, "*.sql"))):
                name = os.path.basename(f)
                if name in done:
                    continue
                with open(f, encoding="utf-8") as fh:
                    for stmt in _statements(fh.read()):
                        raw.execute(stmt)
                con.execute("INSERT INTO schema_migrations VALUES (?, ?)", (name, now()))
            raw.execute("COMMIT") if not pg else raw.commit()
        except Exception:
            raw.execute("ROLLBACK") if not pg else raw.rollback()
            raise
        finally:
            raw.close()
        _migrated.add(url)


@contextlib.contextmanager
def tx():
    """A connection inside one transaction: committed on success, rolled back on any error."""
    url = config.database_url()
    migrate(url)
    pg = url.startswith("postgresql://")
    raw = _postgres(url) if pg else _sqlite(url[len("sqlite:///"):])
    con = Con(raw, pg)
    try:
        if not pg:
            raw.execute("BEGIN IMMEDIATE")
        yield con
        raw.commit() if pg else raw.execute("COMMIT")
    except BaseException:
        raw.rollback() if pg else raw.execute("ROLLBACK")
        raise
    finally:
        raw.close()


def one(con: Con, sql, *args) -> dict | None:
    r = con.execute(sql, args).fetchone()
    return dict(r) if r else None


def all_(con: Con, sql, *args) -> list[dict]:
    return [dict(r) for r in con.execute(sql, args).fetchall()]


def audit(con: Con, actor_id, action: str, target: str = "", **detail) -> None:
    con.execute("INSERT INTO audit_log (actor_id, action, target, detail) VALUES (?, ?, ?, ?)",
                (actor_id, action, str(target), json.dumps(detail, default=str)))


def reset_database() -> None:
    """Drop everything (demo seed --reset only)."""
    url = config.database_url()
    if url.startswith("postgresql://"):
        raw = _postgres(url)
        try:
            raw.execute("DROP SCHEMA public CASCADE")
            raw.execute("CREATE SCHEMA public")
            raw.commit()
        finally:
            raw.close()
    else:
        path = url[len("sqlite:///"):]
        for suffix in ("", "-wal", "-shm"):
            if os.path.exists(path + suffix):
                os.remove(path + suffix)
    _migrated.discard(url)

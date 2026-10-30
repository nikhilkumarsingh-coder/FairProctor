"""Tests, questions, sittings and candidates."""
from __future__ import annotations

import csv
import io
import json

from .. import db
from ..http import ApiError
from ..security import hash_secret, new_login_code, new_session_id

LETTERS = "ABCDEFGH"


def parse_items_csv(text: str) -> list[dict]:
    """Columns: text, option_a, option_b, [option_c, ...], correct, [difficulty], [kind: mcq|short].

    A short-answer row leaves the options empty and puts the expected answer in `correct`."""
    rd = csv.DictReader(io.StringIO(text))
    cols = [c.strip().lower() for c in (rd.fieldnames or [])]
    opt_cols = [c for c in cols if c.startswith("option_")]
    if "text" not in cols or "correct" not in cols or len(opt_cols) < 2:
        raise ApiError(400, "bad_csv", "CSV needs columns: text, option_a, option_b, ..., correct")
    items, problems = [], []
    for n, row in enumerate(rd, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        opts = {c[-1].upper(): row[c] for c in opt_cols if row.get(c)}
        kind = (row.get("kind") or "mcq").lower()
        correct = row.get("correct", "") if kind == "short" else row.get("correct", "").upper()
        if not row.get("text"):
            problems.append(dict(line=n, problem="question text is empty"))
        elif kind not in ("mcq", "short"):
            problems.append(dict(line=n, problem="kind must be mcq or short"))
        elif kind == "short":
            if not correct:
                problems.append(dict(line=n, problem="short-answer question needs its correct answer"))
            else:
                diff = row.get("difficulty")
                items.append(dict(text=row["text"], options={}, correct_option=correct,
                                  difficulty=float(diff) if diff else None, kind="short"))
        elif len(opts) < 2:
            problems.append(dict(line=n, problem="needs at least two options"))
        elif correct not in opts:
            problems.append(dict(line=n, problem=f"correct answer '{correct}' is not one of the options"))
        else:
            diff = row.get("difficulty")
            items.append(dict(text=row["text"], options=opts, correct_option=correct,
                              difficulty=float(diff) if diff else None, kind="mcq"))
    if problems:
        raise ApiError(400, "bad_rows", f"{len(problems)} row(s) need fixing.", rows=problems[:100])
    if not items:
        raise ApiError(400, "empty", "No questions found in the file.")
    return items


def replace_items(con, test_id: int, items: list[dict]) -> int:
    if db.one(con, "SELECT 1 FROM sittings WHERE test_id = ? AND status != 'scheduled'", test_id):
        raise ApiError(409, "test_in_use", "Questions cannot change once a sitting of this test has started.")
    con.execute("DELETE FROM items WHERE test_id = ?", (test_id,))
    for pos, it in enumerate(items):
        con.execute("""INSERT INTO items (test_id, position, kind, text, options, correct_option, difficulty)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (test_id, pos, it["kind"], it["text"], json.dumps(it["options"], ensure_ascii=False),
                     it["correct_option"], it["difficulty"]))
    return len(items)


def parse_candidates_csv(text: str) -> list[dict]:
    rd = csv.DictReader(io.StringIO(text))
    cols = [c.strip().lower() for c in (rd.fieldnames or [])]
    if "roll_no" not in cols or "name" not in cols:
        raise ApiError(400, "bad_csv", "CSV needs columns: roll_no, name, [language]")
    out, seen, problems = [], set(), []
    for n, row in enumerate(rd, start=2):
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        r = row.get("roll_no", "")
        if not r or not row.get("name"):
            problems.append(dict(line=n, problem="roll_no and name are needed"))
        elif r in seen:
            problems.append(dict(line=n, problem=f"roll_no {r} appears twice"))
        else:
            seen.add(r)
            lang = row.get("language", "en").lower()
            out.append(dict(roll_no=r, name=row["name"], language="hi" if lang.startswith("hi") else "en"))
    if problems:
        raise ApiError(400, "bad_rows", f"{len(problems)} row(s) need fixing.", rows=problems[:100])
    return out


def create_sitting(con, test_id: int, title: str, starts_at: str, ends_at: str, status: str = "scheduled",
                   join_code: str | None = None) -> int:
    from ..security import new_join_code
    code = join_code or new_join_code()
    while db.one(con, "SELECT 1 FROM sittings WHERE join_code = ?", code):
        code = new_join_code()
    return con.insert("""INSERT INTO sittings (test_id, title, starts_at, ends_at, status, join_code)
                         VALUES (?, ?, ?, ?, ?, ?)""", (test_id, title, starts_at, ends_at, status, code))


def add_candidates(con, sitting_id: int, cands: list[dict]) -> list[dict]:
    """Creates a login + session for each candidate. Codes are returned ONCE (only their hash is stored)."""
    out = []
    for c in cands:
        if db.one(con, "SELECT 1 FROM users WHERE sitting_id = ? AND roll_no = ?", sitting_id, c["roll_no"]):
            raise ApiError(409, "duplicate", f"Roll no. {c['roll_no']} is already in this sitting.")
        code = new_login_code()
        uid = con.insert("""INSERT INTO users (role, name, roll_no, sitting_id, secret_hash, language)
                            VALUES ('candidate', ?, ?, ?, ?, ?)""",
                         (c["name"], c["roll_no"], sitting_id, hash_secret(code), c["language"]))
        con.execute("INSERT INTO sessions (id, sitting_id, user_id) VALUES (?, ?, ?)",
                    (new_session_id(), sitting_id, uid))
        out.append(dict(user_id=uid, roll_no=c["roll_no"], name=c["name"], code=code))
    return out


def codes_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["roll_no", "name", "login_code"])
    for r in rows:
        w.writerow([r["roll_no"], r["name"], r["code"]])
    return buf.getvalue()


def sitting_live(con, sitting_id: int) -> dict:
    rows = db.all_(con, "SELECT status, COUNT(*) n FROM sessions WHERE sitting_id = ? AND is_synthetic = 0 GROUP BY status",
                   sitting_id)
    c = {r["status"]: r["n"] for r in rows}
    bands = {r["band"]: r["n"] for r in db.all_(con, "SELECT band, COUNT(*) n FROM scores WHERE sitting_id = ? GROUP BY band",
                                                 sitting_id)}
    synth = db.one(con, "SELECT COUNT(*) n FROM sessions WHERE sitting_id = ? AND is_synthetic = 1", sitting_id)["n"]
    return dict(not_started=c.get("not_started", 0), in_progress=c.get("in_progress", 0), submitted=c.get("submitted", 0),
                reference_sessions=synth, bands=bands)

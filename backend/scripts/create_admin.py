"""Create an admin (or reviewer) account, or reset its password, straight in the database.

There is no sign-up page for staff. Passwords are stored as scrypt hashes, so they cannot be typed into the database
by hand: use this command (it asks for the password twice and never prints it).

    python -m backend.scripts.create_admin --email head@college.edu --name "Exam Head"
    python -m backend.scripts.create_admin --email rev@college.edu --name "Reviewer" --role reviewer
    python -m backend.scripts.create_admin --email head@college.edu --reset-password
    python -m backend.scripts.create_admin --list

Uses the same database as the server (FP_DB / DATABASE_URL). Admins add reviewers and candidates in the staff app.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

from .. import db
from ..schemas import check_password
from ..security import hash_secret


def ask_password() -> str:
    pw = os.environ.get("FP_NEW_PASSWORD")                       # for scripts / CI; never shown
    if pw is None:
        pw = getpass.getpass("New password (8+ characters, letters and numbers): ")
        if getpass.getpass("Type it again: ") != pw:
            sys.exit("The two passwords are different. Nothing was changed.")
    try:
        check_password(pw)
    except ValueError as e:
        sys.exit(f"Password not accepted: {e}. Nothing was changed.")
    if len(pw) < 8:
        sys.exit("Password not accepted: use at least 8 characters. Nothing was changed.")
    return pw


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Create or reset a staff account (admin or reviewer).")
    ap.add_argument("--email")
    ap.add_argument("--name")
    ap.add_argument("--role", choices=["admin", "reviewer"], default="admin")
    ap.add_argument("--reset-password", action="store_true", help="set a new password for an existing account")
    ap.add_argument("--list", action="store_true", help="show the staff accounts")
    a = ap.parse_args(argv)
    db.migrate()
    with db.tx() as con:
        if a.list:
            for u in db.all_(con, "SELECT id, role, name, email, created_at FROM users WHERE role IN ('admin', 'reviewer') ORDER BY role, id"):
                print(f"{u['id']:>4}  {u['role']:<8}  {u['email']:<36}  {u['name']}")
            return 0
        if not a.email:
            ap.error("--email is required")
        email = a.email.strip().lower()
        u = db.one(con, "SELECT * FROM users WHERE lower(email) = ?", email)
        if a.reset_password:
            if not u or u["role"] not in ("admin", "reviewer"):
                sys.exit(f"No admin or reviewer account with the email {email}.")
            pw = ask_password()
            con.execute("""UPDATE users SET secret_hash = ?, password_changed_at = ?, token_version = token_version + 1,
                           failed_logins = 0, locked_until = NULL WHERE id = ?""", (hash_secret(pw), db.now(), u["id"]))
            db.audit(con, None, "password_reset_cli", str(u["id"]))
            print(f"Password changed for {email}. Other devices of this account are logged out.")
            return 0
        if u:
            sys.exit(f"An account with the email {email} already exists (role: {u['role']}). Use --reset-password to change its password.")
        if not a.name:
            ap.error("--name is required for a new account")
        pw = ask_password()
        uid = con.insert("INSERT INTO users (role, name, email, secret_hash) VALUES (?, ?, ?, ?)",
                         (a.role, a.name.strip(), email, hash_secret(pw)))
        db.audit(con, None, "user_created_cli", str(uid), role=a.role)
    print(f"Created {a.role} {email}. Log in at /staff/login.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

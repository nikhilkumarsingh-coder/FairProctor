"""Delete a pilot's data once its results are written (the consent form promises this within 7 days).

    python -m pilot.cleanup --dir pilot/out/<name> --yes

Deletes the pilot sittings with everything in them (participant logins, sessions, answers, camera numbers, code,
scores, reviews, appeals) and the login codes and cards in the pilot folder. Keeps the anonymous results
(reports/PILOT_RESULTS.md, the charts, and the key of roll numbers to roles, which names nobody).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import db  # noqa: E402


def cleanup(folder: str) -> list[int]:
    path = os.path.join(folder, "pilot.json")
    with open(path, encoding="utf-8") as fh:
        meta = json.load(fh)
    gone = []
    with db.tx() as con:
        for t in meta["tests"].values():
            sid = t["sitting_id"]
            if db.one(con, "SELECT 1 FROM sittings WHERE id = ?", sid):
                con.execute("DELETE FROM sittings WHERE id = ?", (sid,))
                db.audit(con, None, "pilot_deleted", sid, name=meta["name"])
                gone.append(sid)
    for name in ("logins.csv", "cards.html"):
        if os.path.exists(os.path.join(folder, name)):
            os.remove(os.path.join(folder, name))
    shutil.rmtree(os.path.join(folder, "cards"), ignore_errors=True)
    meta["deleted_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    return gone


def main():
    ap = argparse.ArgumentParser(description="Delete a pilot's data from the database and its login codes.")
    ap.add_argument("--dir", required=True)
    ap.add_argument("--yes", action="store_true", help="really delete")
    a = ap.parse_args()
    if not a.yes:
        raise SystemExit("This deletes the pilot sittings and everything in them. Add --yes to go ahead.")
    gone = cleanup(a.dir)
    print(f"Deleted sitting(s) {', '.join(map(str, gone)) or '(already gone)'}, the login codes and the cards. "
          "The anonymous results are kept.")


if __name__ == "__main__":
    main()

"""The pilot kit end to end, in-process: roles, setup, cards, a rehearsal with simulated participants through the API,
close & score, the report (which must not touch README.md), and data deletion.

    python -m unittest backend.tests.test_pilot -v
"""
from __future__ import annotations

import csv
import os
import shutil
import tempfile
import unittest
from collections import Counter

TMP = tempfile.mkdtemp(prefix="fp-pilot-")
os.environ.pop("DATABASE_URL", None)
if os.environ.get("FP_TEST_DATABASE_URL"):
    os.environ["FP_DATABASE_URL"] = os.environ["FP_TEST_DATABASE_URL"]
else:
    os.environ.pop("FP_DATABASE_URL", None)
    os.environ["FP_DB"] = os.path.join(TMP, "pilot.db")
os.environ["FP_RETENTION"] = "0"

from backend import db  # noqa: E402
from backend.app import app  # noqa: E402
from pilot import cleanup, dry_run, prepare, report  # noqa: E402
from pilot.roles import ROLES, assign  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class Roles(unittest.TestCase):
    def test_balanced_and_paired(self):
        for test in ("mcq", "coding"):
            for n in range(4, 25):
                rows = assign(test, n, seed=n)
                self.assertEqual(len(rows), n)
                self.assertEqual(len({r["roll_no"] for r in rows}), n)
                kinds = Counter(r["kind"] for r in rows)
                self.assertGreaterEqual(kinds["cheat"], 2)
                self.assertGreaterEqual(kinds["honest"], n // 2)
                by = {r["roll_no"]: r for r in rows}
                for r in rows:
                    if ROLES[r["role"]].get("pair"):
                        self.assertEqual(by[r["partner"]]["partner"], r["roll_no"])
                        self.assertEqual(by[r["partner"]]["role"], r["role"])
                    else:
                        self.assertEqual(r["partner"], "")

    def test_same_seed_same_roles(self):
        self.assertEqual(assign("mcq", 16, 5), assign("mcq", 16, 5))


class Rehearsal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        cls.readme = read(os.path.join(ROOT, "README.md"))
        cls.folder = os.path.join(TMP, "rehearsal")
        prepare.create("test rehearsal", 10, 4, seed=3, reference=True, url="https://example.trycloudflare.com",
                       folder=cls.folder, dry_run=True)
        cls.out = dry_run.run(cls.folder, dry_run.InProcess(app))

    def test_files(self):
        for name in ("cards.html", "consent.html", "logins.csv", "key-SEALED.csv", "pilot.json", "PILOT_DRYRUN.md",
                     "pilot-queue-mcq.svg", "pilot-queue-coding-dark.svg", os.path.join("cards", "P01.html")):
            self.assertTrue(os.path.exists(os.path.join(self.folder, name)), name)
        with open(os.path.join(self.folder, "logins.csv"), encoding="utf-8") as fh:
            logins = list(csv.DictReader(fh))
        self.assertEqual(len(logins), 14)
        cards = read(os.path.join(self.folder, "cards.html"))
        for r in logins:
            self.assertIn(r["code"], cards)
        self.assertIn("https://example.trycloudflare.com", cards)

    def test_report(self):
        text = read(self.out)
        self.assertTrue(self.out.startswith(self.folder))              # a rehearsal never writes to reports/
        self.assertIn("DRY RUN", text)
        self.assertIn("## Question test", text)
        self.assertIn("## Coding test", text)
        for roll in [f"P{i:02d}" for i in range(1, 11)] + [f"PC{i:02d}" for i in range(1, 5)]:
            self.assertIn(f"| {roll} |", text)
        self.assertEqual(read(os.path.join(ROOT, "README.md")), self.readme)

    def test_summary_is_sane(self):
        import json
        meta = json.loads(read(os.path.join(self.folder, "pilot.json")))
        key = {r["roll_no"]: r for r in prepare.read_csv(os.path.join(self.folder, "key-SEALED.csv"))}
        with db.tx() as con:
            d = report.collect(con, "mcq", meta["tests"]["mcq"]["sitting_id"], key)
        s = report.summarise(d)
        self.assertEqual(s["n"], 10)
        self.assertEqual(s["n_cheat"] + s["n_honest"], 10)
        self.assertEqual(s["ours_any"] + s["h_ours_any"], d["w_any"])
        self.assertEqual(s["old_any"] + s["h_old_any"], d["w_any"])   # the old rules get the same number of flags
        self.assertGreaterEqual(s["ours_any"], 1)

    def test_refuses_real_pilot_and_unscored(self):
        real = os.path.join(TMP, "real")
        prepare.create("real one", 4, 0, seed=1, reference=False, url=None, folder=real)
        with self.assertRaises(SystemExit):
            dry_run.run(real, dry_run.InProcess(app))               # simulated people never go into a real pilot
        with self.assertRaises(SystemExit):
            report.write(real)                                     # not closed and scored yet
        with self.assertRaises(SystemExit):
            prepare.create("real one", 4, 0, seed=1, reference=False, url=None, folder=real)   # never overwrite a key

    def test_zz_cleanup(self):
        import json
        meta = json.loads(read(os.path.join(self.folder, "pilot.json")))
        gone = cleanup.cleanup(self.folder)
        self.assertEqual(sorted(gone), sorted(t["sitting_id"] for t in meta["tests"].values()))
        with db.tx() as con:
            for sid in gone:
                self.assertIsNone(db.one(con, "SELECT 1 FROM sittings WHERE id = ?", sid))
                self.assertEqual(db.one(con, "SELECT COUNT(*) n FROM sessions WHERE sitting_id = ?", sid)["n"], 0)
                self.assertEqual(db.one(con, "SELECT COUNT(*) n FROM users WHERE sitting_id = ?", sid)["n"], 0)
        self.assertFalse(os.path.exists(os.path.join(self.folder, "logins.csv")))
        self.assertTrue(os.path.exists(os.path.join(self.folder, "PILOT_DRYRUN.md")))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

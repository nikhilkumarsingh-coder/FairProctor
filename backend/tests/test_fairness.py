"""Fairness report: the statistics, and the report on the seeded demo sitting after close & score.

    python -m unittest backend.tests.test_fairness -v
"""
from __future__ import annotations

import os
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="fp-fair-")
os.environ.pop("DATABASE_URL", None)
if os.environ.get("FP_TEST_DATABASE_URL"):
    os.environ["FP_DATABASE_URL"] = os.environ["FP_TEST_DATABASE_URL"]
else:
    os.environ.pop("FP_DATABASE_URL", None)
    os.environ["FP_DB"] = os.path.join(TMP, "fair.db")
os.environ["FP_RETENTION"] = "0"

from backend.app import app  # noqa: E402
from backend.jobs import worker  # noqa: E402
from backend.services import fairness  # noqa: E402
from backend.tests.client import Client  # noqa: E402


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class Stats(unittest.TestCase):
    def test_wilson(self):
        lo, hi = fairness.wilson(0, 10)
        self.assertEqual(lo, 0.0)
        self.assertAlmostEqual(hi, 0.2775, places=3)
        lo, hi = fairness.wilson(5, 10)
        self.assertAlmostEqual(lo, 0.2366, places=3)
        self.assertAlmostEqual(hi, 0.7634, places=3)
        self.assertEqual(fairness.wilson(0, 0), (None, None))

    def test_gap(self):
        same = fairness.gap(fairness.rate(30, 100), fairness.rate(30, 100))
        self.assertEqual(same["verdict"], "no_clear_difference")
        self.assertLess(same["lo"], 0)
        self.assertGreater(same["hi"], 0)
        worse = fairness.gap(fairness.rate(60, 100), fairness.rate(20, 100))
        self.assertEqual(worse["verdict"], "higher")
        self.assertAlmostEqual(worse["diff"], 0.4)
        self.assertGreater(worse["lo"], 0.25)
        better = fairness.gap(fairness.rate(5, 100), fairness.rate(40, 100))
        self.assertEqual(better["verdict"], "lower")
        self.assertEqual(fairness.gap(fairness.rate(3, 5), fairness.rate(10, 100))["verdict"], "too_few")


class Report(unittest.TestCase):
    """The seeded demo sitting (200 reference sessions with true labels), closed and scored."""

    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        cls.seeded = seed(reset=True, n_live=0)
        cls.a = Client(app)
        login(cls.a, email="admin@fairproctor.demo", password="Admin@2026")
        sid = cls.seeded["sitting_id"]
        cls.before = cls.a.get(f"/api/admin/sittings/{sid}/fairness").json()
        job = worker.wait_for(cls.a.post(f"/api/admin/sittings/{sid}/close").json()["job_id"], timeout=600)
        assert job["status"] == "done", job
        cls.r = cls.a.get(f"/api/admin/sittings/{sid}/fairness").json()

    def test_not_ready_before_scoring(self):
        self.assertFalse(self.before["ready"])

    def test_labels_and_workload(self):
        r = self.r
        self.assertTrue(r["ready"])
        self.assertEqual(r["n"], 200)
        planted = sum(self.seeded["planted"].values())
        self.assertEqual(r["labels"], dict(honest=200 - planted, malpractice=planted, pending=0, reference=200))
        for level in ("any", "first"):
            self.assertGreater(r["workload"][level]["n"], 0)
        self.assertGreaterEqual(r["workload"]["any"]["n"], r["workload"]["first"]["n"])

    def test_views(self):
        r = self.r
        self.assertEqual(set(r["views"]), {"honest.any", "honest.first", "all.any", "all.first"})
        for key, v in r["views"].items():
            dims = {d["key"] for d in v["dimensions"]}
            self.assertTrue({"room", "bandwidth", "light", "device", "framing"} <= dims, key)
            # the old rules get exactly as many review slots as FairProctor used
            if key.startswith("all."):
                self.assertEqual(v["overall"]["ours"]["k"], v["overall"]["old"]["k"])
            for d in v["dimensions"]:
                self.assertEqual(sum(1 for g in d["groups"] if g["reference"]), 1)
                self.assertEqual(sum(g["n"] for g in d["groups"]) <= v["n"], True)
                for g in d["groups"]:
                    for s in ("ours", "old"):
                        x = g[s]
                        self.assertLessEqual(x["lo"], x["rate"] + 1e-9)
                        self.assertGreaterEqual(x["hi"], x["rate"] - 1e-9)
                    if not g["reference"]:
                        self.assertIn(g["gap"]["ours"]["verdict"], ("higher", "lower", "no_clear_difference", "too_few"))

    def test_story(self):
        """The point of the report: the old rules flag honest phone and low-bandwidth candidates far more; FairProctor does not."""
        v = self.r["views"]["honest.any"]
        dev = {g["key"]: g for d in v["dimensions"] if d["key"] == "device" for g in d["groups"]}
        self.assertEqual(dev["phone"]["gap"]["old"]["verdict"], "higher")
        self.assertNotEqual(dev["phone"]["gap"]["ours"]["verdict"], "higher")
        bw = {g["key"]: g for d in v["dimensions"] if d["key"] == "bandwidth" for g in d["groups"]}
        self.assertEqual(bw["low"]["gap"]["old"]["verdict"], "higher")
        self.assertNotEqual(bw["low"]["gap"]["ours"]["verdict"], "higher")
        self.assertIsNotNone(v["largest"]["old"])

    def test_reviewer_cannot_read(self):
        c = Client(app)
        login(c, email="reviewer@fairproctor.demo", password="Review@2026")
        self.assertEqual(c.get(f"/api/admin/sittings/{self.seeded['sitting_id']}/fairness").status_code, 403)

    def test_missing_sitting(self):
        self.assertEqual(self.a.get("/api/admin/sittings/9999/fairness").status_code, 404)


class Story(unittest.TestCase):
    """The scored story sitting: Priya (honest; 2G, phone, dim shared room) is cleared, Rahul (second phone) goes first."""

    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        cls.st = seed(reset=True, n_live=0, story=True)["story"]
        cls.a = Client(app)
        login(cls.a, email="reviewer@fairproctor.demo", password="Review@2026")
        cls.people = {p["roll_no"]: p for p in cls.st["people"]}

    def test_scored_and_ranked(self):
        q = self.a.get(f"/api/review/queue?sitting_id={self.st['sitting_id']}&band=all&include_reference=0").json()
        rows = {r["session_id"]: r for r in q["rows"]}
        priya, rahul = rows[self.people["STORY01"]["session_id"]], rows[self.people["STORY02"]["session_id"]]
        self.assertEqual(priya["band"], "clear")
        self.assertEqual(rahul["band"], "review_first")
        self.assertIn("pause", rahul["families"])

    def test_priya_context(self):
        d = self.a.get(f"/api/review/sessions/{self.people['STORY01']['session_id']}").json()
        ctx = " ".join(d["explanation"]["context"]).lower()
        for words in ("low-bandwidth", "dim room", "walking past", "phone held"):
            self.assertIn(words, ctx)

    def test_results_for_the_candidates(self):
        for roll, state in (("STORY01", "clear"), ("STORY02", "under_review")):
            c = Client(app)
            login(c, roll_no=roll, code=self.people[roll]["code"])
            r = c.get("/api/exam/result").json()
            self.assertEqual(r["state"], state)
        self.assertTrue(r["can_appeal"])
        self.assertTrue(r["points"])

    def test_fairness_ready(self):
        a = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        r = a.get(f"/api/admin/sittings/{self.st['sitting_id']}/fairness").json()
        self.assertTrue(r["ready"])
        self.assertEqual(r["n"], 202)


if __name__ == "__main__":
    unittest.main()

"""Proctoring rules: phone (warning, then end), more than 5 multi-face episodes or tab switches (end), logins during
the test (counted, never an end), disconnects (flag), and a per-candidate question order.

    python -m unittest backend.tests.test_rules -v
"""
from __future__ import annotations

import os
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="fp-rules-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("FP_DATABASE_URL", None)
os.environ["FP_DB"] = os.path.join(TMP, "test.db")
os.environ["FP_RETENTION"] = "0"

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.jobs import worker  # noqa: E402
from backend.services import rules  # noqa: E402
from backend.tests.client import Client  # noqa: E402

ITEMS = "text,option_a,option_b,option_c,option_d,correct,kind\n" + "".join(
    f"Question {i}?,1,2,3,4,{'ABCD'[i % 4]},mcq\n" for i in range(1, 11))


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class Rules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        a = cls.admin = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        tid = a.post("/api/admin/tests", json=dict(title="Rules test", duration_min=20)).json()["id"]
        a.post(f"/api/admin/tests/{tid}/items", data=ITEMS, headers={"content-type": "text/csv"})
        cls.sid = a.post("/api/admin/sittings", json=dict(test_id=tid, title="Rules sitting", starts_at="2026-01-01T10:00:00+05:30",
                                                            ends_at="2030-01-01T10:00:00+05:30")).json()["id"]
        rolls = "".join(f"R{i},Cand {i}\n" for i in range(1, 7))
        up = a.post(f"/api/admin/sittings/{cls.sid}/candidates", data="roll_no,name\n" + rolls,
                    headers={"content-type": "text/csv"}).json()
        cls.codes = {c["roll_no"]: c["code"] for c in up["candidates"]}
        a.post(f"/api/admin/sittings/{cls.sid}/open")

    def cand(self, roll):
        c = Client(app)
        login(c, roll_no=roll, code=self.codes[roll])
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
        return c

    def send(self, c, seq, t, type_, item=-1, option=""):
        return c.post("/api/exam/events", json=dict(events=[dict(seq=seq, t=t, type=type_, item=item, option=option)])).json()

    def test_shuffle_per_candidate(self):
        c1, c2 = self.cand("R1"), self.cand("R2")
        o1 = [it["item"] for it in c1.post("/api/exam/start", json={}).json()["items"]]
        again = [it["item"] for it in c1.post("/api/exam/start", json={}).json()["items"]]
        o2 = [it["item"] for it in c2.post("/api/exam/start", json={}).json()["items"]]
        self.assertEqual(sorted(o1), list(range(10)))                       # every question, once
        self.assertEqual(o1, again)                                          # same order on resume
        self.assertNotEqual(o1, o2)                                          # different order per candidate
        self.assertNotEqual(o1, list(range(10)))

    def test_tab_switch_limit(self):
        c = self.cand("R3")
        c.post("/api/exam/start", json={})
        for k in range(config.TAB_SWITCH_MAX):
            self.assertNotIn("terminated", self.send(c, 10 + k, 5 + k, "focus_lost"))
        out = self.send(c, 50, 30, "focus_lost")                            # the 6th: ended by the server
        self.assertEqual(out["terminated"], "tab_switch")
        r = c.get("/api/exam/result").json()
        self.assertEqual(r["terminated"]["reason"], "tab_switch")
        self.assertEqual(c.post("/api/exam/start", json={}).json()["error"]["code"], "already_submitted")

    def test_phone_warning_then_end(self):
        c = self.cand("R4")
        c.post("/api/exam/start", json={})
        self.assertNotIn("terminated", self.send(c, 1, 10, "phone_seen"))   # first: a warning only
        self.assertEqual(c.post("/api/exam/terminate").json()["error"]["code"], "no_limit_passed")
        with db.tx() as con:
            self.assertEqual(db.one(con, "SELECT status FROM sessions WHERE id = (SELECT id FROM sessions s WHERE s.user_id = "
                                         "(SELECT id FROM users WHERE roll_no = 'R4'))")["status"], "in_progress")
        self.assertEqual(self.send(c, 2, 40, "phone_seen")["terminated"], "phone")
        self.assertEqual(c.post("/api/exam/terminate").json()["terminated"], "phone")   # idempotent

    def test_snapshot_of_the_ending_moment_is_kept(self):
        import base64, datetime as dt
        jpg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 200).decode()
        c = self.cand("R1")
        c.post("/api/exam/start", json={})
        for k in range(config.TAB_SWITCH_MAX + 1):
            out = self.send(c, 500 + k, 20 + k, "focus_lost")
        self.assertEqual(out["terminated"], "tab_switch")
        snap = dict(t=31, reason="tab_return", phase="after", image=jpg)
        self.assertTrue(c.post("/api/exam/snapshot", json=snap).json()["stored"])          # the photo right after the end
        with db.tx() as con:
            con.execute("UPDATE sessions SET terminated_at = ? WHERE id = (SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id "
                        "WHERE u.roll_no = 'R1')", ((dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
        late = c.post("/api/exam/snapshot", json=dict(snap, t=400))
        self.assertEqual(late.json()["error"]["code"], "not_writing")                       # not long after it

    def test_multi_face_limit(self):
        c = self.cand("R5")
        c.post("/api/exam/start", json={})
        for k in range(config.MULTI_FACE_MAX):
            self.assertNotIn("terminated", self.send(c, 1 + k, 10 * k, "multi_face"))
        self.assertEqual(self.send(c, 99, 80, "multi_face")["terminated"], "multiple_faces")

    def test_relogin_is_counted_not_ended(self):
        c = self.cand("R6")
        c.post("/api/exam/start", json={})
        for _ in range(2):
            login(Client(app), roll_no="R6", code=self.codes["R6"])            # logged in again during the test
        with db.tx() as con:
            s = db.one(con, "SELECT s.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.roll_no = 'R6'")
            self.assertEqual((s["relogins"], s["status"]), (2, "in_progress"))
            c6 = rules.counts(con, s["id"])
        self.assertEqual(rules.chips(c6), ["relogin"])
        self.assertEqual(rules.band_floor("clear", c6), "review")
        self.assertEqual(rules.band_floor("review_first", c6), "review_first")   # never lowers

    def test_disconnect_flag(self):
        ev = []
        for k in range(config.DISCONNECT_MAX + 1):
            ev += [dict(t=100 * k, type="offline_start"), dict(t=100 * k + 30, type="offline_end")]
        quiet = rules.counts_from(ev)
        self.assertFalse(rules.disconnect_flag(quiet))                      # disconnects alone: counted, no flag
        ev.append(dict(t=100 * 3 + 38, type="answer", item=1, correct=1))   # answered 8 s after reconnecting
        c = rules.counts_from(ev)
        self.assertTrue(rules.disconnect_flag(c))
        self.assertIn("disconnect", rules.chips(c))
        five = rules.counts_from(ev[2:])                                    # 5 disconnects: below the limit
        self.assertFalse(rules.disconnect_flag(five))

    def test_y_reinstate(self):
        c = self.cand("R2")                                                  # (started in the shuffle test)
        c.post("/api/exam/start", json={})
        for k in range(config.TAB_SWITCH_MAX + 1):
            out = self.send(c, 200 + k, 100 + k, "focus_lost")
        self.assertEqual(out["terminated"], "tab_switch")
        with db.tx() as con:
            sid = db.one(con, "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.roll_no = 'R2'")["id"]
            con.execute("UPDATE sessions SET terminated_at = ? WHERE id = ?",     # it stood ended for 2 minutes
                        ((__import__("datetime").datetime.now(__import__("datetime").timezone.utc)
                          - __import__("datetime").timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M:%SZ"), sid))
        dl_before = c.get("/api/exam/me").json()["session"]["deadline"]
        rev = Client(app)
        login(rev, email="reviewer@fairproctor.demo", password="Review@2026")
        self.assertEqual(rev.post(f"/api/review/sessions/{sid}/reinstate", json=dict(note="ok")).status_code, 422)   # a reason is needed
        self.assertEqual(c.post(f"/api/review/sessions/{sid}/reinstate", json=dict(note="trying myself")).status_code, 403)
        r = rev.post(f"/api/review/sessions/{sid}/reinstate", json=dict(note="Snapshot shows a notification, not another app"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertGreaterEqual(r.json()["minutes_back"], 1.9)
        again = rev.post(f"/api/review/sessions/{sid}/reinstate", json=dict(note="second reviewer at the same time"))
        self.assertEqual(again.json()["error"]["code"], "not_ended_by_rule")          # the first reviewer wins
        me = c.get("/api/exam/me").json()
        self.assertEqual((me["session"]["status"], me["session"]["reopened"]), ("in_progress", True))
        self.assertGreater(me["session"]["deadline"], dl_before)                      # minutes given back
        st = c.post("/api/exam/start", json={}).json()
        self.assertEqual(st["rules"]["tab_switch"], 0)                                 # the rule that ended it starts again
        self.assertNotIn("terminated", self.send(c, 300, 400, "focus_lost"))           # one more leave does not end it
        with db.tx() as con:
            cnt = rules.counts(con, sid)
        self.assertEqual(cnt["tab_switch"], 1)
        self.assertIn("reinstated", [f["key"] for f in rules.flags(cnt)])

    def test_y_reinstate_needs_open_window(self):
        with db.tx() as con:
            s = db.one(con, "SELECT s.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.roll_no = 'R5'")
            sit_end = db.one(con, "SELECT ends_at FROM sittings WHERE id = ?", s["sitting_id"])["ends_at"]
            con.execute("UPDATE sittings SET ends_at = ? WHERE id = ?", ("2026-01-01T11:00:00+05:30", s["sitting_id"]))
        rev = Client(app)
        login(rev, email="reviewer@fairproctor.demo", password="Review@2026")
        out = rev.post(f"/api/review/sessions/{s['id']}/reinstate", json=dict(note="window is over by now"))
        self.assertEqual(out.json()["error"]["code"], "window_closed")
        with db.tx() as con:
            con.execute("UPDATE sittings SET ends_at = ? WHERE id = ?", (sit_end, s["sitting_id"]))

    def test_z_scoring_keeps_reasons(self):
        a = self.admin
        job = a.post(f"/api/admin/sittings/{self.sid}/close").json()["job_id"]
        self.assertEqual(worker.wait_for(job, timeout=300)["status"], "done")
        with db.tx() as con:
            rows = {r["roll_no"]: r for r in db.all_(con, """SELECT u.roll_no, c.band, c.families FROM scores c
                                                            JOIN sessions s ON s.id = c.session_id JOIN users u ON u.id = s.user_id
                                                            WHERE c.sitting_id = ?""", self.sid)}
        for roll in ("R3", "R4", "R5"):                                     # every ended test goes to a person
            self.assertIn("terminated", rows[roll]["families"])
            self.assertNotEqual(rows[roll]["band"], "clear")
        self.assertIn("relogin", rows["R6"]["families"])


if __name__ == "__main__":
    unittest.main()

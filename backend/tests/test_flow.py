"""End-to-end tests of the web backend (each Part's "done when" from the workflow doc).

    python -m unittest backend.tests.test_flow -v        # from the project root (temporary SQLite)
    set FP_TEST_DATABASE_URL=postgresql://user:pass@host/testdb   # optional: run the same tests on PostgreSQL
                                                                  # (WARNING: wipes that database)

Needs artifacts/model.pkl (run the research pipeline once).
"""
from __future__ import annotations

import base64
import math
import os
import random
import tempfile
import time
import unittest

TMP = tempfile.mkdtemp(prefix="fp-test-")
os.environ.pop("DATABASE_URL", None)
if os.environ.get("FP_TEST_DATABASE_URL"):
    os.environ["FP_DATABASE_URL"] = os.environ["FP_TEST_DATABASE_URL"]
else:
    os.environ.pop("FP_DATABASE_URL", None)
    os.environ["FP_DB"] = os.path.join(TMP, "test.db")
os.environ["FP_RETENTION"] = "0"

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.jobs import worker  # noqa: E402
from backend.tests.client import Client  # noqa: E402

ITEMS_CSV = """text,option_a,option_b,option_c,option_d,correct,kind
What is 2 + 2?,3,4,5,6,B,mcq
What is 10 x 3?,13,30,33,300,B,mcq
Capital of India?,Mumbai,Delhi,Kolkata,Chennai,B,mcq
Next: 2 4 8 16 ?,18,24,32,30,C,mcq
How many days in a week?,,,,,7,short
"""


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text
    return r.json()["user"]


def exam_events(rng, n_items, answers, start_seq=1, speed=1.0, base=40.0):
    """item_shown + answer for each item; one frame every 5 s."""
    ev, fr, t, seq = [], [], 2.0, start_seq
    for i in range(n_items):
        ev.append(dict(seq=seq, t=round(t, 2), type="item_shown", item=i))
        seq += 1
        t += max(2.0, rng.lognormvariate(math.log(base * speed), 0.35))
        ev.append(dict(seq=seq, t=round(t, 2), type="answer", item=i, option=answers[i]))
        seq += 1
        t += 1.5
    k = 0.0
    while k < t:
        fr.append(dict(seq=seq, t=round(k, 1), faces=1, face_visible=True, gaze="centre", brightness=120, blur=0.1))
        seq += 1
        k += 5
    return ev, fr, seq


class T1_Auth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        cls.seeded = seed(reset=True, n_live=3)

    def test_roles(self):
        a, r, cand = Client(app), Client(app), Client(app)
        self.assertEqual(login(a, email="admin@fairproctor.demo", password="Admin@2026")["role"], "admin")
        self.assertEqual(login(r, email="reviewer@fairproctor.demo", password="Review@2026")["role"], "reviewer")
        t = self.seeded["team"][0]
        self.assertEqual(login(cand, roll_no=t["roll_no"], code=t["code"].lower())["role"], "candidate")
        self.assertEqual(cand.get("/api/review/queue").status_code, 403)
        self.assertEqual(cand.get("/api/admin/tests").status_code, 403)
        self.assertEqual(Client(app).get("/api/exam/me").status_code, 401)
        self.assertEqual(r.get("/api/admin/tests").status_code, 403)

    def test_wrong_login_locks(self):
        c = Client(app)
        for _ in range(config.MAX_LOGIN_FAILS):
            self.assertEqual(c.post("/api/auth/login", json=dict(email="reviewer@fairproctor.demo", password="nope")).status_code, 401)
        self.assertEqual(c.post("/api/auth/login", json=dict(email="reviewer@fairproctor.demo", password="Review@2026")).status_code, 429)
        with db.tx() as con:   # unlock for the other tests
            con.execute("UPDATE users SET locked_until = NULL WHERE email = 'reviewer@fairproctor.demo'")

    def test_no_signup_two_apps_logout(self):
        c = Client(app)                                  # Bearer token only, no cookies (cross-site frontend)
        r = c.post("/api/auth/signup", json=dict(name="Asha Verma", email="asha@example.com", password="exam2026ok"))
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (410, "signup_disabled"))   # the admin makes accounts
        t, t2 = self.seeded["team"][0], self.seeded["team"][1]
        # the candidate app takes only candidates, the staff app only reviewers and admins
        staff_in_cand = c.post("/api/auth/login", json=dict(email="admin@fairproctor.demo", password="Admin@2026", app="candidate"))
        self.assertEqual((staff_in_cand.status_code, staff_in_cand.json()["error"]["code"]), (403, "wrong_app"))
        cand_in_staff = c.post("/api/auth/login", json=dict(roll_no=t["roll_no"], code=t["code"], app="staff"))
        self.assertEqual(cand_in_staff.json()["error"]["code"], "wrong_app")
        self.assertEqual(login(Client(app), email="reviewer@fairproctor.demo", password="Review@2026", app="staff")["role"], "reviewer")
        self.assertEqual(login(c, roll_no=t2["roll_no"], code=t2["code"], app="candidate")["role"], "candidate")
        self.assertEqual(c.post("/api/exam/join", json=dict(join_code="fp-demo26")).json()["error"]["code"], "signup_disabled")
        again = Client(app)
        login(again, roll_no=t2["roll_no"], code=t2["code"])
        self.assertEqual(c.post("/api/auth/logout").status_code, 200)
        self.assertEqual(c.get("/api/me").json()["error"]["code"], "not_logged_in")   # revoked token
        self.assertEqual(again.get("/api/me").status_code, 200)                       # other logins unaffected
        c.token = "not-a-jwt"
        self.assertEqual(c.get("/api/me").status_code, 401)
        # one-click demo (demo mode only): a fresh candidate already in the demo test
        d = Client(app)
        made = d.post("/api/demo/candidate", json=dict(kind="mcq", language="hi"))
        self.assertEqual(made.status_code, 201, made.text)
        self.assertEqual(d.get("/api/exam/me").json()["test"]["n_items"], 30)
        self.assertTrue(d.get("/api/me").json()["roll_no"].startswith("DEMO"))

    def test_profile_and_password(self):
        a = Client(app)                                       # staff accounts are made by an admin (no sign-up)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        self.assertEqual(a.post("/api/admin/users", json=dict(role="reviewer", name="Ravi Kumar", email="ravi@example.com",
                                                              password="first2026ok")).status_code, 201)
        c = Client(app)
        login(c, email="ravi@example.com", password="first2026ok")
        me = c.get("/api/me").json()
        self.assertTrue(me["has_password"])
        self.assertIn("created_at", me)
        r = c.request("PATCH", "/api/me", json_body=dict(name="Ravi K. Kumar", language="hi"))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["name"], r.json()["language"]), ("Ravi K. Kumar", "hi"))
        self.assertEqual(c.request("PATCH", "/api/me", json_body=dict(language="fr")).status_code, 422)
        self.assertEqual(c.request("PATCH", "/api/me", json_body=dict(role="admin")).status_code, 422)   # cannot promote yourself
        other = Client(app)                                   # a second device, logged in before the change
        login(other, email="ravi@example.com", password="first2026ok")
        cp = lambda cur, new: c.post("/api/auth/change-password", json=dict(current_password=cur, new_password=new))
        self.assertEqual(cp("wrong-one1", "second2026ok").json()["error"]["code"], "wrong_password")
        self.assertEqual(cp("first2026ok", "first2026ok").json()["error"]["code"], "same_password")
        self.assertEqual(cp("first2026ok", "short").status_code, 422)
        r = cp("first2026ok", "second2026ok")
        self.assertEqual(r.status_code, 200, r.text)
        c.token = r.json()["access_token"]                    # this device gets a fresh token
        self.assertEqual(c.get("/api/me").status_code, 200)
        self.assertEqual(other.get("/api/me").json()["error"]["code"], "session_expired")   # other devices are logged out
        self.assertEqual(Client(app).post("/api/auth/login", json=dict(email="ravi@example.com", password="first2026ok")).status_code, 401)
        login(Client(app), email="ravi@example.com", password="second2026ok")
        cand = Client(app)                                    # roll no. + code candidates have no password to change
        with db.tx() as con:
            sit = db.one(con, "SELECT id FROM sittings ORDER BY id LIMIT 1")["id"]
            from backend.security import hash_secret
            con.insert("INSERT INTO users (role, name, roll_no, sitting_id, secret_hash) VALUES ('candidate', 'Roll One', 'R-001', ?, ?)",
                       (sit, hash_secret("ABC123")))
        login(cand, roll_no="R-001", code="abc123")
        self.assertFalse(cand.get("/api/me").json()["has_password"])
        self.assertEqual(cand.request("PATCH", "/api/me", json_body=dict(name="Someone Else")).json()["error"]["code"], "name_locked")
        self.assertEqual(cand.request("PATCH", "/api/me", json_body=dict(language="hi")).json()["language"], "hi")
        self.assertEqual(cand.post("/api/auth/change-password", json=dict(current_password="ABC123", new_password="new2026pass")
                                   ).json()["error"]["code"], "no_password")

    def test_bad_body(self):
        r = Client(app).post("/api/auth/login", json=dict(email="x"))
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json()["error"]["code"], "invalid")


class T2_AdminAndExam(unittest.TestCase):
    """A brand-new test made through the admin API, two candidates, close, score, review, appeal, delete."""

    def test_full_cycle(self):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        a = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        tid = a.post("/api/admin/tests", json=dict(title="Mini test", duration_min=20)).json()["id"]
        bad = a.post(f"/api/admin/tests/{tid}/items", data="text,option_a,option_b,correct\nQ,1,2,Z\n",
                     headers={"content-type": "text/csv"})
        self.assertEqual(bad.json()["error"]["code"], "bad_rows")
        r = a.post(f"/api/admin/tests/{tid}/items", data=ITEMS_CSV, headers={"content-type": "text/csv"})
        self.assertEqual(r.json()["n_items"], 5)
        made = a.post("/api/admin/sittings", json=dict(test_id=tid, title="Mini sitting", starts_at="2026-01-01T10:00:00+05:30",
                                                         ends_at="2030-01-01T10:00:00+05:30")).json()
        sid = made["id"]
        self.assertTrue(made["join_code"].startswith("FP-"))
        up = a.post(f"/api/admin/sittings/{sid}/candidates", data="roll_no,name,language\nR1,Asha,hi\nR2,Ravi,en\n",
                    headers={"content-type": "text/csv"}).json()
        self.assertEqual(up["n"], 2)
        codes = {c["roll_no"]: c["code"] for c in up["candidates"]}
        c1 = Client(app)
        login(c1, roll_no="R1", code=codes["R1"])
        self.assertEqual(c1.post("/api/exam/start", json={}).json()["error"]["code"], "no_consent")
        self.assertEqual(c1.post("/api/exam/consent", json=dict(version="old", understood=True)).status_code, 409)
        no_cam = c1.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True, camera_ok=False))
        self.assertEqual((no_cam.status_code, no_cam.json()["error"]["code"]), (422, "camera_required"))
        self.assertEqual(c1.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True,
                                                                 precheck_share_ok=False)).status_code, 200)
        self.assertEqual(c1.post("/api/exam/precheck", json=dict(brightness=90)).json()["stored"], False)
        self.assertEqual(c1.post("/api/exam/start", json={}).json()["error"]["code"], "not_live")
        a.post(f"/api/admin/sittings/{sid}/open")
        st = c1.post("/api/exam/start", json=dict(device="phone", bandwidth_class="low")).json()
        self.assertEqual(len(st["items"]), 5)
        self.assertNotIn("correct_option", str(st["items"]))           # the key never reaches the browser
        # camera snapshots at flagged moments: small JPEGs only, stored once, seen by the candidate and reviewers
        jpg = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 300).decode()
        snap = dict(t=12.5, reason="two_people", phase="at", image=jpg)
        self.assertTrue(c1.post("/api/exam/snapshot", json=snap).json()["stored"])
        self.assertEqual(c1.post("/api/exam/snapshot", json=snap).json()["reason"], "duplicate")
        png = dict(snap, image=base64.b64encode(b"\x89PNG" + b"0" * 300).decode())
        self.assertEqual(c1.post("/api/exam/snapshot", json=png).json()["error"]["code"], "bad_image")
        self.assertEqual(c1.post("/api/exam/snapshot", json=dict(snap, reason="other")).status_code, 422)
        mine = c1.get("/api/exam/snapshots").json()
        self.assertEqual((len(mine["snapshots"]), mine["snapshots"][0]["label"]), (1, "A second person in view"))
        self.assertTrue(mine["snapshots"][0]["image"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(len(a.get(f"/api/review/sessions/{st['session_id']}/snapshots").json()["snapshots"]), 1)
        self.assertEqual(c1.get(f"/api/review/sessions/{st['session_id']}/snapshots").status_code, 403)
        from backend.services.snapshots import expire
        with db.tx() as con:
            self.assertEqual(expire(con, days=-1), 1)                  # past the snapshot retention: gone
        self.assertEqual(c1.get("/api/exam/snapshots").json()["snapshots"], [])
        rng = random.Random(1)
        ev, fr, _ = exam_events(rng, 5, ["B", "B", "A", "C", " 7 "])
        ev.insert(3, dict(seq=900, t=10, type="paste", item=1, chars=42))
        b = c1.post("/api/exam/events", json=dict(events=ev, frames=fr)).json()
        self.assertEqual(b["rejected"], 0)
        again = c1.post("/api/exam/events", json=dict(events=ev, frames=fr)).json()   # 2G retry: stored once
        self.assertEqual(again["saved"], 0)
        self.assertEqual(again["duplicates"], len(ev) + len(fr))
        with db.tx() as con:
            got = {r["item"]: r["correct"] for r in db.all_(con, "SELECT item, correct FROM events WHERE type='answer' AND session_id=?",
                                                              st["session_id"])}
        self.assertEqual(got, {0: 1, 1: 1, 2: 0, 3: 1, 4: 1})
        resumed = c1.post("/api/exam/start", json={}).json()          # refresh mid-exam resumes
        self.assertEqual(resumed["answers"]["2"], "A")
        self.assertEqual(c1.post("/api/exam/submit").json()["status"], "submitted")
        # R2 starts but never submits -> auto-submitted at close
        c2 = Client(app)
        login(c2, roll_no="R2", code=codes["R2"])
        c2.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
        c2.post("/api/exam/start", json={})
        ev2, fr2, _ = exam_events(rng, 5, ["B", "C", "B", "C", "8"])
        c2.post("/api/exam/events", json=dict(events=ev2, frames=fr2))
        self.assertEqual(c1.get("/api/exam/result").json()["state"], "pending")
        close = a.post(f"/api/admin/sittings/{sid}/close").json()
        self.assertEqual(close["auto_submitted"], 1)
        job = worker.wait_for(close["job_id"], timeout=120)
        self.assertEqual(job["status"], "done", job["message"])
        self.assertEqual(c2.post("/api/exam/events", json=dict(events=ev2)).json()["error"]["code"], "sitting_closed")
        r = Client(app)
        login(r, email="reviewer@fairproctor.demo", password="Review@2026")
        q = r.get(f"/api/review/queue?sitting_id={sid}&band=all").json()
        self.assertEqual(q["total"], 2)
        s1 = st["session_id"]
        d = r.get(f"/api/review/sessions/{s1}").json()
        self.assertIn("explanation", d)
        self.assertIsNone(d["identity"])                                  # no name before a confirmation
        self.assertEqual(r.post(f"/api/review/sessions/{s1}/decision", json=dict(decision="confirm", note="x")).status_code, 422)
        r.post(f"/api/review/sessions/{s1}/decision", json=dict(decision="confirm", note="Pasted 42 characters on Q2"))
        self.assertEqual(r.get(f"/api/review/sessions/{s1}").json()["identity"]["roll_no"], "R1")
        ex = next(e for e in r.get("/api/review/exams").json() if e["id"] == sid)   # exam-wise view
        self.assertEqual((ex["status"], ex["candidates"], ex["submitted"]), ("scored", 2, 2))
        self.assertEqual(sum(ex["bands"].values()), 2)
        self.assertEqual(ex["flagged"], ex["bands"]["review_first"] + ex["bands"]["review"])
        self.assertEqual(ex["confirmed"], 1)
        res = c1.get("/api/exam/result").json()
        self.assertEqual(res["state"], "confirmed")
        self.assertTrue(res["can_appeal"])
        self.assertEqual(c1.post("/api/exam/appeal", json=dict(text="I copied my own rough work from notepad.")).status_code, 201)
        self.assertEqual(c1.post("/api/exam/appeal", json=dict(text="second try here")).status_code, 409)
        ap = r.get("/api/review/appeals").json()
        self.assertEqual(len(ap), 1)
        r.post(f"/api/review/appeals/{ap[0]['id']}/decide", json=dict(outcome="overturned", response="Accepted: own notes."))
        self.assertEqual(c1.get("/api/exam/result").json()["state"], "cleared_after_appeal")
        # deletion on request
        c1.post("/api/exam/delete-request")
        self.assertEqual(len(a.get("/api/admin/deletion-requests").json()), 1)
        self.assertEqual(a.delete(f"/api/admin/sessions/{s1}").json()["deleted"], True)
        with db.tx() as con:
            for t in ("events", "frame_stats", "scores", "appeals", "reviews", "consents"):
                self.assertEqual(db.one(con, f"SELECT COUNT(*) n FROM {t} WHERE session_id = ?", s1)["n"], 0, t)
            self.assertIsNone(db.one(con, "SELECT 1 FROM users WHERE roll_no = 'R1'"))
        actions = [x["action"] for x in a.get("/api/admin/audit?limit=200").json()]
        for want in ("login", "consent", "exam_started", "sitting_closed", "sitting_scored", "review_confirm",
                     "appeal_sent", "appeal_overturned", "session_deleted"):
            self.assertIn(want, actions)


class T3_DemoCollusion(unittest.TestCase):
    """The live demo: 200 reference sessions + 3 team members, two of whom share answers."""

    def test_demo(self):
        from backend.scripts.seed_demo import seed
        from backend.services.scoring import model_bundle
        info = seed(reset=True, n_live=3)
        st = model_bundle()["stats"]
        rng = random.Random(11)
        with db.tx() as con:
            key = {r["position"]: (r["kind"], r["correct_option"]) for r in
                   db.all_(con, "SELECT position, kind, correct_option FROM items WHERE test_id = ?", info["test_id"])}
        n = len(key)
        honest = [key[i][1] if rng.random() < 0.65 else rng.choice("ABCD") if key[i][0] == "mcq" else "0" for i in range(n)]
        # B and C: one shared answer sheet, including the same unusual wrong options
        shared = [key[i][1] if (key[i][0] == "short" or i % 3) else
                  next(L for L in "DCBA" if L != key[i][1]) for i in range(n)]
        clients = []
        for t in info["team"]:
            c = Client(app)
            login(c, roll_no=t["roll_no"], code=t["code"])
            c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
            c.post("/api/exam/start", json=dict(device="phone"))
            clients.append(c)
        # A: honest pace from the paper's own typical times
        ev, fr, t, seq = [], [], 2.0, 1
        for i in range(n):
            ev.append(dict(seq=seq, t=round(t, 1), type="item_shown", item=i)); seq += 1
            t += math.exp(st.med_logt[i] + rng.gauss(0, 0.3))
            ev.append(dict(seq=seq, t=round(t, 1), type="answer", item=i, option=honest[i])); seq += 1
            t += 2
        for k in range(0, int(t), 5):
            fr.append(dict(seq=seq, t=k, faces=2 if 300 <= k < 310 else 1, face_visible=True,
                           gaze="down" if k % 60 < 15 else "centre", brightness=60, blur=0.3)); seq += 1
        clients[0].post("/api/exam/events", json=dict(events=ev, frames=fr))
        # B and C: same answers, each a few seconds apart, much faster than the paper's typical time on hard items
        for j, c in enumerate(clients[1:]):
            ev, fr, t, seq = [], [], 2.0, 1
            for i in range(n):
                ev.append(dict(seq=seq, t=round(t, 1), type="item_shown", item=i)); seq += 1
                t += max(4.0, 0.35 * math.exp(st.med_logt[i])) + 3 * j
                ev.append(dict(seq=seq, t=round(t, 1), type="answer", item=i, option=shared[i])); seq += 1
                t += 1 - 3 * j if j else 1
            for k in range(0, int(t), 5):
                fr.append(dict(seq=seq, t=k, faces=1, face_visible=True, gaze="centre", brightness=120, blur=0.1)); seq += 1
            c.post("/api/exam/events", json=dict(events=ev, frames=fr))
        # live monitor while they are still writing: the trained model on partial answers + raw alerts
        rv = Client(app)
        login(rv, email="reviewer@fairproctor.demo", password="Review@2026")
        self.assertIn(info["sitting_id"], [s["id"] for s in rv.get("/api/review/live").json()])   # (the coding sitting is live too)
        snap = rv.get(f"/api/review/live/{info['sitting_id']}").json()
        self.assertEqual(snap["counts"]["in_progress"], 3)
        by_risk = {c["session_id"]: c for c in snap["candidates"]}
        self.assertEqual(len(by_risk), 3)
        self.assertTrue(all("name" not in c for c in snap["candidates"]))         # reviewers see pseudonyms only
        matched = [c for c in snap["candidates"] if "match" in c["families"] and c["risk"] >= 50]   # flagged for matching
        self.assertEqual(len(matched), 2, [(c["who"], c["risk"], c["families"]) for c in snap["candidates"]])
        self.assertTrue(all(c["risk"] < 50 for c in snap["candidates"] if c not in matched))     # the honest one stays clear
        self.assertNotIn("L-", " ".join(c["headline"] for c in snap["candidates"]))  # partners by pseudonym
        self.assertIn("second_person", {a["kind"] for a in snap["alerts"]})
        self.assertEqual(rv.get("/api/review/live/99999").status_code, 404)
        for c in clients:
            c.post("/api/exam/submit")
        a = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        t0 = time.time()
        job = worker.wait_for(a.post(f"/api/admin/sittings/{info['sitting_id']}/close").json()["job_id"], timeout=600)
        self.assertEqual(job["status"], "done", job["message"])
        print(f"\n  demo sitting scored in {time.time() - t0:.1f} s: {job['message']}")
        r = Client(app)
        login(r, email="reviewer@fairproctor.demo", password="Review@2026")
        rows = r.get(f"/api/review/queue?sitting_id={info['sitting_id']}&band=all&limit=500").json()["rows"]
        live = {x["session_id"]: x for x in rows if not x["reference"]}
        with db.tx() as con:
            roll = {s["id"]: u for s in db.all_(con, "SELECT id, user_id FROM sessions WHERE is_synthetic = 0")
                    for u in [db.one(con, "SELECT roll_no FROM users WHERE id = ?", s["user_id"])["roll_no"]]}
        for sid, x in live.items():
            print(f"  {roll[sid]}: band={x['band']:<12} priority={x['priority']:>3} rank={x['rank']:>3}  {x['headline'][:90]}")
        by = {roll[s]: x for s, x in live.items()}
        self.assertEqual(by["TEAM01"]["band"], "clear")
        self.assertNotEqual(by["TEAM02"]["band"], "clear")
        self.assertNotEqual(by["TEAM03"]["band"], "clear")
        self.assertIn("match", by["TEAM02"]["families"])
        a_detail = r.get(f"/api/review/sessions/{[s for s in live if roll[s] == 'TEAM01'][0]}").json()
        print("  TEAM01 not counted:", a_detail["explanation"]["context"])
        b_detail = r.get(f"/api/review/sessions/{[s for s in live if roll[s] == 'TEAM02'][0]}").json()
        self.assertNotIn("L-", " ".join(str(x) for x in b_detail["explanation"]["reasons"]))   # partner shown by pseudonym


if __name__ == "__main__":
    unittest.main(verbosity=2)

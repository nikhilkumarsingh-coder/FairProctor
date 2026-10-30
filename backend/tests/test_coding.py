"""Coding tests end to end through the API: problems, Run, Submit, marks, and that hidden tests never leak.

    python -m unittest backend.tests.test_coding -v
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="fp-code-")
os.environ.pop("DATABASE_URL", None)
if os.environ.get("FP_TEST_DATABASE_URL"):
    os.environ["FP_DATABASE_URL"] = os.environ["FP_TEST_DATABASE_URL"]
else:
    os.environ.pop("FP_DATABASE_URL", None)
    os.environ["FP_DB"] = os.path.join(TMP, "code.db")
os.environ["FP_RETENTION"] = "0"
os.environ.setdefault("FP_ADMIN_EMAIL", "admin@x.test")
os.environ.setdefault("FP_ADMIN_PASSWORD", "Admin2026x")

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.tests.client import Client  # noqa: E402

SECRET = "HIDDEN-EXPECTED-91827"
PROBLEMS = {"problems": [
    dict(title="Double it", statement="Read n, print 2n.", time_limit=1,
         starter={"python": "n = int(input())\n# print 2n\n"},
         samples=[dict(input="3\n", output="6\n")],
         tests=[dict(input="5\n", output="10\n"), dict(input="-4\n", output="-8\n"), dict(input="91827\n", output="183654\n")],
         solution=dict(language="python", code="print(2*int(input()))\n")),
    dict(title="Echo", statement="Print the line.", languages=["python", "javascript"],
         samples=[dict(input="hi\n", output="hi\n")], tests=[dict(input=SECRET + "\n", output=SECRET + "\n")]),
]}


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class Coding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        db.reset_database()
        db.migrate()
        cls.a = Client(app)
        from backend.app import bootstrap_admin
        bootstrap_admin()
        login(cls.a, email="admin@x.test", password="Admin2026x")

    def test_coding_flow(self):
        a = self.a
        tid = a.post("/api/admin/tests", json=dict(title="Coding round", duration_min=60, kind="coding")).json()["id"]
        bad = json.loads(json.dumps(PROBLEMS))
        bad["problems"][0]["solution"]["code"] = "print(3*int(input()))\n"
        r = a.post(f"/api/admin/tests/{tid}/problems", json=bad)
        self.assertEqual(r.json()["error"]["code"], "bad_rows")
        self.assertIn("wrong_answer", r.json()["error"]["rows"][0]["problem"])
        self.assertEqual(a.post(f"/api/admin/tests/{tid}/items", data="text,option_a,option_b,correct\nx,1,2,A\n",
                                headers={"content-type": "text/csv"}).json()["error"]["code"], "coding_test")
        r = a.post(f"/api/admin/tests/{tid}/problems", json=PROBLEMS)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), dict(n_items=2, checked=1))
        detail = a.get(f"/api/admin/tests/{tid}").json()
        self.assertEqual(detail["kind"], "coding")
        self.assertEqual(len(detail["problems"][0]["hidden"]), 3)                 # admins see hidden tests
        now = dt.datetime.now(dt.timezone.utc)
        sit = a.post("/api/admin/sittings", json=dict(test_id=tid, title="Coding sitting",
                                                      starts_at=(now - dt.timedelta(minutes=5)).isoformat(),
                                                      ends_at=(now + dt.timedelta(hours=2)).isoformat())).json()
        a.post(f"/api/admin/sittings/{sit['id']}/open")
        langs = Client(app).get("/api/code/languages").json()
        self.assertTrue(next(x for x in langs if x["key"] == "python")["available"])

        up = a.post(f"/api/admin/sittings/{sit['id']}/candidates", data="roll_no,name\nC1,Coder One\n",
                    headers={"content-type": "text/csv"}).json()
        c = Client(app)
        c.post("/api/auth/login", json=dict(roll_no="C1", code=up["candidates"][0]["code"], app="candidate"))
        self.assertEqual(c.get("/api/exam/me").json()["test"]["kind"], "coding")
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
        start = c.post("/api/exam/start", json=dict(device="desktop"))
        self.assertEqual(start.status_code, 200, start.text)
        s = start.json()
        self.assertNotIn(SECRET, start.text)                                       # hidden tests never reach the browser
        self.assertNotIn("183654", start.text)
        p0 = s["items"][0]
        self.assertEqual((p0["kind"], p0["code"]["title"], p0["code"]["hidden_tests"]), ("code", "Double it", 3))
        self.assertEqual(p0["code"]["samples"], [dict(input="3\n", output="6\n")])
        self.assertEqual([l["key"] for l in s["items"][1]["code"]["languages"]][:1], ["python"])

        run = lambda **b: c.post("/api/exam/code/run", json=dict(item=0, language="python", **b)).json()
        sub = lambda **b: c.post("/api/exam/code/submit", json=dict(item=0, language="python", **b)).json()
        r = run(code="print(int(input())+1)\n")
        self.assertEqual((r["verdict"], r["tests"][0]["output"].strip(), r["tests"][0]["expected"].strip()), ("wrong_answer", "4", "6"))
        r = run(code="print(2*int(input()))\n", input="21")
        self.assertEqual((r["mode"], r["status"], r["output"].strip()), ("custom", "ok", "42"))
        r = sub(code="n=int(input())\nprint(n+n if n>0 else 0)\n", t=120.5)
        self.assertEqual((r["verdict"], r["passed"], r["total"]), ("wrong_answer", 2, 3))
        self.assertNotIn(SECRET, json.dumps(r))
        self.assertTrue(all(set(t) == {"n", "status"} for t in r["tests"]))      # pass/fail only
        r = sub(code="print(2*int(input()))\n", t=200)
        self.assertEqual((r["verdict"], r["passed"]), ("accepted", 3))
        r = sub(code="print(0)\n", t=250)                                           # a worse resubmit does not lower marks
        self.assertEqual(r["passed"], 0)
        bad = c.post("/api/exam/code/submit", json=dict(item=1, language="java", code="class Main{}"))
        self.assertEqual(bad.json()["error"]["code"], "language_not_allowed")
        self.assertEqual(c.post("/api/exam/code/submit", json=dict(item=9, language="python", code="x")).json()["error"]["code"], "no_problem")
        ev = c.post("/api/exam/events", json=dict(events=[
            dict(seq=1, t=1, type="item_shown", item=0),
            dict(seq=2, t=20, type="code_typing", item=0, meta=dict(ins=40, dele=3, keys=45, max_ins=6, len=40)),
            dict(seq=3, t=30, type="paste", item=0, chars=380)])).json()
        self.assertEqual((ev["saved"], ev["rejected"]), (3, 0))
        self.assertEqual(c.post("/api/exam/events", json=dict(events=[dict(seq=4, t=31, type="code_typing", item=0,
                                                                             meta={"x" * 30: 1})])).status_code, 422)
        state = c.post("/api/exam/start", json={}).json()["code_state"]
        self.assertEqual(state["0"]["best"]["passed"], 3)
        self.assertEqual(state["0"]["code"], "print(0)\n")                            # last code restores the editor
        c.post("/api/exam/submit")
        res = c.get("/api/exam/result").json()
        self.assertEqual(res["coding"]["marks"], 100.0)
        self.assertEqual(res["coding"]["out_of"], 200)
        self.assertEqual(res["coding"]["problems"][1]["verdict"], "not_submitted")
        self.assertEqual(c.post("/api/exam/code/run", json=dict(item=0, language="python", code="print(1)")).json()["error"]["code"],
                         "not_in_progress")


if __name__ == "__main__":
    unittest.main()


P1 = "import sys\nvals = sys.stdin.read().split()\nn = int(vals[0])\nnums = set(int(v) for v in vals[1:1 + n])\nbig = max(nums)\nnums.discard(big)\nprint(max(nums) if nums else -1)\n"
P2 = ("import sys\nrows = sys.stdin.read().split()\nt = int(rows[0])\nclose = {')': '(', ']': '[', '}': '{'}\nfor word in rows[1:1 + t]:\n"
      "    stack = []\n    good = True\n    for ch in word:\n        if ch in '([{':\n            stack.append(ch)\n"
      "        elif stack and stack[-1] == close[ch]:\n            stack.pop()\n        else:\n            good = False\n            break\n"
      "    print('YES' if good and not stack else 'NO')\n")
P3 = ("import sys\nfrom collections import defaultdict\nnums = sys.stdin.read().split()\nn, k = int(nums[0]), int(nums[1])\n"
      "counts = defaultdict(int)\npairs = 0\nfor v in map(int, nums[2:2 + n]):\n    pairs += counts[k - v]\n    counts[v] += 1\nprint(pairs)\n")
WEB = {0: "import sys\nd=sys.stdin.read().split();n=int(d[0]);a=set(map(int,d[1:1+n]))\ns=sorted(a,reverse=True)\nprint(s[1] if len(s)>1 else -1)\n",
       2: P3.replace("pairs", "ans").replace("counts", "seen")}


class CodingDemo(unittest.TestCase):
    """The seeded coding sitting: an honest coder, a web paster and a copier, scored live and at close."""

    def test_demo_coding(self):
        from backend.jobs import worker
        from backend.scripts.seed_demo import seed
        info = seed(reset=True, n_live=3)["coding"]
        sid = info["sitting_id"]
        cl = {}
        for t in info["team"]:
            c = Client(app)
            login(c, roll_no=t["roll_no"], code=t["code"])
            c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
            self.assertEqual(c.post("/api/exam/start", json=dict(device="desktop")).status_code, 200)
            cl[t["roll_no"]] = c

        def typed(c, item, t0, code, cps=3.0, edit=0.25):
            """item_shown + typing windows of 5 s that add up to the program, with corrections."""
            ev, seq, t, length = [dict(seq=1000 * item + 1, t=t0, type="item_shown", item=item)], 1000 * item + 2, t0 + 30, 0
            total = int(len(code) * (1 + edit))
            while total > 0:
                ins = min(total, int(cps * 5))
                dele = int(ins * edit)
                length += ins - dele
                total -= ins
                ev.append(dict(seq=seq, t=t, type="code_typing", item=item, meta=dict(ins=ins, dele=dele, keys=ins + dele, max_ins=2, len=length)))
                seq += 1
                t += 5 if seq % 7 else 25
            r = c.post("/api/exam/events", json=dict(events=ev))
            self.assertEqual(r.json()["rejected"], 0, r.text)
            return t

        def submit(c, item, code, t, language="python"):
            r = c.post("/api/exam/code/submit", json=dict(item=item, language=language, code=code, t=t)).json()
            self.assertEqual(r["verdict"], "accepted", (item, r))
            return r

        # CODE01: honest — types each program, tries the samples, then submits
        a, t = cl["CODE01"], 20.0
        for item, code in enumerate((P1, P2, P3)):
            t = typed(a, item, t, code)
            a.post("/api/exam/code/run", json=dict(item=item, language="python", code=code, t=t + 5))
            submit(a, item, code, t + 20)
            t += 120
        # CODE02: leaves the tab, comes back, pastes a whole web solution, submits within a minute (problems 1 and 3)
        b = cl["CODE02"]
        for item, t0 in ((0, 300.0), (2, 1500.0)):
            b.post("/api/exam/events", json=dict(events=[
                dict(seq=10 * item + 1, t=t0, type="item_shown", item=item), dict(seq=10 * item + 2, t=t0 + 20, type="focus_lost", item=item),
                dict(seq=10 * item + 3, t=t0 + 140, type="focus_gained", item=item),
                dict(seq=10 * item + 4, t=t0 + 150, type="paste", item=item, chars=len(WEB[item]))]))
            submit(b, item, WEB[item], t0 + 190)
        # CODE03: pastes CODE01's programs (verbatim) after CODE01 had them
        c3 = cl["CODE03"]
        for item, code, t0 in ((0, P1, 900.0), (1, P2, 1300.0)):
            c3.post("/api/exam/events", json=dict(events=[
                dict(seq=10 * item + 1, t=t0, type="item_shown", item=item), dict(seq=10 * item + 2, t=t0 + 30, type="focus_lost", item=item),
                dict(seq=10 * item + 3, t=t0 + 80, type="focus_gained", item=item),
                dict(seq=10 * item + 4, t=t0 + 85, type="paste", item=item, chars=len(code))]))
            submit(c3, item, code, t0 + 120)

        # live monitor: the coding model on what is there so far
        rv = Client(app)
        login(rv, email="reviewer@fairproctor.demo", password="Review@2026")
        snap = rv.get(f"/api/review/live/{sid}").json()
        self.assertEqual(snap["kind"], "coding")
        live = {c["session_id"]: c for c in snap["candidates"]}
        self.assertEqual(len(live), 3)
        risky = sorted(snap["candidates"], key=lambda c: -(c["risk"] or 0))
        print("\n  live:", [(c["who"], c["risk"], c["families"]) for c in risky])
        self.assertTrue(all(c["risk"] is not None for c in risky))
        self.assertIn("paste", {a["kind"] for a in snap["alerts"]})

        for c in cl.values():
            c.post("/api/exam/submit")
        adm = Client(app)
        login(adm, email="admin@fairproctor.demo", password="Admin@2026")
        job = worker.wait_for(adm.post(f"/api/admin/sittings/{sid}/close").json()["job_id"], timeout=600)
        self.assertEqual(job["status"], "done", job["message"])
        rows = rv.get(f"/api/review/queue?sitting_id={sid}&band=all&limit=500").json()["rows"]
        with db.tx() as con:
            roll = {r["id"]: r["roll_no"] for r in db.all_(con, """SELECT s.id, u.roll_no FROM sessions s JOIN users u ON u.id = s.user_id
                                                                   WHERE s.sitting_id = ?""", sid)}
        by = {roll[r["session_id"]]: r for r in rows if r["session_id"] in roll}
        for k, r in sorted(by.items()):
            print(f"  {k}: band={r['band']:<12} priority={r['priority']:>3} families={r['families']} {r['headline'][:100]}")
        self.assertNotEqual(by["CODE02"]["band"], "clear")
        self.assertIn("paste", by["CODE02"]["families"])
        self.assertNotEqual(by["CODE03"]["band"], "clear")
        self.assertIn("code_match", by["CODE03"]["families"])
        planted = [r for r in rows if r["reference"] and r["band"] == "review_first"]
        self.assertTrue(planted, "planted reference malpractice should be in review first")
        d = rv.get(f"/api/review/sessions/{by['CODE03']['session_id']}").json()
        self.assertEqual(d["kind"], "coding")
        m = next(c["match"] for c in d["code"] if c.get("match"))
        self.assertEqual(m["code"], P1 if d["code"][0].get("match") else P2)        # the partner's program, for the reviewer
        self.assertTrue(m["pseudonym"].startswith("Candidate "))
        self.assertNotIn("L-", json.dumps(d["explanation"]["reasons"]))           # ids only as pseudonyms in the text
        res = cl["CODE03"].get("/api/exam/result").json()
        self.assertEqual(res["test_kind"], "coding")
        self.assertEqual(res["coding"]["marks"], 200.0)
        self.assertTrue(res["points"])
        self.assertNotIn("L-", json.dumps(res))

"""Safe Exam Browser: off by default; when an admin requires it, only SEB with the sitting's Config Key can write the test.

    python -m unittest backend.tests.test_seb -v
"""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="fp-seb-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("FP_DATABASE_URL", None)
os.environ["FP_DB"] = os.path.join(TMP, "test.db")
os.environ["FP_RETENTION"] = "0"

from backend import config  # noqa: E402
from backend.app import app  # noqa: E402
from backend.tests.client import Client  # noqa: E402

CK = hashlib.sha256(b"an SEB settings file").hexdigest()          # what the SEB Config Tool shows as the Config Key
ITEMS = "text,option_a,option_b,option_c,option_d,correct,kind\nWhat is 2 + 2?,3,4,5,6,B,mcq\nWhat is 3 + 3?,5,6,7,8,B,mcq\n"


def ck_hash(url: str, key: str = CK) -> str:
    return hashlib.sha256((url + key).encode()).hexdigest()


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class SafeExamBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        a = cls.admin = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        tid = a.post("/api/admin/tests", json=dict(title="SEB test", duration_min=20)).json()["id"]
        a.post(f"/api/admin/tests/{tid}/items", data=ITEMS, headers={"content-type": "text/csv"})
        cls.sid = a.post("/api/admin/sittings", json=dict(test_id=tid, title="Laptop sitting", starts_at="2026-01-01T10:00:00+05:30",
                                                            ends_at="2030-01-01T10:00:00+05:30")).json()["id"]
        up = a.post(f"/api/admin/sittings/{cls.sid}/candidates", data="roll_no,name\nS1,Asha\nS2,Ravi\n",
                    headers={"content-type": "text/csv"}).json()
        cls.codes = {c["roll_no"]: c["code"] for c in up["candidates"]}
        a.post(f"/api/admin/sittings/{cls.sid}/open")

    def cand(self, roll):
        c = Client(app)
        login(c, roll_no=roll, code=self.codes[roll])
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
        return c

    def seb(self, **b):
        return self.admin.request("PUT", f"/api/admin/sittings/{self.sid}/seb", json_body=b)

    def test_1_off_by_default(self):
        c = self.cand("S1")
        self.assertEqual(c.get("/api/exam/me").json()["seb"], dict(required=False))
        self.assertEqual(c.post("/api/exam/start", json={}).status_code, 200)

    def test_2_admin_checks(self):
        self.assertEqual(self.seb(required=True).json()["error"]["code"], "config_key_needed")
        self.assertEqual(self.seb(required=True, config_key="not-a-key").json()["error"]["code"], "bad_config_key")
        self.assertEqual(self.seb(required=False, file_base64="@@@").json()["error"]["code"], "bad_seb_file")
        c = self.cand("S1")
        self.assertEqual(c.request("PUT", f"/api/admin/sittings/{self.sid}/seb", json_body=dict(required=False)).status_code, 403)

    def test_3_required(self):
        f = base64.b64encode(b"<plist>seb settings</plist>").decode()
        out = self.seb(required=True, config_key=CK.upper(), file_base64=f).json()
        self.assertTrue(out["required"] and out["file_uploaded"] and out["config_key_set"])
        detail = self.admin.get(f"/api/admin/sittings/{self.sid}").json()
        self.assertNotIn("seb_config_key", detail)                       # the key and file never go back out in lists
        self.assertTrue(detail["seb"]["required"])
        got = Client(app).get(out["config_url"])                         # SEB itself downloads it: no login
        self.assertEqual((got.status_code, got.content), (200, b"<plist>seb settings</plist>"))
        self.assertEqual(Client(app).get("/api/seb/wrong.seb").status_code, 404)

        c = self.cand("S2")
        me = c.get("/api/exam/me").json()["seb"]
        self.assertTrue(me["required"])
        self.assertFalse(me["verified"])
        self.assertEqual(me["config_url"], out["config_url"])
        # a normal browser cannot start, send answers or submit
        r = c.post("/api/exam/start", json={})
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "seb_required"))
        self.assertTrue(r.json()["error"]["seb"]["required"])
        self.assertEqual(c.post("/api/exam/submit").status_code, 403)
        # a forged or stale key is refused
        page = "http://testserver/exam/run"
        bad = {"X-SEB-Page-Url": page, "X-SEB-Config-Key-Hash": ck_hash(page, "0" * 64)}
        self.assertEqual(c.post("/api/exam/start", json={}, headers=bad).status_code, 403)
        other_site = {"X-SEB-Page-Url": "http://evil.example/exam", "X-SEB-Config-Key-Hash": ck_hash("http://evil.example/exam")}
        self.assertEqual(c.post("/api/exam/start", json={}, headers=other_site).status_code, 403)
        # SEB's JavaScript API value for the page (the React app sends it with every call)
        ok = {"X-SEB-Page-Url": page + "#q3", "X-SEB-Config-Key-Hash": ck_hash(page)}
        st = c.post("/api/exam/start", json={}, headers=ok)
        self.assertEqual(st.status_code, 200, st.text)
        self.assertTrue(c.get("/api/exam/me", headers=ok).json()["seb"]["verified"])
        ev = dict(events=[dict(seq=1, t=2, type="item_shown", item=0), dict(seq=2, t=9, type="answer", item=0, option="B")])
        self.assertEqual(c.post("/api/exam/events", json=ev, headers=ok).json()["saved"], 2)
        # SEB's own header on this request's URL, also behind an HTTPS tunnel
        native = {"X-SafeExamBrowser-ConfigKeyHash": ck_hash("http://testserver/api/exam/events")}
        self.assertEqual(c.post("/api/exam/events", json=ev, headers=native).status_code, 200)
        tunnel = {"X-Forwarded-Proto": "https", "X-Forwarded-Host": "abc.ngrok.app",
                  "X-SafeExamBrowser-ConfigKeyHash": ck_hash("https://abc.ngrok.app/api/exam/events")}
        self.assertEqual(c.post("/api/exam/events", json=ev, headers=tunnel).status_code, 200)
        self.assertEqual(c.post("/api/exam/submit", headers=ok).status_code, 200)

    def test_4_switch_off(self):
        self.assertFalse(self.seb(required=False, clear_file=True).json()["required"])
        self.assertEqual(self.cand("S1").get("/api/exam/me").json()["seb"], dict(required=False))


if __name__ == "__main__":
    unittest.main()

"""Device decided automatically: SEB is required on laptops only, phones get kiosk mode, a laptop pretending to be a
phone gets a "device check" flag (never an end), and leaving full screen is noted, never a rule.

    python -m unittest backend.tests.test_device -v
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import unittest

TMP = tempfile.mkdtemp(prefix="fp-device-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("FP_DATABASE_URL", None)
os.environ["FP_DB"] = os.path.join(TMP, "test.db")
os.environ["FP_RETENTION"] = "0"

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.services import rules  # noqa: E402
from backend.tests.client import Client  # noqa: E402

CK = hashlib.sha256(b"device test seb settings").hexdigest()
ITEMS = "text,option_a,option_b,option_c,option_d,correct,kind\nWhat is 2 + 2?,3,4,5,6,B,mcq\nWhat is 3 + 3?,5,6,7,8,B,mcq\n"
ANDROID = {"User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36"}
LAPTOP = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36"}
PHONE_SCREEN = dict(touch=5, w=412, h=915, coarse=True, fullscreen=True, wake_lock=True)
LAPTOP_SCREEN = dict(touch=0, w=1920, h=1080, coarse=False, fullscreen=True, wake_lock=True)


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class Device(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        a = cls.admin = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        tid = a.post("/api/admin/tests", json=dict(title="Device test", duration_min=20)).json()["id"]
        a.post(f"/api/admin/tests/{tid}/items", data=ITEMS, headers={"content-type": "text/csv"})
        cls.sid = a.post("/api/admin/sittings", json=dict(test_id=tid, title="SEB on laptops", starts_at="2026-01-01T10:00:00+05:30",
                                                            ends_at="2030-01-01T10:00:00+05:30")).json()["id"]
        up = a.post(f"/api/admin/sittings/{cls.sid}/candidates", data="roll_no,name\nD1,A\nD2,B\nD3,C\nD4,D\n",
                    headers={"content-type": "text/csv"}).json()
        cls.codes = {c["roll_no"]: c["code"] for c in up["candidates"]}
        a.post(f"/api/admin/sittings/{cls.sid}/open")
        r = a.request("PUT", f"/api/admin/sittings/{cls.sid}/seb", json_body=dict(required=True, config_key=CK))
        assert r.json()["required"], r.text

    def cand(self, roll, hdr):
        c = Client(app)
        login(c, roll_no=roll, code=self.codes[roll])
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True), headers=hdr)
        return c

    def info(self, roll):
        with db.tx() as con:
            s = db.one(con, "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.roll_no = ?", roll)
            return s["id"], rules.counts(con, s["id"])

    def test_laptop_needs_seb(self):
        c = self.cand("D1", LAPTOP)
        self.assertTrue(c.get("/api/exam/me", headers=LAPTOP).json()["seb"]["required"])
        r = c.post("/api/exam/start", json=dict(signals=LAPTOP_SCREEN), headers=LAPTOP)
        self.assertEqual((r.status_code, r.json()["error"]["code"]), (403, "seb_required"))

    def test_phone_gets_kiosk(self):
        c = self.cand("D2", ANDROID)
        me = c.get("/api/exam/me", headers=ANDROID).json()
        self.assertEqual(me["seb"], dict(required=False, exempt="phone"))
        self.assertTrue(me["kiosk"])
        st = c.post("/api/exam/start", json=dict(device="phone", signals=PHONE_SCREEN), headers=ANDROID)
        self.assertEqual(st.status_code, 200, st.text)
        self.assertTrue(st.json()["kiosk"])
        ev = dict(events=[dict(seq=1, t=5, type="fullscreen_exit"), dict(seq=2, t=9, type="fullscreen_enter")])
        self.assertEqual(c.post("/api/exam/events", json=ev, headers=ANDROID).json()["saved"], 2)
        _, cnt = self.info("D2")
        self.assertEqual(cnt["fullscreen_exits"], 1)
        self.assertEqual((cnt["device"]["mismatch"], cnt["device"]["seb_exempt"]), (False, True))
        self.assertEqual(rules.chips(cnt), [])                          # leaving full screen is never a rule
        self.assertEqual(rules.band_floor("clear", cnt), "clear")
        self.assertIn("fullscreen", [f["key"] for f in rules.flags(cnt)])

    def test_laptop_pretending_to_be_a_phone(self):
        c = self.cand("D3", ANDROID)
        st = c.post("/api/exam/start", json=dict(device="phone", signals=LAPTOP_SCREEN), headers=ANDROID)
        self.assertEqual(st.status_code, 200)                           # let in (it might be a real tablet)…
        _, cnt = self.info("D3")
        self.assertTrue(cnt["device"]["mismatch"])                      # …but a person looks
        self.assertIn("device_check", rules.chips(cnt))
        self.assertEqual(rules.band_floor("clear", cnt), "review")
        self.assertEqual(c.get("/api/exam/me", headers=ANDROID).json()["session"]["status"], "in_progress")   # never ended

    def test_client_hint_counts_as_mobile_and_seb_skips_kiosk(self):
        c = self.cand("D4", {**LAPTOP, "Sec-CH-UA-Mobile": "?1"})
        self.assertEqual(c.get("/api/exam/me", headers={**LAPTOP, "Sec-CH-UA-Mobile": "?1"}).json()["seb"]["required"], False)
        page = "http://testserver/exam/run"
        seb = {"User-Agent": LAPTOP["User-Agent"] + " SEB/3.7", "X-SEB-Page-Url": page,
               "X-SEB-Config-Key-Hash": hashlib.sha256((page + CK).encode()).hexdigest()}
        st = c.post("/api/exam/start", json=dict(signals=LAPTOP_SCREEN), headers=seb).json()
        self.assertFalse(st["kiosk"])                                   # inside SEB the page does not add its own kiosk
        _, cnt = self.info("D4")
        self.assertEqual((cnt["device"]["mode"], cnt["device"]["mismatch"]), ("seb", False))


if __name__ == "__main__":
    unittest.main()

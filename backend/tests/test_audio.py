"""Microphone "speech-like sound" check: events are stored, the explanation gets a supporting line or a "not counted"
note, and the score, band and order never change because of sound.

    python -m unittest backend.tests.test_audio -v
"""
from __future__ import annotations

import os
import tempfile
import unittest

import pandas as pd

TMP = tempfile.mkdtemp(prefix="fp-audio-")
os.environ.pop("DATABASE_URL", None)
os.environ.pop("FP_DATABASE_URL", None)
os.environ["FP_DB"] = os.path.join(TMP, "test.db")
os.environ["FP_RETENTION"] = "0"

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.jobs import worker  # noqa: E402
from backend.services import audio, scoring  # noqa: E402
from backend.tests.client import Client  # noqa: E402

ITEMS = "text,option_a,option_b,option_c,option_d,correct,kind\n" + "".join(
    f"Question {i}?,1,2,3,4,{'ABCD'[i % 4]},mcq\n" for i in range(1, 11))


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text


class Audio(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from backend.scripts.seed_demo import seed
        seed(reset=True, n_live=0)
        a = cls.admin = Client(app)
        login(a, email="admin@fairproctor.demo", password="Admin@2026")
        tid = a.post("/api/admin/tests", json=dict(title="Audio test", duration_min=20)).json()["id"]
        a.post(f"/api/admin/tests/{tid}/items", data=ITEMS, headers={"content-type": "text/csv"})
        cls.sid = a.post("/api/admin/sittings", json=dict(test_id=tid, title="Audio sitting", starts_at="2026-01-01T10:00:00+05:30",
                                                            ends_at="2030-01-01T10:00:00+05:30")).json()["id"]
        up = a.post(f"/api/admin/sittings/{cls.sid}/candidates", data="roll_no,name\nA1,Asha\nA2,Ravi\nA3,Meena\n",
                    headers={"content-type": "text/csv"}).json()
        cls.codes = {c["roll_no"]: c["code"] for c in up["candidates"]}
        a.post(f"/api/admin/sittings/{cls.sid}/open")

    def cand(self, roll):
        c = Client(app)
        login(c, roll_no=roll, code=self.codes[roll])
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
        return c

    def sheet(self, c, extra):
        """Answer all 10 (the key is A..D by position) with a long silent pause before Q3, plus `extra` events."""
        st = c.post("/api/exam/start", json={}).json()
        self.assertEqual(st["mic"], config.MIC_MODE)
        key = "ABCD"
        ev, seq, t = [], 1, 2.0
        for it in st["items"]:
            k = it["item"]
            ev.append(dict(seq=seq, t=t, type="item_shown", item=k)); seq += 1
            if k == 2:
                ev += [dict(seq=seq, t=t + 3, type="idle_start", item=k), dict(seq=seq + 1, t=t + 43, type="idle_end", item=k)]
                seq += 2
                t += 45
            else:
                t += 20
            ev.append(dict(seq=seq, t=t, type="answer", item=k, option=key[(k + 1) % 4])); seq += 1
            t += 1
        for e in extra:
            ev.append(dict(e, seq=seq)); seq += 1
        out = c.post("/api/exam/events", json=dict(events=ev)).json()
        self.assertEqual(out["rejected"], 0, out)
        self.assertEqual(c.post("/api/exam/submit").status_code, 200)
        return st

    def test_1_events_and_scoring(self):
        a1 = self.cand("A1")
        self.assertEqual(a1.get("/api/exam/me").json()["mic"], config.MIC_MODE)
        # the pause before Q3 lasts 40 s; a speech-like window ends inside it
        st = self.sheet(a1, [])
        with db.tx() as con:
            sess = db.one(con, "SELECT s.id FROM sessions s JOIN users u ON u.id = s.user_id WHERE u.roll_no = 'A1'")["id"]
            ev = pd.DataFrame(db.all_(con, "SELECT t, type, item, correct FROM events WHERE session_id = ? ORDER BY t", sess))
        pause = audio.silent_pauses(ev)
        self.assertEqual(len(pause), 1)
        a, b, q = pause[0]
        self.assertEqual(q, 2)
        speech_t = round(a + 20, 1)
        with db.tx() as con:                               # the sound events, as the phone would have sent them
            for i, (typ, t, opt, meta) in enumerate([("mic_on", 1.0, "", None), ("speech_like", speech_t, "", '{"s": 2.1, "a": 3.0}'),
                                                     ("speech_like", round(b + 120, 1), "", '{"s": 1.0, "a": 2.0}')]):
                con.execute("INSERT INTO events (session_id, seq, t, type, item, option, correct, chars, meta) VALUES (?, ?, ?, ?, -1, ?, -1, 0, ?)",
                            (sess, 900 + i, t, typ, opt, meta))
        self.assertTrue(st["items"])

        a2 = self.cand("A2")                               # talking-like sound, no pauses; the check stopped (slow phone)
        self.sheet(a2, [dict(t=1, type="mic_on"), dict(t=30, type="speech_like", meta=dict(s=1.5, a=2.5)),
                        dict(t=60, type="speech_like", meta=dict(s=2.0, a=3.0)), dict(t=90, type="mic_off", option="slow")])
        self.sheet(self.cand("A3"), [])

        job = self.admin.post(f"/api/admin/sittings/{self.sid}/close").json()["job_id"]
        self.assertEqual(worker.wait_for(job, timeout=300)["status"], "done")
        before = self.scores()
        e2 = before["A2"]["e"]
        self.assertEqual(e2["audio"]["windows"], 2)
        self.assertFalse(e2["audio"]["supporting"])
        self.assertTrue(any(n.startswith("Speech-like sound was picked up 2 times") for n in e2["context"]))
        self.assertTrue(any("microphone check stopped" in n and "too slow" in n for n in e2["context"]))
        e1 = before["A1"]["e"]
        self.assertEqual(e1["audio"]["pauses_with_speech"], 1)
        pause_reason = [r for r in e1["reasons"] if r["family"] == "pause"]
        if pause_reason:                                    # the model put the pause in the reasons: a supporting line
            ev_keys = [x["key"] for x in pause_reason[0]["evidence"]]
            self.assertIn("speech_in_pause", ev_keys)
            self.assertTrue(e1["audio"]["supporting"])
        else:                                               # it did not: sound alone is only "not counted"
            self.assertTrue(any(n.startswith("Speech-like sound was picked up") for n in e1["context"]))
        self.assertIsNone(before["A3"]["e"].get("audio"))

        # the same sitting scored again without any sound events: identical score, band and order
        with db.tx() as con:
            con.execute("DELETE FROM events WHERE type IN ('speech_like', 'mic_on', 'mic_off')")
        scoring.score_sitting(0, self.sid)
        after = self.scores()
        for roll in ("A1", "A2", "A3"):
            self.assertEqual((before[roll]["raw"], before[roll]["band"], before[roll]["rank"]),
                             (after[roll]["raw"], after[roll]["band"], after[roll]["rank"]), roll)

    def scores(self):
        import json
        with db.tx() as con:
            rows = db.all_(con, """SELECT u.roll_no, c.raw, c.band, c.rank, c.explanation FROM scores c
                                   JOIN sessions s ON s.id = c.session_id JOIN users u ON u.id = s.user_id
                                   WHERE c.sitting_id = ?""", self.sid)
        return {r["roll_no"]: dict(raw=round(r["raw"], 9), band=r["band"], rank=r["rank"], e=json.loads(r["explanation"])) for r in rows}

    def test_2_annotate_never_scores(self):
        ev = pd.DataFrame([dict(t=10, type="idle_start", item=4, correct=-1), dict(t=40, type="idle_end", item=4, correct=-1),
                           dict(t=45, type="answer", item=4, correct=1),
                           dict(t=100, type="idle_start", item=6, correct=-1), dict(t=130, type="idle_end", item=6, correct=-1),
                           dict(t=140, type="answer", item=6, correct=0)])           # this pause ends in a wrong answer
        e = dict(score=61.0, band="review", rank=3, reasons=[dict(family="pause", weight=0.7, evidence=[])], moments=[], context=[])
        audio.annotate(e, dict(windows=[(25.0, 2.0), (120.0, 1.0)], mic_on=True, stopped=[]), ev)
        self.assertEqual((e["score"], e["band"], e["rank"], e["reasons"][0]["weight"]), (61.0, "review", 3, 0.7))
        line = e["reasons"][0]["evidence"][0]
        self.assertTrue(line["supporting"])
        self.assertEqual(line["items"], [4])
        self.assertIn("1 of these 1 silent pause", line["text"])
        self.assertEqual(e["audio"]["pauses_with_speech"], 1)
        self.assertEqual(e["context"], [])
        # no pause reason: the same sound is "not counted"
        e2 = dict(score=20.0, band="clear", reasons=[], moments=[], context=[])
        audio.annotate(e2, dict(windows=[(25.0, 2.0)], mic_on=True, stopped=[]), ev)
        self.assertEqual(e2["band"], "clear")
        self.assertIn("Not counted", e2["context"][0])
        # nothing measured: nothing added
        e3 = dict(reasons=[], context=[])
        self.assertEqual(audio.annotate(e3, None, ev), dict(reasons=[], context=[]))

    def test_0_unknown_mic_reason_and_types(self):
        self.assertIn("speech_like", config.EVENT_TYPES)
        self.assertIn(config.MIC_MODE, ("off", "optional", "required"))


if __name__ == "__main__":
    unittest.main()

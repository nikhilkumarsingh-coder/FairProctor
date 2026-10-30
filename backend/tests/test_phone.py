"""Phone-in-view signal: schema, feature, the supporting-evidence rule and the explanation.

    python -m unittest backend.tests.test_phone -v
"""
from __future__ import annotations

import os
import pickle
import unittest

import numpy as np
import pandas as pd
from pydantic import ValidationError

from backend import config
from backend.schemas import FrameIn
from fairproctor.explain import PHONE_MIN_ITEMS, explain, phone_band
from fairproctor.features import RISK_FEATURES, SUPPORTING_FEATURES, build, load

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class Schema(unittest.TestCase):
    def test_phone_field(self):
        base = dict(seq=1, t=1.0, faces=1, face_visible=True)
        self.assertIsNone(FrameIn(**base).phone)                  # older clients: not checked
        self.assertEqual(FrameIn(**base, phone=0.4).phone, 0.4)
        with self.assertRaises(ValidationError):
            FrameIn(**base, phone=1.5)


class Feature(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s, e, f, i = load(os.path.join(ROOT, "data", "sample"))
        cheat = s[s["_truth_type"] == "second_phone"].session_id.iloc[:6].tolist()
        cls.s, cls.e, cls.f, cls.i = s[s.session_id.isin(cheat)], e[e.session_id.isin(cheat)], f[f.session_id.isin(cheat)], i
        with open(os.path.join(config.artifacts_dir(), "model.pkl"), "rb") as fh:
            cls.stats = pickle.load(fh)["stats"]

    def run_with(self, phone):
        fr = self.f.copy()
        fr["phone"] = phone
        X, evid, _ = build(self.s, self.e, fr, self.i, stats=self.stats)
        return X, evid

    def test_not_a_model_input(self):
        self.assertNotIn("phone_on_correct", RISK_FEATURES)        # supporting evidence only
        self.assertIn("phone_on_correct", SUPPORTING_FEATURES)

    def test_missing_detector_is_no_evidence(self):
        X, _ = self.run_with(np.nan)
        self.assertTrue(X.phone_on_correct.isna().all())
        self.assertTrue((X._phone_secs == 0).all())

    def test_phone_always_in_view(self):
        X, evid = self.run_with(1.0)
        self.assertTrue((X._phone_secs > 0).all())
        self.assertTrue((X.phone_on_correct >= 0).all())
        hit = X.index[X.phone_on_correct >= 1]
        self.assertGreater(len(hit), 0)                           # cheaters answer hard items right
        ev = [e for e in evid[hit[0]] if e.key == "phone_on_correct"]
        self.assertEqual(len(ev), 1)
        self.assertIn("no image was sent", ev[0].text)
        self.assertTrue(ev[0].moments)

    def test_phone_never_in_view(self):
        X, _ = self.run_with(0.0)
        self.assertTrue((X.phone_on_correct == 0).all())


class Rule(unittest.TestCase):
    def test_band(self):
        self.assertEqual(phone_band("clear", dict(phone_on_correct=PHONE_MIN_ITEMS)), "review")
        self.assertEqual(phone_band("clear", dict(phone_on_correct=1)), "clear")
        self.assertEqual(phone_band("clear", dict(phone_on_correct=float("nan"))), "clear")
        self.assertEqual(phone_band("clear", {}), "clear")
        self.assertEqual(phone_band("review_first", dict(phone_on_correct=5)), "review_first")   # never lowers

    def test_explanation_has_phone_reason(self):
        from fairproctor.features import Evidence
        ev = [Evidence("phone_on_correct", 10, 50, [3, 4], "A phone was in view for about 9 s while Q4, Q5 were answered "
                       "correctly (seen by the on-device detector; no image was sent).",
                       "A phone was visible to the camera while you answered Q4, Q5.", moments=[(10, "Q4: phone in view (5 s)")])]
        f = dict(phone_on_correct=2, _phone_secs=9)
        e = explain("S1", f, {}, ev, dict(device="desktop"), 40.0, "review")
        fams = [r["family"] for r in e["reasons"]]
        self.assertIn("phone", fams)
        self.assertTrue(any(m["label"].startswith("Q4: phone") for m in e["moments"]))
        clear = explain("S1", f, {}, ev, dict(device="desktop"), 10.0, "clear")
        self.assertNotIn("phone", [r["family"] for r in clear["reasons"]])

    def test_not_counted_note(self):
        e = explain("S1", dict(phone_on_correct=0, _phone_secs=12), {}, [], dict(device="desktop"), 10.0, "clear")
        self.assertTrue(any("A phone was in view for about 12 s" in n for n in e["context"]))


if __name__ == "__main__":
    unittest.main()

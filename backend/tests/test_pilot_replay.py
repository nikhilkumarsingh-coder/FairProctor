"""Replay the first hostel pilot (real people, anonymised) through the scoring engine on every change.

It is a regression fixture, not evidence: it checks that real behaviour (answers changed, questions revisited, a
45-minute paper clicked through in a minute) never crashes scoring and that the rules added after the pilot hold.

    python -m unittest backend.tests.test_pilot_replay -v
"""
from __future__ import annotations

import os
import pickle
import unittest

import numpy as np
import pandas as pd

from backend import config
from fairproctor.explain import explain, phone_band
from fairproctor.features import (TIMING_FEATURES, ItemStats, build, collusion_table, load,
                                  one_answer_per_item)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PILOT = os.path.join(ROOT, "data", "pilot1")


def sitting():
    """The 10 pilot participants plus 200 synthetic reference candidates of the same paper, as the product scores them."""
    s, e, f, items = load(os.path.join(ROOT, "data", "sample"))
    ref = s[s.window_id == 1].copy()
    ref_ids = set(ref.session_id)
    ref = ref.assign(window_id=4, is_synthetic=1)
    e, f = e[e.session_id.isin(ref_ids)], f[f.session_id.isin(ref_ids)]
    ps = pd.read_csv(os.path.join(PILOT, "sessions.csv"), keep_default_na=False)
    pe = pd.read_csv(os.path.join(PILOT, "events.csv"), keep_default_na=False)
    pf = pd.read_csv(os.path.join(PILOT, "frames.csv"), keep_default_na=False)
    cols = ["session_id", "window_id", "device", "bandwidth_class", "precheck_light", "precheck_framing", "is_synthetic"]
    sess = pd.concat([ref[cols], ps[cols]], ignore_index=True)
    ev = pd.concat([e, pe[e.columns.intersection(pe.columns)]], ignore_index=True)
    for c in ("item", "correct", "chars"):
        ev[c] = pd.to_numeric(ev[c], errors="coerce").fillna(-1 if c != "chars" else 0).astype(int)
    ev["t"] = pd.to_numeric(ev["t"])
    fr = pd.concat([f, pf[f.columns.intersection(pf.columns)]], ignore_index=True)
    for c in ("t", "faces", "brightness", "blur", "phone"):
        if c in fr:
            fr[c] = pd.to_numeric(fr[c], errors="coerce")
    return sess, ev.sort_values(["session_id", "t"], kind="stable"), fr, items, ps


class PilotReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sess, cls.ev, cls.fr, cls.items, cls.people = sitting()
        with open(os.path.join(config.artifacts_dir(), "model.pkl"), "rb") as fh:
            cls.bundle = pickle.load(fh)
        st = ItemStats.fit(cls.ev, cls.items)                     # 210 sessions: the sitting's own statistics
        cls.X, cls.evid, cls.st = build(cls.sess, cls.ev, cls.fr, cls.items, stats=st)
        cls.real = list(cls.people.session_id)

    def test_real_behaviour_is_in_the_fixture(self):
        a = self.ev[(self.ev.type == "answer") & self.ev.session_id.isin(self.real)]
        self.assertTrue(a.duplicated(["session_id", "item"]).any())          # answers were changed
        self.assertEqual(len(one_answer_per_item(a).drop_duplicates(["session_id", "item"])), len(one_answer_per_item(a)))

    def test_scores_every_participant(self):
        M = self.bundle["model"]
        X = self.X.loc[self.real]
        raw = M.raw(X)
        self.assertTrue(np.isfinite(raw).all())
        contrib = M.contributions(X)
        meta = self.sess.set_index("session_id").to_dict("index")
        for i, sid in enumerate(self.real):
            band = "review_first" if raw[i] >= self.bundle["H"] else ("review" if raw[i] >= self.bundle["T"] else "clear")
            band = phone_band(band, X.loc[sid].to_dict())
            e = explain(sid, X.loc[sid].to_dict(), contrib.loc[sid].to_dict(), self.evid[sid], dict(meta[sid], session_id=sid),
                        50.0, band, events=self.ev[self.ev.session_id == sid], stats=self.st)
            self.assertIn("headline", e)

    def test_clicking_through_is_not_timing_evidence(self):
        rushed = [s for s in self.real if self.X.loc[s, "_rushed_guess"] == 1]
        self.assertTrue(rushed)                                              # the pilot has people who clicked through
        for s in rushed:
            for k in TIMING_FEATURES:
                self.assertEqual(self.X.loc[s, k], 0, (s, k))
            self.assertFalse([e for e in self.evid[s] if e.key in TIMING_FEATURES])
        # fast AND right is still counted: no one with a high score is treated as clicking through
        for s in self.real:
            a = one_answer_per_item(self.ev[(self.ev.session_id == s) & (self.ev.type == "answer")])
            if len(a) >= 8 and a.correct.mean() > 0.6:
                self.assertEqual(self.X.loc[s, "_rushed_guess"], 0, s)

    def test_reference_crowd_cannot_make_real_matches_stronger(self):
        new = collusion_table(self.ev, self.sess, self.st.kind)
        old = collusion_table(self.ev, self.sess.drop(columns="is_synthetic"), self.st.kind)   # every option rarity from all 210
        for s in self.real:
            self.assertLessEqual(new[s]["score"], old[s]["score"] + 1e-9, s)


if __name__ == "__main__":
    unittest.main()

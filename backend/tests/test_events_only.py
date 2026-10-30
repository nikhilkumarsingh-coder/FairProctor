"""Event logs only (the problem statement's labelled dataset has answer timing, focus and paste events, no video):
the pipeline must train and score without frames, and models saved before this option must load unchanged.

    python -m unittest backend.tests.test_events_only -v
"""
from __future__ import annotations

import os
import pickle
import shutil
import tempfile
import unittest

import numpy as np
from sklearn.metrics import roc_auc_score

from backend import config
from fairproctor.explain import explain
from fairproctor.features import build, load
from fairproctor.model import EVENT_RISK, MODEL_CONTEXT, RISK_FEATURES, VIDEO_RISK, IntegrityModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SAMPLE = os.path.join(ROOT, "data", "sample")


class EventsOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s, e, f, items = load(SAMPLE)
        keep = set(s[s.window_id < 8].session_id)                       # 8 sittings: enough to train, quick to run
        cls.s, cls.e, cls.items = s[s.session_id.isin(keep)], e[e.session_id.isin(keep)], items
        cls.tmp = tempfile.mkdtemp(prefix="fp-events-")
        cls.s.to_csv(os.path.join(cls.tmp, "sessions.csv"), index=False)
        cls.e.to_csv(os.path.join(cls.tmp, "events.csv.gz"), index=False)
        items.to_csv(os.path.join(cls.tmp, "items.csv"), index=False)  # no frames.csv.gz at all

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_trains_and_scores_without_video(self):
        s, e, f, items = load(self.tmp)
        self.assertTrue(f.empty)                                        # a missing frames file is fine
        X, evidence, st = build(s, e, f, items)
        S = s.set_index("session_id").loc[X.index]
        y = (S.verdict == "confirmed").values.astype(int)
        m = IntegrityModel(events_only=True).fit(X, y, S.window_id.values)
        self.assertGreater(roc_auc_score(y, m.oof_raw), 0.75)
        self.assertFalse(set(VIDEO_RISK) & set(m._risk()))
        c = m.oof_contributions(X)
        self.assertEqual(list(c.columns), EVENT_RISK)
        sid = X.index[int(np.argmax(m.oof_raw))]
        ex = explain(sid, X.loc[sid].to_dict(), c.loc[sid].to_dict(), evidence[sid], dict(S.loc[sid], session_id=sid),
                     90.0, "review_first", events=e[e.session_id == sid], stats=st)
        self.assertTrue(any(n.startswith("No usable video") for n in ex["context"]))
        self.assertTrue(ex["reasons"])

    def test_saved_video_model_is_unchanged(self):
        with open(os.path.join(config.artifacts_dir(), "model.pkl"), "rb") as fh:
            M = pickle.load(fh)["model"]                                 # saved before the events-only option existed
        self.assertEqual(M._risk(), RISK_FEATURES)
        self.assertEqual(M._ctx(), MODEL_CONTEXT)


if __name__ == "__main__":
    unittest.main()

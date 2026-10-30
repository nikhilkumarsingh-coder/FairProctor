"""Real candidates change answers and revisit questions: scoring must use the final answer and never crash.

    python -m unittest backend.tests.test_real_answers -v
"""
from __future__ import annotations

import os
import pickle
import unittest

import pandas as pd

from backend import config
from fairproctor.features import build, load, one_answer_per_item

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ChangedAnswers(unittest.TestCase):
    def test_final_answer_first_view(self):
        ev = pd.DataFrame([
            dict(session_id="S", t=1.0, type="item_shown", item=0, option="", correct=-1),
            dict(session_id="S", t=5.0, type="answer", item=0, option="A", correct=0),
            dict(session_id="S", t=9.0, type="item_shown", item=1, option="", correct=-1),
            dict(session_id="S", t=60.0, type="item_shown", item=0, option="", correct=-1),   # back to Q1
            dict(session_id="S", t=62.0, type="answer", item=0, option="B", correct=1),        # changed: final counts
            dict(session_id="S", t=63.0, type="focus_lost", item=-1, option="", correct=-1),
        ])
        out = one_answer_per_item(ev)
        a = out[out.type == "answer"]
        self.assertEqual(a.option.tolist(), ["B"])
        self.assertEqual(out[(out.type == "item_shown") & (out.item == 0)].t.tolist(), [1.0])   # first view: 61 s, not 2 s
        self.assertEqual((out.type == "focus_lost").sum(), 1)
        self.assertIs(one_answer_per_item(out[out.type != "focus_lost"].iloc[:0]).empty, True)

    def test_build_with_revisits(self):
        s, e, f, i = load(os.path.join(ROOT, "data", "sample"))
        keep = s.session_id.iloc[:8].tolist()
        s, e, f = s[s.session_id.isin(keep)], e[e.session_id.isin(keep)], f[f.session_id.isin(keep)]
        with open(os.path.join(config.artifacts_dir(), "model.pkl"), "rb") as fh:
            stats = pickle.load(fh)["stats"]
        base, _, _ = build(s, e, f, i, stats=stats)
        a = e[(e.type == "answer")].iloc[:20].copy()
        a["t"] = a["t"] + 0.01                                           # same answer submitted again
        sh = e[(e.type == "item_shown")].iloc[:20].copy()
        sh["t"] = sh["t"] + 0.005                                        # and the question shown again
        X, _, _ = build(s, pd.concat([e, a, sh]).sort_values(["session_id", "t"]), f, i, stats=stats)
        self.assertEqual(list(X.index), list(base.index))
        self.assertTrue((X.n_answered == base.n_answered).all())


if __name__ == "__main__":
    unittest.main()

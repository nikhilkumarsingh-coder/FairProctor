"""Integrity scoring model (CPU only).

* Gradient-boosted trees (scikit-learn HistGradientBoostingClassifier) — trains in
  seconds and scores thousands of sessions per second on a laptop CPU.
* Monotonic constraints: more behavioural evidence can never LOWER the score.
* Environment-neutral by construction: we subtract the score the environment
  alone would produce for a perfectly ordinary candidate, so a dark room, a
  phone or a 2G link can change how much a video signal is trusted, but can
  never add suspicion on its own.
* Isotonic calibration on out-of-fold scores, so the score reads as a probability.
* Per-feature contributions (replace-with-reference) drive the explanations.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from .features import CONTEXT_FEATURES, RISK_FEATURES

# bandwidth class and device are deliberately NOT model inputs: they act as a
# proxy for where someone lives. Only direct measurements of video quality are used.
MODEL_CONTEXT = ["video_fpm", "face_visible_frac", "brightness_mean", "blur_mean", "fast_wrong_frac", "n_answered"]
MODEL_FEATURES = RISK_FEATURES + MODEL_CONTEXT

# Event logs only (no video at all, like an exported log of answer timing, focus and paste events): the same model
# without the camera features. Missing video is not evidence, so the camera inputs are simply left out.
VIDEO_RISK = ["multi_face_persist_frac", "multi_face_on_correct", "gaze_down_excess_idle", "gaze_down_on_unexpected"]
EVENT_RISK = [c for c in RISK_FEATURES if c not in VIDEO_RISK]
EVENT_CONTEXT = ["fast_wrong_frac", "n_answered"]


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


class IntegrityModel:
    def __init__(self, seed: int = 0, events_only: bool = False):
        self.seed = seed
        self.events_only = events_only

    # the inputs: all features, or the event-log ones (models saved before this option use all)
    def _risk(self):
        return EVENT_RISK if getattr(self, "events_only", False) else RISK_FEATURES

    def _ctx(self):
        return EVENT_CONTEXT if getattr(self, "events_only", False) else MODEL_CONTEXT

    def _new(self):
        cst = [1] * len(self._risk()) + [0] * len(self._ctx())
        return HistGradientBoostingClassifier(
            max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
            l2_regularization=1.0, monotonic_cst=cst, class_weight={0: 1, 1: 4}, random_state=self.seed)

    # ------------------------------------------------------------------ raw score
    def _prep(self, X: pd.DataFrame) -> pd.DataFrame:
        """Missing behavioural evidence (e.g. no frames during a pause on a 2G link)
        is set to the honest reference: absence of video is never evidence."""
        Xm = X[self._risk() + self._ctx()].copy()
        for c in self._risk():
            Xm[c] = Xm[c].fillna(self.ref[c])
        return Xm

    def _raw(self, clf, X: pd.DataFrame) -> np.ndarray:
        Xm = self._prep(X)
        lo = _logit(clf.predict_proba(Xm)[:, 1])
        # environment-only score: same context, behaviour at the honest reference
        Xe = Xm.copy()
        for c in self._risk():
            Xe[c] = self.ref[c]
        env = _logit(clf.predict_proba(Xe)[:, 1])
        Xr = Xe.copy()
        for c in self._ctx():
            Xr[c] = self.ref[c]
        base = _logit(clf.predict_proba(Xr)[:, 1])
        return lo - (env - base)

    # ------------------------------------------------------------------ training
    def fit(self, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, n_splits: int = 5):
        honest = X[y == 0]
        self.ref = {c: float(np.nanmedian(honest[c])) if honest[c].notna().any() else 0.0 for c in self._risk() + self._ctx()}
        oof = np.zeros(len(X))
        fold = np.zeros(len(X), int)
        self.fold_clfs = []
        for k, (tr, te) in enumerate(GroupKFold(n_splits).split(X, y, groups)):
            clf = self._new().fit(self._prep(X.iloc[tr]), y[tr])
            oof[te] = self._raw(clf, X.iloc[te])
            fold[te] = k
            self.fold_clfs.append(clf)
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(oof, y)
        self.clf = self._new().fit(self._prep(X), y)
        self.oof_raw, self.oof_fold = oof, fold
        self.oof_prob = self.iso.predict(oof)
        return self

    # ------------------------------------------------------------------ scoring
    def raw(self, X):
        return self._raw(self.clf, X)

    def oof_raw_for(self, X: pd.DataFrame) -> np.ndarray:
        """Score X (same sessions as training, possibly degraded) with the model that did NOT see each session."""
        out = np.zeros(len(X))
        for k, clf in enumerate(self.fold_clfs):
            m = self.oof_fold == k
            out[m] = self._raw(clf, X.iloc[np.where(m)[0]])
        return out

    def prob(self, X):
        return self.iso.predict(self.raw(X))

    def contributions(self, X: pd.DataFrame, clf=None) -> pd.DataFrame:
        """Log-odds each risk feature adds versus an ordinary honest value."""
        clf = clf or self.clf
        base = self._raw(clf, X)
        out = {}
        for c in self._risk():
            Xc = X.copy()
            Xc[c] = self.ref[c]
            out[c] = base - self._raw(clf, Xc)
        return pd.DataFrame(out, index=X.index)

    def oof_contributions(self, X: pd.DataFrame) -> pd.DataFrame:
        parts = []
        for k, clf in enumerate(self.fold_clfs):
            idx = np.where(self.oof_fold == k)[0]
            parts.append(self.contributions(X.iloc[idx], clf))
        return pd.concat(parts).loc[X.index]

    def to_score(self, raw):
        """0–100 integrity-risk score shown to reviewers (calibrated probability × 100)."""
        return np.round(100 * self.iso.predict(raw), 1)

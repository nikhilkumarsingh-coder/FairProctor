"""Session features + time-stamped evidence.

Design rules
------------
1. Environment is context, behaviour is evidence. Video quality, brightness,
   frame rate and device are passed to the model as *context* features (no
   monotonic push), so they can only change how much a video signal is trusted.
2. Video evidence is always normalised by what the camera could actually see.
   If no frames arrived during a moment, that moment produces "no evidence"
   (NaN), never suspicion.
3. Raw per-frame flags are grouped into episodes; one person walking past for
   six seconds is one short episode, not six flags.
4. Every evidence feature carries the moments (item numbers, timestamps) that
   produced it, so every flag in the console links back to the session timeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import os

import numpy as np
import pandas as pd

UNEXPECTED_P = 0.55     # expected-correct prob below which a correct answer is "unexpected"
FAST_Z = -1.5           # robust z of log-time below which an answer is "fast"
SLOW_Z = 0.6
MUTUAL_Z = 6.0          # pair must stand out at this robust z from BOTH candidates' side
RUSH_SHARE = 0.2        # answered in under a fifth of the typical time for those questions...
RUSH_MARGIN = 0.2       # ...with accuracy no better than guessing + this: clicking through, not relaying answers
TIMING_FEATURES = ("fast_correct_unexpected", "fast_burst", "self_fast_correct", "misfit")


# --------------------------------------------------------------------------- utils
def mmss(t: float) -> str:
    t = max(0, int(round(t)))
    return f"{t // 60:02d}:{t % 60:02d}"


def qlabel(qs) -> str:
    qs = sorted(int(q) + 1 for q in qs)
    if not qs:
        return ""
    if len(qs) > 2 and qs[-1] - qs[0] == len(qs) - 1:
        return f"Q{qs[0]}–Q{qs[-1]}"
    if len(qs) > 6:
        return ", ".join(f"Q{q}" for q in qs[:6]) + f" and {len(qs) - 6} more"
    return ", ".join(f"Q{q}" for q in qs)


def pl(n, word, plural=None):
    """'1 long pause', '3 long pauses'."""
    n = int(n)
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def load(dir_: str):
    sessions = pd.read_csv(f"{dir_}/sessions.csv")
    events = pd.read_csv(f"{dir_}/events.csv.gz", keep_default_na=False)
    fp = f"{dir_}/frames.csv.gz"                   # event logs without video: no frames file is fine
    frames = (pd.read_csv(fp, keep_default_na=False) if os.path.exists(fp) else
              pd.DataFrame(columns=["session_id", "t", "faces", "face_visible", "gaze", "brightness", "blur"]))
    items = pd.read_csv(f"{dir_}/items.csv", keep_default_na=False)
    return sessions, events, frames, items


# --------------------------------------------------------------------------- item stats
@dataclass
class ItemStats:
    """Label-free statistics of the paper, estimated from everyone's responses."""
    med_logt: np.ndarray
    sd_logt: np.ndarray
    b: np.ndarray            # difficulty on a logit scale
    kind: np.ndarray

    @classmethod
    def fit(cls, events: pd.DataFrame, items: pd.DataFrame) -> "ItemStats":
        events = one_answer_per_item(events)
        shown = events[events.type == "item_shown"][["session_id", "item", "t"]].rename(columns={"t": "t0"})
        ans = events[events.type == "answer"][["session_id", "item", "t", "correct"]]
        a = ans.merge(shown, on=["session_id", "item"])
        a["logt"] = np.log(np.maximum(a.t - a.t0, 1.0))
        n = len(items)
        g = a.groupby("item")
        med = g.logt.median().reindex(range(n)).values
        mad = g.logt.apply(lambda x: np.median(np.abs(x - np.median(x)))).reindex(range(n)).values
        p = g.correct.mean().reindex(range(n)).clip(0.03, 0.97).values
        kind = items.kind.values
        # remove guessing floor for MCQ before converting to a logit difficulty
        p_eff = np.where(kind == "mcq", np.clip((p - 0.25) / 0.75, 0.03, 0.97), p)
        return cls(med_logt=med, sd_logt=np.maximum(1.4826 * mad, 0.15), b=-np.log(p_eff / (1 - p_eff)), kind=kind)


def one_answer_per_item(events: pd.DataFrame) -> pd.DataFrame:
    """Real candidates go back and change answers. Scoring uses each question once per session: the FINAL answer
    (it is what is marked) and the FIRST time the question was shown, so the time counted runs from first seeing the
    question to the final answer. Coming back to fix an answer can only make that time longer, never 'suspiciously
    fast'. Other events are kept as they are. Idempotent; the synthetic training data already has one of each."""
    if events.empty or "item" not in events:
        return events
    is_ans, is_shown = events.type == "answer", events.type == "item_shown"
    a = events[is_ans]
    s = events[is_shown]
    if not a.duplicated(["session_id", "item"]).any() and not s.duplicated(["session_id", "item"]).any():
        return events
    a = a.sort_values("t", kind="stable").drop_duplicates(["session_id", "item"], keep="last")
    s = s.sort_values("t", kind="stable").drop_duplicates(["session_id", "item"], keep="first")
    out = pd.concat([events[~(is_ans | is_shown)], s, a])
    return out.sort_values(["session_id", "t"], kind="stable").reset_index(drop=True)


def estimate_theta(b, correct, guess):
    """Rasch-with-guessing ability estimate (a few Newton steps, bounded)."""
    th = 0.0
    for _ in range(25):
        ps = sigmoid(th - b)
        p = guess + (1 - guess) * ps
        # derivative of log-likelihood
        dp = (1 - guess) * ps * (1 - ps)
        g = np.sum((correct - p) * dp / (p * (1 - p)))
        h = -np.sum(dp ** 2 / (p * (1 - p))) - 1e-3
        th = np.clip(th - g / h - 0.02 * th, -4, 4)
    return th


# --------------------------------------------------------------------------- collusion
def collusion_table(events: pd.DataFrame, sessions: pd.DataFrame, items_kind: np.ndarray):
    """For every session, its strongest partner by rarity-weighted identical WRONG answers.

    Popular wrong options are shared by honest people all the time, so each
    shared wrong answer is weighted by -log(frequency of that option in the sitting).
    Synchrony (both answering within 30 s) is reported alongside.
    """
    ans = events[(events.type == "answer")].copy()
    ans = ans[ans["item"].isin(np.where(items_kind == "mcq")[0])]
    cols = ["session_id", "window_id"] + (["is_synthetic"] if "is_synthetic" in sessions else [])
    ans = ans.merge(sessions[cols], on="session_id")
    if "is_synthetic" not in ans:
        ans["is_synthetic"] = 0
    out = {}
    for w, g in ans.groupby("window_id"):
        sids = np.array(sorted(g.session_id.unique()))
        idx = {s: i for i, s in enumerate(sids)}
        n, q = len(sids), int(items_kind.size)
        opt = np.full((n, q), -1)
        tt = np.full((n, q), np.nan)
        cor = np.zeros((n, q), bool)
        rows = g.session_id.map(idx).values
        cols = g["item"].values.astype(int)
        opt[rows, cols] = g.option.map({"A": 0, "B": 1, "C": 2, "D": 3}).values
        tt[rows, cols] = g.t.values
        cor[rows, cols] = g.correct.values == 1
        wrong = (opt >= 0) & ~cor
        syn = np.zeros(n, bool)
        syn[rows] = g.is_synthetic.fillna(0).astype(int).values == 1
        # Real candidates scored together with synthetic reference candidates: the reference people spread their wrong
        # answers evenly, while real people share the same misconceptions. Measured against the reference crowd, a
        # common human mistake looks rare. So for a real candidate an option counts as rare only if it is rare among
        # the REAL candidates too (Laplace-smoothed: with 10 real people no shared answer can look rarer than ~1 in 7;
        # with hundreds the estimate converges to the plain frequency). Found in the first hostel pilot.
        real = ~syn
        mixed = bool(syn.any() and real.any())
        weight = np.zeros((n, q))
        for j in range(q):
            col = opt[:, j]
            valid = col >= 0
            if not valid.any():
                continue
            freq = np.bincount(col[valid], minlength=4) / valid.sum()
            f = np.where(valid, freq[np.maximum(col, 0)], 1.0)
            if mixed:
                rv = valid & real
                freq_real = (np.bincount(col[rv], minlength=4) + 1) / (rv.sum() + 4)
                f = np.where(real & valid, np.maximum(f, freq_real[np.maximum(col, 0)]), f)
            weight[valid, j] = -np.log(np.maximum(f[valid], 1e-3))
        answered = opt >= 0
        Z = np.full((n, n), -np.inf)
        rows_i = []
        for i in range(n):
            same = (opt == opt[i]) & answered & answered[i]
            same[i] = False
            same_wrong = same & wrong & wrong[i]
            # every identical answer counts, weighted by how rare that option is in
            # the sitting: sharing a rare right answer or a rare wrong answer is
            # informative, sharing the popular answer is not.
            wscore = (same * weight[i]).sum(axis=1)
            nshare = same_wrong.sum(axis=1)
            # identical answer submitted within 20 s of each other. Ignored on items
            # that most of the sitting answers at the same moment (the opening
            # questions), where it means nothing.
            close = answered & answered[i] & (np.abs(tt - tt[i]) < 20)
            close[i] = False
            crowded = close.sum(axis=0) / max(n - 1, 1) > 0.2
            lock = close & same & ~crowded
            lscore = (lock * weight[i]).sum(axis=1) + 0.7 * lock.sum(axis=1)
            nlock = lock.sum(axis=1)
            pair = wscore + lscore
            pair[i] = -np.inf
            others = pair[np.isfinite(pair)]
            med = np.median(others)
            mad = 1.4826 * np.median(np.abs(others - med)) + 1e-6
            Z[i] = (pair - med) / mad
            rows_i.append((pair, nshare, nlock, same_wrong, lock))
        # A pair is only as strong as the WEAKER of the two views: candidate A's
        # best match out of 200 is often unremarkable from B's side (chance), but
        # real partners stand out for each other.
        M = np.minimum(Z, Z.T)
        np.fill_diagonal(M, -np.inf)
        for i in range(n):
            pair, nshare, nlock, same_wrong, lock = rows_i[i]
            j = int(np.argmax(pair))
            mo = np.argsort(-M[i])[:3]

            def tup(k):
                return (sids[k], int(nshare[k]), int(nlock[k]), float(M[i, k]),
                        np.where(same_wrong[k])[0].tolist(), np.where(lock[k])[0].tolist())
            partners = [tup(k) for k in mo if M[i, k] > MUTUAL_Z]
            out[sids[i]] = dict(closest=tup(j), score=float(pair[j]), nshare=int(nshare[j]), sync=int(nlock[j]),
                                pair_z=float(Z[i, j]), mutual_z=float(M[i, mo[0]]), n_wrong=int(wrong[i].sum()),
                                top_mutual=[(sids[k], float(M[i, k])) for k in mo],
                                partners=partners)
    return out


# --------------------------------------------------------------------------- per-session
@dataclass
class Evidence:
    key: str            # feature this evidence explains
    t0: float
    t1: float
    items: list
    text: str           # reviewer wording
    candidate_text: str  # plain-language wording for the candidate
    strength: float = 0.0
    moments: list = field(default_factory=list)  # [(t, label)] jump points

    def as_dict(self):
        return dict(key=self.key, t0=round(self.t0, 1), t1=round(self.t1, 1), items=[int(q) + 1 for q in self.items],
                    text=self.text, candidate_text=self.candidate_text, strength=round(self.strength, 3),
                    moments=[dict(t=round(t, 1), label=l) for t, l in self.moments])


RISK_FEATURES = [
    "fast_correct_unexpected", "fast_burst", "self_fast_correct", "misfit", "idle_correct_unexpected", "idle_correct_excess",
    "focus_then_correct", "focus_away_total", "paste_large", "paste_chars_max", "collusion_score",
    "collusion_nshare", "collusion_sync", "collusion_pair_z", "collusion_mutual_z", "ring_size", "ring_partner_fast", "ring_attach", "multi_face_persist_frac", "multi_face_on_correct",
    "gaze_down_excess_idle", "gaze_down_on_unexpected",
]
# Supporting evidence computed for reviewers but kept OUT of the trained model: the phone-in-view detector is new and
# not in the labelled data's distribution; a rule (backend/services/scoring.py) makes sure a human sees it.
SUPPORTING_FEATURES = ["phone_on_correct"]
CONTEXT_FEATURES = ["video_fpm", "face_visible_frac", "brightness_mean", "blur_mean", "is_phone", "is_low_bw",
                    "fast_wrong_frac", "n_answered"]
FEATURES = RISK_FEATURES + CONTEXT_FEATURES


def session_features(sid, ev: pd.DataFrame, fr: pd.DataFrame, meta: dict, st: ItemStats, coll: dict):
    feats: dict[str, float] = {}
    evid: list[Evidence] = []
    nq = st.b.size

    shown = ev[ev.type == "item_shown"].set_index("item").t
    ans = ev[ev.type == "answer"].set_index("item")
    qs = [q for q in ans.index if q in shown.index]
    t0 = np.array([shown[q] for q in qs])
    t1 = np.array([ans.loc[q, "t"] for q in qs])
    corr = np.array([ans.loc[q, "correct"] for q in qs]).astype(float)
    qa = np.array(qs, dtype=int)
    feats["n_answered"] = len(qs)

    # ------------------------------------------------ answer timing & person-fit
    if len(qs):
        z = (np.log(np.maximum(t1 - t0, 1)) - st.med_logt[qa]) / st.sd_logt[qa]
        guess = np.where(st.kind[qa] == "mcq", 0.25, 0.0)
        theta = estimate_theta(st.b[qa], corr, guess)
        pexp = guess + (1 - guess) * sigmoid(theta - st.b[qa])
        # ability estimate WITHOUT the suspicious items is unknown; use a robust
        # version: theta from the slowest-honest-looking half (|z|<1)
        normal = np.abs(z) < 1
        if normal.sum() >= 8:
            th_r = estimate_theta(st.b[qa][normal], corr[normal], guess[normal])
            pexp_r = guess + (1 - guess) * sigmoid(th_r - st.b[qa])
        else:
            pexp_r = pexp
        fast = z < FAST_Z
        unexpected = (corr == 1) & (pexp_r < UNEXPECTED_P)
        fcu = fast & unexpected
        feats["fast_correct_unexpected"] = int(fcu.sum())
        feats["fast_wrong_frac"] = float((fast & (corr == 0)).sum() / len(qs))
        # longest run of fast correct answers
        run = best = 0
        best_end = -1
        for i, f in enumerate(fast & (corr == 1)):
            run = run + 1 if f else 0
            if run > best:
                best, best_end = run, i
        feats["fast_burst"] = best
        # standardised person-fit lz (negative = misfit); we export -lz
        p = np.clip(pexp, 0.02, 0.98)
        l0 = np.sum(corr * np.log(p) + (1 - corr) * np.log(1 - p))
        el = np.sum(p * np.log(p) + (1 - p) * np.log(1 - p))
        vl = np.sum(p * (1 - p) * np.log(p / (1 - p)) ** 2)
        feats["misfit"] = float(-(l0 - el) / np.sqrt(max(vl, 1e-6)))

        # answers far faster than this candidate's OWN usual pace, and correct.
        # A slow, careful candidate who suddenly answers several items in a few
        # seconds each — without rushing at the end — is relaying answers.
        own = np.median(z)
        late = t1 > (t1.max() - 0.15 * (t1.max() - t0.min()))
        sfc = (z - own < -2.0) & (corr == 1) & ~late & (z < -0.5)
        feats["self_fast_correct"] = int(sfc.sum())
        if sfc.sum() >= 1:
            idx = np.where(sfc)[0]
            evid.append(Evidence(
                "self_fast_correct", t0[idx].min(), t1[idx].max(), qa[idx].tolist(),
                f"{qlabel(qa[idx])}: {pl(len(idx), 'correct answer')} in {np.min(t1[idx] - t0[idx]):.0f}–{np.max(t1[idx] - t0[idx]):.0f} s each, "
                f"about {np.median(np.exp((own - z[idx]) * st.sd_logt[qa[idx]])):.0f}× faster than this candidate's own pace on the rest of the paper "
                f"(not end-of-test rushing).",
                f"Some answers ({qlabel(qa[idx])}) were given much faster than your usual pace in the rest of the test.",
                moments=[(t1[i], f"Q{qa[i] + 1} in {t1[i] - t0[i]:.0f} s") for i in idx]))

        if fcu.sum() >= 1:
            idx = np.where(fcu)[0]
            secs = (t1 - t0)[idx]
            evid.append(Evidence(
                "fast_correct_unexpected", t0[idx].min(), t1[idx].max(), qa[idx].tolist(),
                f"{qlabel(qa[idx])}: {pl(len(idx), 'hard item')} answered correctly in {secs.min():.0f}–{secs.max():.0f} s each "
                f"(typical time for these items: {np.exp(st.med_logt[qa[idx]]).min():.0f}–{np.exp(st.med_logt[qa[idx]]).max():.0f} s).",
                f"Some difficult questions ({qlabel(qa[idx])}) were answered correctly much faster than most candidates take.",
                moments=[(t1[i], f"Q{qa[i] + 1} answered in {t1[i] - t0[i]:.0f} s") for i in idx]))
        if best >= 3:
            idx = np.arange(best_end - best + 1, best_end + 1)
            evid.append(Evidence(
                "fast_burst", t0[idx].min(), t1[idx].max(), qa[idx].tolist(),
                f"{qlabel(qa[idx])} ({mmss(t0[idx].min())}–{mmss(t1[idx].max())}): {best} answers in a row, each correct "
                f"and each faster than usual (median {np.median(t1[idx] - t0[idx]):.0f} s).",
                f"Between {mmss(t0[idx].min())} and {mmss(t1[idx].max())} several answers in a row were submitted unusually quickly.",
                moments=[(t0[idx].min(), "burst starts"), (t1[idx].max(), "burst ends")]))
        if feats["misfit"] > 1.0:
            hard_right = qa[(corr == 1) & (pexp < 0.4)]
            easy_wrong = qa[(corr == 0) & (pexp > 0.8)]
            evid.append(Evidence(
                "misfit", t0.min(), t1.max(), list(hard_right) + list(easy_wrong),
                f"Answer pattern is unusual for one person: correct on {len(hard_right)} items most candidates of this "
                f"level miss ({qlabel(hard_right)}) but wrong on {len(easy_wrong)} easy items ({qlabel(easy_wrong)}).",
                "The pattern of right and wrong answers was unusual (hard questions right, easy ones wrong).",
                moments=[(ans.loc[q, "t"], f"Q{q + 1} hard, correct") for q in hard_right[:6]]
                + [(ans.loc[q, "t"], f"Q{q + 1} easy, wrong") for q in easy_wrong[:4]]))
    else:
        for k in ["fast_correct_unexpected", "fast_wrong_frac", "fast_burst", "self_fast_correct", "misfit"]:
            feats[k] = 0.0
        unexpected = np.zeros(0, bool)
        pexp_r = np.zeros(0)
        z = np.zeros(0)

    # ------------------------------------------------ idle pauses (no input) + answer
    idle = ev[ev.type.isin(["idle_start", "idle_end"])].sort_values("t")
    idle_iv = []
    st_t = None
    for _, r in idle.iterrows():
        if r.type == "idle_start":
            st_t = r.t
        elif st_t is not None:
            idle_iv.append((st_t, r.t))
            st_t = None
    focus = ev[ev.type.isin(["focus_lost", "focus_gained"])].sort_values("t")
    focus_iv = []
    st_t = None
    for _, r in focus.iterrows():
        if r.type == "focus_lost":
            st_t = r.t
        elif st_t is not None:
            focus_iv.append((st_t, r.t))
            st_t = None

    def item_of(t):
        k = np.where((t0 <= t) & (t <= t1 + 0.5))[0]
        return k[0] if len(k) else None

    idle_items = []
    for a, b in idle_iv:
        k = item_of(a)
        if k is None or b - a < 20:
            continue
        in_focus_loss = any(fa < b and fb > a for fa, fb in focus_iv)
        if not in_focus_loss and z[k] > -0.5:
            idle_items.append((k, a, b))
    ic = [k for k, a, b in idle_items if corr[k] == 1 and pexp_r[k] < UNEXPECTED_P]
    feats["idle_correct_unexpected"] = len(ic)
    if idle_items:
        ks = [k for k, _, _ in idle_items]
        feats["idle_correct_excess"] = float(corr[ks].sum() - pexp_r[ks].sum())
    else:
        feats["idle_correct_excess"] = 0.0

    # ------------------------------------------------ focus changes
    ftc = []
    for a, b in focus_iv:
        k = item_of(b)
        if k is not None and 0 <= t1[k] - b <= 15 and corr[k] == 1 and pexp_r[k] < 0.7:
            ftc.append((k, a, b))
    feats["focus_then_correct"] = len(ftc)
    feats["focus_away_total"] = float(sum(b - a for a, b in focus_iv))
    if ftc:
        evid.append(Evidence(
            "focus_then_correct", min(a for _, a, _ in ftc), max(t1[k] for k, _, _ in ftc), [qa[k] for k, _, _ in ftc],
            f"{pl(len(ftc), 'time')} the test window lost focus (left for {', '.join(f'{b - a:.0f} s' for _, a, b in ftc[:5])}) "
            f"and on return a difficult item was answered correctly within 15 s ({qlabel([qa[k] for k, _, _ in ftc])}).",
            f"You left the test screen {pl(len(ftc), 'time')} and answered a question correctly soon after coming back.",
            moments=[(a, f"left test window (Q{qa[k] + 1})") for k, a, _ in ftc] + [(b, "returned") for _, _, b in ftc]))
    elif focus_iv:
        tot = sum(b - a for a, b in focus_iv)
        evid.append(Evidence(
            "focus_then_correct", focus_iv[0][0], focus_iv[-1][1], [],
            f"Left the test window {pl(len(focus_iv), 'time')}, {tot:.0f} s in total; none was followed by a quick correct answer.",
            f"You left the test screen {pl(len(focus_iv), 'time')}.",
            moments=[(a, f"left test window ({b - a:.0f} s)") for a, b in focus_iv]))

    # ------------------------------------------------ paste
    pastes = ev[ev.type == "paste"]
    feats["paste_large"] = int((pastes.chars >= 60).sum())
    feats["paste_chars_max"] = float(pastes.chars.max()) if len(pastes) else 0.0
    big = pastes[pastes.chars >= 60]
    if not len(big):
        big = pastes
    if len(big):
        evid.append(Evidence(
            "paste_large", big.t.min(), big.t.max(), big["item"].tolist(),
            f"Pasted text into {qlabel(big['item'])}: " + ", ".join(f"{c} characters at {mmss(t)}" for c, t in zip(big.chars, big.t)) + ".",
            f"Text was pasted into {qlabel(big['item'])} rather than typed.",
            moments=[(t, f"paste {c} chars") for c, t in zip(big.chars, big.t)]))

    # ------------------------------------------------ collusion
    c = coll.get(sid, dict(score=0, nshare=0, sync=0, pair_z=0, mutual_z=0, partners=[]))
    feats["collusion_score"] = c["score"]
    feats["collusion_nshare"] = c["nshare"]
    feats["collusion_sync"] = c["sync"]
    feats["collusion_pair_z"] = min(c["pair_z"], 50.0)
    feats["collusion_mutual_z"] = min(c.get("mutual_z", 0.0), 50.0)
    feats["_top_mutual"] = c.get("top_mutual", [])
    if c["partners"] or c.get("closest"):
        strong = bool(c["partners"])
        p0 = c["partners"][0] if strong else c["closest"]
        others = [p[0] for p in c["partners"][1:]]
        shared_q, lock_q = p0[4], p0[5]
        qs_all = sorted(set(shared_q) | set(lock_q))
        times = [ans.loc[q, "t"] for q in qs_all if q in ans.index]
        evid.append(Evidence(
            "collusion_score", min(times) if times else 0, max(times) if times else 0, qs_all,
            (f"Matches {p0[0]} far more than chance, and the match stands out from both candidates' side "
             f"(each is the other's unusual match among ~200 in the sitting): " if strong
             else f"Closest match in the sitting is {p0[0]} (within the normal range for this sitting, z = {c['pair_z']:.1f}): ")
            + f"the same wrong option on {pl(p0[1], 'item')}"
            + (f" ({qlabel(shared_q)})" if shared_q else "")
            + f", and the same option submitted within 20 s of each other on {pl(p0[2], 'item')}"
            + (f" ({qlabel(lock_q)})" if lock_q else "") + "."
            + (f" Also matches {', '.join(others)}." if others else ""),
            "Your answers matched another candidate's in the same sitting much more than chance would explain — "
            "including the same wrong answers, submitted at nearly the same moment.",
            moments=[(ans.loc[q, "t"], f"Q{q + 1}: {ans.loc[q, 'option']} (same as {p0[0]})") for q in qs_all if q in ans.index]))
        if strong:
            feats["_partners"] = [p[0] for p in c["partners"]]

    # ------------------------------------------------ video, normalised by coverage
    duration = max(t1.max() if len(t1) else 1, 60)
    ft = fr.t.values
    feats["video_fpm"] = len(ft) / (duration / 60)
    feats["face_visible_frac"] = float(fr.face_visible.mean()) if len(fr) else np.nan
    feats["brightness_mean"] = float(fr.brightness.mean()) if len(fr) else np.nan
    feats["blur_mean"] = float(fr.blur.mean()) if len(fr) else np.nan
    feats["is_phone"] = float(meta["device"] == "phone")
    feats["is_low_bw"] = float(meta["bandwidth_class"] == "low")

    if len(ft) >= 5:
        multi = fr.faces.values >= 2
        gap = np.median(np.diff(ft)) if len(ft) > 1 else 5
        # episodes: consecutive multi-face frames, allowing one missing frame
        eps = []
        i = 0
        while i < len(ft):
            if multi[i]:
                j = i
                while j + 1 < len(ft) and (multi[j + 1] or (j + 2 < len(ft) and multi[j + 2])) and ft[j + 1] - ft[j] < 3 * gap + 5:
                    j += 1
                while j > i and not multi[j]:
                    j -= 1
                dur = ft[j] - ft[i] + gap
                eps.append((ft[i], ft[j] + gap / 2, dur, j - i + 1, multi[i:j + 1].sum()))
                i = j + 1
            else:
                i += 1
        persist = [e for e in eps if e[2] >= 25 and e[4] >= 3]
        feats["multi_face_persist_frac"] = sum(e[2] for e in persist) / duration
        # second face while answering correctly
        if len(qs):
            on = []
            for k in range(len(qs)):
                m = (ft >= t0[k]) & (ft <= t1[k])
                if m.sum() and corr[k] == 1 and multi[m].mean() >= 0.5:
                    on.append(k)
            feats["multi_face_on_correct"] = len(on)
        else:
            feats["multi_face_on_correct"] = 0
        if persist:
            e = max(persist, key=lambda e: e[2])
            ks = [k for k in range(len(qs)) if t0[k] < e[1] and t1[k] > e[0]]
            nc = int(sum(corr[k] for k in ks))
            evid.append(Evidence(
                "multi_face_persist_frac", e[0], e[1], [qa[k] for k in ks],
                f"A second face stayed in view for {e[2] / 60:.1f} min ({mmss(e[0])}–{mmss(e[1])}, {e[4]} of {e[3]} frames)"
                + (f" while {qlabel([qa[k] for k in ks])} were answered ({nc} of {len(ks)} correct)." if ks else "."),
                f"Another person was visible next to you for about {max(1, round(e[2] / 60))} minute(s) from {mmss(e[0])}.",
                moments=[(e[0], "second face appears"), (e[1], "second face leaves")]))
        elif feats["multi_face_on_correct"]:
            evid.append(Evidence(
                "multi_face_persist_frac", t0[on].min(), t1[on].max(), [qa[k] for k in on],
                f"A second face was in at least half the frames while answering {qlabel([qa[k] for k in on])} (all correct); "
                f"no single appearance lasted 25 s or more.",
                f"Another person was visible while you answered {qlabel([qa[k] for k in on])}.",
                moments=[(t0[k], f"Q{qa[k] + 1}: second face") for k in on]))
        short = [e for e in eps if e not in persist]
        feats["_transient_faces"] = len(short)

        # head-down during no-input pauses vs the candidate's own baseline
        gz = fr.gaze.values
        vis = fr.face_visible.values == 1
        in_idle = np.zeros(len(ft), bool)
        for k, a, b in idle_items:
            in_idle |= (ft >= a) & (ft <= b)
        base = (gz[vis & ~in_idle] == "down").mean() if (vis & ~in_idle).sum() >= 5 else np.nan
        if (vis & in_idle).sum() >= 2 and not np.isnan(base):
            feats["gaze_down_excess_idle"] = float((gz[vis & in_idle] == "down").mean() - base)
        else:
            feats["gaze_down_excess_idle"] = np.nan  # camera could not see: no evidence
        gdu_items = []
        for k in range(len(qs)):
            m = (ft >= t0[k]) & (ft <= t1[k]) & vis
            if m.sum() >= 2 and corr[k] == 1 and pexp_r[k] < UNEXPECTED_P and (gz[m] == "down").mean() >= 0.6 and (gz[m] == "down").mean() > base + 0.25:
                gdu_items.append(k)
        feats["gaze_down_on_unexpected"] = len(gdu_items)
    else:
        for k in ["multi_face_persist_frac", "multi_face_on_correct", "gaze_down_excess_idle", "gaze_down_on_unexpected"]:
            feats[k] = np.nan
        feats["_transient_faces"] = 0
        base = np.nan
        gdu_items = []

    # ------------------------------------------------ phone in view (on-device detector, reports/PHONE_DETECTOR_CHECK.md)
    # Each frame carries the share of seconds since the previous frame in which the phone's own detector saw a phone.
    # Missing (slow link, detector not loaded) = no evidence. A phone counts only when seen for >= 2 s inside an
    # answer window AND that answer is an unexpectedly correct one (a hard item for this candidate): on its own a
    # phone in view never adds suspicion.
    feats["_phone_secs"] = 0.0
    ph = pd.to_numeric(fr["phone"], errors="coerce").values if "phone" in fr else np.zeros(0)
    if len(ph) and np.isfinite(ph).sum() >= 5:
        gaps = np.clip(np.diff(np.concatenate([[ft[0] if len(ft) else 0.0], ft])), 0, 10)
        gaps[0] = np.median(gaps[1:]) if len(gaps) > 1 else 1.0
        secs = np.nan_to_num(ph) * gaps
        feats["_phone_secs"] = float(secs.sum())
        ph_items, ph_secs = [], []
        for k in range(len(qs)):
            m = (ft >= t0[k]) & (ft <= t1[k] + 1)
            sk = float(secs[m].sum())
            if sk >= 2 and corr[k] == 1 and pexp_r[k] < UNEXPECTED_P:   # a hard item answered correctly
                ph_items.append(k)
                ph_secs.append(sk)
        feats["phone_on_correct"] = len(ph_items)
        if ph_items:
            evid.append(Evidence(
                "phone_on_correct", t0[ph_items].min(), t1[ph_items].max(), [qa[k] for k in ph_items],
                f"A phone was in view for about {sum(ph_secs):.0f} s while {qlabel([qa[k] for k in ph_items])} "
                f"{'was' if len(ph_items) == 1 else 'were'} answered correctly (seen by the on-device detector; no image was sent).",
                f"A phone was visible to the camera while you answered {qlabel([qa[k] for k in ph_items])}.",
                moments=[(t0[k], f"Q{qa[k] + 1}: phone in view ({s_:.0f} s)") for k, s_ in zip(ph_items, ph_secs)]))
    else:
        feats["phone_on_correct"] = np.nan          # detector did not run: no evidence

    pause_items = ic if ic else [k for k, a, b in idle_items if corr[k] == 1]
    if pause_items:
        ic = pause_items
        ks = [k for k, a, b in idle_items if k in ic]
        ivs = [(a, b) for k, a, b in idle_items if k in ic]
        dmean = np.mean([b - a for a, b in ivs])
        gde = feats.get("gaze_down_excess_idle")
        video_part = ""
        if gde is not None and not np.isnan(gde):
            video_part = f" Head was down {100 * (base + gde):.0f}% of visible frames during these pauses vs {100 * base:.0f}% at other times."
        else:
            video_part = " Video was too sparse during these pauses to confirm or rule out a device; timing alone triggered this."
        evid.append(Evidence(
            "idle_correct_unexpected", min(a for a, _ in ivs), max(b for _, b in ivs), [qa[k] for k in ks],
            f"{pl(len(ks), 'long pause')} with no mouse, touch or keyboard input (avg {dmean:.0f} s) on difficult "
            f"{'item' if len(ks) == 1 else 'items'} {qlabel([qa[k] for k in ks])}, "
            f"{'followed' if len(ks) == 1 else 'each followed'} by a correct answer without leaving the test window.{video_part}",
            "On several hard questions there was a long pause with no activity on the test screen, followed by a correct answer.",
            moments=[(a, f"Q{qa[k] + 1}: input stops") for k, a, _ in idle_items if k in ic]))
    elif gdu_items:
        evid.append(Evidence(
            "idle_correct_unexpected", t0[gdu_items].min(), t1[gdu_items].max(), [qa[k] for k in gdu_items],
            f"Head down in most visible frames while answering difficult items {qlabel([qa[k] for k in gdu_items])} correctly "
            f"(this candidate's usual head-down rate: {100 * base:.0f}%).",
            "While answering some hard questions you were looking down for most of the time.",
            moments=[(t0[k], f"Q{qa[k] + 1}: head down") for k in gdu_items]))

    # legacy flags (what the old rules would have raised) — for comparison only
    legacy = int((fr.faces >= 2).sum() + (fr.face_visible == 0).sum() + (fr.gaze.isin(["down", "left", "right", "away"])).sum()
                 + (ev.type == "focus_lost").sum() + (ev.type == "paste").sum())
    feats["_legacy_flags"] = legacy
    feats["_legacy_frame_rate"] = (legacy - (ev.type == "focus_lost").sum() - (ev.type == "paste").sum()) / max(len(fr), 1)
    feats["_focus_losses"] = len(focus_iv)
    feats["_duration"] = float(duration)
    # ------------------------------------------------ clicking through the paper
    # A candidate who races through in a fraction of the usual time with answers at chance level is not relaying
    # answers (that gives fast AND right). Their timing pattern says nothing about malpractice, so it is not counted;
    # the reviewer sees a note. Fast and mostly right is still counted. Found in the first hostel pilot.
    feats["_rushed_guess"] = 0.0
    if len(qs) >= 8:
        spent = float(np.sum(np.maximum(t1 - t0, 0)))
        typical = float(np.sum(np.exp(st.med_logt[qa])))
        guess_rate = float(np.mean(np.where(st.kind[qa] == "mcq", 0.25, 0.0)))
        if typical > 0 and spent < RUSH_SHARE * typical and corr.mean() <= guess_rate + RUSH_MARGIN:
            feats["_rushed_guess"] = 1.0
            feats["_rush_secs"], feats["_rush_typical"] = spent, typical
            for k in TIMING_FEATURES:
                if k in feats:
                    feats[k] = 0.0
            evid = [e for e in evid if e.key not in TIMING_FEATURES]
    return feats, evid


def build(sessions, events, frames, items, stats: ItemStats | None = None, frame_every: float | None = None):
    """Compute features + evidence for every session.

    frame_every: if given, simulate a worse connection by keeping at most one
    frame per `frame_every` seconds (used for the 1-frame-per-5-s robustness test).
    """
    events = one_answer_per_item(events)
    st = stats or ItemStats.fit(events, items)
    if frame_every:
        frames = frames.copy()
        frames["_bin"] = (frames.t // frame_every).astype(int)
        frames = frames.drop_duplicates(["session_id", "_bin"]).drop(columns="_bin")
    coll = collusion_table(events, sessions, st.kind)
    ev_g = {k: g for k, g in events.groupby("session_id")}
    fr_g = {k: g for k, g in frames.groupby("session_id")}
    empty_ev = events.iloc[:0]
    empty_fr = frames.iloc[:0]
    rows, evidence = [], {}
    for meta in sessions.to_dict("records"):
        sid = meta["session_id"]
        f, e = session_features(sid, ev_g.get(sid, empty_ev), fr_g.get(sid, empty_fr), meta, st, coll)
        f["session_id"] = sid
        rows.append(f)
        evidence[sid] = e
    df = pd.DataFrame(rows).set_index("session_id")
    _ring_features(df, evidence)
    return df, evidence, st


def _ring_features(df: pd.DataFrame, evidence: dict):
    """Group mutual matches into rings. A ring 'leader' who answered on their own
    still gets linked to the followers who relayed their answers quickly."""
    parts = {sid: (p if isinstance(p, list) else []) for sid, p in df.get("_partners", pd.Series(dtype=object)).items()}
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, ps in parts.items():
        for b in ps:
            parent[find(a)] = find(b)
    comp = {}
    for a in parts:
        if parts[a]:
            comp.setdefault(find(a), []).append(a)
    size = {a: len(m) for m in comp.values() for a in m}
    fast = (df["self_fast_correct"].fillna(0) + df["fast_correct_unexpected"].fillna(0)).to_dict()
    df["ring_size"] = [size.get(a, 0) for a in df.index]
    df["ring_partner_fast"] = [max([fast.get(b, 0) for b in parts.get(a, [])], default=0) for a in df.index]
    # attach: strongest two-sided match is a member of a ring of 3+ (catches a member just under the bar)
    tm = df.get("_top_mutual", pd.Series(dtype=object)).to_dict()
    df["ring_attach"] = [max([z for b, z in (tm.get(a) if isinstance(tm.get(a), list) else []) if size.get(b, 0) >= 3 and a not in parts.get(b, [])] or [0.0])
                         if size.get(a, 0) == 0 else 0.0 for a in df.index]
    for a in df.index:
        if df.at[a, "ring_attach"] > 0:
            b, z = max(((b, z) for b, z in tm[a] if size.get(b, 0) >= 3), key=lambda x: x[1])
            members = sorted(comp[find(b)])
            evidence[a].append(Evidence(
                "collusion_score", 0, 0, [],
                f"Strongest two-sided answer match is {b} (z = {z:.1f}), who belongs to a group of {len(members)} candidates "
                f"whose answers match each other: {', '.join(members)}.",
                "Your answers were similar to those of a group of candidates whose answers matched each other closely."))
    for a in df.index:
        if size.get(a, 0) >= 3:
            members = sorted(m for m in comp[find(a)] if m != a)
            for e in evidence[a]:
                if e.key == "collusion_score":
                    e.text += f" Part of a group of {size[a]} candidates who match each other: {', '.join(members)}."

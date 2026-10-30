"""Integrity signals and model for coding tests.

Signals (each with the moments it happened, so a reviewer can check it):
  code_match   the final program matches another candidate's after renaming / spacing / comments are ignored
  paste        most of a solution arrived by paste, often right after leaving the test window
  typing       text that was neither typed nor pasted (large insertions), or a long still pause followed by the
               whole solution typed with almost no corrections (copying from a phone or a helper)
  timing       solved far faster than the problem's typical time, first try, without trying the samples
What is NOT counted: small pastes (moving your own lines), short tab switches with no paste after, fast typing
by itself, and similar short programs that many candidates write the same way (common fragments are removed).

The model is the same kind as for question tests (gradient-boosted trees with monotonic constraints and
calibration), trained on synthetic coding sittings (fairproctor/coding_synth.py).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.isotonic import IsotonicRegression
from sklearn.model_selection import GroupKFold

from .codesim import common_fingerprints, fingerprints, similarity

RISK = ["code_sim", "code_sim_n", "code_verbatim", "paste_share", "big_paste_accept", "focus_paste", "burst_share", "untyped_share",
        "no_fix", "idle_burst", "fast_accept", "first_try_fast"]
CONTEXT = ["n_accepted", "n_attempted"]
FEATURES = RISK + CONTEXT
FAMILY = dict(code_sim="code_match", code_sim_n="code_match", code_verbatim="code_match", paste_share="paste", big_paste_accept="paste",
              focus_paste="paste", burst_share="typing", untyped_share="typing", no_fix="typing", idle_burst="typing",
              fast_accept="timing", first_try_fast="timing")
FAMILY_TITLE = dict(code_match="Code matches another candidate", paste="Solution pasted in",
                    typing="Code that was not typed normally", timing="Solved unusually fast")
CANDIDATE_TITLE = dict(code_match="Your code is very similar to another candidate's",
                       paste="Large parts of the code were pasted",
                       typing="Unusual typing", timing="Some problems were solved very quickly")
SIM_LINE = 0.7            # a problem counts as "matching" from here
BIG_PASTE = 120           # characters


def mmss(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


@dataclass
class CodingStats:
    """Per problem: typical time from opening to the first accepted submit (seconds)."""
    typical: dict[int, float] = field(default_factory=dict)

    @staticmethod
    def fit(ev: pd.DataFrame, runs: pd.DataFrame, items: list[int]) -> "CodingStats":
        tta = _time_to_accept(ev, runs)
        typ = {}
        for it in items:
            v = [x for (s, i), x in tta.items() if i == it]
            typ[it] = float(np.median(v)) if len(v) >= 5 else 600.0
        return CodingStats(typ)


def _time_to_accept(ev: pd.DataFrame, runs: pd.DataFrame) -> dict[tuple[str, int], float]:
    shown = ev[ev.type == "item_shown"].groupby(["session_id", "item"]).t.min().to_dict()
    acc = runs[(runs.kind == "submit") & (runs.verdict == "accepted")].groupby(["session_id", "item"]).t.min().to_dict()
    return {k: max(1.0, acc[k] - shown.get(k, 0.0)) for k in acc}


def final_codes(runs: pd.DataFrame) -> dict[tuple[str, int], dict]:
    """The program each candidate stands by: best submit (latest on ties), else the last run."""
    out = {}
    for (sid, item), g in runs.groupby(["session_id", "item"]):
        sub = g[g.kind == "submit"]
        if len(sub):
            best = sub.sort_values(["passed", "t"]).iloc[-1]
        else:
            best = g.sort_values("t").iloc[-1]
        out[(sid, item)] = dict(code=best.code, language=best.language, t=float(best.t), verdict=best.verdict,
                                passed=int(best.passed), total=int(best.total))
    return out


def similarity_table(sessions: pd.DataFrame, runs: pd.DataFrame, starters: dict | None = None):
    """Best match per (session, problem) within the same sitting and language: (sim, partner, my lines, their lines)."""
    finals = final_codes(runs)
    sitting = sessions.set_index("session_id").window_id.to_dict()
    groups: dict[tuple, list] = {}
    for (sid, item), f in finals.items():
        groups.setdefault((sitting.get(sid), item, f["language"]), []).append(sid)
    out = {}
    for (w, item, lang), sids in groups.items():
        fps = {s: fingerprints(finals[(s, item)]["code"], lang) for s in sids}
        st = [(starters or {}).get(item, {}).get(lang, "")] if starters else []
        ignore = common_fingerprints(list(fps.values()), 0.3, [x for x in st if x], lang)
        raw: dict[str, dict] = {}
        for i, a in enumerate(sids):
            for b in sids[i + 1:]:
                sim, la, lb = similarity(fps[a], fps[b], ignore)
                if sim <= 0:
                    continue
                verb = 0.0
                if sim >= 0.5:                      # same names and values too? (a verbatim copy keeps them)
                    for s_ in (a, b):
                        if s_ not in raw:
                            raw[s_] = fingerprints(finals[(s_, item)]["code"], lang, raw=True)
                    verb = similarity(raw[a], raw[b], min_size=8)[0]
                for me, other, lm, lo in ((a, b, la, lb), (b, a, lb, la)):
                    if sim > out.get((me, item), (0,))[0] or (sim == out[(me, item)][0] and verb > out[(me, item)][4]):
                        out[(me, item)] = (sim, other, sorted(lm), sorted(lo), verb)
    return out, finals


def build(sessions: pd.DataFrame, events: pd.DataFrame, runs: pd.DataFrame, items: list[int],
          stats: CodingStats | None = None, starters: dict | None = None):
    """Features + evidence for every session. events: session_id, t, type, item, chars, meta (dict)."""
    st = stats or CodingStats.fit(events, runs, items)
    simt, finals = similarity_table(sessions, runs, starters)
    tta = _time_to_accept(events, runs)
    ev_by = {k: g.sort_values("t") for k, g in events.groupby("session_id")}
    runs_by = {k: g.sort_values("t") for k, g in runs.groupby("session_id")}
    rows, evidence = {}, {}
    for sid in sessions.session_id:
        e = ev_by.get(sid, events.iloc[0:0])
        r = runs_by.get(sid, runs.iloc[0:0])
        f = {k: 0.0 for k in FEATURES}
        f["_partners"] = []
        evd = []
        accepted = set(r[(r.kind == "submit") & (r.verdict == "accepted")].item)
        f["n_accepted"] = len(accepted)
        f["n_attempted"] = int(r.item.nunique()) if len(r) else 0
        for it in items:
            fin = finals.get((sid, it))
            if not fin:
                continue
            L = max(len(fin["code"]), 1)
            P = it + 1
            ei = e[e.item == it]
            typing = ei[ei.type == "code_typing"]
            metas = [m if isinstance(m, dict) else {} for m in typing.meta] if len(typing) else []
            ins = sum(float(m.get("ins", 0)) for m in metas)
            dele = sum(float(m.get("dele", 0)) for m in metas)
            pastes = ei[ei.type == "paste"]
            pchars = float(pastes.chars.sum()) if len(pastes) else 0.0
            # ---- code match
            if (sid, it) in simt:
                sim, other, lm, lo, verb = simt[(sid, it)]
                f["code_sim"] = max(f["code_sim"], sim)
                f["code_verbatim"] = max(f["code_verbatim"], verb if sim >= SIM_LINE else 0.0)
                if 0.5 <= sim < SIM_LINE:
                    evd.append(dict(key="code_sim_partial", family="code_match", t0=fin["t"], t1=fin["t"], items=[P], strength=sim,
                                    text=f"P{P}: final program partly matches {other} ({round(100 * sim)}% after renaming is ignored).",
                                    candidate_text=f"Parts of your program for problem {P} are similar to another candidate's.",
                                    moments=[dict(t=fin["t"], label=f"P{P}: program submitted")],
                                    lines=lm, partner=other, partner_lines=lo, item=it))
                if sim >= SIM_LINE:
                    f["code_sim_n"] += 1
                    if other not in f["_partners"]:
                        f["_partners"].append(other)
                    ofin = finals.get((other, it), {})
                    first = "after" if fin["t"] > ofin.get("t", 0) else "before"
                    evd.append(dict(key="code_sim", family="code_match", t0=fin["t"], t1=fin["t"], items=[P], strength=sim,
                                    text=(f"P{P}: final program matches {other} at {round(100 * sim)}% after renaming, spacing and "
                                          f"comments are ignored (common fragments and starter code removed)"
                                          + (f"; {round(100 * verb)}% even with the original names and values" if verb >= 0.5 else "")
                                          + f". Submitted {abs(fin['t'] - ofin.get('t', fin['t'])) / 60:.0f} min {first} theirs."),
                                    candidate_text=f"Your program for problem {P} is very similar to another candidate's program.",
                                    moments=[dict(t=fin["t"], label=f"P{P}: matching program submitted")],
                                    lines=lm, partner=other, partner_lines=lo, item=it))
            # ---- paste
            share = min(1.0, pchars / L)
            f["paste_share"] = max(f["paste_share"], share)
            sub = r[(r.item == it) & (r.kind == "submit") & (r.verdict == "accepted")]
            for _, p in pastes.iterrows():
                if p.chars >= max(BIG_PASTE, 0.4 * L):
                    after = sub[(sub.t >= p.t) & (sub.t <= p.t + 240)]
                    if len(after):
                        f["big_paste_accept"] += 1
                        evd.append(dict(key="big_paste_accept", family="paste", t0=float(p.t), t1=float(after.t.iloc[0]), items=[P],
                                        strength=share,
                                        text=(f"P{P}: pasted {int(p.chars)} characters ({round(100 * min(1, p.chars / L))}% of the "
                                              f"final program) at {mmss(p.t)}; accepted {after.t.iloc[0] - p.t:.0f} s later."),
                                        candidate_text=f"Most of your code for problem {P} was pasted in, then accepted soon after.",
                                        moments=[dict(t=float(p.t), label=f"P{P}: paste {int(p.chars)} chars"),
                                                 dict(t=float(after.t.iloc[0]), label=f"P{P}: accepted")], item=it))
            fl = ei[ei.type.isin(["focus_lost", "focus_gained"])].sort_values("t")
            for _, g in fl[fl.type == "focus_gained"].iterrows():
                nxt = pastes[(pastes.t >= g.t) & (pastes.t <= g.t + 30) & (pastes.chars >= 80)]
                if len(nxt):
                    lost = fl[(fl.type == "focus_lost") & (fl.t <= g.t)].t
                    away = g.t - (lost.iloc[-1] if len(lost) else g.t)
                    f["focus_paste"] += 1
                    evd.append(dict(key="focus_paste", family="paste", t0=float(g.t - away), t1=float(nxt.t.iloc[0]), items=[P],
                                    strength=1.0,
                                    text=(f"P{P}: left the test window for {away:.0f} s, came back and pasted "
                                          f"{int(nxt.chars.iloc[0])} characters {nxt.t.iloc[0] - g.t:.0f} s later."),
                                    candidate_text=f"You left the test screen and pasted code into problem {P} right after coming back.",
                                    moments=[dict(t=float(g.t - away), label=f"P{P}: left test window"),
                                             dict(t=float(nxt.t.iloc[0]), label=f"P{P}: paste")], item=it))
            # ---- typing
            bursts = [(float(t), float(m.get("ins", 0)), float(m.get("max_ins", 0))) for t, m in zip(typing.t, metas)
                      if float(m.get("max_ins", 0)) >= 60 or float(m.get("ins", 0)) - float(m.get("dele", 0)) >= 150]
            bshare = min(1.0, sum(b[1] for b in bursts) / L)
            f["burst_share"] = max(f["burst_share"], bshare)
            if bursts:
                evd.append(dict(key="burst_share", family="typing", t0=bursts[0][0], t1=bursts[-1][0], items=[P], strength=bshare,
                                text=(f"P{P}: {len(bursts)} insertion(s) of {', '.join(str(int(b[1])) for b in bursts[:4])} characters "
                                      f"within 5 s that were not pastes ({round(100 * bshare)}% of the program)."),
                                candidate_text=f"Large blocks of code appeared in problem {P} without being typed or pasted.",
                                moments=[dict(t=b[0], label=f"P{P}: {int(b[1])} chars at once") for b in bursts[:4]], item=it))
            # characters that went in by typing (deletions and clearing the starter code do not cancel them)
            typed_in = max(0.0, ins - sum(b[1] for b in bursts))
            typed_net = typed_in
            untyped = max(0.0, 1 - min(1.0, (typed_in + pchars) / L))
            f["untyped_share"] = max(f["untyped_share"], untyped)
            t_end = fin["t"]
            if untyped >= 0.4 and not bursts:
                evd.append(dict(key="untyped_share", family="typing", t0=float(typing.t.min()) if len(typing) else t_end, t1=t_end,
                                items=[P], strength=untyped,
                                text=(f"P{P}: only {round(100 * (1 - untyped))}% of the final program ({L} characters) was typed or "
                                      f"pasted in the editor ({int(typed_net)} typed, {int(pchars)} pasted)."),
                                candidate_text=f"Much of your code for problem {P} did not come from typing or pasting in the editor.",
                                moments=[dict(t=t_end, label=f"P{P}: program submitted")], item=it))
            if ins >= 150:
                ratio = dele / max(ins, 1)
                nf = max(0.0, 0.12 - ratio) / 0.12
                f["no_fix"] = max(f["no_fix"], nf)
                if nf >= 0.5:
                    evd.append(dict(key="no_fix", family="typing", t0=float(typing.t.min()), t1=float(typing.t.max()), items=[P],
                                    strength=nf,
                                    text=(f"P{P}: {int(ins)} characters typed with only {int(dele)} deleted "
                                          f"({100 * ratio:.0f}%; most people correct 15–60% as they write)."),
                                    candidate_text=f"Your code for problem {P} was typed with almost no corrections.",
                                    moments=[dict(t=float(typing.t.min()), label=f"P{P}: typing starts")], item=it))
            # a still pause (no typing, never left the window), then most of the program typed fast and clean
            times = list(typing.t)
            for k in range(1, len(times)):
                gap = times[k] - times[k - 1] if k else 0
                if gap < 90:
                    continue
                left_during = len(fl[(fl.t > times[k - 1]) & (fl.t < times[k])])
                if left_during:
                    continue
                window = [(t, m) for t, m in zip(times[k:], metas[k:]) if t <= times[k] + 120]
                w_ins = sum(float(m.get("ins", 0)) for _, m in window)
                w_del = sum(float(m.get("dele", 0)) for _, m in window)
                if w_ins >= max(150, 0.5 * L) and w_del <= 0.06 * w_ins:
                    f["idle_burst"] += 1
                    evd.append(dict(key="idle_burst", family="typing", t0=float(times[k - 1]), t1=float(window[-1][0]), items=[P],
                                    strength=1.0,
                                    text=(f"P{P}: {gap / 60:.1f} min with no typing while staying on the test, then "
                                          f"{int(w_ins)} characters typed in {window[-1][0] - times[k] + 5:.0f} s with "
                                          f"{int(w_del)} corrections."),
                                    candidate_text=(f"On problem {P} there was a long pause with no typing, then most of the code "
                                                    "was typed quickly without corrections."),
                                    moments=[dict(t=float(times[k - 1]), label=f"P{P}: typing stops"),
                                             dict(t=float(times[k]), label=f"P{P}: fast clean typing starts")], item=it))
                    break
            # ---- timing
            if (sid, it) in tta:
                took = tta[(sid, it)]
                typ = st.typical.get(it, 600.0)
                fa = max(0.0, math.log(typ / took))
                f["fast_accept"] = max(f["fast_accept"], fa)
                if fa >= 0.7:
                    evd.append(dict(key="fast_accept", family="timing", t0=float(sub.t.min() - took), t1=float(sub.t.min()),
                                    items=[P], strength=typ / took,
                                    text=(f"P{P}: accepted {took / 60:.1f} min after opening it; the typical time in this "
                                          f"sitting is {typ / 60:.1f} min."),
                                    candidate_text=f"Problem {P} was solved much faster than most candidates.",
                                    moments=[dict(t=float(sub.t.min()), label=f"P{P}: accepted")], item=it))
                n_before = len(r[(r.item == it) & (r.t < sub.t.min())]) if len(sub) else 0
                if n_before == 0 and took < 0.5 * typ:
                    f["first_try_fast"] += 1
                    evd.append(dict(key="first_try_fast", family="timing", t0=float(sub.t.min() - took), t1=float(sub.t.min()),
                                    items=[P], strength=typ / took,
                                    text=(f"P{P}: accepted on the first submit after {took / 60:.1f} min, with no sample run "
                                          f"(typical: {typ / 60:.1f} min)."),
                                    candidate_text=f"Problem {P} was solved much faster than usual, on the first try.",
                                    moments=[dict(t=float(sub.t.min()), label=f"P{P}: accepted first try")], item=it))
        rows[sid] = f
        evidence[sid] = evd
    X = pd.DataFrame.from_dict(rows, orient="index")
    return X, evidence, st


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


class CodingModel:
    """Same recipe as IntegrityModel: monotone in every risk signal, skill (problems solved) can never add risk."""

    def __init__(self, seed: int = 0):
        self.seed = seed

    def _new(self):
        return HistGradientBoostingClassifier(max_iter=250, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20,
                                              l2_regularization=1.0, monotonic_cst=[1] * len(RISK) + [0] * len(CONTEXT),
                                              class_weight={0: 1, 1: 4}, random_state=self.seed)

    def _raw(self, clf, X):
        Xm = X[FEATURES].astype(float).fillna(0.0)
        lo = _logit(clf.predict_proba(Xm)[:, 1])
        Xe = Xm.copy()
        for c in RISK:
            Xe[c] = self.ref[c]
        env = _logit(clf.predict_proba(Xe)[:, 1])
        Xr = Xe.copy()
        for c in CONTEXT:
            Xr[c] = self.ref[c]
        return lo - (env - _logit(clf.predict_proba(Xr)[:, 1]))

    def fit(self, X, y, groups, n_splits=5):
        honest = X[y == 0]
        self.ref = {c: float(np.nanmedian(honest[c].astype(float))) for c in FEATURES}
        oof, fold, self.fold_clfs = np.zeros(len(X)), np.zeros(len(X), int), []
        for k, (tr, te) in enumerate(GroupKFold(n_splits).split(X, y, groups)):
            clf = self._new().fit(X.iloc[tr][FEATURES].astype(float).fillna(0), y[tr])
            oof[te] = self._raw(clf, X.iloc[te])
            fold[te] = k
            self.fold_clfs.append(clf)
        self.iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999).fit(oof, y)
        self.clf = self._new().fit(X[FEATURES].astype(float).fillna(0), y)
        self.oof_raw, self.oof_fold = oof, fold
        return self

    def raw(self, X):
        return self._raw(self.clf, X)

    def contributions(self, X, clf=None):
        clf = clf or self.clf
        base = self._raw(clf, X)
        out = {}
        for c in RISK:
            Xc = X.copy()
            Xc[c] = self.ref[c]
            out[c] = base - self._raw(clf, Xc)
        return pd.DataFrame(out, index=X.index)

    def oof_contributions(self, X):
        parts = []
        for k, clf in enumerate(self.fold_clfs):
            parts.append(self.contributions(X.iloc[np.where(self.oof_fold == k)[0]], clf))
        return pd.concat(parts).loc[X.index]


def context_notes(f: dict, evidence: list) -> list[str]:
    """What was looked at and deliberately not counted."""
    notes = []
    if 0 < f.get("paste_share", 0) and not any(e["family"] == "paste" for e in evidence):
        notes.append("Small pastes (moving your own lines within the editor) were not counted.")
    if 0 < f.get("code_sim", 0) < SIM_LINE:
        notes.append("Some similarity with other programs is normal for short problems; common fragments and starter "
                     "code were removed and the remaining similarity was below the review line.")
    if f.get("fast_accept", 0) > 0.5 and not any(e["key"] == "first_try_fast" for e in evidence):
        notes.append("Fast solving on its own is not counted: fast candidates who try the samples and fix mistakes are normal.")
    if not notes:
        notes.append("Leaving the tab briefly with no paste after it, and typing speed on its own, are not counted.")
    return notes


def explain(sid: str, f: dict, contrib: dict, evidence: list, score: float, band: str, mask=lambda s: s) -> dict:
    fam_c: dict[str, float] = {}
    for k, v in contrib.items():
        if v > 0:
            fam_c[FAMILY[k]] = fam_c.get(FAMILY[k], 0) + float(v)
    total = sum(fam_c.values()) or 1.0
    reasons = []
    for n, (fam, c) in enumerate(sorted(fam_c.items(), key=lambda x: -x[1])):
        ev = sorted([dict(e, text=mask(e["text"])) for e in evidence if e["family"] == fam],
                    key=lambda e: (e["key"] in ("code_sim_partial", "fast_accept", "untyped_share"), -float(e.get("strength") or 0)))
        if c < 0.4 and not (n == 0 and band != "clear"):
            continue
        if not ev:
            continue
        reasons.append(dict(family=fam, title=FAMILY_TITLE[fam], candidate_title=CANDIDATE_TITLE[fam],
                            weight=round(c / total, 3), logodds=round(c, 2), evidence=ev, fallback=None))
    if reasons:
        headline = reasons[0]["evidence"][0]["text"].split(". ")[0].rstrip(".") + "."
        if len(reasons) > 1:
            t2 = reasons[1]["title"]
            headline += f" Also: {t2[0].lower()}{t2[1:]}."
    else:
        headline = "No sign of copied, pasted or untyped code. Normal coding behaviour."
    moments = sorted({(m["t"], m["label"]) for r in reasons for e in r["evidence"] for m in e["moments"]})
    points = []
    if band != "clear":
        for r in reasons:
            for e in r["evidence"][:2]:
                points.append(dict(title=r["candidate_title"], text=e["candidate_text"], when=f"{mmss(e['t0'])}–{mmss(e['t1'])}",
                                   questions=e["items"][:12]))
    return dict(session_id=sid, score=score, band=band, headline=headline, reasons=reasons,
                context=context_notes(f, evidence),
                moments=[dict(t=t, at=mmss(t), label=l) for t, l in moments],
                partners=list(f.get("_partners") or []),
                candidate=dict(summary=("Your test was reviewed automatically and no issues were found that need a human check."
                                        if band == "clear" else
                                        "Your test has been sent for a check by a human reviewer. This is not a decision. "
                                        "Below is what the system noticed, with the time in the test it happened, so you can explain it."),
                               points=points, can_appeal=band != "clear"))

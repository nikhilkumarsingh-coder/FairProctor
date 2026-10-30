"""End-to-end: features -> model -> thresholds -> evaluation -> artifacts for the service.

    python -m fairproctor.pipeline --data data/sample --out artifacts
    python -m fairproctor.pipeline --data data/imap --out artifacts/events_only --events-only

--events-only (also chosen automatically when the data has no video frames): the model uses answer timing, focus,
paste and shared-answer features only, and the report goes to reports/RESULTS_EVENTS_ONLY.md.
"""
from __future__ import annotations

import argparse
import json
import os
import pickle
import time

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from .explain import explain
from .features import build, load
from .model import IntegrityModel

MARGIN = 0.25         # safety margin (log-odds) below the lowest-scoring confirmed case
TOP_PRECISION = 0.90  # "Review first" band: the top of the queue where precision stays >= this
GAZE = {"centre": 0, "down": 1, "left": 2, "right": 3, "away": 4, "unknown": 5}


def p_at_k(score, y, k):
    o = np.argsort(-score)[:k]
    return float(y[o].mean())


def evaluate(raw, y, s, legacy_rate, legacy_flags, fold):
    """All numbers are out-of-fold: each session is scored by a model that never saw it."""
    n = len(y)
    m = {}
    m["n_sessions"] = int(n)
    m["n_confirmed"] = int(y.sum())
    m["auc"] = round(float(roc_auc_score(y, raw)), 4)
    m["average_precision"] = round(float(average_precision_score(y, raw)), 4)
    m["queue_at_full_recall"] = round(float((raw >= raw[y == 1].min()).mean()), 4)
    m["precision_at_k"] = {str(k): round(p_at_k(raw, y, k), 3) for k in (25, 50, 100, 200, int(y.sum()))}
    m["legacy_precision_at_k"] = {str(k): round(p_at_k(legacy_rate, y, k), 3) for k in (25, 50, 100, 200, int(y.sum()))}

    # ---- queue policy, chosen without looking at the fold being evaluated
    rows = []
    for k in np.unique(fold):
        tr, te = fold != k, fold == k
        T = raw[tr & (y == 1)].min() - MARGIN
        sel = raw[te] >= T
        rows.append(dict(fold=int(k), queue=int(sel.sum()), n=int(te.sum()), confirmed=int(y[te].sum()),
                         caught=int((sel & (y[te] == 1)).sum())))
    df = pd.DataFrame(rows)
    m["holdout_policy"] = dict(
        folds=rows,
        queue_fraction=round(df.queue.sum() / df.n.sum(), 3),
        recall=round(df.caught.sum() / df.confirmed.sum(), 4),
        missed=int(df.confirmed.sum() - df.caught.sum()),
    )
    # legacy baseline queue: every session with at least one flag
    m["legacy_queue_fraction"] = round(float((legacy_flags > 0).mean()), 3)
    m["legacy_flags_median"] = {bw: int(np.median(legacy_flags[s.bandwidth_class.values == bw])) for bw in ("low", "normal")}
    m["queue_reduction_vs_legacy"] = round(1 - m["holdout_policy"]["queue_fraction"] / m["legacy_queue_fraction"], 3)

    # ---- false-flag rate by bandwidth at the deployed threshold, vs legacy at the same queue size
    T = raw[y == 1].min() - MARGIN
    q = raw >= T
    n_q = int(q.sum())
    leg_q = np.zeros(n, bool)
    leg_q[np.argsort(-legacy_rate)[:n_q]] = True
    fpr = {}
    for bw in ("low", "normal"):
        hm = (s.bandwidth_class.values == bw) & (y == 0)
        fpr[bw] = dict(honest_sessions=int(hm.sum()),
                       ours=round(float(q[hm].mean()), 3),
                       legacy_same_queue_size=round(float(leg_q[hm].mean()), 3),
                       recall_ours=round(float(q[(s.bandwidth_class.values == bw) & (y == 1)].mean()), 3))
    m["false_flag_rate_by_bandwidth"] = fpr
    for dev in ("phone", "desktop"):
        hm = (s.device.values == dev) & (y == 0)
        m.setdefault("false_flag_rate_by_device", {})[dev] = round(float(q[hm].mean()), 3)
    m["deployed_threshold_queue_fraction"] = round(n_q / n, 3)
    if "_truth_type" in s:
        m["recall_by_type"] = {t: round(float(q[(s._truth_type.values == t) & (y == 1)].mean()), 3)
                               for t in sorted(set(s._truth_type)) if t != "none" and ((s._truth_type.values == t) & (y == 1)).any()}
    return m, T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/sample")
    ap.add_argument("--out", default="artifacts")
    ap.add_argument("--events-only", action="store_true", help="ignore video frames (event logs only)")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    t_start = time.time()

    sessions, events, frames, items = load(args.data)
    events_only = args.events_only or frames.empty
    if events_only:
        frames = frames.iloc[:0]
        print("event logs only: no video features")
    print("building features ...")
    X, evidence, stats = build(sessions, events, frames, items)
    s = sessions.set_index("session_id").loc[X.index]
    y = (s.verdict == "confirmed").values.astype(int)
    groups = s.window_id.values

    print("training ...")
    t0 = time.time()
    model = IntegrityModel(events_only=events_only).fit(X, y, groups)
    train_s = time.time() - t0
    raw = model.oof_raw
    # legacy ranking: share of analysed frames that raised a flag, plus browser flags
    legacy_rate = (X["_legacy_frame_rate"] + 0.01 * X["_focus_losses"]).values

    metrics, T = evaluate(raw, y, s, legacy_rate, X["_legacy_flags"].values, model.oof_fold)

    # "Review first" band
    o = np.argsort(-raw)
    prec = np.cumsum(y[o]) / np.arange(1, len(y) + 1)
    ok = np.where(prec >= TOP_PRECISION)[0]
    H = raw[o][ok.max()] if len(ok) else raw.max()
    metrics["review_first"] = dict(n=int((raw >= H).sum()), precision=round(float(y[raw >= H].mean()), 3))

    metrics["events_only"] = bool(events_only)
    pos = np.sort(raw[y == 1])[::-1]                    # queue needed to catch 80 / 90 / 95% of confirmed cases
    metrics["queue_at_recall"] = {str(r): round(float((raw >= pos[int(np.ceil(r * y.sum())) - 1]).mean()), 4)
                                  for r in (0.8, 0.9, 0.95)}
    half = raw >= np.sort(raw)[::-1][len(raw) // 2 - 1]
    metrics["recall_in_top_half"] = round(float(half[y == 1].mean()), 4)
    if "_truth_type" in s:
        metrics["recall_in_top_half_by_type"] = {t: round(float(half[(s._truth_type.values == t) & (y == 1)].mean()), 3)
                                                 for t in sorted(set(s._truth_type)) if t != "none" and ((s._truth_type.values == t) & (y == 1)).any()}

    # ---- robustness: video at one frame every 5 seconds (not applicable without video)
    print("robustness test: 1 frame / 5 s ..." if not events_only else "no video: skipping the 1 frame / 5 s test")
    Xd, evd, _ = build(sessions, events, frames, items, stats=stats, frame_every=None if events_only else 5.0)
    rawd = model.oof_raw_for(Xd.loc[X.index])
    qd = rawd >= T
    metrics["one_frame_per_5s"] = dict(
        auc=round(float(roc_auc_score(y, rawd)), 4),
        recall_at_threshold=round(float(qd[y == 1].mean()), 4),
        queue_fraction=round(float(qd.mean()), 3),
        precision_at_100=round(p_at_k(rawd, y, 100), 3),
        rank_correlation_with_full_video=round(float(pd.Series(raw).corr(pd.Series(rawd), method="spearman")), 3),
        recall_by_type={t: round(float(qd[(s._truth_type.values == t) & (y == 1)].mean()), 3)
                        for t in sorted(set(s._truth_type)) if t != "none" and ((s._truth_type.values == t) & (y == 1)).any()}
        if "_truth_type" in s else {},
    )
    # ---- CPU scoring speed
    t0 = time.time()
    model.raw(X.iloc[:1000])
    metrics["cpu_scoring_ms_per_session"] = round(1000 * (time.time() - t0) / 1000, 3)
    metrics["train_seconds"] = round(train_s, 1)

    # ---- explanations (out-of-fold contributions)
    print("explanations ...")
    contrib = model.oof_contributions(X)
    prob = model.iso.predict(raw)
    bands = np.where(raw >= H, "review_first", np.where(raw >= T, "review", "clear"))
    order_rank = pd.Series(raw, index=X.index).rank(ascending=False, method="first").astype(int)
    expl = {}
    ev_g = {k: g for k, g in events.groupby("session_id")}
    fdict = X.to_dict("index")
    cdict = contrib.to_dict("index")
    meta = sessions.set_index("session_id").to_dict("index")
    for i, sid in enumerate(X.index):
        expl[sid] = explain(sid, fdict[sid], cdict[sid], evidence[sid], meta[sid], round(100 * float(prob[i]), 1), bands[i],
                            events=ev_g[sid], stats=stats)
        expl[sid]["rank"] = int(order_rank[sid])

    # every flagged session must link back to moments
    q = bands != "clear"
    with_moments = np.mean([len(expl[sid]["moments"]) > 0 or any(r["fallback"] for r in expl[sid]["reasons"]) for sid in X.index[q]])
    metrics["flagged_sessions_with_linked_moments"] = round(float(np.mean([len(expl[sid]["moments"]) > 0 for sid in X.index[q]])), 3)
    metrics["flagged_sessions_with_any_explanation"] = round(float(with_moments), 3)

    # ---- store for the service
    fr_g = {k: g for k, g in frames.groupby("session_id")}
    store = {}
    for i, sid in enumerate(X.index):
        e = ev_g[sid]
        fr = fr_g.get(sid)
        store[sid] = dict(
            meta={k: (v if not isinstance(v, (np.integer,)) else int(v)) for k, v in meta[sid].items() if not k.startswith("_")},
            label=meta[sid]["verdict"],
            raw=float(raw[i]),
            explanation=expl[sid],
            events=e[["t", "type", "item", "option", "correct", "chars"]].values.tolist(),
            frames=None if fr is None else dict(
                t=fr.t.values.astype(np.float32), faces=fr.faces.values.astype(np.int8),
                vis=fr.face_visible.values.astype(np.int8), gaze=fr.gaze.map(GAZE).values.astype(np.int8)),
            duration=float(X.loc[sid, "_duration"]),
        )
    with open(f"{args.out}/store.pkl", "wb") as fh:
        pickle.dump(store, fh)
    with open(f"{args.out}/model.pkl", "wb") as fh:
        pickle.dump(dict(model=model, stats=stats, T=float(T), H=float(H)), fh)
    with open(f"{args.out}/metrics.json", "w") as fh:
        json.dump(metrics, fh, indent=2)
    from .report import render, render_events_only
    os.makedirs("reports", exist_ok=True)
    out_md = "reports/RESULTS_EVENTS_ONLY.md" if events_only else "reports/RESULTS.md"
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write(render_events_only(metrics) if events_only else render(metrics))
    print(json.dumps(metrics, indent=2))
    print(f"done in {time.time() - t_start:.0f} s")


if __name__ == "__main__":
    main()

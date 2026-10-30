"""Train and evaluate the coding integrity model on synthetic coding sittings.

    python -m fairproctor.coding_pipeline --out backend/model        # ~1 min on a laptop CPU

Writes coding_model.pkl (model, thresholds, priority scale data), coding_metrics.json and reports/CODING_RESULTS.md.
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

from . import coding
from .coding_synth import generate

TOP_PRECISION = 0.9
RECALL_LINE = 0.95


def p_at_k(score, y, k):
    o = np.argsort(-score)[:k]
    return float(y[o].mean())


def main(out: str, n_sittings: int = 30, per_sitting: int = 170, seed: int = 7):
    t0 = time.time()
    sessions, events, runs = generate(n_sittings, per_sitting, seed)
    print(f"generated {len(sessions)} sessions, {len(events)} events, {len(runs)} runs in {time.time() - t0:.1f} s")
    t0 = time.time()
    X, evidence, stats = coding.build(sessions, events, runs, items=[0, 1, 2])
    X = X.loc[sessions.session_id]
    print(f"features in {time.time() - t0:.1f} s")
    y = (sessions.verdict == "confirmed").astype(int).values
    groups = sessions.window_id.values
    t0 = time.time()
    model = coding.CodingModel().fit(X, y, groups)
    train_s = time.time() - t0
    raw = model.oof_raw
    o = np.argsort(-raw)
    rec = np.cumsum(y[o]) / y.sum()
    T = float(raw[o][np.searchsorted(rec, RECALL_LINE)])              # review line: 95 % of malpractice above it
    prec = np.cumsum(y[o]) / np.arange(1, len(y) + 1)
    ok = np.where(prec >= TOP_PRECISION)[0]
    H = float(raw[o][ok.max()]) if len(ok) else float(raw.max())
    q = raw >= T
    kinds = sessions._truth_type.values
    honest = y == 0
    expert = (sessions._expert.values == 1) & honest
    pasted_own = honest & X.paste_share.values.astype(bool)
    left_tab = honest & events[events.type == "focus_lost"].groupby("session_id").size().reindex(sessions.session_id).fillna(0).values.astype(bool)
    # a simple rule many tools use: any paste of 50+ characters or any tab switch flags the candidate
    big_paste = events[(events.type == "paste") & (events.chars >= 50)].groupby("session_id").size()
    naive = (sessions.session_id.map(big_paste).fillna(0).values > 0) | \
        sessions.session_id.isin(events[events.type == "focus_lost"].session_id).values
    m = dict(
        n_sessions=int(len(y)), n_malpractice=int(y.sum()),
        auc=round(float(roc_auc_score(y, raw)), 4), average_precision=round(float(average_precision_score(y, raw)), 4),
        precision_at_k={k: round(p_at_k(raw, y, k), 3) for k in (25, 50, 100, 200, int(y.sum()))},
        review_line=dict(recall=round(float(q[y == 1].mean()), 3), queue_fraction=round(float(q.mean()), 3),
                         honest_flagged=round(float(q[honest].mean()), 3)),
        review_first=dict(n=int((raw >= H).sum()), precision=round(float(y[raw >= H].mean()), 3)),
        recall_by_type={t: round(float(q[(kinds == t)].mean()), 3) for t in sorted(set(kinds)) if t != "none"},
        honest_flagged_by_group=dict(
            fast_experts=round(float(q[expert].mean()), 3), own_small_pastes=round(float(q[pasted_own].mean()), 3),
            left_tab_briefly=round(float(q[left_tab].mean()), 3), all_honest=round(float(q[honest].mean()), 3)),
        naive_rule=dict(rule="any paste of 50+ characters or any tab switch",
                        honest_flagged=round(float(naive[honest].mean()), 3), recall=round(float(naive[y == 1].mean()), 3)),
        train_seconds=round(train_s, 1),
    )
    # explanations: every queued session should point at moments
    contrib = model.oof_contributions(X)
    with_m = []
    for i, sid in enumerate(X.index):
        if raw[i] >= T:
            e = coding.explain(sid, X.loc[sid].to_dict(), contrib.loc[sid].to_dict(), evidence[sid], 0, "review")
            with_m.append(len(e["moments"]) > 0)
    m["queued_with_moments"] = round(float(np.mean(with_m)), 3) if with_m else None
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "coding_model.pkl"), "wb") as fh:
        pickle.dump(dict(model=model, stats=stats, T=T, H=H, raws=raw.astype(np.float32)), fh)
    with open(os.path.join(out, "coding_metrics.json"), "w") as fh:
        json.dump(m, fh, indent=2)
    report(m)
    print(json.dumps(m, indent=2))


def report(m: dict):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rb = m["recall_by_type"]
    hg = m["honest_flagged_by_group"]
    lines = [
        "# Coding integrity model — results on synthetic coding sittings",
        "",
        f"{m['n_sessions']} candidates in 30 synthetic sittings of the demo coding test (3 problems, Python and C++), "
        f"{m['n_malpractice']} with malpractice on 1–3 problems. Programs are real source code built from interchangeable "
        "parts; typing, pastes, tab switches, runs and submits are simulated over time. Scores are out-of-fold "
        "(each sitting scored by a model that never saw it). **These are synthetic results and are optimistic: real "
        "candidates and real cheating are more varied.**",
        "",
        "| Measure | Value |",
        "|---|---|",
        f"| AUC | {m['auc']} |",
        f"| Average precision | {m['average_precision']} |",
        f"| Precision in the top 50 / 100 | {m['precision_at_k'][50]} / {m['precision_at_k'][100]} |",
        f"| Review line: malpractice caught | {m['review_line']['recall']:.0%} |",
        f"| Review line: share of all candidates in the queue | {m['review_line']['queue_fraction']:.1%} |",
        f"| Review first: candidates / precision | {m['review_first']['n']} / {m['review_first']['precision']:.0%} |",
        "",
        "Caught at the review line, by kind of malpractice:",
        "",
        "| Web paste | Copied from a partner (both) | Typed from a phone or helper | Injected text |",
        "|---|---|---|---|",
        f"| {rb.get('web_paste', 0):.0%} | {rb.get('copy_pair', 0):.0%} | {rb.get('transcribe', 0):.0%} | {rb.get('inject', 0):.0%} |",
        "",
        "Honest candidates sent to review (false flags):",
        "",
        "| Group | FairProctor | Simple rule: any 50+ char paste or tab switch |",
        "|---|---|---|",
        f"| All honest candidates | {hg['all_honest']:.1%} | {m['naive_rule']['honest_flagged']:.1%} |",
        f"| Fast experts | {hg['fast_experts']:.1%} | |",
        f"| Moved their own lines with small pastes | {hg['own_small_pastes']:.1%} | |",
        f"| Left the tab briefly (no paste after) | {hg['left_tab_briefly']:.1%} | |",
        "",
        f"The simple rule catches {m['naive_rule']['recall']:.0%} of malpractice but flags "
        f"{m['naive_rule']['honest_flagged']:.0%} of honest candidates; FairProctor reviews "
        f"{m['review_line']['queue_fraction']:.0%} of candidates to catch {m['review_line']['recall']:.0%}.",
        "",
        "Known limits: the partner who *shared* code behaves honestly and is found only through the similarity of the "
        "two programs; very short programs give little to compare; a cheater who retypes a solution slowly with "
        "deliberate mistakes looks like an honest candidate. Similarity, paste and typing are evidence for a human "
        "reviewer, never a verdict.",
    ]
    with open(os.path.join(root, "reports", "CODING_RESULTS.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="backend/model")
    ap.add_argument("--sittings", type=int, default=30)
    a = ap.parse_args()
    main(a.out, a.sittings)

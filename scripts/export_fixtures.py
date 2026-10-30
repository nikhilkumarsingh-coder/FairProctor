"""Export real model output as demo fixtures for the FairProctor frontend.

    python scripts/export_fixtures.py --out ../fairproctor-web/public/demo

Writes:
    index.json              every session as a compact queue row (all 5,000)
    sessions/<id>.json      full detail for ~250 sessions (top of queue, a spread of
                            review / cleared / low-bandwidth sessions, and their
                            answer-match partners)
    metrics.json            evaluation numbers, marked as measured on synthetic data

Everything here is synthetic. Pseudonyms, sitting times and demo review statuses
are assigned deterministically so the same session always looks the same.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pickle
import random

import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fairproctor.display import EXAM, PriorityScale, demo_status, pseudonym, sitting, started_at  # noqa: E402

GAZE = ["centre", "down", "left", "right", "away", "unknown"]


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if np.isnan(o) else round(float(o), 2)
    if isinstance(o, float):
        return None if o != o else round(o, 2)
    return o


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", default="artifacts")
    ap.add_argument("--out", default="fixtures")
    ap.add_argument("--details", type=int, default=250)
    a = ap.parse_args()
    store = pickle.load(open(os.path.join(a.artifacts, "store.pkl"), "rb"))
    metrics = json.load(open(os.path.join(a.artifacts, "metrics.json")))
    os.makedirs(os.path.join(a.out, "sessions"), exist_ok=True)
    bundle = pickle.load(open(os.path.join(a.artifacts, "model.pkl"), "rb"))
    priority = PriorityScale([d["raw"] for d in store.values()], bundle["T"], bundle["H"])

    rows = []
    for sid, d in store.items():
        e, m = d["explanation"], d["meta"]
        rows.append(dict(
            id=sid, pseudonym=pseudonym(sid), sitting=sitting(m["window_id"]),
            startedAt=started_at(sid, m["window_id"]), durationS=round(d["duration"]),
            rank=e["rank"], priority=priority(d["raw"]), band=e["band"],
            status=demo_status(sid, e["band"], d.get("label", "")),
            families=[r["family"] for r in e["reasons"]], headline=e["headline"],
            bandwidth=m["bandwidth_class"], device=m["device"],
            eventCount=len(d["events"]), legacyFlags=e["legacy_flags"],
            hasMatchPartners=bool(e["partners"])))
    rows.sort(key=lambda r: r["rank"])

    # detail subset
    rnd = random.Random(7)
    pick = [r["id"] for r in rows[:110]]
    review = [r["id"] for r in rows if r["band"] == "review"]
    clear = [r["id"] for r in rows if r["band"] == "clear"]
    low = [r["id"] for r in rows if r["bandwidth"] == "low" and r["band"] != "review_first"]
    pick += rnd.sample(review, 45) + rnd.sample(clear, 35) + rnd.sample(low, 25)
    for sid in list(pick):
        pick += store[sid]["explanation"]["partners"]
    pick = list(dict.fromkeys(pick))[: a.details + 60]

    for sid in pick:
        d, row = store[sid], next(r for r in rows if r["id"] == sid)
        fr = d["frames"]
        detail = dict(
            row, synthetic=True, exam=EXAM,
            environment=dict(bandwidth=d["meta"]["bandwidth_class"], device=d["meta"]["device"],
                             precheckLight=d["meta"]["precheck_light"], precheckFraming=d["meta"]["precheck_framing"],
                             framesReceived=0 if fr is None else int(len(fr["t"])),
                             secondsPerFrame=None if fr is None or len(fr["t"]) < 2 else round(d["duration"] / len(fr["t"]), 1),
                             notCounted=d["explanation"]["context"]),
            sampleVerdict=d.get("label"),
            explanation={k: v for k, v in d["explanation"].items() if k not in ("candidate", "score")},
            calibratedProbabilitySynthetic=d["explanation"]["score"],
            candidateView=d["explanation"]["candidate"],
            events=[dict(t=e[0], type=e[1], item=e[2] if e[2] >= 0 else None, option=e[3] or None,
                         correct=None if e[4] < 0 else bool(e[4]), chars=e[5] or None) for e in d["events"]],
            frames=None if fr is None else dict(t=np.round(fr["t"], 1).tolist(), faces=fr["faces"].tolist(),
                                                faceVisible=fr["vis"].tolist(), gaze=[GAZE[g] for g in fr["gaze"]]),
        )
        with open(os.path.join(a.out, "sessions", f"{sid}.json"), "w") as fh:
            json.dump(clean(detail), fh, separators=(",", ":"))

    detail_ids = set(pick)
    for r in rows:
        r["hasDetail"] = r["id"] in detail_ids
    index = dict(synthetic=True, exam=EXAM, generatedAt=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                 counts={b: sum(r["band"] == b for r in rows) for b in ("review_first", "review", "clear")},
                 priorityLines=dict(review=50, reviewFirst=priority.review_first_line),
                 rows=rows)
    with open(os.path.join(a.out, "index.json"), "w") as fh:
        json.dump(clean(index), fh, separators=(",", ":"))
    with open(os.path.join(a.out, "metrics.json"), "w") as fh:
        json.dump(dict(metrics, synthetic=True, note="Measured on synthetic sample data, not real candidates."), fh, indent=1)
    print(f"index: {len(rows)} rows · details: {len(pick)} sessions · out: {a.out}")


if __name__ == "__main__":
    main()

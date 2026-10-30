"""FairProctor scoring service + reviewer console + candidate pages.

Built on Starlette (the framework FastAPI runs on), so it runs with only
`starlette` and `uvicorn`. Run from the project root:

    python -m uvicorn service.app:app --port 8000

Then open:
    http://localhost:8000/console              reviewer queue
    http://localhost:8000/precheck             candidate pre-test check (open on a phone)
    http://localhost:8000/candidate/S00042     what a candidate sees after a flag
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pickle
import secrets
import sys
import time

import numpy as np
import pandas as pd
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fairproctor.display import EXAM, PriorityScale, demo_status, pseudonym, sitting, started_at  # noqa: E402
from fairproctor.explain import explain  # noqa: E402
from fairproctor.features import build  # noqa: E402

ART = os.environ.get("FAIRPROCTOR_ARTIFACTS", os.path.join(ROOT, "artifacts"))
WEB = os.path.join(ROOT, "web")
LOGS = os.path.join(ART, "logs")
os.makedirs(LOGS, exist_ok=True)

with open(os.path.join(ART, "store.pkl"), "rb") as fh:
    STORE: dict = pickle.load(fh)
with open(os.path.join(ART, "model.pkl"), "rb") as fh:
    BUNDLE = pickle.load(fh)
with open(os.path.join(ART, "metrics.json")) as fh:
    METRICS = json.load(fh)
MODEL, STATS, T, H = BUNDLE["model"], BUNDLE["stats"], BUNDLE["T"], BUNDLE["H"]
PRIORITY = PriorityScale([d["raw"] for d in STORE.values()], T, H)
GAZE_NAMES = ["centre", "down", "left", "right", "away", "unknown"]
EV_COLS = ["t", "type", "item", "option", "correct", "chars"]


def _append(name, rec):
    rec = dict(rec, at=dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"))
    with open(os.path.join(LOGS, name), "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, float) and np.isnan(o):
        return None
    return o


def _row(sid, d):
    e = d["explanation"]
    w = d["meta"]["window_id"]
    return dict(session_id=sid, pseudonym=pseudonym(sid), sitting=sitting(w), started_at=started_at(sid, w),
                duration_s=round(d["duration"]), event_count=len(d["events"]), priority=PRIORITY(d["raw"]),
                status=demo_status(sid, e["band"], d.get("label", "")),
                rank=e["rank"], score=e["score"], band=e["band"], headline=e["headline"],
                families=[r["family"] for r in e["reasons"]], bandwidth=d["meta"]["bandwidth_class"],
                device=d["meta"]["device"], window=d["meta"]["window_id"], legacy_flags=e["legacy_flags"],
                label=d.get("label"))


QUEUE = sorted(STORE, key=lambda s: STORE[s]["explanation"]["rank"])


# --------------------------------------------------------------------------- pages
async def index(request):
    return RedirectResponse("/console")


async def console(request):
    return FileResponse(os.path.join(WEB, "console", "index.html"))


async def precheck(request):
    return FileResponse(os.path.join(WEB, "precheck", "index.html"))


async def candidate_page(request):
    return FileResponse(os.path.join(WEB, "candidate", "index.html"))


# --------------------------------------------------------------------------- API
async def api_queue(request: Request):
    p = request.query_params
    band = p.get("band", "queue")          # queue | review_first | review | clear | all
    bw = p.get("bandwidth", "all")
    q = p.get("q", "").strip().upper()
    fam = p.get("family", "")
    limit = min(int(p.get("limit", 50)), 500)
    offset = int(p.get("offset", 0))
    rows = []
    for sid in QUEUE:
        d = STORE[sid]
        e = d["explanation"]
        if band == "queue" and e["band"] == "clear":
            continue
        if band not in ("queue", "all") and e["band"] != band:
            continue
        if bw != "all" and d["meta"]["bandwidth_class"] != bw:
            continue
        if q and q not in sid:
            continue
        if fam and fam not in [r["family"] for r in e["reasons"]]:
            continue
        rows.append(sid)
    total = len(rows)
    counts = {b: sum(1 for s in STORE.values() if s["explanation"]["band"] == b) for b in ("review_first", "review", "clear")}
    return JSONResponse(dict(total=total, counts=counts, n_sessions=len(STORE), exam=EXAM, synthetic=True,
                             priority_lines=dict(review=50, review_first=PRIORITY.review_first_line),
                             rows=[_row(s, STORE[s]) for s in rows[offset:offset + limit]]))


async def api_session(request: Request):
    sid = request.path_params["sid"]
    d = STORE.get(sid)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    fr = d["frames"]
    frames = None
    if fr is not None:
        frames = dict(t=np.round(fr["t"], 1).tolist(), faces=fr["faces"].tolist(), vis=fr["vis"].tolist(),
                      gaze=[GAZE_NAMES[g] for g in fr["gaze"]])
    out = dict(session_id=sid, meta=d["meta"], label=d.get("label"), duration=d["duration"],
               explanation=d["explanation"], events=[dict(zip(EV_COLS, e)) for e in d["events"]], frames=frames,
               thresholds=dict(review=T, review_first=H), summary=_row(sid, d), exam=EXAM,
               priority_lines=dict(review=50, review_first=PRIORITY.review_first_line))
    return JSONResponse(_clean(out))


async def api_candidate(request: Request):
    """Only what the candidate may see: no partner ids, no reviewer labels, no scores of others."""
    sid = request.path_params["sid"]
    d = STORE.get(sid)
    if not d:
        return JSONResponse({"error": "not found"}, status_code=404)
    e = d["explanation"]
    return JSONResponse(_clean(dict(session_id=sid, status=e["band"], candidate=e["candidate"],
                                    retention_days=int(os.environ.get("RETENTION_DAYS", 90)))))


async def api_metrics(request):
    return JSONResponse(METRICS)


async def api_score(request: Request):
    """Score one session.

    Body: {"session": {session_id, window_id, device, bandwidth_class, precheck_light, precheck_framing},
           "events": [{t, type, item, option, correct, chars}, ...],
           "frames": [{t, faces, face_visible, gaze, brightness, blur}, ...]}
    Answer matching is done against the other sessions already stored for the same window.
    """
    body = await request.json()
    meta = body["session"]
    sid = meta["session_id"]
    w = meta.get("window_id", -1)
    t_start = time.time()
    # "replay_of" lets a stored session be re-scored live without matching against itself
    skip = {sid, meta.pop("replay_of", None)}
    others = [s for s, d in STORE.items() if d["meta"].get("window_id") == w and s not in skip]
    sess = pd.DataFrame([dict(STORE[s]["meta"], session_id=s) for s in others] + [dict(meta)])
    ev_rows = [dict(zip(EV_COLS, e), session_id=s) for s in others for e in STORE[s]["events"]]
    ev_rows += [dict({k: e.get(k, d) for k, d in (("t", 0), ("type", ""), ("item", -1), ("option", ""), ("correct", -1), ("chars", 0))}, session_id=sid)
                for e in body.get("events", [])]
    events = pd.DataFrame(ev_rows).sort_values(["session_id", "t"])
    frames = pd.DataFrame(body.get("frames", []), columns=["t", "faces", "face_visible", "gaze", "brightness", "blur"])
    frames["session_id"] = sid
    items = pd.DataFrame(dict(item=range(STATS.b.size), kind=STATS.kind))
    X, evid, _ = build(sess, events, frames, items, stats=STATS)
    x = X.loc[[sid]]
    raw = float(MODEL.raw(x)[0])
    prob = float(MODEL.iso.predict([raw])[0])
    band = "review_first" if raw >= H else ("review" if raw >= T else "clear")
    contrib = MODEL.contributions(x).iloc[0].to_dict()
    e = explain(sid, X.loc[sid].to_dict(), contrib, evid[sid], meta, round(100 * prob, 1), band,
                events=events[events.session_id == sid], stats=STATS)
    e["priority"] = PRIORITY(raw)
    e["scoring_ms"] = round(1000 * (time.time() - t_start), 1)
    return JSONResponse(_clean(e))


async def api_review(request: Request):
    sid = request.path_params["sid"]
    body = await request.json()
    if body.get("decision") not in ("confirm", "clear", "need_more"):
        return JSONResponse({"error": "decision must be confirm, clear or need_more"}, status_code=400)
    _append("reviews.jsonl", dict(session_id=sid, decision=body["decision"], note=body.get("note", "")[:2000],
                                  reviewer=body.get("reviewer", "reviewer")))
    return JSONResponse({"ok": True})


async def api_appeal(request: Request):
    sid = request.path_params["sid"]
    body = await request.json()
    _append("appeals.jsonl", dict(session_id=sid, text=body.get("text", "")[:4000],
                                  moments=body.get("moments", [])[:50]))
    return JSONResponse({"ok": True, "message": "Your explanation has been sent to the reviewer with your test record."})


async def api_probe(request: Request):
    kb = min(int(request.query_params.get("kb", 200)), 2000)
    return Response(secrets.token_bytes(kb * 1024), media_type="application/octet-stream",
                    headers={"Cache-Control": "no-store"})


async def api_probe_up(request: Request):
    body = await request.body()
    return JSONResponse({"bytes": len(body)})


async def api_precheck_result(request: Request):
    """Stores only the numeric results of the check, never images, and only with consent."""
    body = await request.json()
    if not body.get("consent"):
        return JSONResponse({"stored": False})
    keep = {k: body.get(k) for k in ("brightness", "backlight", "face_found", "face_size", "face_offset", "blur",
                                     "down_kbps", "up_kbps", "camera_ok", "device", "passed")}
    _append("precheck.jsonl", keep)
    return JSONResponse({"stored": True})


async def api_delete(request: Request):
    """Deletion on request or when the client's retention window ends (DPDP)."""
    sid = request.path_params["sid"]
    existed = STORE.pop(sid, None) is not None
    if existed:
        QUEUE.remove(sid)
    _append("deletions.jsonl", dict(session_id=sid, existed=existed))
    return JSONResponse({"deleted": existed})


routes = [
    Route("/", index),
    Route("/console", console),
    Route("/precheck", precheck),
    Route("/candidate/{sid}", candidate_page),
    Route("/api/queue", api_queue),
    Route("/api/session/{sid}", api_session),
    Route("/api/session/{sid}", api_delete, methods=["DELETE"]),
    Route("/api/session/{sid}/candidate", api_candidate),
    Route("/api/metrics", api_metrics),
    Route("/api/score", api_score, methods=["POST"]),
    Route("/api/review/{sid}", api_review, methods=["POST"]),
    Route("/api/appeal/{sid}", api_appeal, methods=["POST"]),
    Route("/api/precheck/probe", api_probe),
    Route("/api/precheck/probe", api_probe_up, methods=["POST"]),
    Route("/api/precheck/result", api_precheck_result, methods=["POST"]),
    Mount("/static", StaticFiles(directory=WEB), name="static"),
]
app = Starlette(routes=routes)

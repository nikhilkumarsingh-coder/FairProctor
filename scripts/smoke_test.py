"""Smoke test against a running service:  python scripts/smoke_test.py [http://localhost:8000]

Re-submits stored sessions to POST /api/score under a new id and checks the
live scorer agrees with the batch pipeline, then checks the other endpoints.
"""
import json
import pickle
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
GAZE = ["centre", "down", "left", "right", "away", "unknown"]


def call(path, body=None, method=None):
    req = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


store = pickle.load(open("artifacts/store.pkl", "rb"))
q = call("/api/queue?limit=5")
assert q["rows"], "queue is empty"
print(f"queue: {q['total']} of {q['n_sessions']} need review; top = {q['rows'][0]['session_id']} ({q['rows'][0]['score']})")

checked = 0
for sid in [q["rows"][0]["session_id"], q["rows"][3]["session_id"], next(s for s, d in store.items() if d["explanation"]["band"] == "clear")]:
    d = store[sid]
    fr = d["frames"]
    frames = [] if fr is None else [dict(t=float(t), faces=int(f), face_visible=int(v), gaze=GAZE[g], brightness=120, blur=0.3)
                                    for t, f, v, g in zip(fr["t"], fr["faces"], fr["vis"], fr["gaze"])]
    events = [dict(zip(["t", "type", "item", "option", "correct", "chars"], e)) for e in d["events"]]
    meta = dict(d["meta"], session_id="NEW_" + sid, replay_of=sid)
    r = call("/api/score", dict(session=meta, events=events, frames=frames))
    print(f"{sid}: batch band={d['explanation']['band']:<12} live band={r['band']:<12} live score={r['score']:5.1f} "
          f"moments={len(r['moments'])} in {r['scoring_ms']} ms")
    print("   ", r["headline"][:150])
    checked += 1

s = call(f"/api/session/{q['rows'][0]['session_id']}")
assert s["explanation"]["moments"], "top session has no linked moments"
c = call(f"/api/session/{q['rows'][0]['session_id']}/candidate")
assert "partners" not in json.dumps(c), "candidate view must not expose other candidates"
assert not any(p in json.dumps(c) for p in s["explanation"]["partners"]), "candidate view leaked a partner id"
call(f"/api/review/{q['rows'][0]['session_id']}", dict(decision="need_more", note="smoke test"))
call(f"/api/appeal/{q['rows'][0]['session_id']}", dict(text="smoke test", moments=["06:05"]))
assert call("/api/precheck/result", dict(consent=False))["stored"] is False
print(f"OK: {checked} live scores, session, candidate view (no partner ids), review, appeal, consent checks passed")

"""Export real backend responses as frontend mock data (for VITE_USE_MOCKS=true).

    python -m backend.scripts.export_mocks out/mock-data.json

Runs a fresh demo in a temporary database: seed, 3 team members take the test
(TEAM01 honest, TEAM02 + TEAM03 share answers), close & score, then records the
API responses every screen needs.
"""
import json
import math
import os
import random
import sys
import tempfile

os.environ["FP_DB"] = os.path.join(tempfile.mkdtemp(prefix="fp-mock-"), "mock.db")
os.environ["FP_RETENTION"] = "0"

from backend import config, db  # noqa: E402
from backend.app import app  # noqa: E402
from backend.jobs import worker  # noqa: E402
from backend.scripts.seed_demo import ADMIN, REVIEWER, seed  # noqa: E402
from backend.services.scoring import model_bundle  # noqa: E402
from backend.tests.client import Client  # noqa: E402

FIXED_CODES = {"TEAM01": "DEMO01", "TEAM02": "DEMO02", "TEAM03": "DEMO03"}


def login(c, **kw):
    r = c.post("/api/auth/login", json=kw)
    assert r.status_code == 200, r.text
    return r.json()["user"]


def thin_frames(frames, every=10.0):
    out, nxt = [], -1
    for f in frames:
        if f["t"] >= nxt:
            out.append(f)
            nxt = f["t"] + every
    return out


def main(out_path):
    info = seed(reset=True, n_live=3)
    st = model_bundle()["stats"]
    rng = random.Random(11)
    with db.tx() as con:
        key = {r["position"]: (r["kind"], r["correct_option"]) for r in
               db.all_(con, "SELECT position, kind, correct_option FROM items WHERE test_id = ?", info["test_id"])}
    n = len(key)
    codes = {t["roll_no"]: t["code"] for t in info["team"]}
    M = {"_note": "Real FairProctor backend responses, exported by backend/scripts/export_mocks.py. "
                  "Same shapes as docs/API.md.",
         "logins": {"admin": {"email": ADMIN[0], "password": ADMIN[1]},
                    "reviewer": {"email": REVIEWER[0], "password": REVIEWER[1]},
                    "candidates": [{"roll_no": r, "code": FIXED_CODES[r], "name": f"Team member {i}"}
                                   for i, r in enumerate(sorted(codes), start=1)]},
         "consent_version": config.CONSENT_VERSION}
    cl = {}
    for r in sorted(codes):
        c = Client(app)
        M.setdefault("me", {})[r] = login(c, roll_no=r, code=codes[r])
        cl[r] = c
    M["exam_me_before_start"] = cl["TEAM01"].get("/api/exam/me").json()
    for c in cl.values():
        c.post("/api/exam/consent", json=dict(version=config.CONSENT_VERSION, understood=True))
    M["exam_start"] = cl["TEAM01"].post("/api/exam/start", json=dict(device="phone")).json()
    honest = [key[i][1] if rng.random() < 0.65 else (rng.choice("ABCD") if key[i][0] == "mcq" else "0") for i in range(n)]
    shared = [key[i][1] if (key[i][0] == "short" or i % 3) else next(L for L in "DCBA" if L != key[i][1]) for i in range(n)]
    ev, fr, t, seq = [], [], 2.0, 1
    for i in range(n):
        ev.append(dict(seq=seq, t=round(t, 1), type="item_shown", item=i)); seq += 1
        t += math.exp(st.med_logt[i] + rng.gauss(0, 0.3))
        ev.append(dict(seq=seq, t=round(t, 1), type="answer", item=i, option=honest[i])); seq += 1
        t += 2
    for k in range(0, int(t), 5):
        fr.append(dict(seq=seq, t=k, faces=2 if 300 <= k < 310 else 1, face_visible=True,
                       gaze="down" if k % 60 < 15 else "centre", brightness=60, blur=0.3)); seq += 1
    M["exam_events_example_request"] = dict(events=ev[:6], frames=fr[:2])
    M["exam_events_example_response"] = cl["TEAM01"].post("/api/exam/events", json=dict(events=ev, frames=fr)).json()
    for j, r in enumerate(["TEAM02", "TEAM03"]):
        c = cl[r]
        c.post("/api/exam/start", json=dict(device="desktop"))
        ev, fr, t, seq = [], [], 2.0, 1
        for i in range(n):
            ev.append(dict(seq=seq, t=round(t, 1), type="item_shown", item=i)); seq += 1
            t += max(4.0, 0.35 * math.exp(st.med_logt[i])) + 3 * j
            ev.append(dict(seq=seq, t=round(t, 1), type="answer", item=i, option=shared[i])); seq += 1
            t += 1
        for k in range(0, int(t), 5):
            fr.append(dict(seq=seq, t=k, faces=1, face_visible=True, gaze="centre", brightness=120, blur=0.1)); seq += 1
        c.post("/api/exam/events", json=dict(events=ev, frames=fr))
    M["exam_me_in_progress"] = cl["TEAM01"].get("/api/exam/me").json()
    for c in cl.values():
        c.post("/api/exam/submit")
    M["exam_me_submitted"] = cl["TEAM01"].get("/api/exam/me").json()
    M["result_pending"] = cl["TEAM01"].get("/api/exam/result").json()

    a = Client(app)
    M["me"]["admin"] = login(a, email=ADMIN[0], password=ADMIN[1])
    sid = info["sitting_id"]
    M["admin_sitting_before_close"] = a.get(f"/api/admin/sittings/{sid}").json()
    close = a.post(f"/api/admin/sittings/{sid}/close").json()
    M["admin_close_response"] = close
    job = worker.wait_for(close["job_id"], timeout=600)
    assert job["status"] == "done", job
    M["admin_job_done"] = job
    M["admin_job_running_example"] = dict(job, status="running", progress=0.6, message="scoring", finished_at=None)
    M["admin_tests"] = a.get("/api/admin/tests").json()
    M["admin_test_detail"] = a.get(f"/api/admin/tests/{info['test_id']}").json()
    M["admin_sittings"] = a.get("/api/admin/sittings").json()
    M["admin_sitting_after_score"] = a.get(f"/api/admin/sittings/{sid}").json()

    for r in sorted(codes):
        M.setdefault("result_after_score", {})[r] = cl[r].get("/api/exam/result").json()
    rv = Client(app)
    M["me"]["reviewer"] = login(rv, email=REVIEWER[0], password=REVIEWER[1])
    q = rv.get(f"/api/review/queue?sitting_id={sid}&band=all&limit=500").json()
    M["review_queue_all"] = q
    with db.tx() as con:
        live = {s["id"]: db.one(con, "SELECT roll_no FROM users WHERE id = ?", s["user_id"])["roll_no"]
                for s in db.all_(con, "SELECT id, user_id FROM sessions WHERE is_synthetic = 0")}
    M["live_session_ids"] = {roll: s for s, roll in live.items()}
    pick = [x["session_id"] for x in q["rows"] if x["band"] != "clear"][:6]
    pick += [x["session_id"] for x in q["rows"] if x["band"] == "clear"][:2] + list(live)
    details = {}
    for s in dict.fromkeys(pick):
        d = rv.get(f"/api/review/sessions/{s}").json()
        d["frames"] = thin_frames(d["frames"], every=20.0)
        d["also_viewing"] = []
        details[s] = d
    M["review_session_details"] = details
    # a confirmed session (identity shown) and an appeal
    t2 = M["live_session_ids"]["TEAM02"]
    rv.post(f"/api/review/sessions/{t2}/decision",
            json=dict(decision="confirm", note="Same rare wrong options as Candidate partner, answered seconds apart on 10 items."))
    M["review_session_after_confirm_example"] = {k: v for k, v in rv.get(f"/api/review/sessions/{t2}").json().items()
                                                 if k in ("session_id", "identity", "reviews")}
    M["result_confirmed_example"] = cl["TEAM02"].get("/api/exam/result").json()
    cl["TEAM02"].post("/api/exam/appeal", json=dict(text="Hum dono ek hi coaching mein padhte hain, isliye galti bhi same hui.",
                                                    moments=[]))
    M["review_appeals_open"] = rv.get("/api/review/appeals").json()
    M["result_with_open_appeal_example"] = cl["TEAM02"].get("/api/exam/result").json()
    ap = M["review_appeals_open"][0]["id"]
    rv.post(f"/api/review/appeals/{ap}/decide", json=dict(outcome="upheld", response="The matching answers are too rare to be a coincidence."))
    M["result_appeal_decided_example"] = cl["TEAM02"].get("/api/exam/result").json()
    M["error_examples"] = {
        "wrong_login": Client(app).post("/api/auth/login", json=dict(roll_no="TEAM01", code="XXXXXX")).json(),
        "not_logged_in": Client(app).get("/api/exam/me").json(),
        "not_allowed": cl["TEAM01"].get("/api/review/queue").json(),
        "bad_rows": a.post(f"/api/admin/tests/{info['test_id']}/items", data="text,option_a,option_b,correct\nQ,1,2,Z\n",
                           headers={"content-type": "text/csv"}).json(),
    }
    # swap the random login codes for fixed demo codes everywhere they appear
    text = json.dumps(M, ensure_ascii=False, separators=(",", ":"))
    for r, c in codes.items():
        text = text.replace(c, FIXED_CODES[r])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"wrote {out_path} ({len(text) / 1e3:.0f} KB): {len(q['rows'])} queue rows, {len(details)} session details")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "frontend/src/api/mocks/mock-data.json")

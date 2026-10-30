"""Two candidates (TEAM02, TEAM03) sharing one answer sheet, sent through the real HTTP API.

    python colluders.py                        # all 30 answers, then submit
    python colluders.py --items 15 --no-submit # halfway through, still writing (for the live monitor)
"""
import json, random, re, sys, urllib.request

import os
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000")

def call(path, body=None, token=None, method=None):
    h = {"Content-Type": "application/json"}
    if token: h["Authorization"] = "Bearer " + token
    r = urllib.request.Request(BASE + path, data=None if body is None else json.dumps(body).encode(), headers=h,
                               method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(r) as res:
        return json.loads(res.read() or b"null")

import argparse
ap = argparse.ArgumentParser()
ap.add_argument("logins", nargs="?")
ap.add_argument("--items", type=int, default=0, help="answer only the first N questions")
ap.add_argument("--no-submit", action="store_true", help="leave them writing")
args = ap.parse_args()
LOGINS = args.logins if args.logins else os.path.join(os.path.dirname(__file__), "..", "backend", "data", "demo_logins.txt")
codes = dict(re.findall(r"(TEAM0\d)\s+(\w{6})", open(LOGINS).read()))
admin = call("/api/auth/login", {"email": "admin@fairproctor.demo", "password": "Admin@2026"})["access_token"]
items = call("/api/admin/tests/1", token=admin)["items"]
key = {it["position"]: (it["kind"], it["correct_option"]) for it in items}
n = min(len(key), args.items) if args.items else len(key)
shared = [key[i][1] if (key[i][0] == "short" or i % 3) else next(L for L in "DCBA" if L != key[i][1]) for i in range(n)]
rng = random.Random(5)
for j, roll in enumerate(["TEAM02", "TEAM03"]):
    tok = call("/api/auth/login", {"roll_no": roll, "code": codes[roll]})["access_token"]
    call("/api/exam/consent", {"version": call("/api/exam/me", token=tok)["consent"]["version_needed"], "understood": True}, tok)
    call("/api/exam/start", {"device": "desktop"}, tok)
    ev, fr, t, seq = [], [], 2.0, 1
    for i in range(n):
        ev.append(dict(seq=seq, t=round(t, 1), type="item_shown", item=i)); seq += 1
        t += 7 + rng.random() * 3 + 3 * j
        ev.append(dict(seq=seq, t=round(t, 1), type="answer", item=i, option=shared[i])); seq += 1
        t += 1 if not j else -2
    for k in range(0, int(t), 5):
        fr.append(dict(seq=seq, t=k, faces=1, face_visible=True, gaze="centre", brightness=120, blur=0.1)); seq += 1
    sent = call("/api/exam/events", {"events": ev, "frames": fr}, tok)
    print(roll, sent, "still writing" if args.no_submit else call("/api/exam/submit", {}, tok)["status"])

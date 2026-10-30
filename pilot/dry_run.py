"""Rehearse a pilot with simulated participants, through the real HTTP API, then score it and write the report.

    python -m pilot.prepare --rehearsal --people 14 --coding-people 6
    python -m pilot.dry_run --dir pilot/out/rehearsal-<date>          # backend running on http://127.0.0.1:8000

Every participant logs in with their card's roll no. and code, gives consent, starts, sends answers, focus changes,
pastes and camera numbers (or, for code: typing, pastes, runs and submits that the server really judges), and
submits, acting out their sealed role. Then the admin closes and scores each pilot sitting, and pilot.report writes
PILOT_DRYRUN.md into the pilot folder. The behaviour comes from the same simulator as the training data, so this only
proves the kit works end to end; it is not evidence about real people. Refuses to touch a pilot that is not a rehearsal.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import config, db  # noqa: E402

from .prepare import read_csv  # noqa: E402
from .roles import CODING  # noqa: E402

ENV = dict(bandwidth="normal", device="desktop", room="alone", light="ok", framing="ok", benign_focus=0, benign_paste=False)
ROLE_ENV = {"honest_dim": dict(light="dim"), "honest_shared": dict(room="shared_home"), "honest_phone_low": dict(device="phone"),
            "honest_slow": dict(bandwidth="low", device="phone"), "honest_interrupted": dict(benign_focus=2),
            "cheat_helper": dict(room="shared_home")}


class Http:
    """The backend over HTTP (urllib, no extra packages)."""

    def __init__(self, base: str):
        self.base = base.rstrip("/")

    def call(self, method: str, path: str, body=None, token: str | None = None):
        h = {"Content-Type": "application/json"}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                     headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")


class InProcess:
    """The same calls against the ASGI app in this process (used by the tests)."""

    def __init__(self, app):
        from backend.tests.client import Client
        self.client = Client(app)

    def call(self, method: str, path: str, body=None, token: str | None = None):
        r = self.client.request(method, path, json_body=body, headers={"authorization": f"Bearer {token}"} if token else None)
        return r.status_code, r.json()


def stable(*parts) -> int:
    """A seed that is the same on every run (Python's own hash() of strings changes per process)."""
    return int(hashlib.sha1("-".join(map(str, parts)).encode()).hexdigest(), 16) % 2 ** 32


def ok(res, what: str):
    status, body = res
    if status >= 400:
        raise SystemExit(f"{what} failed ({status}): {body}")
    return body


def _login(api, roll: str, code: str) -> str:
    tok = ok(api.call("POST", "/api/auth/login", {"roll_no": roll, "code": code}), f"login {roll}")["access_token"]
    ok(api.call("POST", "/api/exam/consent", {"version": config.CONSENT_VERSION, "understood": True, "camera_ok": True,
                                              "precheck_share_ok": False}, tok), f"consent {roll}")
    return tok


def _send(api, tok: str, events: list[dict], frames: list[dict], roll: str) -> None:
    """Events and camera numbers share one sequence counter, in time order, as the browser sends them."""
    allrec = sorted([("e", e) for e in events] + [("f", f) for f in frames], key=lambda x: x[1]["t"])
    for i, (_, r) in enumerate(allrec, start=1):
        r["seq"] = i
    for k in range(0, len(allrec), 1500):
        chunk = allrec[k:k + 1500]
        res = ok(api.call("POST", "/api/exam/events", {"events": [r for kind, r in chunk if kind == "e"],
                                                      "frames": [r for kind, r in chunk if kind == "f"]}, tok), f"events {roll}")
        if res["rejected"]:
            print(f"  {roll}: {res['rejected']} records rejected")


# ------------------------------------------------------------------ question test
def mcq(api, people: list[dict], codes: dict[str, str], seed: int, test_id: int) -> None:
    from backend.scripts.make_story import _generator
    gen = _generator()
    items = gen.make_items(np.random.default_rng(7))
    with db.tx() as con:
        key = {r["position"]: r["correct_option"] for r in db.all_(con, "SELECT position, correct_option FROM items WHERE test_id = ?",
                                                                     test_id)}
    hardest = [int(q) for q in np.argsort(-items["b"]) if items["kind"][q] == "mcq"]
    sims = {}
    order = sorted(people, key=lambda p: (p["role"] == "cheat_pair" and p["partner"] < p["roll_no"], p["roll_no"]))
    for p in order:                                                  # pair leaders are simulated before followers
        rng = np.random.default_rng(stable(seed, p["roll_no"]))
        env = dict(ENV, **ROLE_ENV.get(p["role"], {}))
        mal, cfg, leader = "none", {}, None
        if p["role"] == "cheat_phone":
            mal, cfg = "second_phone", dict(items=set(rng.choice(hardest[:14], 9, replace=False).tolist()), acc=0.92)
        elif p["role"] == "cheat_search":
            mal, cfg = "tab_search", gen.mal_config(rng, items, "tab_search")
        elif p["role"] == "cheat_helper":
            mal, cfg = "helper", gen.mal_config(rng, items, "helper")
        elif p["role"] == "cheat_pair":
            mal = "collusion"
            shared = set(np.random.default_rng(stable(seed, *sorted([p["roll_no"], p["partner"]])))
                         .choice(30, 16, replace=False).tolist())
            cfg = dict(shared_items=shared)
            leader = sims.get(p["partner"])
        s = gen.Session(p["roll_no"], 0, rng, items, env, mal, cfg)
        s.simulate(leader)
        sims[p["roll_no"]] = s
        fr = s.frames()
        keep, last = [], -1e9                                         # the browser sends camera numbers about every 5 s
        for t in fr.t:
            keep.append(t - last >= 5)
            if keep[-1]:
                last = t
        fr = fr[keep]
        events = []
        for (_, t, typ, item, option, correct, chars) in sorted(s.events, key=lambda e: e[1]):
            e = dict(t=float(t), type=typ, item=int(item))
            if typ == "answer":
                e["option"] = (key[item] if correct else "0") if option == "TEXT" else option
            if typ == "paste":
                e["chars"] = int(chars)
            events.append(e)
        frames = [dict(t=float(r.t), faces=int(r.faces), face_visible=bool(r.face_visible), gaze=r.gaze,
                       brightness=float(r.brightness), blur=float(r.blur)) for r in fr.itertuples()]
        tok = _login(api, p["roll_no"], codes[p["roll_no"]])
        ok(api.call("POST", "/api/exam/start", {"device": env["device"], "bandwidth_class": env["bandwidth"],
                                                "precheck_light": env["light"], "precheck_framing": "ok"}, tok), "start")
        _send(api, tok, events, frames, p["roll_no"])
        ok(api.call("POST", "/api/exam/submit", {}, tok), f"submit {p['roll_no']}")
        print(f"  {p['roll_no']} done ({len(events)} events, {len(frames)} camera numbers)")


# ------------------------------------------------------------------ coding test
def coding(api, people: list[dict], codes: dict[str, str], seed: int, test_id: int) -> None:
    from fairproctor import coding_synth as cs
    done: dict[str, dict] = {}
    order = sorted(people, key=lambda p: (p["role"] == "code_pair" and p["partner"] < p["roll_no"], p["roll_no"]))
    for p in order:
        r = random.Random(f"{seed}-{p['roll_no']}")
        tl = cs.Timeline(p["roll_no"])
        lang, skill = "python", r.betavariate(2.2, 2)          # Python always runs; other compilers may be missing
        kind = {"code_web": "web_paste", "code_retype": "transcribe", "code_pair": "copy_pair"}.get(p["role"])
        follower = kind == "copy_pair" and p["partner"] in done
        affected = set(r.sample(range(3), 1 if kind == "copy_pair" else r.choice([1, 2]))) if kind else set()
        if kind == "copy_pair" and not follower:
            affected = set()                                     # the partner who shares writes honestly
        t, finals, times = r.uniform(5, 40), {}, {}
        for item in range(3):
            if item in affected and kind == "copy_pair":
                src = done[p["partner"]]
                t, code = cs.cheat_problem(tl, item, lang, t, kind, r, src["finals"][item], src["times"][item])
            elif item in affected:
                t, code = cs.cheat_problem(tl, item, lang, t, kind, r)
            else:
                t, code, _ = cs.honest_problem(tl, item, lang, t, skill, r)
            finals[item], times[item] = code, t
            t += r.uniform(10, 60)
        done[p["roll_no"]] = dict(finals=finals, times=times)
        tok = _login(api, p["roll_no"], codes[p["roll_no"]])
        ok(api.call("POST", "/api/exam/start", {"device": "desktop"}, tok), "start")
        events = [dict(t=e["t"], type=e["type"], item=e["item"], chars=e["chars"], **({"meta": e["meta"]} if e["meta"] else {}))
                  for e in tl.ev]
        _send(api, tok, events, [], p["roll_no"])
        verdicts = []
        for run in sorted(tl.runs, key=lambda x: x["t"]):
            path = "/api/exam/code/submit" if run["kind"] == "submit" else "/api/exam/code/run"
            res = ok(api.call("POST", path, {"item": run["item"], "language": lang, "code": run["code"], "t": run["t"]}, tok),
                     f"{run['kind']} {p['roll_no']}")
            if run["kind"] == "submit":
                verdicts.append(res["verdict"])
        ok(api.call("POST", "/api/exam/submit", {}, tok), f"submit {p['roll_no']}")
        print(f"  {p['roll_no']} done ({len(events)} events, submits: {', '.join(verdicts) or 'none'})")


def close_and_score(api, sitting_id: int, email: str, password: str) -> None:
    tok = ok(api.call("POST", "/api/auth/login", {"email": email, "password": password}), "admin login")["access_token"]
    job = ok(api.call("POST", f"/api/admin/sittings/{sitting_id}/close", {}, tok), "close")["job_id"]
    end = time.time() + 900
    while time.time() < end:
        j = ok(api.call("GET", f"/api/admin/jobs/{job}", None, tok), "job")
        if j["status"] in ("done", "failed"):
            if j["status"] == "failed":
                raise SystemExit(f"scoring failed: {j['message']}")
            return
        time.sleep(1)
    raise SystemExit("scoring took too long")


def run(folder: str, api, email: str = "admin@fairproctor.demo", password: str = "Admin@2026") -> str:
    with open(os.path.join(folder, "pilot.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    if not meta.get("dry_run"):
        raise SystemExit("This pilot is not a rehearsal; simulated participants would mix with real ones. "
                         "Make one with: python -m pilot.prepare --rehearsal --people 14")
    people = read_csv(os.path.join(folder, "key-SEALED.csv"))
    codes = {r["roll_no"]: r["code"] for r in read_csv(os.path.join(folder, "logins.csv"))}
    for test, t in meta["tests"].items():
        group = [p for p in people if p["test"] == test]
        print(f"{'Coding' if test == CODING else 'Question'} test: {len(group)} simulated participants")
        (coding if test == CODING else mcq)(api, group, codes, meta["seed"], t["test_id"])
        print("  closing and scoring ...")
        close_and_score(api, t["sitting_id"], email, password)
    from .report import write
    return write(folder, dry_run=True)


def main():
    ap = argparse.ArgumentParser(description="Rehearse a pilot with simulated participants.")
    ap.add_argument("--dir", required=True, help="a rehearsal pilot folder (pilot.prepare --rehearsal)")
    ap.add_argument("--base", default="http://127.0.0.1:8000", help="the running backend")
    ap.add_argument("--admin-email", default="admin@fairproctor.demo")
    ap.add_argument("--admin-password", default="Admin@2026")
    a = ap.parse_args()
    out = run(a.dir, Http(a.base), a.admin_email, a.admin_password)
    print(f"\nWritten: {out}\n")
    with open(out, encoding="utf-8") as fh:
        print(fh.read().split("## What this does")[0])


if __name__ == "__main__":
    main()

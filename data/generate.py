"""Synthetic IMAP-like session generator.

Produces 5,000 sessions with reviewer verdicts, browser/answer events and
per-frame video analysis results, following docs/SCHEMA.md.

The point of the synthetic data is to reproduce the *shape* of the real problem:
  * honest candidates in shared homes, cyber cafes, dim rooms and on phones held
    at an angle produce many legacy flags;
  * low-bandwidth sessions get one analysed frame every 3-8 seconds, with drops;
  * real malpractice mostly does NOT look like "two faces": a second phone below
    the frame, collusion rings, tab searching/pasting, and a helper in the room.

Run:  python data/generate.py --out data/sample --n 5000 --seed 7
"""
from __future__ import annotations

import argparse
import hashlib
import os
import zlib

import numpy as np
import pandas as pd

N_ITEMS = 30
N_MCQ = 25  # items 0..24 are MCQ, 25..29 short answer
TIME_LIMIT = 2400.0
OPTS = np.array(list("ABCD"))


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def make_items(rng):
    kind = np.array(["mcq"] * N_MCQ + ["short"] * (N_ITEMS - N_MCQ))
    b = rng.normal(0, 1, N_ITEMS)
    base_t = np.where(kind == "mcq", rng.uniform(25, 70, N_ITEMS), rng.uniform(80, 160, N_ITEMS))
    correct_opt = rng.integers(0, 4, N_ITEMS)
    # popularity of each wrong option (honest people share popular distractors)
    distractor_p = rng.dirichlet([1.2, 1.2, 1.2], N_ITEMS)
    return dict(kind=kind, b=b, base_t=base_t, correct_opt=correct_opt, distractor_p=distractor_p)


def pick_wrong(rng, items, q):
    wrong = [o for o in range(4) if o != items["correct_opt"][q]]
    return wrong[rng.choice(3, p=items["distractor_p"][q])]


class Session:
    def __init__(self, sid, window, rng, items, env, mal_type, mal_cfg):
        self.sid, self.window, self.rng, self.items = sid, window, rng, items
        self.env, self.mal_type, self.mal = env, mal_type, mal_cfg
        self.theta = rng.normal(0, 1)
        self.speed = rng.normal(0, 0.3)
        self.events = []
        self.overlays = []  # (t0, t1, kind)
        self.answer_t = {}
        self.answer_opt = {}

    def ev(self, t, typ, item=-1, option="", correct=-1, chars=0):
        self.events.append((self.sid, round(float(t), 2), typ, int(item), option, int(correct), int(chars)))

    # ---------------- answering ----------------
    def simulate(self, leader: "Session | None" = None):
        rng, it = self.rng, self.items
        t = rng.uniform(2, 6)
        shared = self.mal.get("shared_items", set())
        for q in range(N_ITEMS):
            if t > TIME_LIMIT - 5:
                break
            self.ev(t, "item_shown", q)
            mcq = it["kind"][q] == "mcq"
            gap = it["b"][q] - self.theta
            p_honest = sigmoid(1.2 * -gap)
            if mcq:
                p_honest = 0.25 + 0.75 * p_honest
            d = it["base_t"][q] * np.exp(-self.speed + rng.normal(0, 0.35)) * (1 + 0.25 * np.clip(gap, -1, 2))
            p = p_honest
            mode = "honest"

            remaining = TIME_LIMIT - t
            items_left = N_ITEMS - q
            if remaining < items_left * 20:  # time pressure: rush and guess
                d = rng.uniform(4, 10)
                p = 0.25 if mcq else 0.05
            elif gap > 1.5 and rng.random() < 0.12:  # honest give-up guess on a very hard item
                d = rng.uniform(5, 12)
                p = 0.25 if mcq else 0.02

            mt = self.mal_type
            if mt == "second_phone" and q in self.mal["items"]:
                mode = "phone"
                d = it["base_t"][q] * rng.uniform(1.2, 2.4)
                p = self.mal["acc"]
            elif mt == "tab_search" and q in self.mal["items"]:
                mode = "tab"
                p = self.mal["acc"]
            elif mt == "helper" and q in self.mal["items"]:
                mode = "helper"
                d = it["base_t"][q] * rng.uniform(0.5, 1.0)
                p = self.mal["acc"]
            elif mt == "collusion" and q in shared and leader is not None and q in leader.answer_t:
                mode = "copy"

            # ---- side events inside the item ----
            if mode == "phone":
                i0 = t + rng.uniform(3, 8)
                i1 = t + d - rng.uniform(2, 5)
                if i1 > i0 + 20:
                    self.ev(i0, "idle_start", q)
                    self.ev(i1, "idle_end", q)
                self.overlays.append((i0, i1, "look_down"))
            elif mode == "tab":
                f0 = t + rng.uniform(3, 8)
                away = rng.uniform(10, 60)
                self.ev(f0, "focus_lost", q)
                self.ev(f0 + away, "focus_gained", q)
                if not mcq and rng.random() < 0.85:
                    self.ev(f0 + away + rng.uniform(1, 4), "paste", q, chars=rng.integers(80, 400))
                d = (f0 + away - t) + rng.uniform(3, 12)
            elif mode == "helper":
                self.overlays.append((t, t + d, "helper"))
            elif mode == "honest":
                if d > 45 and gap > 0.3 and rng.random() < 0.3:  # honest thinking pause
                    i0 = t + rng.uniform(5, 15)
                    i1 = min(t + d - 3, i0 + rng.uniform(20, 60))
                    if i1 > i0 + 20:
                        self.ev(i0, "idle_start", q)
                        self.ev(i1, "idle_end", q)
                        self.overlays.append((i0, i1, "think"))
                if not mcq and self.env["benign_paste"] and rng.random() < 0.5:
                    self.ev(t + d * rng.uniform(0.3, 0.9), "paste", q, chars=rng.integers(5, 40))

            if mode == "copy":
                lt = leader.answer_t[q]
                ans_t = max(t + rng.uniform(4, 10), lt + rng.uniform(-8, 25))
                opt = leader.answer_opt[q]
                correct = int(opt == OPTS[it["correct_opt"][q]]) if mcq else leader._sa_correct[q]
                d = ans_t - t
            else:
                d = max(d, 2.0)
                ans_t = t + d
                c = rng.random() < p
                if mcq:
                    oi = it["correct_opt"][q] if c else pick_wrong(rng, it, q)
                    opt = OPTS[oi]
                else:
                    opt = "TEXT"
                correct = int(c)
            if not mcq:
                if not hasattr(self, "_sa_correct"):
                    self._sa_correct = {}
                self._sa_correct[q] = correct
                opt_store = "TEXT"
            else:
                opt_store = opt
            if ans_t > TIME_LIMIT:
                break
            self.ev(ans_t, "answer", q, opt_store, correct)
            self.answer_t[q] = ans_t
            self.answer_opt[q] = opt_store if mcq else "TEXT"
            t = ans_t + rng.uniform(1, 3)

        # benign focus losses (notifications, calls, battery popups)
        for _ in range(self.env["benign_focus"]):
            f0 = rng.uniform(30, max(60, t - 30))
            self.ev(f0, "focus_lost")
            self.ev(f0 + rng.uniform(2, 35), "focus_gained")
        self.end_t = t

    # ---------------- video frames ----------------
    def frames(self):
        rng, env = self.rng, self.env
        end = self.end_t
        if env["bandwidth"] == "low":
            interval = rng.uniform(3, 8)
        else:
            interval = rng.uniform(1, 2)
        ts = np.arange(rng.uniform(0, interval), end, interval)
        ts = ts + rng.normal(0, interval * 0.15, len(ts))
        ts = np.sort(ts[(ts > 0) & (ts < end)])
        # connection drops
        if env["bandwidth"] == "low":
            n_drops = rng.poisson(4)
        else:
            n_drops = rng.poisson(0.5)
        keep = np.ones(len(ts), bool)
        for _ in range(n_drops):
            d0 = rng.uniform(0, end)
            keep &= ~((ts > d0) & (ts < d0 + rng.uniform(15, 90)))
        ts = ts[keep]
        n = len(ts)

        light = env["light"]
        p_vis = {"ok": 0.97, "dim": 0.82, "backlit": 0.72}[light]
        if env["device"] == "phone":
            p_vis -= 0.05
        if env["bandwidth"] == "low":
            p_vis -= 0.08
        blur = np.clip(rng.normal(0.55 if env["bandwidth"] == "low" else 0.2, 0.12, n), 0, 1)
        vis = rng.random(n) < (p_vis - 0.25 * (blur > 0.75))
        bright_base = {"ok": 140, "dim": 60, "backlit": 75}[light]
        brightness = np.clip(rng.normal(bright_base, 15, n), 0, 255)

        # gaze baseline: phones held low read as "down" a lot for honest people
        if env["device"] == "phone":
            g_p = [0.62, 0.26, 0.04, 0.04, 0.04]
        else:
            g_p = [0.85, 0.07, 0.03, 0.03, 0.02]
        gaze = rng.choice(np.array(["centre", "down", "left", "right", "away"]), n, p=g_p)
        faces = vis.astype(int)

        # transient people in shared spaces
        room = env["room"]
        rate = {"alone": 1 / 1800, "shared_home": 1 / 360, "cafe": 1 / 150}[room]
        for _ in range(rng.poisson(rate * end)):
            a = rng.uniform(0, end)
            m = (ts > a) & (ts < a + rng.uniform(2, 12))
            faces[m] += 1
        if room == "cafe":  # background faces occasionally detected
            faces += (rng.random(n) < 0.04).astype(int)

        for (a, b, kind) in self.overlays:
            m = (ts >= a) & (ts <= b)
            k = m.sum()
            if not k:
                continue
            if kind == "look_down":
                gaze[m] = np.where(rng.random(k) < 0.75, "down", gaze[m])
            elif kind == "think":
                gaze[m] = np.where(rng.random(k) < 0.3, "away", gaze[m])
            elif kind == "helper":
                faces[m] = np.maximum(faces[m], 1) + (rng.random(k) < 0.75)
                gaze[m] = np.where(rng.random(k) < 0.4, rng.choice(["left", "right"], k), gaze[m])
        gaze = np.where(vis, gaze, "unknown")
        return pd.DataFrame(dict(session_id=self.sid, t=ts.round(2), faces=faces, face_visible=vis.astype(int),
                                 gaze=gaze, brightness=brightness.round(0).astype(int), blur=blur.round(2),
                                 phone=self.phone_track(ts)))

    def phone_track(self, ts):
        """On-device phone-in-view detector: share of the seconds since the previous frame with a phone seen.
        NaN when the detector does not run (slow link: the model is never downloaded; some browsers can't run it).
        Uses its own random stream so every other column stays exactly as before.
        Rates from reports/PHONE_DETECTOR_CHECK.md: a phone held in view is seen in ~35% of seconds, false alarms ~0.3%."""
        r = np.random.default_rng(zlib.crc32(self.sid.encode()))
        n = len(ts)
        if self.env["bandwidth"] == "low" or r.random() < 0.15:
            return np.full(n, np.nan)
        secs = np.maximum(1, np.round(np.diff(np.concatenate([[0.0], ts]))).astype(int))
        p = np.full(n, 0.003)                                        # false alarms (hand near the face, a remote)
        if self.mal_type == "none" and r.random() < 0.08:            # honest: checks the time / silences a call once
            a = r.uniform(0, self.end_t)
            p[(ts > a) & (ts < a + r.uniform(5, 20))] = 0.35
        if self.mal_type == "second_phone" and r.random() < 0.3:    # careless: lifts the phone into view while reading it
            for (a, b, kind) in self.overlays:
                if kind == "look_down":
                    m = (ts >= a) & (ts <= b)
                    p[m] = np.where(r.random(m.sum()) < 0.5, 0.35, p[m])
        return (r.binomial(secs, p) / secs).round(2)


def sample_env(rng):
    bandwidth = "low" if rng.random() < 0.35 else "normal"
    device = "phone" if rng.random() < (0.7 if bandwidth == "low" else 0.3) else "desktop"
    room = rng.choice(["alone", "shared_home", "cafe"], p=[0.5, 0.35, 0.15])
    light = rng.choice(["ok", "dim", "backlit"], p=[0.55, 0.3, 0.15])
    framing = rng.choice(["ok", "off_centre", "too_close"], p=[0.7, 0.2, 0.1])
    benign_focus = int(rng.choice([0, 0, 0, 1, 2, 3], p=[0.35, 0.2, 0.15, 0.15, 0.1, 0.05]))
    if device == "phone":
        benign_focus += int(rng.random() < 0.25)
    return dict(bandwidth=bandwidth, device=device, room=room, light=light, framing=framing,
                benign_focus=benign_focus, benign_paste=rng.random() < 0.05)


def mal_config(rng, items, mt):
    hard = np.argsort(-items["b"])
    if mt == "second_phone":
        k = rng.integers(6, 16)
        pool = list(hard[:20])
        chosen = set(rng.choice(pool, k, replace=False).tolist())
        return dict(items=chosen, acc=rng.uniform(0.8, 0.95))
    if mt == "tab_search":
        k = rng.integers(5, 12)
        chosen = set(rng.choice(N_ITEMS, k, replace=False).tolist()) | {int(rng.integers(N_MCQ, N_ITEMS))}
        return dict(items=chosen, acc=rng.uniform(0.8, 0.95))
    if mt == "helper":
        start = int(rng.integers(0, N_ITEMS - 10))
        length = int(rng.integers(5, 11))
        return dict(items=set(range(start, start + length)), acc=rng.uniform(0.82, 0.95))
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/sample")
    ap.add_argument("--n", type=int, default=5000)
    ap.add_argument("--windows", type=int, default=25)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    rng = np.random.default_rng(args.seed)
    os.makedirs(args.out, exist_ok=True)
    items = make_items(rng)

    per_window = args.n // args.windows
    sess_rows, ev_rows, frame_dfs = [], [], []
    sid_counter = 0
    for w in range(args.windows):
        n = per_window
        types = np.array(["none"] * n, dtype=object)
        # ~6% malpractice overall
        idx = rng.permutation(n)
        n_phone, n_tab, n_helper = rng.poisson(5), rng.poisson(2.4), rng.poisson(1.8)
        n_rings = rng.poisson(1.0)
        pos = 0
        for mt, k in (("second_phone", n_phone), ("tab_search", n_tab), ("helper", n_helper)):
            types[idx[pos:pos + k]] = mt
            pos += k
        rings = []
        for _ in range(n_rings):
            size = int(rng.choice([2, 3, 3, 4]))
            members = idx[pos:pos + size]
            pos += size
            types[members] = "collusion"
            rings.append(members)
        # cafes: put some honest candidates on a shared IP
        cafe_ips = [hashlib.sha1(f"cafe{w}{i}".encode()).hexdigest()[:10] for i in range(3)]

        sessions = []
        for i in range(n):
            sid = f"S{sid_counter:05d}"
            sid_counter += 1
            env = sample_env(rng)
            mt = types[i]
            cfg = mal_config(rng, items, mt) if mt not in ("none", "collusion") else {}
            s = Session(sid, w, rng, items, env, mt, cfg)
            if env["room"] == "cafe":
                s.ip = cafe_ips[rng.integers(0, 3)]
            else:
                s.ip = hashlib.sha1(f"home{sid}".encode()).hexdigest()[:10]
            sessions.append(s)

        ring_of = {}
        for r_id, members in enumerate(rings):
            shared = set(rng.choice(N_ITEMS, int(rng.integers(12, 22)), replace=False).tolist())
            same_cafe = rng.random() < 0.3
            for m in members:
                ring_of[m] = (r_id, members[0])
                sessions[m].mal = dict(shared_items=shared)
                if same_cafe:
                    sessions[m].ip = cafe_ips[0]
                    sessions[m].env["room"] = "cafe"

        # leaders first
        order = sorted(range(n), key=lambda i: 0 if (i in ring_of and ring_of[i][1] == i) or i not in ring_of else 1)
        for i in order:
            s = sessions[i]
            leader = None
            if i in ring_of and ring_of[i][1] != i:
                leader = sessions[ring_of[i][1]]
            elif i in ring_of:
                s.mal_type_effective = "none"  # leader answers honestly
            s.simulate(leader)

        for i, s in enumerate(sessions):
            mal = s.mal_type != "none"
            verdict = "confirmed" if mal else "cleared"
            # a few honest people were wrongly confirmed by reviewers? No: we keep
            # verdicts clean for confirmed; a few real cases slipped past reviewers.
            if mal and rng.random() < 0.03:
                verdict = "cleared"
            sess_rows.append(dict(session_id=s.sid, window_id=w, network_ip_hash=s.ip, device=s.env["device"],
                                  bandwidth_class=s.env["bandwidth"], precheck_light=s.env["light"],
                                  precheck_framing=s.env["framing"], verdict=verdict,
                                  _truth_type=s.mal_type, _room=s.env["room"]))
            ev_rows.extend(s.events)
            frame_dfs.append(s.frames())
        print(f"window {w}: {n} sessions, malpractice {int((types != 'none').sum())}")

    sessions_df = pd.DataFrame(sess_rows)
    events_df = pd.DataFrame(ev_rows, columns=["session_id", "t", "type", "item", "option", "correct", "chars"])
    events_df = events_df.sort_values(["session_id", "t"]).reset_index(drop=True)
    frames_df = pd.concat(frame_dfs, ignore_index=True)
    items_df = pd.DataFrame(dict(item=range(N_ITEMS), kind=items["kind"],
                                 n_options=np.where(items["kind"] == "mcq", 4, 0),
                                 correct_option=np.where(items["kind"] == "mcq", OPTS[items["correct_opt"]], "")))
    sessions_df.to_csv(f"{args.out}/sessions.csv", index=False)
    events_df.to_csv(f"{args.out}/events.csv.gz", index=False)
    frames_df.to_csv(f"{args.out}/frames.csv.gz", index=False)
    items_df.to_csv(f"{args.out}/items.csv", index=False)
    print(sessions_df.verdict.value_counts().to_dict(), sessions_df._truth_type.value_counts().to_dict())
    print("events", len(events_df), "frames", len(frames_df))


if __name__ == "__main__":
    main()

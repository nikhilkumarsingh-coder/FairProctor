"""Build a ready-to-demo database.

    python -m backend.scripts.seed_demo            # from the project root; add --reset to start from scratch

Creates:
  * an admin and a reviewer login
  * the 30-question aptitude test the model was trained on (25 MCQ + 5 short answer)
  * one LIVE sitting holding 200 reference sessions (synthetic sitting 1 from data/sample: honest
    candidates plus a few planted malpractice cases, already submitted)
  * 3 team logins (TEAM01-TEAM03) who take the test live during the demo
  * the coding test with a live coding sitting (FP-CODE26) and CODE01-CODE03 logins
  * a finished, already scored sitting of the same test with Priya (honest: 2G, phone, dim shared room) and
    Rahul (second phone below the frame), so the review queue and the fairness report have a story from the start
    (skip it with --no-story)
Logins are printed and written to backend/data/demo_logins.txt.

Why reference sessions: collusion and "unusually fast" only mean something against other people
taking the same paper. In a real sitting those are the other candidates.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import random
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend import config, db  # noqa: E402
from backend.security import hash_secret, new_login_code  # noqa: E402

ADMIN = ("admin@fairproctor.demo", os.environ.get("FP_DEMO_ADMIN_PASSWORD", "Admin@2026"))
REVIEWER = ("reviewer@fairproctor.demo", os.environ.get("FP_DEMO_REVIEWER_PASSWORD", "Review@2026"))
TITLE = "Campus Hiring Assessment 2026 — Aptitude & Reasoning"
JOIN_CODE = "FP-DEMO26"     # candidates who sign up join the demo sitting with this


def make_question(rng: random.Random, n: int, letter: str) -> tuple[str, dict]:
    """A simple aptitude question whose right answer sits at `letter`."""
    kind = n % 5
    if kind == 0:
        a, b = rng.randint(12, 49), rng.randint(6, 19)
        q, ans = f"What is {a} × {b}?", a * b
        wrong = {ans + 10, ans - b, ans + a, ans - 10}
    elif kind == 1:
        p, x = rng.choice([10, 15, 20, 25, 30, 40]), rng.choice([120, 160, 240, 320, 480, 600])
        q, ans = f"What is {p}% of {x}?", p * x // 100
        wrong = {ans + 10, ans * 2, ans - 5, x // 10}
    elif kind == 2:
        a, d = rng.randint(2, 9), rng.randint(3, 8)
        seq = [a + i * d for i in range(5)]
        q, ans = f"Next number in the series: {', '.join(map(str, seq))}, ?", a + 5 * d
        wrong = {ans + 1, ans + d, ans - 1, ans + 2 * d}
    elif kind == 3:
        s, t = rng.choice([40, 45, 50, 60, 72]), rng.choice([2, 3, 4, 5])
        q, ans = f"A bus travels at {s} km/h for {t} hours. How far does it go (km)?", s * t
        wrong = {ans + s, ans - s, s + t * 10, ans + 20}
    else:
        a, b, total = rng.randint(2, 5), rng.randint(3, 7), 0
        total = (a + b) * rng.randint(5, 12)
        q, ans = f"₹{total} is shared in the ratio {a}:{b}. How much is the smaller share (₹)?", total * min(a, b) // (a + b)
        wrong = {total * max(a, b) // (a + b), ans + 5, ans - 5, total // 2}
    wrong = [w for w in wrong if w != ans and w > 0][:3]
    while len(wrong) < 3:
        wrong.append(ans + 7 * (len(wrong) + 1))
    letters = "ABCD"
    opts, wi = {}, iter(wrong)
    for L in letters:
        opts[L] = str(ans) if L == letter else str(next(wi))
    return q, opts


SHORT = [("How many minutes are there in 3.5 hours?", "210"),
         ("If 5 pens cost ₹60, how much do 8 pens cost (₹)?", "96"),
         ("What is the average of 12, 18, 24 and 30?", "21"),
         ("A shop gives 20% off on ₹450. What is the price after discount (₹)?", "360"),
         ("What is 15% of 15% of 400?", "9")]


CODE_TITLE = "Campus Hiring 2026 — Coding Round"
CODE_JOIN = "FP-CODE26"


def coding_reference(con, sit_id: int, start: str, n_reference: int = 150, seed: int = 3):
    """Synthetic coding candidates (already submitted) with typing, pastes, runs, submits and true labels."""
    from fairproctor.coding_synth import generate
    sess, ev, runs = generate(1, n_reference, seed=seed)
    ids = {s: f"C{sit_id}-S{s.split('-S')[1]}" for s in sess.session_id}
    for r in sess.rename(columns={"_truth_type": "truth"}).itertuples():
        con.execute("""INSERT INTO sessions (id, sitting_id, status, started_at, submitted_at, device, bandwidth_class, is_synthetic,
                                             ref_truth)
                       VALUES (?, ?, 'submitted', ?, ?, 'desktop', 'normal', 1, ?)""",
                    (ids[r.session_id], sit_id, start, start, r.truth))
    con.copy("events", ["session_id", "seq", "t", "type", "item", "option", "correct", "chars", "meta"],
             [(ids[r.session_id], int(r.seq), float(r.t), r.type, int(r.item), r.option or "", -1, int(r.chars),
               json.dumps(r.meta) if isinstance(r.meta, dict) else None) for r in ev.itertuples()])
    con.copy("code_runs", ["session_id", "item", "kind", "language", "code", "verdict", "passed", "total", "t", "at"],
             [(ids[r.session_id], int(r.item), r.kind, r.language, r.code, r.verdict, int(r.passed), int(r.total), float(r.t), start)
              for r in runs.itertuples()])
    return sess, ids


def seed_coding(con, now, n_live: int = 3, n_reference: int = 150) -> dict:
    """The coding test (3 problems), a live coding sitting with synthetic reference sessions, and CODE01.. logins."""
    from backend.schemas import ProblemSetIn
    from backend.services.admin import add_candidates, create_sitting
    from backend.services.coding import replace_problems
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "demo_data", "coding_problems.json")
    with open(path, encoding="utf-8") as fh:
        problems = ProblemSetIn(**json.load(fh)).problems
    test_id = con.insert("INSERT INTO tests (title, duration_min, kind) VALUES (?, ?, 'coding')", (CODE_TITLE, 60))
    replace_problems(con, test_id, problems)
    sit_id = create_sitting(con, test_id, "Coding sitting", (now - dt.timedelta(minutes=10)).isoformat(),
                            (now + dt.timedelta(days=2)).isoformat(), status="live", join_code=CODE_JOIN)
    start = (now - dt.timedelta(hours=1, minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sess, ids = coding_reference(con, sit_id, start, n_reference)
    team = add_candidates(con, sit_id, [dict(roll_no=f"CODE{i:02d}", name=f"Coder {i}", language="en") for i in range(1, n_live + 1)])
    truth = sess.set_index("session_id")["_truth_type"]
    db.audit(con, None, "demo_seeded", sit_id, reference=len(ids), live=n_live, kind="coding")
    return dict(test_id=test_id, sitting_id=sit_id, reference_sessions=len(ids), team=team,
                planted={t: int(n) for t, n in truth[truth != "none"].value_counts().items()})


def _reference(con, sit_id: int, ref: pd.DataFrame, events: pd.DataFrame, frames: pd.DataFrame, start: str) -> dict:
    """Synthetic reference sessions (already submitted) with their events, camera numbers and true labels."""
    ids = {s: f"R{sit_id}-{s}" for s in ref.session_id}
    for r in ref.rename(columns={"_truth_type": "truth"}).itertuples():
        con.execute("""INSERT INTO sessions (id, sitting_id, status, started_at, submitted_at, device, bandwidth_class,
                                             precheck_light, precheck_framing, is_synthetic, ref_truth)
                       VALUES (?, ?, 'submitted', ?, ?, ?, ?, ?, ?, 1, ?)""",
                    (ids[r.session_id], sit_id, start, start, r.device, r.bandwidth_class, r.precheck_light,
                     r.precheck_framing, r.truth))
    ev = events[events.session_id.isin(ids)].copy()
    ev["seq"] = ev.groupby("session_id").cumcount() + 1
    con.copy("events", ["session_id", "seq", "t", "type", "item", "option", "correct", "chars"],
             [(ids[r.session_id], int(r.seq), float(r.t), r.type, int(r.item), r.option, int(r.correct), int(r.chars))
              for r in ev.itertuples()])
    fr = frames[frames.session_id.isin(ids)].copy()
    fr["seq"] = fr.groupby("session_id").cumcount() + 1
    if "phone" not in fr:
        fr["phone"] = np.nan
    con.copy("frame_stats", ["session_id", "seq", "t", "faces", "face_visible", "gaze", "brightness", "blur", "phone"],
             [(ids[r.session_id], int(r.seq), float(r.t), int(r.faces), int(r.face_visible), r.gaze,
               float(r.brightness), float(r.blur), None if pd.isna(r.phone) else float(r.phone)) for r in fr.itertuples()])
    return ids


STORY_TITLE = "Morning sitting — already scored"
STORY_JOIN = "FP-MORN26"


def story_logins(data_dir: str | None = None) -> list[dict]:
    """Priya and Rahul: roll no., name, fixed login code (public demo accounts)."""
    path = os.path.join(data_dir or config.demo_data_dir(), "story_sessions.csv")
    if not os.path.exists(path):
        return []
    return pd.read_csv(path, keep_default_na=False).to_dict("records")


def seed_story(con, test_id: int, now, ref: pd.DataFrame, events: pd.DataFrame, frames: pd.DataFrame, data_dir: str) -> dict:
    """A finished sitting of the same test: 200 reference sessions plus Priya (honest; 2G, phone, dim shared room)
    and Rahul (second phone below the frame). Scored right after the seed, so the queue has a story from the start."""
    from backend.services.admin import add_candidates, create_sitting
    people = story_logins(data_dir)
    if not people:
        return {}
    sev = pd.read_csv(os.path.join(data_dir, "story_events.csv"), keep_default_na=False)
    sfr = pd.read_csv(os.path.join(data_dir, "story_frames.csv.gz"), keep_default_na=False)
    began = now - dt.timedelta(hours=3)
    sit_id = create_sitting(con, test_id, STORY_TITLE, began.isoformat(), (now - dt.timedelta(hours=1)).isoformat(),
                            status="live", join_code=STORY_JOIN)
    ids = _reference(con, sit_id, ref, events, frames, (began + dt.timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    made = add_candidates(con, sit_id, [dict(roll_no=p["roll_no"], name=p["name"], language=p["language"]) for p in people])
    out = []
    for p, m in zip(people, made):
        con.execute("UPDATE users SET secret_hash = ? WHERE id = ?", (hash_secret(p["code"]), m["user_id"]))
        sid = db.one(con, "SELECT id FROM sessions WHERE user_id = ?", m["user_id"])["id"]
        ev = sev[sev.key == p["key"]].sort_values("t")
        fr = sfr[sfr.key == p["key"]].sort_values("t")
        n_ev = len(ev)
        con.copy("events", ["session_id", "seq", "t", "type", "item", "option", "correct", "chars"],
                 [(sid, i + 1, float(r.t), r.type, int(r.item), r.option, int(r.correct), int(r.chars))
                  for i, r in enumerate(ev.itertuples())])
        ph = fr["phone"] if "phone" in fr else pd.Series([np.nan] * len(fr), index=fr.index)
        con.copy("frame_stats", ["session_id", "seq", "t", "faces", "face_visible", "gaze", "brightness", "blur", "phone"],
                 [(sid, n_ev + i + 1, float(r.t), int(r.faces), int(r.face_visible), r.gaze, float(r.brightness), float(r.blur),
                   None if pd.isna(p) else float(p)) for i, (r, p) in enumerate(zip(fr.itertuples(), ph))])
        t0 = began + dt.timedelta(minutes=5)
        t1 = t0 + dt.timedelta(seconds=float(ev.t.max()) + 20)
        con.execute("""UPDATE sessions SET status = 'submitted', started_at = ?, submitted_at = ?, device = ?, bandwidth_class = ?,
                                           precheck_light = ?, precheck_framing = ?, last_seq = ? WHERE id = ?""",
                    (t0.strftime("%Y-%m-%dT%H:%M:%SZ"), t1.strftime("%Y-%m-%dT%H:%M:%SZ"), p["device"], p["bandwidth_class"],
                     p["precheck_light"], p["precheck_framing"], n_ev + len(fr), sid))
        con.execute("INSERT INTO consents (session_id, version, camera_ok, precheck_share_ok) VALUES (?, ?, 1, 0)",
                    (sid, config.CONSENT_VERSION))
        out.append(dict(roll_no=p["roll_no"], name=p["name"], code=p["code"], session_id=sid))
    db.audit(con, None, "demo_seeded", sit_id, reference=len(ids), story=len(out))
    return dict(sitting_id=sit_id, reference_sessions=len(ids), people=out)


def score_now(sitting_id: int) -> None:
    """Score a sitting synchronously (the seed runs without the server's job worker)."""
    from backend.services import scoring
    with db.tx() as con:
        con.execute("UPDATE sittings SET status = 'scoring', closed_at = ? WHERE id = ?", (db.now(), sitting_id))
        job = con.insert("INSERT INTO jobs (kind, target, status) VALUES ('score_sitting', ?, 'running')", (str(sitting_id),))
    scoring.score_sitting(job, sitting_id)
    with db.tx() as con:
        con.execute("UPDATE jobs SET status = 'done', progress = 1, finished_at = ? WHERE id = ?", (db.now(), job))


def seed(reset: bool = False, data_dir: str | None = None, window: int = 0, n_live: int = 3, story: bool = False) -> dict:
    if reset:
        db.reset_database()
    data_dir = data_dir or config.demo_data_dir()
    if not os.path.exists(os.path.join(data_dir, "sessions.csv")):
        raise SystemExit(f"Demo data not found in {data_dir}. It ships in backend/demo_data; "
                         "or pass --data data/sample after running `python data/generate.py`.")
    sessions = pd.read_csv(os.path.join(data_dir, "sessions.csv"))
    events = pd.read_csv(os.path.join(data_dir, "events.csv.gz"), keep_default_na=False)
    frames = pd.read_csv(os.path.join(data_dir, "frames.csv.gz"), keep_default_na=False)
    items = pd.read_csv(os.path.join(data_dir, "items.csv"), keep_default_na=False)
    rng = random.Random(7)
    out = {}
    with db.tx() as con:
        for (email, pw), role, name in ((ADMIN, "admin", "Demo Admin"), (REVIEWER, "reviewer", "Demo Reviewer")):
            if not db.one(con, "SELECT 1 FROM users WHERE email = ?", email):
                con.execute("INSERT INTO users (role, name, email, secret_hash) VALUES (?, ?, ?, ?)",
                            (role, name, email, hash_secret(pw)))
        test_id = con.insert("INSERT INTO tests (title, duration_min) VALUES (?, ?)", (TITLE, 45))
        short_iter = iter(SHORT)
        for r in items.itertuples():
            if r.kind == "mcq":
                text, opts = make_question(rng, r.item, r.correct_option)
                correct = r.correct_option
            else:
                text, correct = next(short_iter)
                opts = {}
            con.execute("""INSERT INTO items (test_id, position, kind, text, options, correct_option)
                           VALUES (?, ?, ?, ?, ?, ?)""", (test_id, int(r.item), r.kind, text, json.dumps(opts, ensure_ascii=False),
                                                         correct))
        now = dt.datetime.now(dt.timezone.utc)
        from backend.services.admin import add_candidates, create_sitting
        sit_id = create_sitting(con, test_id, "Demo sitting", (now - dt.timedelta(minutes=10)).isoformat(),
                                (now + dt.timedelta(days=2)).isoformat(), status="live", join_code=JOIN_CODE)
        # reference sessions, already submitted
        ref = sessions[sessions.window_id == window]
        start = (now - dt.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ids = _reference(con, sit_id, ref, events, frames, start)
        # live team logins
        team = add_candidates(con, sit_id, [dict(roll_no=f"TEAM{i:02d}", name=f"Team member {i}", language="en")
                                            for i in range(1, n_live + 1)])
        db.audit(con, None, "demo_seeded", sit_id, reference=len(ids), live=n_live)
        truth = ref.set_index("session_id")["_truth_type"]
        out = dict(test_id=test_id, sitting_id=sit_id, reference_sessions=len(ids), team=team,
                   planted={t: int(n) for t, n in truth[truth != "none"].value_counts().items()})
        out["coding"] = seed_coding(con, now, n_live)
        out["story"] = seed_story(con, test_id, now, ref, events, frames, data_dir) if story else {}
    if out["story"]:
        score_now(out["story"]["sitting_id"])
    where = "PostgreSQL" if config.is_postgres() else config.db_path()
    lines = [f"FairProctor demo logins (database: {where})", "",
             f"Admin     {ADMIN[0]} / {ADMIN[1]}", f"Reviewer  {REVIEWER[0]} / {REVIEWER[1]}", "",
             f"Sitting {out['sitting_id']} is LIVE with {out['reference_sessions']} reference sessions "
             f"(planted malpractice: {out['planted']}).",
             f"Join code for candidates who sign up: {JOIN_CODE}", "", "Candidates (roll no / code):"]
    lines += [f"  {t['roll_no']}  {t['code']}" for t in out["team"]]
    c = out["coding"]
    lines += ["", f"Coding sitting {c['sitting_id']} ({CODE_TITLE}) is LIVE with {c['reference_sessions']} reference sessions "
              f"(planted malpractice: {c['planted']}).", f"Join code for the coding test: {CODE_JOIN}", "",
              "Coding candidates (roll no / code):"]
    lines += [f"  {t['roll_no']}  {t['code']}" for t in c["team"]]
    if out["story"]:
        st = out["story"]
        lines += ["", f"Sitting {st['sitting_id']} ({STORY_TITLE}) is SCORED: {st['reference_sessions']} reference sessions plus",
                  "Priya (honest: 2G, phone, dim shared room) and Rahul (second phone below the frame).",
                  "Their results (roll no / code):"]
        lines += [f"  {p['roll_no']}  {p['code']}   {p['name']}" for p in st["people"]]
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(os.path.join(config.DATA_DIR, "demo_logins.txt"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="DELETE all data first (SQLite file, or every table in the PostgreSQL database)")
    ap.add_argument("--data", default=None, help="synthetic data folder (default backend/demo_data)")
    ap.add_argument("--window", type=int, default=0, help="which synthetic sitting to use as reference")
    ap.add_argument("--team", type=int, default=3, help="number of live candidate logins")
    ap.add_argument("--no-story", action="store_true", help="skip the scored sitting with Priya and Rahul")
    ap.add_argument("--if-empty", action="store_true", help="do nothing if the database already has sittings (for Docker)")
    a = ap.parse_args()
    if a.if_empty and not a.reset:
        db.migrate()
        with db.tx() as con:
            if db.one(con, "SELECT COUNT(*) n FROM sittings")["n"]:
                print("Database already has data; not seeding (use --reset to start over).")
                raise SystemExit(0)
    seed(a.reset, a.data, a.window, a.team, story=not a.no_story)

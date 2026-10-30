"""Write the two story candidates of the demo into backend/demo_data/story_*.csv (run once; the files ship).

    python -m backend.scripts.make_story

Priya Sharma — honest. Low bandwidth (camera numbers arrive every ~8 s, with drops), a phone held low, a dim room in a
  shared home where people walk past, and one call notification that takes her out of the test for a moment.
  Old frame-by-frame rules would flag her hundreds of times; FairProctor should clear her and say why.
Rahul Verma — a second phone below the frame on 12 of the hardest questions: silent pauses with no touch or key,
  head down, then a correct answer. Good light, a laptop, alone in the room. FairProctor should put him first.

Both are simulated with the same engine as the reference data (data/generate.py), on the same 30 questions.
"""
from __future__ import annotations

import importlib.util
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "backend", "demo_data")

STORY = [
    dict(key="priya", roll_no="STORY01", name="Priya Sharma", code="PRIYA1", language="en", seed=103, theta=0.5, speed=0.0,
         env=dict(bandwidth="low", device="phone", room="shared_home", light="dim", framing="ok", benign_focus=1,
                  benign_paste=False), mal="none"),
    dict(key="rahul", roll_no="STORY02", name="Rahul Verma", code="RAHUL1", language="en", seed=202, theta=-0.6, speed=0.1,
         env=dict(bandwidth="normal", device="desktop", room="alone", light="ok", framing="ok", benign_focus=0,
                  benign_paste=False), mal="second_phone"),
]


def _generator():
    spec = importlib.util.spec_from_file_location("fp_generate", os.path.join(ROOT, "data", "generate.py"))
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    return gen


def build() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    gen = _generator()
    items = gen.make_items(np.random.default_rng(7))          # the same 30 questions as the reference data (seed 7)
    shipped = pd.read_csv(os.path.join(OUT, "items.csv"), keep_default_na=False)
    mcq = items["kind"] == "mcq"
    assert list(gen.OPTS[items["correct_opt"]][mcq]) == list(shipped.correct_option[mcq]), "items differ from demo data"
    hardest = [int(q) for q in np.argsort(-items["b"]) if items["kind"][q] == "mcq"]
    rows, events, frames = [], [], []
    for p in STORY:
        rng = np.random.default_rng(p["seed"])
        cfg = dict(items=set(hardest[:12]), acc=0.95) if p["mal"] == "second_phone" else {}
        s = gen.Session(p["key"], 0, rng, items, dict(p["env"]), p["mal"], cfg)
        s.theta, s.speed = p["theta"], p["speed"]
        s.simulate()
        fr = s.frames()
        if p["env"]["bandwidth"] == "low":                    # 2G: a camera number every ~8 s at best
            keep, last = [], -1e9
            for t in fr.t:
                keep.append(t - last >= 7.5)
                if keep[-1]:
                    last = t
            fr = fr[keep]
        rows.append(dict(key=p["key"], roll_no=p["roll_no"], name=p["name"], code=p["code"], language=p["language"],
                         device=p["env"]["device"], bandwidth_class=p["env"]["bandwidth"], precheck_light=p["env"]["light"],
                         precheck_framing=p["env"]["framing"], truth=p["mal"], room=p["env"]["room"]))
        events.extend(s.events)
        frames.append(fr)
    ev = pd.DataFrame(events, columns=["key", "t", "type", "item", "option", "correct", "chars"]).sort_values(["key", "t"])
    return pd.DataFrame(rows), ev.reset_index(drop=True), pd.concat(frames, ignore_index=True).rename(columns={"session_id": "key"})


def main():
    sess, ev, fr = build()
    sess.to_csv(os.path.join(OUT, "story_sessions.csv"), index=False)
    ev.to_csv(os.path.join(OUT, "story_events.csv"), index=False)
    fr.to_csv(os.path.join(OUT, "story_frames.csv.gz"), index=False)
    for k, g in fr.groupby("key"):
        e = ev[ev.key == k]
        print(f"{k}: {int((e.type == 'answer').sum())} answers, {int(e[e.type == 'answer'].correct.sum())} correct, "
              f"{int((e.type == 'idle_start').sum())} silent pauses, {int((e.type == 'focus_lost').sum())} focus losses, "
              f"{len(g)} camera numbers ({(g.gaze == 'down').mean():.0%} looking down, {(g.faces >= 2).sum()} with a second face, "
              f"mean brightness {g.brightness.mean():.0f})")


if __name__ == "__main__":
    main()

"""Map the real IMAP proctoring event schema onto docs/SCHEMA.md.

Fill in IMAP_EVENT_TYPES and the column names once the IMAP schema document is
available, then run:

    python -m fairproctor.adapters --imap path/to/export --out data/imap
    python -m fairproctor.pipeline --data data/imap --out artifacts

An export with no video frames (event logs only) needs no frames file: the pipeline then trains the events-only model
and writes reports/RESULTS_EVENTS_ONLY.md.
"""
import argparse
import os

import pandas as pd

# IMAP event name -> FairProctor event type. Placeholder names; replace with the real ones.
IMAP_EVENT_TYPES = {
    "QUESTION_VIEW": "item_shown",
    "ANSWER_SUBMIT": "answer",
    "TAB_BLUR": "focus_lost",
    "TAB_FOCUS": "focus_gained",
    "PASTE": "paste",
    "IDLE_START": "idle_start",
    "IDLE_END": "idle_end",
}


def convert(src: str, out: str):
    os.makedirs(out, exist_ok=True)
    ev = pd.read_csv(os.path.join(src, "events.csv"))
    ev = ev[ev["event"].isin(IMAP_EVENT_TYPES)]
    ev = pd.DataFrame(dict(
        session_id=ev["session_id"], t=ev["ts_ms"] / 1000.0, type=ev["event"].map(IMAP_EVENT_TYPES),
        item=ev.get("question_index", -1), option=ev.get("option", ""), correct=ev.get("is_correct", -1),
        chars=ev.get("paste_length", 0)))
    ev.to_csv(os.path.join(out, "events.csv.gz"), index=False)
    # frames, sessions and items follow the same pattern; see docs/SCHEMA.md for the target columns.


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--imap", required=True)
    ap.add_argument("--out", default="data/imap")
    a = ap.parse_args()
    convert(a.imap, a.out)

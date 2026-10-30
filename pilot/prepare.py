"""Set up a real pilot: create the pilot sitting(s), import participants, and write their cards and the sealed key.

    python -m pilot.prepare --people 16                        # question test for 16 people
    python -m pilot.prepare --people 16 --coding-people 8      # plus a coding test for 8 (can be the same people)
    python -m pilot.prepare --people 16 --url https://<your-tunnel>.trycloudflare.com
    python -m pilot.prepare --cards-only --dir pilot/out/<name> --url https://<new-link>   # new link, same people

Run it from the project folder on the computer that runs the backend (it writes to the same database), after
`python -m backend.scripts.seed_demo` has created the demo tests. Everything goes to pilot/out/<name>/:
    cards.html          all cards to print (2 per A4 page); fold each card so the role is hidden
    cards/<roll>.html   one card per person, to send privately instead of printing
    consent.html        participant information and consent (print one per person)
    logins.csv          roll no. and login code of every participant (codes cannot be shown again)
    key-SEALED.csv      who has which role: keep it closed until the sitting is scored
    pilot.json          the sitting ids, for `python -m pilot.report`
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import config, db  # noqa: E402

from . import cards  # noqa: E402
from .roles import CODING, MCQ, ROLES, assign  # noqa: E402

OUT = os.path.join(ROOT, "pilot", "out")


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "pilot"


def _write_csv(path: str, rows: list[dict], cols: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})


def read_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def render(folder: str, meta: dict, people: list[dict], codes: dict[str, str], url: str | None) -> None:
    """cards.html, cards/<roll>.html and consent.html from the key and the codes."""
    os.makedirs(os.path.join(folder, "cards"), exist_ok=True)
    titles = {t: v["test_title"] for t, v in meta["tests"].items()}
    blocks = []
    for i, p in enumerate(people):
        c = cards.card(p, codes[p["roll_no"]], url, titles[p["test"]])
        blocks.append(c + ('<div class="page-break"></div>' if i % 2 == 1 else ""))
        with open(os.path.join(folder, "cards", f"{p['roll_no']}.html"), "w", encoding="utf-8") as fh:
            fh.write(cards.page(f"FairProctor pilot — {p['roll_no']}", c, url))
    note = (f"{len(people)} cards for “{meta['name']}”. Print on A4 (two per page), fold each card on the dashed line, and "
            "hand them out face down. Or send each person their own file from the cards folder.")
    with open(os.path.join(folder, "cards.html"), "w", encoding="utf-8") as fh:
        fh.write(cards.page(f"FairProctor pilot cards — {meta['name']}", "".join(blocks), url, note))
    with open(os.path.join(folder, "consent.html"), "w", encoding="utf-8") as fh:
        fh.write(cards.page("FairProctor pilot — consent", cards.consent(), None,
                            "Print one copy per participant and keep the signed copies."))


def _load_reference():
    import pandas as pd
    d = config.demo_data_dir()
    sessions = pd.read_csv(os.path.join(d, "sessions.csv"))
    events = pd.read_csv(os.path.join(d, "events.csv.gz"), keep_default_na=False)
    frames = pd.read_csv(os.path.join(d, "frames.csv.gz"), keep_default_na=False)
    return sessions[sessions.window_id == 0], events, frames


def create(name: str, people_mcq: int, people_coding: int, seed: int, reference: bool, url: str | None,
           folder: str | None = None, dry_run: bool = False) -> str:
    from backend.scripts.seed_demo import CODE_TITLE, TITLE, _reference, coding_reference
    from backend.services.admin import add_candidates, create_sitting
    slug = slugify(name)
    folder = folder or os.path.join(OUT, slug)
    if os.path.exists(os.path.join(folder, "pilot.json")):
        raise SystemExit(f"{folder} already has a pilot. Choose another --name, or delete that folder first.")
    plan = [(MCQ, people_mcq, TITLE), (CODING, people_coding, CODE_TITLE)]
    now = dt.datetime.now(dt.timezone.utc)
    start = (now - dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = dict(name=name, slug=slug, created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), seed=seed, url=url or "",
                reference=reference, dry_run=dry_run, database="PostgreSQL" if config.is_postgres() else config.db_path(),
                tests={})
    people, codes = [], {}
    with db.tx() as con:
        for test, n, title in plan:
            if not n:
                continue
            t = db.one(con, "SELECT id, duration_min FROM tests WHERE title = ? ORDER BY id LIMIT 1", title)
            if not t:
                raise SystemExit(f"The demo test “{title}” is not in this database. Run "
                                 "`python -m backend.scripts.seed_demo` first (or without --reset to keep your data).")
            label = "coding" if test == CODING else "questions"
            sit = create_sitting(con, t["id"], f"Pilot ({label}) — {name}", (now - dt.timedelta(minutes=5)).isoformat(),
                                 (now + dt.timedelta(days=3)).isoformat(), status="live")
            n_ref = 0
            if reference:
                if test == MCQ:
                    ref, ev, fr = _load_reference()
                    n_ref = len(_reference(con, sit, ref, ev, fr, start))
                else:
                    n_ref = len(coding_reference(con, sit, start, 150)[1])
            roles = assign(test, n, seed)
            made = add_candidates(con, sit, [dict(roll_no=r["roll_no"], name=f"Participant {r['roll_no']}", language="en")
                                             for r in roles])
            codes.update({m["roll_no"]: m["code"] for m in made})
            people += roles
            meta["tests"][test] = dict(sitting_id=sit, test_id=t["id"], test_title=title, duration_min=t["duration_min"],
                                       people=n, reference_sessions=n_ref)
            db.audit(con, None, "pilot_created", sit, people=n, reference=n_ref, dry_run=dry_run)
    os.makedirs(folder, exist_ok=True)
    _write_csv(os.path.join(folder, "key-SEALED.csv"), people, ["roll_no", "test", "role", "kind", "partner"])
    _write_csv(os.path.join(folder, "logins.csv"), [dict(roll_no=p["roll_no"], test=p["test"], code=codes[p["roll_no"]])
                                                    for p in people], ["roll_no", "test", "code"])
    with open(os.path.join(folder, "pilot.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2)
    render(folder, meta, people, codes, url)
    return folder


def main():
    ap = argparse.ArgumentParser(description="Create a FairProctor pilot: sittings, participants, cards, sealed key.")
    ap.add_argument("--people", type=int, default=0, help="participants for the question test (at least 4)")
    ap.add_argument("--coding-people", type=int, default=0, help="participants for the coding test (at least 4)")
    ap.add_argument("--name", default=None, help="a short name, e.g. 'hostel pilot 1' (default: pilot-<date>)")
    ap.add_argument("--url", default=None, help="the link participants open (e.g. your cloudflared https link)")
    ap.add_argument("--seed", type=int, default=None, help="random seed for the roles (default: random)")
    ap.add_argument("--no-reference", action="store_true",
                    help="no synthetic reference candidates in the pilot sittings (not recommended for small pilots)")
    ap.add_argument("--rehearsal", action="store_true",
                    help="a practice pilot for `python -m pilot.dry_run` (simulated participants); never reported to README")
    ap.add_argument("--cards-only", action="store_true", help="re-make the cards of an existing pilot (e.g. with a new --url)")
    ap.add_argument("--dir", default=None, help="the pilot folder (with --cards-only)")
    a = ap.parse_args()
    if a.cards_only:
        if not a.dir:
            raise SystemExit("--cards-only needs --dir pilot/out/<name>")
        with open(os.path.join(a.dir, "pilot.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
        people = read_csv(os.path.join(a.dir, "key-SEALED.csv"))
        codes = {r["roll_no"]: r["code"] for r in read_csv(os.path.join(a.dir, "logins.csv"))}
        url = a.url or meta.get("url") or None
        meta["url"] = url or ""
        with open(os.path.join(a.dir, "pilot.json"), "w", encoding="utf-8") as fh:
            json.dump(meta, fh, indent=2)
        render(a.dir, meta, people, codes, url)
        print(f"Cards re-made in {a.dir}" + (f" with the link {url}" if url else ""))
        return
    if a.people and a.people < 4 or a.coding_people and a.coding_people < 4:
        raise SystemExit("Each test needs at least 4 participants (12–20 is better).")
    if not a.people and not a.coding_people:
        raise SystemExit("Say how many people: --people 16 (question test) and/or --coding-people 8.")
    name = a.name or f"{'rehearsal' if a.rehearsal else 'pilot'} {dt.date.today().isoformat()}"
    seed = a.seed if a.seed is not None else random.SystemRandom().randint(1, 10 ** 6)
    folder = create(name, a.people, a.coding_people, seed, not a.no_reference, a.url, dry_run=a.rehearsal)
    with open(os.path.join(folder, "pilot.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    print(f"\nPilot “{name}” is ready.\n")
    for test, t in meta["tests"].items():
        print(f"  {'Coding' if test == CODING else 'Question'} test: sitting {t['sitting_id']} (live), {t['people']} participants, "
              f"{t['reference_sessions']} reference sessions")
    print(f"\n  Cards to print:     {os.path.join(folder, 'cards.html')}")
    print(f"  One card per person: {os.path.join(folder, 'cards')}")
    print(f"  Consent form:        {os.path.join(folder, 'consent.html')}")
    print(f"  Sealed key:          {os.path.join(folder, 'key-SEALED.csv')}   <- do not open until scoring is done")
    if meta["dry_run"]:
        print("\nThis is a rehearsal. Play it with simulated participants:")
        print(f"  python -m pilot.dry_run --dir {os.path.relpath(folder, ROOT)}")
    else:
        print("\nAfter everyone submits: admin → the pilot sitting → Close & score, then")
        print(f"  python -m pilot.report --dir {os.path.relpath(folder, ROOT)}")
    counts: dict[str, int] = {}
    for p in read_csv(os.path.join(folder, "key-SEALED.csv")):
        counts[ROLES[p["role"]]["kind"]] = counts.get(ROLES[p["role"]]["kind"], 0) + 1
    print(f"\n({counts.get('honest', 0)} honest roles, {counts.get('cheat', 0)} malpractice roles; who is who is only in the key.)")


if __name__ == "__main__":
    main()

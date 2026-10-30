"""Results of a pilot: who was caught, who was flagged, and for what reason, against the sealed role key.

    python -m pilot.report --dir pilot/out/<name>                    # writes reports/PILOT_RESULTS.md + charts
    python -m pilot.report --dir pilot/out/<name> --update-readme    # also fills the "Real pilot" section of README.md

Run it after the admin has pressed Close & score on every pilot sitting. Only the participants are counted; the
synthetic reference candidates in the same sitting are calibration data. A dry run (pilot.dry_run) is reported to
the pilot folder only and never touches README.md or reports/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import db  # noqa: E402
from backend.services import fairness  # noqa: E402

from .prepare import read_csv  # noqa: E402
from .roles import CODING, MCQ, ROLES  # noqa: E402

BAND = {"review_first": "Review first", "review": "Review", "clear": "Cleared"}
FAMILY = {"match": "answer match", "timing": "timing", "pause": "silent pauses", "focus": "left the window",
          "paste": "paste", "person": "another person", "phone": "phone in view", "code_match": "code match", "typing": "typing"}
TEST_NAME = {MCQ: "Question test", CODING: "Coding test"}
THEMES = {"light": dict(bg="#ffffff", ink="#0b0b0b", ink2="#52514e", muted="#898781", band="#ecebe6", cheat="#eb6834", honest="#c3c2b7"),
          "dark": dict(bg="#0d1117", ink="#f0efec", ink2="#c3c2b7", muted="#8b949e", band="#21262d", cheat="#d95926", honest="#484f58")}
MARK = ("<!-- pilot:start -->", "<!-- pilot:end -->")


def pct(k: int, n: int) -> str:
    return f"{k} of {n}" + (f" ({100 * k / n:.0f}%)" if n else "")


def ci(k: int, n: int) -> str:
    lo, hi = fairness.wilson(k, n)
    return "" if lo is None else f"95% CI {100 * lo:.0f}–{100 * hi:.0f}%"


def auc(pos: list[float], neg: list[float]) -> float | None:
    if not pos or not neg:
        return None
    s = sum((p > q) + 0.5 * (p == q) for p in pos for q in neg)
    return s / (len(pos) * len(neg))


def collect(con, test: str, sitting_id: int, key: dict[str, dict]) -> dict:
    sit = db.one(con, "SELECT id, title, status FROM sittings WHERE id = ?", sitting_id)
    if not sit:
        raise SystemExit(f"Sitting {sitting_id} is not in this database (is DATABASE_URL / FP_DB the same as the server's?).")
    if sit["status"] != "scored":
        raise SystemExit(f"“{sit['title']}” is {sit['status']}. As admin, press Close & score on it first, then run this again.")
    rows = db.all_(con, """SELECT u.roll_no, x.id, x.status, x.device, x.bandwidth_class, x.precheck_light, x.precheck_framing,
                                  c.band, c.priority, c.rank, c.families, c.explanation
                           FROM users u JOIN sessions x ON x.user_id = u.id LEFT JOIN scores c ON c.session_id = x.id
                           WHERE x.sitting_id = ? ORDER BY u.roll_no""", sitting_id)
    scored = [r for r in rows if r["band"] and r["roll_no"] in key]
    missing = [r["roll_no"] for r in rows if r["roll_no"] in key and not r["band"]]
    groups, old = fairness._groups(con, sitting_id, test, scored)
    reviews = {r["session_id"]: r["decision"] for r in db.all_(con, """
        SELECT r.session_id, r.decision FROM reviews r JOIN sessions x ON x.id = r.session_id
        WHERE x.sitting_id = ? AND r.id = (SELECT MAX(r2.id) FROM reviews r2 WHERE r2.session_id = r.session_id)""", sitting_id)}
    people = []
    for r in scored:
        k = key[r["roll_no"]]
        role = ROLES[k["role"]]
        fams = json.loads(r["families"] or "[]")
        expl = json.loads(r["explanation"] or "{}")
        measured = [r["device"], f"{r['bandwidth_class']} bandwidth", f"pre-check light {r['precheck_light']}"]
        if groups.get("room", {}).get(r["id"]) == "others":
            measured.append("others around on camera")
        if groups.get("language", {}).get(r["id"]):
            measured.append(groups["language"][r["id"]])
        people.append(dict(roll_no=r["roll_no"], role=k["role"], kind=role["kind"], partner=k.get("partner", ""),
                           title=role["title"][0], band=r["band"], priority=int(r["priority"]), families=fams,
                           reason=(expl.get("reasons") or [{}])[0].get("title", "—") if r["band"] != "clear" else "—",
                           right=bool(set(fams) & set(role.get("expect", set()))) if role["kind"] == "cheat" else None,
                           old=old[r["id"]], measured=", ".join(m for m in measured if m), review=reviews.get(r["id"], "")))
    # queue order of each system among the participants, and the same number of flags for the old rules
    ours = sorted(people, key=lambda p: (-p["priority"], p["roll_no"]))
    oldq = sorted(people, key=lambda p: (-p["old"], hashlib.sha1(p["roll_no"].encode()).hexdigest()))
    w_any = sum(p["band"] != "clear" for p in people)
    w_first = sum(p["band"] == "review_first" for p in people)
    for i, p in enumerate(ours):
        p["rank"] = i + 1
    for i, p in enumerate(oldq):
        p["old_rank"] = i + 1
        p["old_any"], p["old_first"] = i < w_any, i < w_first
    return dict(test=test, title=sit["title"], sitting_id=sitting_id, people=people, missing=missing, ours=ours, oldq=oldq,
                w_any=w_any, w_first=w_first)


def summarise(d: dict) -> dict:
    P = d["people"]
    ch = [p for p in P if p["kind"] == "cheat"]
    ho = [p for p in P if p["kind"] == "honest"]
    s = dict(n=len(P), n_cheat=len(ch), n_honest=len(ho),
             ours_any=sum(p["band"] != "clear" for p in ch), ours_first=sum(p["band"] == "review_first" for p in ch),
             old_any=sum(p["old_any"] for p in ch), old_first=sum(p["old_first"] for p in ch),
             h_ours_any=sum(p["band"] != "clear" for p in ho), h_ours_first=sum(p["band"] == "review_first" for p in ho),
             h_old_any=sum(p["old_any"] for p in ho), h_old_first=sum(p["old_first"] for p in ho),
             right=sum(1 for p in ch if p["band"] != "clear" and p["right"]),
             auc_ours=auc([p["priority"] for p in ch], [p["priority"] for p in ho]),
             auc_old=auc([p["old"] for p in ch], [p["old"] for p in ho]))
    decided = [p for p in P if p["review"] in ("confirm", "clear")]
    s["reviewed"] = len(decided)
    s["rev_ok"] = sum(1 for p in decided if (p["review"] == "confirm") == (p["kind"] == "cheat"))
    return s


def queue_svg(d: dict, theme: str) -> str:
    """Two rows of squares, one per participant in queue order: FairProctor's queue and the old rules' queue."""
    c = THEMES[theme]
    n = len(d["people"])
    cell, gap, left, top = 26, 6, 150, 100
    W = max(left + n * (cell + gap) + 24, 660)
    H = top + 2 * (cell + 52) + 24
    E = html.escape
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           'font-family="system-ui, -apple-system, Segoe UI, sans-serif">',
           f'<title>{E(TEST_NAME[d["test"]])}: participants in queue order, FairProctor vs the old rules</title>',
           f'<rect width="{W}" height="{H}" rx="12" fill="{c["bg"]}"/>',
           f'<text x="24" y="30" font-size="16" font-weight="700" fill="{c["ink"]}">{E(TEST_NAME[d["test"]])}: who is at the top of the queue</text>',
           f'<rect x="24" y="44" width="12" height="12" rx="2" fill="{c["cheat"]}"/>'
           f'<text x="42" y="54" font-size="12.5" fill="{c["ink2"]}">acted out malpractice</text>',
           f'<rect x="190" y="44" width="12" height="12" rx="2" fill="{c["honest"]}"/>'
           f'<text x="208" y="54" font-size="12.5" fill="{c["ink2"]}">honest</text>']
    for row, (label, q) in enumerate((("FairProctor", d["ours"]), ("Old rules", d["oldq"]))):
        y = top + row * (cell + 52)
        x0 = left
        if d["w_any"]:
            out.append(f'<rect x="{x0 - 4}" y="{y - 6}" width="{d["w_any"] * (cell + gap) + 2}" height="{cell + 12}" rx="6" fill="{c["band"]}"/>')
        out.append(f'<text x="24" y="{y + cell / 2 + 5}" font-size="13" font-weight="600" fill="{c["ink"]}">{label}</text>')
        for i, p in enumerate(q):
            x = x0 + i * (cell + gap)
            out.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="4" fill="{c["cheat"] if p["kind"] == "cheat" else c["honest"]}">'
                       f'<title>{E(p["roll_no"])} · {E(p["title"])}</title></rect>')
            out.append(f'<text x="{x + cell / 2}" y="{y + cell + 13}" font-size="9.5" text-anchor="middle" fill="{c["muted"]}">{E(p["roll_no"])}</text>')
        if d["w_any"]:
            out.append(f'<text x="{x0 - 2}" y="{y - 12}" font-size="11" fill="{c["ink2"]}">sent to review ({d["w_any"]} slots)</text>')
    out.append(f'<text x="24" y="{H - 12}" font-size="11.5" fill="{c["muted"]}">Top of the queue on the left. The old rules get the same number of review slots.</text>')
    out.append("</svg>")
    return "\n".join(out)


def md_test(d: dict, s: dict, chart: str | None) -> list[str]:
    L = [f"## {TEST_NAME[d['test']]}", ""]
    L += [f"{s['n']} participants scored ({s['n_cheat']} acted out malpractice, {s['n_honest']} honest)"
          + (f"; did not finish: {', '.join(d['missing'])}" if d["missing"] else "") + ".", ""]
    L += ["| | FairProctor | Old rules, same number of flags |", "|---|---|---|",
          f"| Malpractice caught (sent to review) | **{pct(s['ours_any'], s['n_cheat'])}** · {ci(s['ours_any'], s['n_cheat'])} | {pct(s['old_any'], s['n_cheat'])} |",
          f"| Malpractice in *Review first* | {pct(s['ours_first'], s['n_cheat'])} | {pct(s['old_first'], s['n_cheat'])} |",
          f"| Honest sent to review | **{pct(s['h_ours_any'], s['n_honest'])}** · {ci(s['h_ours_any'], s['n_honest'])} | {pct(s['h_old_any'], s['n_honest'])} |",
          f"| Honest in *Review first* | {pct(s['h_ours_first'], s['n_honest'])} | {pct(s['h_old_first'], s['n_honest'])} |"]
    if s["auc_ours"] is not None:
        L.append(f"| Ranking (AUC: chance that a cheater ranks above an honest participant) | {s['auc_ours']:.2f} | {s['auc_old']:.2f} |")
    L += ["", f"Flagged for the right reason: **{s['right']} of {s['ours_any']}** caught cases showed the reason their role "
          "should produce (for example silent pauses for a second phone, answer match for partners).", ""]
    if s["reviewed"]:
        L += [f"Blind reviewer decisions: {s['rev_ok']} of {s['reviewed']} matched the sealed key.", ""]
    if chart:
        L += [chart, ""]
    by: dict[str, list] = {}
    for p in d["people"]:
        by.setdefault(p["role"], []).append(p)
    L += ["| Role | People | FairProctor: sent to review | of them *Review first* | Old rules: flagged |", "|---|---|---|---|---|"]
    for role in sorted(by, key=lambda r: (ROLES[r]["kind"] != "cheat", r)):
        g = by[role]
        L.append(f"| {ROLES[role]['title'][0]} ({ROLES[role]['kind']}) | {len(g)} | {sum(p['band'] != 'clear' for p in g)} | "
                 f"{sum(p['band'] == 'review_first' for p in g)} | {sum(p['old_any'] for p in g)} |")
    L += ["", "<details><summary>Every participant</summary>", "",
          "| Participant | Role | Measured | FairProctor | Main reason | Queue rank | Old-rules rank | Reviewer |",
          "|---|---|---|---|---|---|---|---|"]
    for p in d["ours"]:
        mark = "" if p["kind"] == "honest" else (" ✓" if p["right"] else (" ✗ reason" if p["band"] != "clear" else ""))
        L.append(f"| {p['roll_no']} | {p['title']}{' with ' + p['partner'] if p['partner'] else ''} | {p['measured']} | "
                 f"{BAND[p['band']]} · {p['priority']}{mark} | {p['reason']} | {p['rank']} | {p['old_rank']} | {p['review'] or '—'} |")
    L += ["", "</details>", ""]
    return L


def write(folder: str, update_readme: bool = False, dry_run: bool | None = None) -> str:
    with open(os.path.join(folder, "pilot.json"), encoding="utf-8") as fh:
        meta = json.load(fh)
    dry = meta.get("dry_run", False) if dry_run is None else dry_run
    key = {r["roll_no"]: r for r in read_csv(os.path.join(folder, "key-SEALED.csv"))}
    results = []
    with db.tx() as con:
        for test, t in meta["tests"].items():
            d = collect(con, test, t["sitting_id"], key)
            results.append((d, summarise(d), t))
    charts_dir = folder if dry else os.path.join(ROOT, "docs", "charts")
    os.makedirs(charts_dir, exist_ok=True)
    when = dt.date.today().isoformat()
    head = (f"# FairProctor pilot — {meta['name']}" + (" (DRY RUN: simulated participants)" if dry else ""))
    L = [head, ""]
    if dry:
        L += ["**This is a rehearsal with simulated participants**, made by the same simulator that produced the training "
              "data. It only checks that the pilot kit works end to end. It says nothing about real people.", ""]
    n_ref = sum(t.get("reference_sessions", 0) for _, _, t in results)
    L += [f"{when}. Each participant followed a secret role card: honest in a hard situation (dim room, shared room, phone "
          "held low, slow connection, interruptions), or acting out malpractice (second phone, searching, sharing answers, "
          "a helper; for code: pasting from the web, copying a partner, typing from a phone). The roles stayed in a sealed "
          "list until scoring was done.", "",
          f"Scoring ran exactly as in the product, together with {n_ref} synthetic reference candidates as calibration; the "
          "numbers below count the participants only. The old rules are the frame-by-frame flags a typical proctoring tool "
          "raises (for code: any 50+ character paste or tab switch), ranked by how often they fire and given the same "
          "number of review slots as FairProctor.", ""]
    for d, s, _ in results:
        slug = "pilot-queue-" + d["test"]
        for theme, suffix in (("light", ""), ("dark", "-dark")):
            with open(os.path.join(charts_dir, slug + suffix + ".svg"), "w", encoding="utf-8") as fh:
                fh.write(queue_svg(d, theme))
        rel = (slug + ".svg") if dry else f"../docs/charts/{slug}.svg"
        L += md_test(d, s, f'<img src="{rel}" alt="{TEST_NAME[d["test"]]}: participants in queue order" width="760">')
    L += ["## What this does and does not show", "",
          "- **Small numbers.** With this many people the 95% intervals are wide; read them before the percentages.",
          "- **Acted, not real.** People knew it was a test. Real cheating can be subtler, or clumsier.",
          "- **Asked for, then measured.** Honest roles were asked to create a situation; the *Measured* column shows what the "
          "device and the pre-check actually recorded.",
          "- **Same paper as the training data.** The question test is the 30-question paper the model was trained on "
          "(synthetic data); a different paper would need fresh statistics.", ""]
    out = os.path.join(folder if dry else os.path.join(ROOT, "reports"), "PILOT_DRYRUN.md" if dry else "PILOT_RESULTS.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    if update_readme and not dry:
        _readme(results, meta)
    return out


def _readme(results, meta) -> None:
    path = os.path.join(ROOT, "README.md")
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    if MARK[0] not in text:
        raise SystemExit("README.md has no pilot section markers; add <!-- pilot:start --> and <!-- pilot:end -->.")
    L = [MARK[0], "", "## Real pilot", ""]
    for d, s, _ in results:
        L += [f"**{TEST_NAME[d['test']]}, {s['n']} people** ({s['n_cheat']} acting out malpractice): FairProctor sent "
              f"**{s['ours_any']} of {s['n_cheat']}** of them to review ({s['ours_first']} in *Review first*) and "
              f"**{s['h_ours_any']} of {s['n_honest']}** honest people; with the same number of flags the old rules caught "
              f"{s['old_any']} of {s['n_cheat']} and flagged {s['h_old_any']} of {s['n_honest']} honest. "
              f"{s['right']} of {s['ours_any']} caught cases showed the right reason.", "",
              f'<picture><source media="(prefers-color-scheme: dark)" srcset="docs/charts/pilot-queue-{d["test"]}-dark.svg">'
              f'<img alt="{TEST_NAME[d["test"]]} pilot: participants in queue order" src="docs/charts/pilot-queue-{d["test"]}.svg" width="760"></picture>', ""]
    L += [f"Small numbers, acted roles: see [`reports/PILOT_RESULTS.md`](reports/PILOT_RESULTS.md) for every participant, "
          f"the intervals and the limits. Pilot kit: [`pilot/PILOT.md`](pilot/PILOT.md).", "", MARK[1]]
    text = re.sub(re.escape(MARK[0]) + r".*?" + re.escape(MARK[1]), "\n".join(L).replace("\\", "\\\\"), text, flags=re.S)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    ap = argparse.ArgumentParser(description="Pilot results against the sealed role key.")
    ap.add_argument("--dir", required=True, help="the pilot folder made by pilot.prepare (pilot/out/<name>)")
    ap.add_argument("--update-readme", action="store_true", help="also fill the 'Real pilot' section of README.md")
    a = ap.parse_args()
    out = write(a.dir, a.update_readme)
    print(f"Written: {out}")
    with open(out, encoding="utf-8") as fh:
        print(fh.read().split("## What this does")[0])


if __name__ == "__main__":
    main()

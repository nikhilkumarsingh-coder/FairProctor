"""Fairness report for a scored sitting: are some groups of candidates sent to review more often than others?

Groups describe a candidate's circumstances, never their behaviour: connection, device, light and framing at the
pre-check, other people around on camera (a second face in at least 1% of camera checks: a shared home or a cafe),
and for coding tests the programming language. Bandwidth and device are not model inputs at all.

For every group the report gives the share sent to review
  * by FairProctor (its review bands), and
  * by the old rules: the frame-by-frame flags a typical proctoring tool raises (face missing, looking away, a second
    face, leaving the tab, paste), ranked by how often they fire and given the SAME number of review slots,
each with a 95% Wilson interval, plus the gap to the reference group with a 95% Newcombe interval.
"Honest" means: reference sessions without planted malpractice (true labels known), and real candidates a reviewer
cleared, or whom the model cleared and nobody reviewed. Confirmed cases are malpractice; flagged real candidates still
waiting for a decision are left out of the honest-only view.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter

from .. import db
from ..http import ApiError

Z = 1.959964            # 95%
MIN_N = 10              # fewer candidates than this in a group: too few to compare
OTHERS_AROUND = 0.01    # a second face in at least 1% of camera checks
MIN_FRAMES = 20         # fewer camera checks than this: no camera numbers for this candidate

LABELS = {
    "room": {"alone": "Alone on camera", "others": "Others around (shared room, cafe)"},
    "bandwidth": {"normal": "Normal connection", "low": "Low bandwidth (2G/3G)"},
    "light": {"ok": "Good light", "dim": "Dim room", "backlit": "Light behind", "bright": "Too bright"},
    "device": {"desktop": "Laptop / desktop", "phone": "Phone"},
    "framing": {"ok": "Well framed", "off_centre": "Off centre", "too_close": "Too close", "too_far": "Too far",
                "no_face": "No face found"},
    "language": {"python": "Python", "cpp": "C++", "java": "Java", "javascript": "JavaScript"},
}
DIMENSIONS = {
    "room": ("Other people around (camera)", "A second face in 1%+ of camera checks: a shared home or a cafe.", "alone"),
    "bandwidth": ("Connection", "Recorded for this report only; never a model input.", "normal"),
    "light": ("Light at the pre-check", "What the phone pre-check found before the test.", "ok"),
    "device": ("Device", "Recorded for this report only; never a model input.", "desktop"),
    "framing": ("Framing at the pre-check", "Where the face sat in the camera picture before the test.", "ok"),
    "language": ("Programming language", "The language each candidate used most.", None),
}
ORDER = {"mcq": ["room", "bandwidth", "light", "device", "framing"], "coding": ["language", "device", "bandwidth", "room"]}
OLD_RULES = {
    "mcq": "Old rules: the frame-by-frame flags a typical proctoring tool raises (face missing, looking away, a second "
           "face, leaving the tab, paste), ranked by how often they fire, given the same number of review slots as FairProctor.",
    "coding": "Old rules: a common coding-test rule (any paste of 50+ characters or any tab switch), ranked by how many "
              "times it fires, given the same number of review slots as FairProctor.",
}


def wilson(k: int, n: int) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def rate(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return dict(k=int(k), n=int(n), rate=(k / n if n else None), lo=lo, hi=hi)


def gap(a: dict, b: dict) -> dict:
    """a minus b (in share points) with Newcombe's 95% interval (hybrid score method)."""
    if not a["n"] or not b["n"]:
        return dict(diff=None, lo=None, hi=None, verdict="too_few")
    p1, p2 = a["rate"], b["rate"]
    d = p1 - p2
    lo = d - math.sqrt((p1 - a["lo"]) ** 2 + (b["hi"] - p2) ** 2)
    hi = d + math.sqrt((a["hi"] - p1) ** 2 + (p2 - b["lo"]) ** 2)
    if a["n"] < MIN_N or b["n"] < MIN_N:
        verdict = "too_few"
    else:
        verdict = "higher" if lo > 0 else "lower" if hi < 0 else "no_clear_difference"
    return dict(diff=d, lo=lo, hi=hi, verdict=verdict)


def _tiebreak(sid: str) -> str:
    return hashlib.sha1(sid.encode()).hexdigest()


def _labels(con, sitting_id: int, sessions: list[dict]) -> dict[str, str]:
    """honest | malpractice | pending for every scored session."""
    reviews = {r["session_id"]: r["decision"] for r in db.all_(con, """
        SELECT r.session_id, r.decision FROM reviews r JOIN sessions x ON x.id = r.session_id
        WHERE x.sitting_id = ? AND r.id = (SELECT MAX(r2.id) FROM reviews r2 WHERE r2.session_id = r.session_id)""", sitting_id)}
    appeals = {r["session_id"]: r["outcome"] for r in db.all_(con, """
        SELECT a.session_id, a.outcome FROM appeals a JOIN sessions x ON x.id = a.session_id
        WHERE x.sitting_id = ? AND a.status = 'decided'""", sitting_id)}
    out = {}
    for s in sessions:
        sid = s["id"]
        if s["is_synthetic"] and s["ref_truth"]:
            out[sid] = "honest" if s["ref_truth"] == "none" else "malpractice"
        elif sid in appeals:
            out[sid] = "honest" if appeals[sid] == "overturned" else "malpractice"
        elif reviews.get(sid) == "confirm":
            out[sid] = "malpractice"
        elif reviews.get(sid) == "clear" or s["band"] == "clear":
            out[sid] = "honest"
        else:
            out[sid] = "pending"
    return out


def _groups(con, sitting_id: int, kind: str, sessions: list[dict]) -> tuple[dict[str, dict[str, str]], dict[str, float]]:
    """Each session's group in every dimension, and its old-rules score."""
    frames = {r["session_id"]: r for r in db.all_(con, """
        SELECT f.session_id, COUNT(*) n,
               SUM(CASE WHEN f.faces >= 2 THEN 1 ELSE 0 END) two,
               SUM(CASE WHEN f.face_visible = 0 THEN 1 ELSE 0 END) novis,
               SUM(CASE WHEN f.gaze IN ('down', 'left', 'right', 'away') THEN 1 ELSE 0 END) away
        FROM frame_stats f JOIN sessions x ON x.id = f.session_id
        WHERE x.sitting_id = ? GROUP BY f.session_id""", sitting_id)}
    events = {r["session_id"]: r for r in db.all_(con, """
        SELECT e.session_id,
               SUM(CASE WHEN e.type = 'focus_lost' THEN 1 ELSE 0 END) focus,
               SUM(CASE WHEN e.type = 'paste' THEN 1 ELSE 0 END) pastes,
               SUM(CASE WHEN e.type = 'paste' AND e.chars >= 50 THEN 1 ELSE 0 END) big_pastes
        FROM events e JOIN sessions x ON x.id = e.session_id
        WHERE x.sitting_id = ? GROUP BY e.session_id""", sitting_id)}
    langs: dict[str, Counter] = {}
    if kind == "coding":
        for r in db.all_(con, """SELECT r.session_id, r.language, COUNT(*) n FROM code_runs r JOIN sessions x ON x.id = r.session_id
                                 WHERE x.sitting_id = ? GROUP BY r.session_id, r.language""", sitting_id):
            langs.setdefault(r["session_id"], Counter())[r["language"]] += int(r["n"])
    groups: dict[str, dict[str, str]] = {d: {} for d in ORDER[kind]}
    old: dict[str, float] = {}
    for s in sessions:
        sid = s["id"]
        f, e = frames.get(sid), events.get(sid) or {}
        focus = int(e.get("focus") or 0)
        if kind == "coding":
            old[sid] = float(int(e.get("big_pastes") or 0) + focus)
        else:
            legacy = (int(f["two"]) + int(f["novis"]) + int(f["away"])) / max(int(f["n"]), 1) if f else 0.0
            old[sid] = legacy + 0.01 * focus
        g = dict(bandwidth=s["bandwidth_class"], device=s["device"], light=s["precheck_light"], framing=s["precheck_framing"])
        if f and int(f["n"]) >= MIN_FRAMES:
            g["room"] = "others" if int(f["two"]) / int(f["n"]) >= OTHERS_AROUND else "alone"
        if sid in langs:
            g["language"] = langs[sid].most_common(1)[0][0]
        for d in groups:
            if g.get(d):
                groups[d][sid] = g[d]
    return groups, old


def report(con, sitting_id: int) -> dict:
    sit = db.one(con, """SELECT s.id, s.title, s.status, s.scored_at, t.kind FROM sittings s JOIN tests t ON t.id = s.test_id
                         WHERE s.id = ?""", sitting_id)
    if not sit:
        raise ApiError(404, "not_found", "Sitting not found.")
    kind = sit["kind"] if sit["kind"] in ORDER else "mcq"
    head = dict(sitting=dict(id=sit["id"], title=sit["title"], status=sit["status"], kind=kind, scored_at=sit["scored_at"]),
                old_rules=OLD_RULES[kind])
    sessions = db.all_(con, """SELECT x.id, x.device, x.bandwidth_class, x.precheck_light, x.precheck_framing, x.is_synthetic,
                                      x.ref_truth, c.band
                               FROM scores c JOIN sessions x ON x.id = c.session_id WHERE c.sitting_id = ?""", sitting_id)
    if not sessions:
        return dict(head, ready=False, n=0)
    labels = _labels(con, sitting_id, sessions)
    groups, old = _groups(con, sitting_id, kind, sessions)
    ids = [s["id"] for s in sessions]
    band = {s["id"]: s["band"] for s in sessions}
    # who each system sends to review, at each level; the old rules get as many review slots as FairProctor used
    ranked_old = sorted(ids, key=lambda sid: (-old[sid], _tiebreak(sid)))
    flagged: dict[str, dict[str, set[str]]] = {}
    for level, bands in (("any", ("review_first", "review")), ("first", ("review_first",))):
        ours = {sid for sid in ids if band[sid] in bands}
        flagged[level] = dict(ours=ours, old=set(ranked_old[:len(ours)]))
    count = Counter(labels.values())
    views = {}
    for pop in ("honest", "all"):
        members = [sid for sid in ids if pop == "all" or labels[sid] == "honest"]
        for level in ("any", "first"):
            views[f"{pop}.{level}"] = _view(kind, members, groups, flagged[level])
    return dict(head, ready=True, n=len(ids),
                labels=dict(honest=count["honest"], malpractice=count["malpractice"], pending=count["pending"],
                            reference=sum(1 for s in sessions if s["is_synthetic"])),
                workload={lv: dict(n=len(flagged[lv]["ours"]), share=len(flagged[lv]["ours"]) / len(ids)) for lv in flagged},
                views=views)


def _view(kind: str, members: list[str], groups: dict, flagged: dict) -> dict:
    def cell(sids):
        return {sys_: rate(sum(1 for s in sids if s in flagged[sys_]), len(sids)) for sys_ in ("ours", "old")}

    dims, skipped = [], []
    largest: dict[str, dict | None] = dict(ours=None, old=None)
    for key in ORDER[kind]:
        title, note, ref = DIMENSIONS[key]
        by: dict[str, list[str]] = {}
        for sid in members:
            g = groups[key].get(sid)
            if g:
                by.setdefault(g, []).append(sid)
        if len(by) < 2:
            if key != "room" or by:         # no camera numbers at all (e.g. coding demo): say nothing
                only = next(iter(by), None)
                skipped.append(dict(key=key, title=title, reason=f"Everyone was in one group ({LABELS[key].get(only, only)})."
                                    if only else "No data for this sitting."))
            continue
        order = list(LABELS[key]) + sorted(g for g in by if g not in LABELS[key])
        reference = ref if ref in by else max(by, key=lambda g: len(by[g]))
        cells = {g: cell(by[g]) for g in by}
        rows = []
        for g in sorted(by, key=lambda g: (g != reference, order.index(g) if g in order else 99)):
            row = dict(key=g, label=LABELS[key].get(g, g.replace("_", " ").capitalize()), n=len(by[g]), reference=g == reference,
                       ours=cells[g]["ours"], old=cells[g]["old"])
            if g != reference:
                row["gap"] = {s: gap(cells[g][s], cells[reference][s]) for s in ("ours", "old")}
                for s in ("ours", "old"):          # the biggest EXTRA flagging of a group (a disadvantage)
                    gp = row["gap"][s]
                    if gp["diff"] is None or gp["verdict"] == "too_few" or gp["diff"] <= 0:
                        continue
                    if largest[s] is None or gp["diff"] > largest[s]["diff"]:
                        largest[s] = dict(gp, dimension=title, group=row["label"],
                                          reference=LABELS[key].get(reference, reference))
            rows.append(row)
        dims.append(dict(key=key, title=title, note=note, groups=rows))
    return dict(n=len(members), overall=cell(members), dimensions=dims, skipped=skipped, largest=largest)

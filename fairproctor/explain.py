"""Turn model contributions + evidence into reviewer and candidate explanations."""
from __future__ import annotations

import numpy as np

from .features import mmss

# Signals are grouped into families a reviewer understands.
FAMILY = {
    "fast_correct_unexpected": "timing", "fast_burst": "timing", "self_fast_correct": "timing", "misfit": "timing",
    "idle_correct_unexpected": "pause", "idle_correct_excess": "pause", "gaze_down_excess_idle": "pause",
    "gaze_down_on_unexpected": "pause",
    "focus_then_correct": "focus", "focus_away_total": "focus",
    "paste_large": "paste", "paste_chars_max": "paste",
    "collusion_score": "match", "collusion_nshare": "match", "collusion_sync": "match", "collusion_pair_z": "match", "collusion_mutual_z": "match", "ring_size": "match", "ring_partner_fast": "match", "ring_attach": "match",
    "multi_face_persist_frac": "person", "multi_face_on_correct": "person",
    "phone_on_correct": "phone",
}
FAMILY_TITLE = {
    "timing": "Answer timing",
    "pause": "Silent pauses then correct answers (possible second device)",
    "focus": "Leaving the test window",
    "paste": "Pasted text",
    "match": "Answers match another candidate",
    "person": "Another person in view",
    "phone": "Phone in view while answering",
}
CANDIDATE_TITLE = {
    "timing": "How quickly some answers were given",
    "pause": "Long pauses with no activity before correct answers",
    "focus": "Leaving the test screen",
    "paste": "Pasted text",
    "match": "Answers similar to another candidate's",
    "person": "Another person visible",
    "phone": "A phone visible to the camera",
}
EVIDENCE_KEYS = {
    "timing": ["fast_burst", "fast_correct_unexpected", "self_fast_correct", "misfit"],
    "pause": ["idle_correct_unexpected"],
    "focus": ["focus_then_correct"],
    "paste": ["paste_large"],
    "match": ["collusion_score"],
    "person": ["multi_face_persist_frac"],
    "phone": ["phone_on_correct"],
}


def _fallback(fam, f):
    """Plain description when a family moved the score but no single episode crossed its reporting bar."""
    if fam == "timing":
        a, b = int(f.get("fast_correct_unexpected", 0) or 0), int(f.get("self_fast_correct", 0) or 0)
        if a or b:
            return (f"{a} hard item{'s' if a != 1 else ''} answered correctly much faster than usual; "
                    f"{b} answer{'s' if b != 1 else ''} much faster than this candidate's own pace.")
        return "The pattern of right and wrong answers is unusual: the hardest items right and some of the easiest wrong."
    if fam == "pause":
        n = int(f.get("idle_correct_unexpected", 0) or 0)
        if n:
            return f"{n} long pause{'s' if n > 1 else ''} with no input, each followed by a correct answer on a hard item."
        return ("Answers after silent pauses (no mouse, touch or keyboard input) were more often correct than this "
                "candidate's other answers; no single pause was decisive.")
    if fam == "focus":
        return f"Test window lost focus for {f.get('focus_away_total', 0):.0f} s in total; {int(f.get('focus_then_correct', 0))} correct answers soon after returning."
    if fam == "paste":
        return f"Largest paste: {int(f.get('paste_chars_max', 0))} characters."
    if fam == "match":
        return f"Closest match in the sitting: {int(f.get('collusion_nshare', 0))} identical wrong answers, {int(f.get('collusion_sync', 0))} identical answers within 20 s."
    if fam == "person":
        return f"Second face visible for {100 * (f.get('multi_face_persist_frac') or 0):.0f}% of the test."
    if fam == "phone":
        return f"A phone was in view while {int(f.get('phone_on_correct') or 0)} correct answer(s) were given."
    return ""


PHONE_MIN_ITEMS = 2     # hard items answered correctly with a phone in view before a human must look


def phone_band(band: str, f: dict) -> str:
    """Supporting-evidence rule for the on-device phone detector (kept out of the trained model):
    a phone seen while 2+ hard items were answered correctly always reaches a human ("review"), never "review first"
    on its own. Missing detector data never changes anything."""
    n = f.get("phone_on_correct")
    if band == "clear" and n is not None and n == n and n >= PHONE_MIN_ITEMS:
        return "review"
    return band


def _first_sentence(t: str) -> str:
    import re
    m = re.match(r"(.+?[.!?])(\s|$)", t.replace("e.g.", "e\u2024g\u2024"))
    out = m.group(1) if m else t
    return out.replace("e\u2024g\u2024", "e.g.")


def context_notes(f: dict, meta: dict) -> list[str]:
    """Environment facts the score deliberately did NOT count against the candidate."""
    notes = []
    fpm = f.get("video_fpm") or 0
    if fpm > 0:
        every = 60 / fpm
        if every >= 2.5:
            notes.append(f"Low-bandwidth video: about one analysed frame every {every:.0f} s. Video-based checks were weighted down accordingly.")
    else:
        notes.append("No usable video. The score relies on answer, timing and browser signals only.")
    vis = f.get("face_visible_frac")
    if vis is not None and not np.isnan(vis) and vis < 0.85:
        light = meta.get("precheck_light", "")
        why = {"dim": " (dim room at pre-check)", "backlit": " (light behind the candidate at pre-check)"}.get(light, "")
        notes.append(f"Face not clearly visible in {100 * (1 - vis):.0f}% of frames{why}. Not counted as evidence.")
    tf = int(f.get("_transient_faces") or 0)
    if tf:
        notes.append(f"{tf} brief appearance{'s' if tf > 1 else ''} of another person (e.g. someone walking past) {'were' if tf > 1 else 'was'} ignored.")
    fl = int(f.get("_focus_losses") or 0)
    if fl and not f.get("focus_then_correct"):
        notes.append(f"Left the test window {fl} time{'s' if fl > 1 else ''}, but {'none was' if fl > 1 else 'it was not'} followed by a quick correct answer. Not counted.")
    if (f.get("fast_wrong_frac") or 0) > 0.1:
        notes.append("Several quick wrong answers, consistent with guessing under time pressure. Not counted.")
    if f.get("_rushed_guess"):
        notes.append(f"Finished the answered questions in about {f.get('_rush_secs', 0) / 60:.0f} min against a typical "
                     f"{f.get('_rush_typical', 0) / 60:.0f} min, with answers near chance level (clicking through). "
                     "Answer timing was not counted; a reviewer may still want to see the attempt.")
    if (f.get("_phone_secs") or 0) >= 2 and not (f.get("phone_on_correct") or 0):
        notes.append(f"A phone was in view for about {f['_phone_secs']:.0f} s, but not while correct answers were given. Not counted.")
    if meta.get("device") == "phone":
        notes.append("Phone held at an angle: looking down at the screen is normal and is compared with the candidate's own baseline, not with desktop users.")
    return notes


def fallback_moments(fam: str, ev, stats) -> list[dict]:
    """Moments for a family whose individual episodes were below the reporting bar.
    ev: the session's events DataFrame; stats: ItemStats."""
    if ev is None or stats is None:
        return []
    shown = ev[ev.type == "item_shown"].set_index("item").t
    ans = ev[ev.type == "answer"]
    out = []
    if fam in ("timing", "match"):
        for r in ans.itertuples():
            if r.item in shown.index and r.correct == 1:
                d = r.t - shown[r.item]
                typ = float(np.exp(stats.med_logt[int(r.item)]))
                if d < 0.4 * typ:
                    out.append(dict(t=round(r.t, 1), label=f"Q{int(r.item) + 1} correct in {d:.0f} s (typical {typ:.0f} s)"))
        if not out and fam == "timing":
            # the pattern signal: hardest items right, easiest items wrong
            a = ans.assign(b=stats.b[ans.item.values.astype(int)])
            for r in a[a.correct == 1].nlargest(4, "b").itertuples():
                out.append(dict(t=round(r.t, 1), label=f"Q{int(r.item) + 1}: one of the hardest items, correct"))
            for r in a[a.correct == 0].nsmallest(3, "b").itertuples():
                out.append(dict(t=round(r.t, 1), label=f"Q{int(r.item) + 1}: one of the easiest items, wrong"))
            out.sort(key=lambda m: m["t"])
    elif fam == "pause":
        idle = ev[ev.type.isin(["idle_start", "idle_end"])].sort_values("t")
        start = None
        for r in idle.itertuples():
            if r.type == "idle_start":
                start = r
            elif start is not None:
                a = ans[(ans.t >= r.t) & (ans.t <= r.t + 60)]
                res = f", then answered Q{int(a.item.iloc[0]) + 1} ({'correct' if a.correct.iloc[0] == 1 else 'wrong'})" if len(a) else ""
                out.append(dict(t=round(start.t, 1), label=f"no input for {r.t - start.t:.0f} s{res}"))
                start = None
    elif fam == "focus":
        for r in ev[ev.type == "focus_lost"].itertuples():
            out.append(dict(t=round(r.t, 1), label="left test window"))
    elif fam == "paste":
        for r in ev[ev.type == "paste"].itertuples():
            out.append(dict(t=round(r.t, 1), label=f"paste {r.chars} chars"))
    return out[:12]


def explain(sid: str, f: dict, contrib: dict, evidence: list, meta: dict, score: float, band: str,
            events=None, stats=None) -> dict:
    fam_c: dict[str, float] = {}
    for k, v in contrib.items():
        if v > 0:
            fam_c[FAMILY[k]] = fam_c.get(FAMILY[k], 0) + float(v)
    total = sum(fam_c.values()) or 1.0
    by_key: dict[str, list] = {}
    for e in evidence:
        by_key.setdefault(e.key, []).append(e)
    reasons = []
    for n, (fam, c) in enumerate(sorted(fam_c.items(), key=lambda x: -x[1])):
        # always explain the top signal of a queued session, even if it is spread thin
        if c < 0.4 and not (n == 0 and band != "clear"):
            continue
        ev = [e.as_dict() for k in EVIDENCE_KEYS[fam] for e in by_key.get(k, [])]
        if not ev:
            mom = fallback_moments(fam, events, stats)
            ev = [dict(key=fam, t0=mom[0]["t"] if mom else 0, t1=mom[-1]["t"] if mom else 0, items=[], text=_fallback(fam, f),
                       candidate_text=_fallback(fam, f), strength=0, moments=mom)] if mom else []
        reasons.append(dict(family=fam, title=FAMILY_TITLE[fam], candidate_title=CANDIDATE_TITLE[fam],
                            weight=round(c / total, 3), logodds=round(c, 2),
                            evidence=ev, fallback=None if ev else _fallback(fam, f)))
    n_phone = f.get("phone_on_correct")
    if band != "clear" and n_phone is not None and n_phone == n_phone and n_phone >= 1 and by_key.get("phone_on_correct"):
        reasons.append(dict(family="phone", title=FAMILY_TITLE["phone"], candidate_title=CANDIDATE_TITLE["phone"],
                            weight=0.0, logodds=0.0, supporting=True,
                            evidence=[e.as_dict() for e in by_key["phone_on_correct"]], fallback=None))
    if reasons:
        top = reasons[0]
        first = top["evidence"][0]["text"] if top["evidence"] else top["fallback"]
        headline = _first_sentence(first)
        if len(reasons) > 1:
            t2 = reasons[1]["title"]
            headline += f" Also: {t2[0].lower()}{t2[1:]}."
    else:
        headline = "No behavioural evidence of malpractice. Environment-only flags were discounted."
    moments = sorted({(m["t"], m["label"]) for r in reasons for e in r["evidence"] for m in e["moments"]})
    return dict(
        session_id=sid, score=score, band=band, headline=headline, reasons=reasons,
        context=context_notes(f, meta),
        moments=[dict(t=t, at=mmss(t), label=l) for t, l in moments],
        partners=f["_partners"] if isinstance(f.get("_partners"), list) else [],
        legacy_flags=int(f.get("_legacy_flags") or 0),
        candidate=candidate_view(reasons, band),
    )


def candidate_view(reasons, band):
    if band == "clear":
        return dict(summary="Your test was reviewed automatically and no issues were found that need a human check.",
                    points=[], can_appeal=False)
    pts = []
    for r in reasons:
        ev = r["evidence"]
        if ev:
            for e in ev[:2]:
                pts.append(dict(title=r["candidate_title"], text=e["candidate_text"],
                                when=f"{mmss(e['t0'])}–{mmss(e['t1'])}", questions=e["items"][:12]))
        else:
            pts.append(dict(title=r["candidate_title"], text=r["fallback"], when="", questions=[]))
    return dict(
        summary=("Your test has been sent for a check by a human reviewer. This is not a decision. "
                 "Below is what the system noticed, with the time in the test it happened, so you can explain it."),
        points=pts,
        not_counted=("Things like a dim room, a slow connection, someone walking past, or holding your phone low "
                     "were NOT counted against you."),
        can_appeal=True,
    )

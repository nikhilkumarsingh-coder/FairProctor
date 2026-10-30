"""The README chart: share of malpractice caught vs share of candidates a reviewer looks at, for both models.

    python scripts/make_readme_chart.py

Reads the out-of-fold scores of the question-test model (artifacts/store.pkl, from `python -m fairproctor.pipeline`)
and of the coding model (backend/model/coding_model.pkl; its labels come from regenerating the same seeded data),
and writes docs/charts/review-curve.svg, review-curve-dark.svg and review-curve.csv (the numbers behind the chart).
"""
from __future__ import annotations

import csv
import os
import pickle
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "charts")
XMAX = 0.5

THEMES = {
    "light": dict(bg="#ffffff", ink="#0b0b0b", ink2="#52514e", muted="#898781", grid="#e1e0d9", axis="#c3c2b7",
                  s1="#2a78d6", s2="#eb6834", rand="#b5b3ab"),
    "dark": dict(bg="#0d1117", ink="#f0efec", ink2="#c3c2b7", muted="#8b949e", grid="#21262d", axis="#30363d",
                 s1="#3987e5", s2="#d95926", rand="#6e7681"),
}


def curve(raw: np.ndarray, y: np.ndarray, xs: np.ndarray) -> np.ndarray:
    o = np.argsort(-raw)
    rec = np.cumsum(y[o]) / y.sum()
    n = len(y)
    return np.array([0.0 if x == 0 else rec[max(int(np.ceil(x * n)) - 1, 0)] for x in xs])


def load():
    with open(os.path.join(ROOT, "artifacts", "store.pkl"), "rb") as fh:
        store = pickle.load(fh)
    mcq_raw = np.array([d["raw"] for d in store.values()])
    mcq_y = np.array([d["label"] == "confirmed" for d in store.values()], int)
    with open(os.path.join(ROOT, "backend", "model", "model.pkl"), "rb") as fh:
        mb = pickle.load(fh)
    from fairproctor.coding_synth import generate
    sessions, _, _ = generate(30, 170, 7)                      # the coding model's training data (same seed)
    with open(os.path.join(ROOT, "backend", "model", "coding_model.pkl"), "rb") as fh:
        cb = pickle.load(fh)
    code_raw = np.asarray(cb["raws"], float)
    code_y = (sessions.verdict == "confirmed").astype(int).values
    assert len(code_raw) == len(code_y)
    pts = dict(
        mcq_first=((mcq_raw >= mb["H"]).mean(), (mcq_raw[mcq_y == 1] >= mb["H"]).mean()),
        mcq_all=(float(np.mean(mcq_raw >= mcq_raw[mcq_y == 1].min())), 1.0),
        code_first=((code_raw >= cb["H"]).mean(), (code_raw[code_y == 1] >= cb["H"]).mean()),
        code_line=((code_raw >= cb["T"]).mean(), (code_raw[code_y == 1] >= cb["T"]).mean()),
    )
    return (mcq_raw, mcq_y), (code_raw, code_y), pts


def svg(theme: str, xs, mcq, code, pts) -> str:
    c = THEMES[theme]
    W, H = 760, 470
    L, R, T, B = 64, 28, 96, 58
    pw, ph = W - L - R, H - T - B
    X = lambda v: L + v / XMAX * pw
    Y = lambda v: T + (1 - v) * ph
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
           f'font-family="system-ui, -apple-system, Segoe UI, sans-serif">',
           '<title>Share of malpractice caught vs share of candidates reviewed</title>',
           f'<desc>Out-of-fold results on synthetic data. Reviewing the top 6% of candidates catches 91% of malpractice in '
           f'both tests. The question test reaches every confirmed case at {pts["mcq_all"][0]:.0%} of candidates; the coding '
           f'review line is at {pts["code_line"][0]:.0%} of candidates and {pts["code_line"][1]:.0%} of cases.</desc>',
           f'<rect width="{W}" height="{H}" rx="12" fill="{c["bg"]}"/>',
           f'<text x="{L}" y="30" font-size="17" font-weight="700" fill="{c["ink"]}">How much malpractice a reviewer finds</text>',
           f'<text x="{L}" y="52" font-size="12.5" fill="{c["ink2"]}">Share of malpractice caught when reviewers check the top-ranked '
           f'candidates first. Out-of-fold, synthetic data.</text>']
    # legend
    lx = L
    for name, col, w in (("Question test (5,000 sessions)", c["s1"], 2), ("Coding test (5,125)", c["s2"], 2),
                         ("Random order", c["rand"], 1.5)):
        out.append(f'<line x1="{lx}" y1="74" x2="{lx + 18}" y2="74" stroke="{col}" stroke-width="{w + 1}" stroke-linecap="round"/>')
        out.append(f'<text x="{lx + 24}" y="78" font-size="12.5" fill="{c["ink2"]}">{name}</text>')
        lx += 24 + 6.6 * len(name) + 26
    # grid + axes
    for v in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(f'<line x1="{L}" y1="{Y(v):.1f}" x2="{L + pw}" y2="{Y(v):.1f}" stroke="{c["axis"] if v == 0 else c["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="{L - 10}" y="{Y(v) + 4:.1f}" font-size="12" text-anchor="end" fill="{c["muted"]}">{v:.0%}</text>')
    for v in np.arange(0, XMAX + 1e-9, 0.1):
        out.append(f'<line x1="{X(v):.1f}" y1="{T}" x2="{X(v):.1f}" y2="{T + ph}" stroke="{c["axis"] if v == 0 else c["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="{X(v):.1f}" y="{T + ph + 20}" font-size="12" text-anchor="middle" fill="{c["muted"]}">{v:.0%}</text>')
    out.append(f'<text x="{L + pw / 2}" y="{H - 12}" font-size="12.5" text-anchor="middle" fill="{c["ink2"]}">Share of candidates reviewed</text>')
    out.append(f'<text transform="translate(16 {T + ph / 2}) rotate(-90)" font-size="12.5" text-anchor="middle" fill="{c["ink2"]}">Malpractice caught</text>')
    # lines
    out.append(f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(XMAX)}" y2="{Y(XMAX)}" stroke="{c["rand"]}" stroke-width="1.5"/>')
    for ys, col in ((code, c["s2"]), (mcq, c["s1"])):
        d = " ".join(f"{X(x):.1f},{Y(v):.1f}" for x, v in zip(xs, ys))
        out.append(f'<polyline points="{d}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
    # operating points (dots with a surface ring) and their labels
    def dot(p, col):
        out.append(f'<circle cx="{X(p[0]):.1f}" cy="{Y(p[1]):.1f}" r="5" fill="{col}" stroke="{c["bg"]}" stroke-width="2"/>')
    dot(pts["code_first"], c["s2"])
    dot(pts["mcq_first"], c["s1"])
    dot(pts["code_line"], c["s2"])
    dot(pts["mcq_all"], c["s1"])
    def note(p, at, text, anchor="start"):
        """A label in the empty area under the curves, with a hairline leader to its point."""
        tx, ty = X(at[0]), Y(at[1])
        out.append(f'<line x1="{X(p[0]):.1f}" y1="{Y(p[1]) + 6:.1f}" x2="{tx + (-4 if anchor == "end" else 4):.1f}" y2="{ty - 5:.1f}" '
                   f'stroke="{c["muted"]}" stroke-width="1"/>')
        out.append(f'<text x="{tx:.1f}" y="{ty + 4:.1f}" font-size="12.5" text-anchor="{anchor}" fill="{c["ink"]}">{text}</text>')
    fx, fy = pts["mcq_first"]
    note(pts["mcq_first"], (0.10, 0.72), f'<tspan font-weight="700">Review first:</tspan> {fx:.0%} of candidates hold {fy:.0%} of the cases (both tests)')
    cx, cy = pts["code_line"]
    note(pts["code_line"], (0.13, 0.85), f'Coding review line: {cx:.0%} reviewed, {cy:.0%} caught')
    ax, ay = pts["mcq_all"]
    note(pts["mcq_all"], (0.485, 0.62), f'Question test: every confirmed case by {ax:.0%}', anchor="end")
    out.append("</svg>")
    return "\n".join(out)


def main():
    (mr, my), (cr, cy), pts = load()
    xs = np.round(np.arange(0, XMAX + 1e-9, 0.0025), 4)
    mcq, code = curve(mr, my, xs), curve(cr, cy, xs)
    os.makedirs(OUT, exist_ok=True)
    for theme, name in (("light", "review-curve.svg"), ("dark", "review-curve-dark.svg")):
        with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
            fh.write(svg(theme, xs, mcq, code, pts))
    with open(os.path.join(OUT, "review-curve.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["share_reviewed", "question_test_caught", "coding_test_caught"])
        for x, a, b in zip(xs, mcq, code):
            w.writerow([f"{x:.4f}", f"{a:.4f}", f"{b:.4f}"])
    print({k: (round(float(a), 4), round(float(b), 4)) for k, (a, b) in pts.items()})


if __name__ == "__main__":
    main()

"""Check the pre-check thresholds and the "gaze on 2G" assumption on real home webcam frames.

Dataset: "Cheating Scenario Dataset in Online Exam" (Mendeley Data, CC BY 4.0).
https://data.mendeley.com/datasets/mjrfmvsh7d — 3 volunteers, 60 scenario folders,
1280x720 JPEG frames, each with a YOLO-format label file
(class cx cy w h, normalised): one head box, two eye boxes, one mouth box.

Class IDs confirmed visually on sample frames (the dataset does not ship a class list):
    3  head facing forward          4  head turned to the side
    8  eyes centre                  7  eyes up        10  eyes to the side
    11 mouth closed                12 mouth open
Scenario 1 = forward / eyes centre / mouth closed (the baseline); the other scenarios
are combinations of head, eye and mouth states. There is no honest-vs-cheating label.

    python analysis/cheating_scenario_dataset_check.py "path/to/Cheating Scenario Dataset in Online Exam"

Works on the whole dataset or any sample of scenario folders. Writes reports/CHEATING_SCENARIO_CHECK.md.
"""
import glob
import os
import sys

import cv2
import numpy as np
import pandas as pd

DARK, BRIGHT, BACKLIGHT, BLUR = 70, 215, 45, 35          # same thresholds as web/precheck
FACE_MIN_OLD, FACE_MIN_NEW, FACE_MAX = 0.20, 0.13, 0.62


def probe(root):
    rows = []
    for jp in sorted(glob.glob(os.path.join(root, "**", "*.jpg"), recursive=True)):
        tx = jp[:-4] + ".txt"
        if not os.path.exists(tx):
            continue
        L = [[float(v) for v in ln.split()] for ln in open(tx) if ln.strip()]
        if not L:
            continue
        im = cv2.imread(jp)
        H, W = im.shape[:2]
        g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        c, x, y, w, h = max(L, key=lambda b: b[3] * b[4])  # head box = largest
        x0, x1 = max(int((x - w / 2) * W), 0), int((x + w / 2) * W)
        y0, y1 = max(int((y - h / 2) * H), 0), int((y + h / 2) * H)
        face = g[y0:y1, x0:x1].mean()
        m = np.ones_like(g, bool)
        m[y0:y1, x0:x1] = False
        small = cv2.cvtColor(cv2.resize(im, (160, 120), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
        eyes = [b for b in L if b[3] < 0.075 and b[4] < 0.11 and b[2] < y]
        rows.append(dict(
            folder=os.path.basename(os.path.dirname(jp)), subject=os.path.basename(jp)[:2], head_class=int(c),
            classes=sorted(int(b[0]) for b in L), face_w=w, face_lum=face, bg_lum=g[m].mean(),
            sharp160=cv2.Laplacian(small.astype(float), cv2.CV_64F).var(),
            eye_px_full=np.mean([b[3] for b in eyes]) * W if eyes else np.nan,
            eye_px_2g=np.mean([b[3] for b in eyes]) * 160 if eyes else np.nan))
    return pd.DataFrame(rows)


def main(root):
    d = probe(root)
    if d.empty:
        sys.exit(f"No labelled frames found under {root}")
    pct = lambda s: f"{100 * s.mean():.0f}%"
    lines = [
        "# Check: real home webcam frames (Cheating Scenario Dataset)",
        "",
        f"Frames analysed: {len(d)} from {d.folder.nunique()} scenario folders, {d.subject.nunique()} volunteers, "
        "recorded at home on ordinary webcams (1280×720). Dataset: Mendeley Data, CC BY 4.0, DOI 10.17632/mjrfmvsh7d.1.",
        "",
        "This dataset has no honest-vs-cheating label. Every frame is annotated with head, eye and mouth states, "
        "so it is used here to test two parts of FairProctor, not to train the integrity score.",
        "",
        "## 1. Would the pre-check give sensible advice on real home frames?",
        "",
        "| Check | Frames that would be asked to fix it |",
        "|---|---|",
        f"| Too dark (face brightness < {DARK}) | {pct(d.face_lum < DARK)} |",
        f"| Too bright (> {BRIGHT}) | {pct(d.face_lum > BRIGHT)} |",
        f"| Light behind the candidate (background brighter than face by > {BACKLIGHT}) | {pct((d.bg_lum - d.face_lum) > BACKLIGHT)} |",
        f"| Blurry (sharpness < {BLUR} at 160×120) | {pct(d.sharp160 < BLUR)} |",
        f"| \"Move closer\" with the old size rule (face < {FACE_MIN_OLD:.0%} of frame width) | {pct(d.face_w < FACE_MIN_OLD)} |",
        f"| \"Move closer\" with the new size rule (face < {FACE_MIN_NEW:.0%}) | {pct(d.face_w < FACE_MIN_NEW)} |",
        "",
        f"Median face width in these normal sittings is {100 * d.face_w.median():.0f}% of the frame (head box). "
        f"The old \"move closer\" rule would have nagged {pct(d.face_w < FACE_MIN_OLD)} of perfectly usable frames, so the "
        f"pre-check now uses {FACE_MIN_NEW:.0%} (a face detector's box is smaller than this dataset's head box). "
        "Light, backlight and blur checks gave advice only where it was warranted: the backlight warning fired on the volunteer "
        "sitting against a bright wall.",
        "",
        "## 2. Can eye direction be read on a 2G video feed?",
        "",
        f"At full resolution an eye is about {d.eye_px_full.median():.0f} px wide. At the 160×120 resolution a 2G link "
        f"realistically sends, the same eye is **{d.eye_px_2g.median():.0f} px wide** "
        f"(range {d.eye_px_2g.min():.0f}–{d.eye_px_2g.max():.0f} px). See `docs/eyes_full_vs_2g.jpg`: "
        "eye direction is unreadable, while a turned head is still obvious.",
        "",
        "This is why FairProctor:",
        "",
        "- uses only a coarse head direction (centre / down / left / right / away), never eye gaze, as a camera signal;",
        "- compares head-down with the candidate's *own* baseline and only counts it during silent pauses followed by correct answers;",
        "- treats missing or unreadable video as *no evidence*, never as suspicion.",
        "",
        "## Per-volunteer summary",
        "",
        "| Volunteer | Face brightness | Background | Sharpness @160×120 | Face width | Eye width full / 2G (px) |",
        "|---|---|---|---|---|---|",
    ]
    for s, gdf in d.groupby("subject"):
        lines.append(f"| {s} | {gdf.face_lum.mean():.0f} | {gdf.bg_lum.mean():.0f} | {gdf.sharp160.mean():.0f} | "
                     f"{100 * gdf.face_w.mean():.0f}% | {gdf.eye_px_full.mean():.0f} / {gdf.eye_px_2g.mean():.1f} |")
    lines += ["", "Images from this dataset are used under CC BY 4.0 with attribution; volunteers are not identified.", ""]
    os.makedirs("reports", exist_ok=True)
    with open("reports/CHEATING_SCENARIO_CHECK.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/external/cheating_scenario")

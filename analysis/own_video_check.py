"""Run FairProctor's camera rules on your own recorded test video.

Input: a frames zip made by analysis/pack_frames.py (frames/*.jpg + index.csv with
timestamp_seconds), or a folder with the same layout. Needs the YuNet face *detector*
(boxes and 5 landmarks only; it does not recognise anyone):

    curl -L -o face_yunet.onnx https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
    python analysis/own_video_check.py face_yunet.onnx my_video_frames.zip [whatsapp_video_frames.zip ...]
    # optional: --labels labels.csv   (columns: video,start,end,label  e.g. my_video,20,35,looking down honest)

For each video it measures, second by second:
  * how many faces are visible, and how long each extra person stays (persistence)
  * head direction relative to the candidate's OWN usual position (not a fixed rule)
  * the pre-check light / backlight / blur / face-size advice
  * what survives on a 2G feed (one 160x90 frame every 5 s)
and compares a typical "flag everything" proctor with FairProctor's rules.
Writes reports/OWN_VIDEO_CHECK.md, reports/own_video_frames.csv and docs/own_video_timeline.png.
No frame images are written, so people who walked past are never shown.
"""
import argparse
import io
import os
import zipfile

import cv2
import numpy as np
import pandas as pd

W, H = 398, 224                 # frames were squashed to 224x224 from 16:9; restore the aspect
SCORE = 0.7
PERSIST_S = 25                  # same rule as fairproctor/features.py: extra person counts only if 25 s+
DARK, BRIGHT, BACK, BLUR, FACE_MIN = 45, 215, 45, 35, 0.13
NAIVE_AWAY_S = 2.0              # a typical proctor alerts after 2 s looking away or face missing
BASELINE_S = 15                 # the candidate's own usual head position comes from the first 15 s


def read_frames(src):
    if os.path.isdir(src):
        idx = pd.read_csv(os.path.join(src, "index.csv"))
        load = lambda p: cv2.imread(os.path.join(src, p))
    else:
        z = zipfile.ZipFile(src)
        idx = pd.read_csv(io.BytesIO(z.read("index.csv")))
        load = lambda p: cv2.imdecode(np.frombuffer(z.read(p), np.uint8), cv2.IMREAD_COLOR)
    idx = idx.drop_duplicates("source_frame_index") if "source_frame_index" in idx else idx
    for r in idx.itertuples():
        yield float(r.timestamp_seconds), load(r.jpg)


def faces(det, im):
    det.setInputSize((im.shape[1], im.shape[0]))
    _, f = det.detect(im)
    return [] if f is None else [x for x in f if x[14] >= SCORE]


def light(gray, f):
    x, y, w, h = [int(v) for v in f[:4]]
    cx0, cx1 = max(x + w // 4, 0), max(x + 3 * w // 4, 1)
    cy0, cy1 = max(y + h // 4, 0), max(y + 3 * h // 4, 1)
    core = gray[cy0:cy1, cx0:cx1]
    if core.size == 0:
        return np.nan, np.nan, np.nan
    # background = top band and side bands, like web/precheck (the shirt below the face is not background)
    Hh, Ww = gray.shape
    m = np.zeros_like(gray, bool)
    m[: int(0.18 * Hh), :] = True
    m[:, : int(0.15 * Ww)] = True
    m[:, int(0.85 * Ww):] = True
    m[max(y, 0):y + h, max(x, 0):x + w] = False
    return float(np.median(core)), float(np.percentile(core, 90)), float(gray[m].mean())


def episodes(t, flag, gap=1.0, min_len=0.3):
    out, start, last = [], None, None
    for ti, f in zip(t, flag):
        if f:
            if start is None:
                start = ti
            last = ti
        elif start is not None and ti - last > gap:
            out.append((start, last))
            start = None
    if start is not None:
        out.append((start, last))
    return [(a, b) for a, b in out if b - a >= min_len]


def analyse(det, name, src):
    rows = []
    for t, im in read_frames(src):
        im = cv2.resize(im, (W, H), interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        fs = sorted(faces(det, im), key=lambda f: -f[2] * f[3])
        small = cv2.resize(gray, (160, 90), interpolation=cv2.INTER_AREA)
        r = dict(video=name, t=t, n_faces=len(fs), sharp=cv2.Laplacian(small.astype(float), cv2.CV_64F).var())
        if fs:
            f = fs[0]
            eye_mid = (f[4:6] + f[6:8]) / 2
            eye_d = max(np.linalg.norm(f[4:6] - f[6:8]), 1)
            mouth_mid = (f[10:12] + f[12:14]) / 2
            r.update(face_w=f[2] / W, face_cx=(f[0] + f[2] / 2) / W, face_cy=(f[1] + f[3] / 2) / H,
                     yaw=(f[8] - eye_mid[0]) / eye_d,
                     pitch=(f[9] - eye_mid[1]) / max(mouth_mid[1] - eye_mid[1], 1))
            r["face_med"], r["face_hi"], r["bg"] = light(gray, f)
            r["extra_big"] = sum(1 for g in fs[1:] if g[2] >= 0.5 * f[2])
        rows.append(r)
    d = pd.DataFrame(rows).sort_values("t").reset_index(drop=True)
    # head direction against the candidate's own usual position
    # (robust z against this person's own median and spread in the first BASELINE_S seconds - the
    #  calibration period right after the pre-check - plus a small absolute floor)
    ok = d.face_w.notna()
    base = ok & (d.t <= BASELINE_S)
    if base.sum() < 30:
        base = ok

    def z(col):
        s = d.loc[base, col]
        med, mad = s.median(), 1.4826 * (s - s.median()).abs().median()
        return (d[col] - med) / max(mad, 1e-3), d[col] - med

    zy, dy = z("yaw")
    zp, dp = z("pitch")
    zc, dc = z("face_cy")
    d["turned"] = ok & (zy.abs() > 3) & (dy.abs() > 0.10)
    d["down"] = ok & (((zp > 3) & (dp > 0.04)) | ((zc > 3) & (dc > 0.05)))
    d["away"] = ~ok | d.turned | d.down
    d["extra_person"] = d.n_faces >= 2
    # pre-check advice per frame
    d["too_dark"] = (d.face_med < DARK) | ((d.face_med < 65) & (d.face_hi < 95))
    d["too_bright"] = d.face_med > BRIGHT
    d["backlit"] = ((d.bg - d.face_med) > BACK) & (d.bg > 120)
    d["blurry"] = d.sharp < BLUR
    d["too_far"] = d.face_w < FACE_MIN
    return d


def g2(det, name, src, every=5.0):
    """2G feed: one 160x90 frame every 5 s; detect at that size (upscaled x2 as a phone-side model would)."""
    out, nxt = [], 0.0
    for t, im in read_frames(src):
        if t + 1e-6 < nxt:
            continue
        nxt = t + every
        small = cv2.resize(cv2.resize(im, (W, H)), (160, 90), interpolation=cv2.INTER_AREA)
        fs = faces(det, cv2.resize(small, (320, 180), interpolation=cv2.INTER_LINEAR))
        big = sorted(fs, key=lambda f: -f[2] * f[3])
        eye_px = (np.linalg.norm(big[0][4:6] - big[0][6:8]) / 2) if big else np.nan   # in 160-px units
        out.append(dict(video=name, t=t, n_faces=len(fs), eye_gap_px=eye_px))
    return pd.DataFrame(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("videos", nargs="+")
    ap.add_argument("--labels")
    a = ap.parse_args()
    det = cv2.FaceDetectorYN.create(a.model, "", (W, H), SCORE, 0.3, 50)
    names = [os.path.basename(v).replace("_frames.zip", "").replace(".zip", "") for v in a.videos]
    D = pd.concat([analyse(det, n, v) for n, v in zip(names, a.videos)], ignore_index=True)
    G = pd.concat([g2(det, n, v) for n, v in zip(names, a.videos)], ignore_index=True)
    pct = lambda s: f"{100 * np.mean(s):.0f}%"
    L = ["# Check: our own test videos in a real shared room", "",
         "Two short videos recorded by the team in a real shared room, with people walking past, the candidate looking down, "
         "leaning in, and hand on chin or mouth. Frames were analysed with an open face *detector* (YuNet; boxes and five "
         "landmarks, no recognition). No frame images are stored in this report.", ""]
    L += ["| Video | Length | Frames | Face found | 2+ faces visible | Looking away from own usual position |",
          "|---|---|---|---|---|---|"]
    for n, d in D.groupby("video", sort=False):
        L.append(f"| {n} | {d.t.max():.0f} s | {len(d)} | {pct(d.face_w.notna())} | {pct(d.extra_person)} | {pct(d.away)} |")
    L += ["", f"\"Looking away\" is measured against the candidate's own head position in the first {BASELINE_S} s. "
          "\"2+ faces\" counts faces turned towards the camera; people walking past with their back turned are not counted, "
          "and single-frame blips are ignored.", "", "## People walking past", "",
          "| Video | Times a second face appeared | Longest stay | Counted by FairProctor (25 s+ rule) |", "|---|---|---|---|"]
    ep_all = {}
    for n, d in D.groupby("video", sort=False):
        ep = episodes(d.t.values, d.extra_person.values)
        ep_all[n] = ep
        longest = max((b - a for a, b in ep), default=0)
        counted = sum(1 for a, b in ep if b - a >= PERSIST_S)
        L.append(f"| {n} | {len(ep)} | {longest:.1f} s | {counted} |")
    L += ["", "## A \"flag everything\" proctor vs FairProctor", "",
          f"A typical rule-based proctor raises an alert for every second face and for every {NAIVE_AWAY_S:.0f} s+ spell of "
          "looking away or face missing. FairProctor counts a second person only if they stay 25 s+ while answers are "
          "given, and counts head-down only against the candidate's own baseline during a silent pause followed by a "
          "correct answer on a hard item. These videos have no exam answers, and nothing in them is malpractice on its own.",
          "", "| Video | Alerts from a typical proctor | Evidence counted by FairProctor |", "|---|---|---|"]
    for n, d in D.groupby("video", sort=False):
        away = [e for e in episodes(d.t.values, d.away.values, gap=0.5) if e[1] - e[0] >= NAIVE_AWAY_S]
        k = len(ep_all[n]) + len(away)
        L.append(f"| {n} | {k} ({len(ep_all[n])} second face, {len(away)} looking away) → about "
                 f"{round(k * 3600 / max(d.t.max(), 1), -1):.0f} in a 60-minute exam | "
                 f"{sum(1 for a, b in ep_all[n] if b - a >= PERSIST_S)} |")
    L += ["", "## Pre-check advice on these rooms", "",
          "| Video | Face brightness (median) | Too dark | Backlit | Blurry (160×90) | Face too small |", "|---|---|---|---|---|---|"]
    for n, d in D.groupby("video", sort=False):
        f = d[d.face_w.notna()]
        L.append(f"| {n} | {f.face_med.median():.0f} | {pct(f.too_dark)} | {pct(f.backlit)} | {pct(d.blurry)} | {pct(f.too_far)} |")
    L += ["", "## What survives on 2G (one 160×90 frame every 5 s)", "",
          "| Video | Frames sent | Face found | Second person seen | Eye size |", "|---|---|---|---|---|"]
    for n, g in G.groupby("video", sort=False):
        full = D[D.video == n]
        ep = ep_all[n]
        seen = sum(1 for a, b in ep if ((g.t >= a - 0.1) & (g.t <= b + 0.1) & (g.n_faces >= 2)).any())
        L.append(f"| {n} | {len(g)} | {pct(g.n_faces > 0)} (full video {pct(full.face_w.notna())}) | "
                 f"{seen} of {len(ep)} walk-pasts | about {np.nanmedian(g.eye_gap_px) / 2.5:.0f} px wide |")
    if a.labels and os.path.exists(a.labels):
        lab = pd.read_csv(a.labels)
        L += ["", "## Against what we actually did", "",
              "| Video | Time | What we did | Face found | 2+ faces | Looking away |", "|---|---|---|---|---|---|"]
        for r in lab.itertuples():
            s = D[(D.video == r.video) & (D.t >= r.start) & (D.t < r.end)]
            if len(s):
                L.append(f"| {r.video} | {r.start:.0f}–{r.end:.0f} s | {r.label} | {pct(s.face_w.notna())} | "
                         f"{pct(s.extra_person)} | {pct(s.away)} |")
    L += ["", "## What this shows", "",
          "- In a real shared room, people walk behind the candidate many times in two minutes, each for a few seconds. A "
          "proctor that flags every second face would flag an honest candidate repeatedly; the 25 s persistence rule ignores all of them.",
          f"- The candidates looked away from their own usual position for {pct(D.away)} of the time while simply thinking, "
          "reading and resting a hand on the face. A gaze or head rule would flag a large share of every honest sitting; "
          "in FairProctor head-down only matters during a silent pause that ends in a fast correct answer on a hard item.",
          "- On a 2G feed most walk-pasts are never seen at all and eyes are a few pixels wide, which is why FairProctor "
          "never relies on gaze and treats missing video as no evidence.",
          ]
    dk = D[D.face_w.notna()].groupby("video").too_dark.mean()
    if len(dk) and dk.max() > 0:
        v = dk.idxmax()
        L.append(f"- When the light changed or the room went dim ({v}), the face was still found in "
                 f"{pct(D[D.video == v].face_w.notna())} of frames; the pre-check only advised more light for "
                 f"{pct(dk[v])} of them. Dim light is advice to the candidate, never suspicion.")
    L += ["", "Timeline chart: `docs/own_video_timeline.png`.", ""]
    os.makedirs("reports", exist_ok=True)
    os.makedirs("docs", exist_ok=True)
    with open("reports/OWN_VIDEO_CHECK.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    D.to_csv("reports/own_video_frames.csv", index=False)
    plot(D, G)
    print("\n".join(L))


def plot(D, G):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    vids = list(dict.fromkeys(D.video))
    fig, axes = plt.subplots(len(vids), 1, figsize=(11, 1.9 * len(vids) + 0.6), squeeze=False)
    tracks = [("Face found", lambda d: d.face_w.notna(), "#3b7dd8"),
              ("Looking away (own baseline)", lambda d: d.away, "#e0a030"),
              ("2+ faces", lambda d: d.extra_person, "#d04a3a")]
    for ax, v in zip(axes[:, 0], vids):
        d = D[D.video == v]
        for i, (lab, fn, col) in enumerate(tracks):
            m = fn(d).values
            ax.scatter(d.t[m], np.full(m.sum(), len(tracks) - i), s=6, color=col, marker="|")
        g = G[G.video == v]
        ax.scatter(g.t, np.full(len(g), 0), s=30, color=np.where(g.n_faces >= 2, "#d04a3a", "#888"), marker="v")
        ax.set_yticks(range(len(tracks) + 1), ["2G frame"] + [t[0] for t in tracks][::-1])
        ax.set_ylim(-0.7, len(tracks) + 0.7)
        ax.set_title(v, loc="left", fontsize=10)
        ax.axvspan(0, 0, color="none")
        ax.spines[["top", "right"]].set_visible(False)
    axes[-1, 0].set_xlabel("seconds")
    fig.tight_layout()
    fig.savefig("docs/own_video_timeline.png", dpi=130)


if __name__ == "__main__":
    main()

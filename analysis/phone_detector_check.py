"""Check: can an on-device detector see a phone IN the frame, and how often does it cry wolf?

Model: MediaPipe EfficientDet-Lite0 (COCO, Apache 2.0) — the same model the browser would run, class "cell phone".
Every set is scored at full resolution and at 2G resolution (160x120, scaled back up), as the phone would see it.

    pip install mediapipe opencv-python pandas
    python analysis/phone_detector_check.py --model efficientdet_lite0.tflite \
        --negatives "Cheating Scenario Dataset in Online Exam" my_video_frames \
        --positives phone_clips \
        --students "Students suspicious behaviors detection dataset_V1 (1).csv"

--negatives: folders of frames with NO phone in view (images, or videos: .mp4/.mov/.avi, every 10th frame is used),
             or frame CSVs: (frame_index, timestamp_ms, pixel_0 ...: 224x224 grayscale or RGB) or
             (frame_index, timestamp_seconds, ..., image_base64: one JPEG per row).
--positives: folders of frames/videos WITH a phone in view (hand, desk, near the face). Name a subfolder
             "calculator", "remote" or "nophone_*" to count it as a look-alike negative instead.
--hidden:    clips of cheating with the phone BELOW the camera (not in view): reported separately, to show what a
             detector cannot see.
--coco-images / --coco-ann: COCO val2017 images and instances_val2017.json. Every image there with a "cell phone"
             box is a positive (split by phone size); images with a "remote" and no phone, and people with neither,
             are negatives. Only the images present in --coco-images are used, so a subset is fine.
--students:  the Students Suspicious Behaviors CSV (features only, no images): used for the phone-confidence and
             phone-position statistics of a lab dataset.
Writes reports/PHONE_DETECTOR_CHECK.md. Only numbers are written; no image is copied or stored.
"""
from __future__ import annotations

import argparse
import glob
import os

import cv2
import pandas as pd

IMG = (".jpg", ".jpeg", ".png", ".bmp")
VID = (".mp4", ".mov", ".avi", ".mkv", ".webm")
THRESHOLDS = (0.3, 0.4, 0.5, 0.6)
_CLAHE = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))


def brighten(bgr):
    """Local contrast boost on the lightness channel — cheap enough to run on a phone before detection."""
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    lab[:, :, 0] = _CLAHE.apply(lab[:, :, 0])
    return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)


def variants(im):
    h, w = im.shape[:2]
    low = cv2.resize(cv2.resize(im, (160, 120), interpolation=cv2.INTER_AREA), (w, h), interpolation=cv2.INTER_LINEAR)
    return (("full", im), ("2G 160x120", low), ("brightened", brighten(im)), ("2G + brightened", brighten(low)))


def csv_frames(path: str):
    """Frames stored as one row of pixel_0..pixel_N per frame (224x224, grayscale or RGB)."""
    import base64
    import numpy as np
    d = pd.read_csv(path)
    if "image_base64" in d:                                # frames stored as base64 JPEG/PNG
        ts = d["timestamp_seconds"] if "timestamp_seconds" in d else pd.Series(range(len(d))) / 24
        for i, t, b64 in zip(d.get("frame_index", range(len(d))), ts, d["image_base64"]):
            im = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
            if im is not None:
                yield f"{path}#{i}@{float(t):.3f}", os.path.splitext(os.path.basename(path))[0], im
        return
    px = d.filter(like="pixel_").to_numpy(np.uint8)
    ch = 3 if px.shape[1] == 224 * 224 * 3 else 1
    ts = d["timestamp_ms"] if "timestamp_ms" in d else pd.Series(range(len(d))) * 1000 / 24
    for i, t, row in zip(d.get("frame_index", range(len(d))), ts, px):
        im = row.reshape(224, 224, ch) if ch == 3 else cv2.cvtColor(row.reshape(224, 224), cv2.COLOR_GRAY2BGR)
        yield f"{path}#{i}@{float(t) / 1000:.3f}", os.path.splitext(os.path.basename(path))[0], im


def frames(folder: str, every: int = 10):
    """Yield (name, subfolder, bgr) for every image, and every n-th frame of every video, under folder."""
    if os.path.isfile(folder) and folder.lower().endswith(".csv"):
        yield from csv_frames(folder)
        return
    for path in sorted(glob.glob(os.path.join(folder, "**", "*"), recursive=True)):
        sub = os.path.relpath(os.path.dirname(path), folder).split(os.sep)[0]
        ext = os.path.splitext(path)[1].lower()
        if ext in IMG:
            im = cv2.imread(path)
            if im is not None:
                yield path, sub, im
        elif ext in VID:
            cap = cv2.VideoCapture(path)
            i = 0
            while True:
                ok, im = cap.read()
                if not ok:
                    break
                if i % every == 0:
                    yield f"{path}#{i}", sub, im
                i += 1
            cap.release()


def make_detector(model: str):
    import mediapipe as mp
    from mediapipe.tasks import python as mpt
    from mediapipe.tasks.python import vision
    det = vision.ObjectDetector.create_from_options(vision.ObjectDetectorOptions(
        base_options=mpt.BaseOptions(model_asset_path=model), score_threshold=0.2, max_results=10))

    def phone_score(bgr):
        img = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
        res = det.detect(img).detections
        s = [d.categories[0].score for d in res if d.categories[0].category_name == "cell phone"]
        phone_score.boxes = [(d.categories[0].score, d.bounding_box.origin_x, d.bounding_box.origin_y, d.bounding_box.width,
                              d.bounding_box.height) for d in res if d.categories[0].category_name == "cell phone"]
        other = [d.categories[0].category_name for d in res if d.categories[0].category_name not in ("cell phone", "person")]
        return max(s, default=0.0), ",".join(sorted(set(other)))
    phone_score.close = det.close
    return phone_score


def score_sets(folders, kind, phone_score, every):
    rows = []
    for folder in folders:
        for name, sub, im in frames(folder, every):
            lk = kind
            if kind == "positive" and (sub.lower().startswith(("calculator", "remote", "nophone"))):
                lk = "look-alike"
            for size, frame in variants(im):
                sc, other = phone_score(frame)
                rows.append(dict(set=os.path.splitext(os.path.basename(os.path.normpath(folder)))[0], sub=sub, kind=lk,
                                 size=size, score=sc, other=other, brightness=float(im.mean()),
                                 t=float(name.rsplit("@", 1)[1]) if "@" in name else None))
    return pd.DataFrame(rows)


def iou(a, b):
    ax, ay, aw, ah = a; bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx)); iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / (aw * ah + bw * bh - inter + 1e-9)


def score_coco(img_dir, ann_path, phone_score):
    """Image-level check on COCO: a positive counts as found only when a phone box overlaps a true phone (IoU >= 0.3)."""
    import json
    ann = json.load(open(ann_path, encoding="utf-8"))
    cats = {c["id"]: c["name"] for c in ann["categories"]}
    names, boxes = {}, {}
    for a in ann["annotations"]:
        names.setdefault(a["image_id"], set()).add(cats[a["category_id"]])
        if cats[a["category_id"]] == "cell phone":
            boxes.setdefault(a["image_id"], []).append(a["bbox"])
    rows = []
    for im in ann["images"]:
        path = os.path.join(img_dir, im["file_name"])
        if not os.path.exists(path):
            continue
        tags = names.get(im["id"], set())
        if "cell phone" in tags:
            area = max(b[2] * b[3] for b in boxes[im["id"]]) / (im["width"] * im["height"])
            kind, group = "positive", ("small phone (<1% of image)" if area < 0.01 else
                                       "medium phone (1–5%)" if area < 0.05 else "large phone (>5%)")
        elif "remote" in tags:
            kind, group = "look-alike", "COCO remote, no phone"
        elif "person" in tags:
            kind, group = "negative", "COCO people, no phone"
        else:
            continue
        bgr = cv2.imread(path)
        for size, frame in variants(bgr):
            sc, other = phone_score(frame)
            if kind == "positive":       # the best phone box that actually overlaps a labelled phone
                sc = max([d[0] for d in phone_score.boxes if any(iou(d[1:], g) >= 0.3 for g in boxes[im["id"]])], default=0.0)
            rows.append(dict(set="COCO val2017", sub=group, kind=kind, size=size, score=sc, other=other))
    return pd.DataFrame(rows)


def pct(x):
    return f"{100 * x:.1f}%"


def students_section(path):
    d = pd.read_csv(path)
    p = d[d.phone_present == 1]
    below = (p.phone_loc_y > p.face_y + p.face_h).mean()
    rate = d.groupby("label").phone_present.mean()
    q = p.phone_conf.quantile([0.05, 0.5, 0.95]).round(2).tolist()
    return [
        "## Lab dataset: Students Suspicious Behaviors (features only)",
        "",
        f"{len(d):,} frames; the CSV holds another detector's output, not images, so it cannot test our detector. What it shows:",
        "",
        "| | Value |",
        "|---|---|",
        f"| Frames with a phone, honest | {pct(rate.get(0, 0))} |",
        f"| Frames with a phone, cheating | {pct(rate.get(1, 0))} |",
        f"| Phone confidence when present (5% / median / 95%) | {q[0]} / {q[1]} / {q[2]} |",
        f"| Phone below the face box | {pct(below)} (the rest: beside or in front of the face) |",
        f"| Face still visible when a phone is seen | {pct(p.face_present.mean())} |",
        "",
        "Every honest frame is phone-free because the lab staged it that way. Trained on this, a model would learn",
        "\"phone in view = cheating\" — wrong for a candidate who takes the test on a phone or has one lying on the desk.",
        "",
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--negatives", nargs="*", default=[])
    ap.add_argument("--positives", nargs="*", default=[])
    ap.add_argument("--students")
    ap.add_argument("--hidden", nargs="*", default=[])
    ap.add_argument("--coco-images")
    ap.add_argument("--coco-ann")
    ap.add_argument("--every", type=int, default=10, help="use every n-th video frame")
    ap.add_argument("--out", default="reports/PHONE_DETECTOR_CHECK.md")
    a = ap.parse_args()
    phone_score = make_detector(a.model)
    df = pd.concat([score_sets(a.negatives, "negative", phone_score, a.every),
                    score_sets(a.positives, "positive", phone_score, a.every),
                    score_sets(a.hidden, "hidden", phone_score, a.every),
                    score_coco(a.coco_images, a.coco_ann, phone_score) if a.coco_images else pd.DataFrame()], ignore_index=True)
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    df.to_csv(os.path.splitext(a.out)[0] + "_frames.csv", index=False)

    L = ["# Check: can we see a phone in the frame?", "",
         "Detector: MediaPipe EfficientDet-Lite0 (COCO, class \"cell phone\"), the model the browser would run on the "
         "candidate's device. Each frame is scored at full size and at 2G size (160×120). Only scores are kept.", ""]
    for kind, title, what in (("negative", "No phone in view (false alarms)", "flagged as phone"),
                              ("look-alike", "Look-alikes: calculator, remote (false alarms)", "flagged as phone"),
                              ("positive", "Phone in view (detection rate)", "phone detected"),
                              ("hidden", "Cheating with the phone below the camera (not in view)", "phone detected")):
        g = df[df.kind == kind]
        if g.empty:
            continue
        L += [f"## {title}", "", "| Set | Resolution | Frames | " + " | ".join(f"{what} ≥ {t}" for t in THRESHOLDS) + " |",
              "|---|---|---|" + "---|" * len(THRESHOLDS)]
        g = g.assign(label=[f"{a} — {b}" if a == "COCO val2017" else a for a, b in zip(g["set"], g["sub"])])
        for (s, z), gg in g.groupby(["label", "size"], sort=True):
            L.append(f"| {s} | {z} | {len(gg)} | " + " | ".join(pct((gg.score >= t).mean()) for t in THRESHOLDS) + " |")
        L.append("")
    if df[df.kind == "positive"].empty:
        L += ["## Phone in view (detection rate)", "",
              "**Not measured yet:** no frames with a phone in view were supplied. Record short clips (phone in hand, on the "
              "desk, held near the face; a calculator and a TV remote as look-alikes) and rerun with `--positives`.", ""]
    if a.students:
        L += students_section(a.students)
    def rate(g, t):
        return f"{pct((g.score >= t).mean())} of {len(g)}" if len(g) else "n/a"
    neg = df[df.kind.isin(["negative", "look-alike"])]
    coco = df[(df.kind == "positive") & (df.set == "COCO val2017")]
    own = df[(df.kind == "positive") & (df.set != "COCO val2017")]
    L += ["## What this means", ""]
    for name, g0 in own.dropna(subset=["t"]).groupby("set"):
        for sz in ("full", "brightened", "2G + brightened"):
            g = g0[g0["size"] == sz]
            sec = g.groupby(g["t"].astype(int)).score.max() >= 0.4
            win = [sec[(sec.index >= w) & (sec.index < w + 10)].sum() >= 2 for w in range(0, max(1, int(sec.index.max()) - 8))]
            L += [f"- **{name}** ({sz}, brightness {g0.brightness.mean():.0f}/255): phone seen in {pct(g.score.ge(0.4).mean())} of "
                  f"frames but in {pct(sec.mean())} of the {len(sec)} seconds; the '2 seconds in 10' rule fires in "
                  f"{sum(win)} of {len(win)} ten-second windows."]
    hid = df[df.kind == "hidden"]
    if not hid.empty:
        L += [f"- **Phone below the camera** ({hid['set'].nunique()} clip(s)): detected in {pct(hid.score.ge(0.4).mean())} of "
              "frames — as expected, the camera cannot show what it cannot see. These cases are caught by behaviour "
              "(silent pauses followed by correct answers), not by the detector."]
    for sz in ("brightened", "2G + brightened"):
        g = neg[neg["size"] == sz]
        L += [f"- **False alarms, {sz}, threshold 0.4:** {rate(g, 0.4)} phone-free or look-alike frames."]
    if not coco.empty:
        for grp in ("large", "medium", "small"):
            g = coco[coco["sub"].str.startswith(grp)]
            L += [f"- COCO {grp} phones, brightened, 0.4: {rate(g[g['size'] == 'brightened'], 0.4)} "
                  f"(2G: {rate(g[g['size'] == '2G + brightened'], 0.4)})."]
    L += ["- A small or distant phone is rarely seen, and a phone *below* the camera never is: missing a phone proves nothing.",
          "- Groups are small and partly not webcam footage: treat rates as indicative and repeat with more webcam clips.", ""]
    L += ["## How FairProctor uses it (implemented)", "",
          "- On the device (`frontend/src/lib/camera.ts`): only on a fast link (pre-check above 1.5 Mbps) the browser loads",
          "  `/models/efficientdet_lite0.tflite`, brightens the frame (level stretch + gamma), runs the detector about once a",
          "  second at threshold 0.4, and sends only the *share of seconds* with a phone in view in each 5 s frame — never the image.",
          "- On the server (`fairproctor/features.py`, `phone_on_correct`): an item counts when a phone was in view for at",
          "  least 2 seconds while it was being answered *and* the answer was a correct one the candidate was unlikely to get.",
          "- Phone-in-view is **supporting evidence only** and is kept out of the trained model, so the validated numbers in",
          "  `reports/RESULTS.md` do not change. Rule (`fairproctor/explain.py`, `phone_band`): 2 or more such items lift a",
          "  session to at least **Review** (a person looks); it never makes *Review first* on its own and never lowers a band.",
          "- A phone seen at other times is listed under \"Not counted against the candidate\".",
          "- Frames where the detector cannot run (2G, no model downloaded) give **no evidence**, never suspicion.",
          "- The most common real method — a phone *below* the camera — stays invisible to any detector; behaviour",
          "  signals remain the main evidence.", ""]
    phone_score.close()
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print("\n".join(L))


if __name__ == "__main__":
    main()

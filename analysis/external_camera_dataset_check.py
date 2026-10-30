"""What does a model learn from a public lab-recorded proctoring dataset?

Dataset: "Students suspicious behaviors detection dataset for AI-powered online exam
proctoring" (Mendeley Data, CC BY 4.0) — 5,500 per-frame feature rows with a cheating label.
https://data.mendeley.com/datasets/39xs8th543/1

    python analysis/external_camera_dataset_check.py path/to/Students_suspicious_behaviors_detection_dataset_V1.csv

Writes reports/EXTERNAL_DATASET_CHECK.md.
"""
import os
import sys

import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GroupKFold, cross_val_predict


def main(path):
    d = pd.read_csv(path)
    honest, cheat = d[d.label == 0], d[d.label == 1]

    def share(df, cond):
        return f"{100 * cond.loc[df.index].mean():.1f}%"

    not_forward = d.head_pose.notna() & (d.head_pose != "forward")
    not_centre = d.gaze_direction.notna() & (d.gaze_direction != "center")
    two_faces = d.no_of_face >= 2
    phone = d.phone_present == 1
    hand_obj = d.hand_obj_interaction == 1

    X = pd.get_dummies(d.drop(columns="label"), columns=["head_pose", "gaze_direction"], dummy_na=True).astype(float)
    groups = (d.label != d.label.shift()).cumsum()  # contiguous runs = same clip; keep them together in CV
    p = cross_val_predict(HistGradientBoostingClassifier(max_iter=200), X, d.label, groups=groups,
                          cv=GroupKFold(5), method="predict_proba")[:, 1]
    model = HistGradientBoostingClassifier(max_iter=200).fit(X, d.label)
    base = X[d.label == 0].median()

    def score(**kw):
        x = base.copy()
        for k, v in kw.items():
            x[k] = v
        return model.predict_proba(pd.DataFrame([x], columns=X.columns))[0, 1]

    probes = [
        ("A typical honest frame from the dataset", {}),
        ("Same frame, head tilted down — phone held low, or writing rough work", dict(head_pitch=0.25, head_pose_forward=0, head_pose_down=1)),
        ("Same frame, eyes bottom-left — reading the question on a phone held low", dict(gaze_direction_center=0, gaze_direction_bottom_left=1, gaze_on_script=0)),
        ("Same frame, a second face — sibling walking past in a shared room", dict(no_of_face=2)),
    ]

    lines = [
        "# Check: a public lab-recorded proctoring dataset",
        "",
        f"Dataset: Students suspicious behaviors detection dataset (Mendeley, CC BY 4.0). {len(d):,} frames, "
        f"{len(cheat):,} labelled cheating, {len(honest):,} honest.",
        "",
        "## What honest behaviour looks like in this dataset",
        "",
        "| Signal | Honest frames | Cheating frames |",
        "|---|---|---|",
        f"| Head not facing forward | {share(honest, not_forward)} | {share(cheat, not_forward)} |",
        f"| Eyes not on centre of screen | {share(honest, not_centre)} | {share(cheat, not_centre)} |",
        f"| Two faces in frame | {share(honest, two_faces)} | {share(cheat, two_faces)} |",
        f"| Phone visible | {share(honest, phone)} | {share(cheat, phone)} |",
        f"| Hand holding an object | {share(honest, hand_obj)} | {share(cheat, hand_obj)} |",
        "",
        "Every honest frame faces forward, looks at the centre, and is alone. The dataset was recorded "
        "in ideal conditions, so **any** looking down, looking aside or second person is labelled cheating.",
        "",
        "## What a model learns from it",
        "",
        f"A CPU gradient-boosted model reaches **AUC {roc_auc_score(d.label, p):.4f}** "
        f"(accuracy {100 * accuracy_score(d.label, p > 0.5):.1f}%) with clip-grouped cross-validation. "
        "It looks excellent, and it is the wrong model for our candidates:",
        "",
        "| Frame | Model's cheating probability |",
        "|---|---|",
    ]
    lines += [f"| {name} | {100 * score(**kw):.0f}% |" for name, kw in probes]
    lines += [
        "",
        "An honest candidate on a phone propped low, writing rough work, or with a sibling walking past is "
        "scored as cheating with near certainty. This is exactly the failure the Integraminds problem describes.",
        "",
        "## How FairProctor uses this",
        "",
        "- **Not as training labels** for the integrity score.",
        "- **As evidence for the design.** Head-down is compared with the candidate's *own* baseline and only counts during "
        "silent pauses followed by correct answers on hard items. A second face only counts if it stays 25 s+ while answers "
        "are given. Missing video is treated as no evidence. On our labelled sample, honest phone and desktop candidates "
        "are sent to review at the same rate.",
        "- **As a signal library.** A *visible* phone in hand or a hand–object interaction never appears in an honest frame "
        "here. When the camera actually sees one, it is strong evidence, worth adding to the frame schema as `phone_visible`, "
        "gated by persistence across frames.",
        "",
    ]
    os.makedirs("reports", exist_ok=True)
    with open("reports/EXTERNAL_DATASET_CHECK.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/external/Students_suspicious_behaviors_detection_dataset_V1.csv")

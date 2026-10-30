# Check: real home webcam frames (Cheating Scenario Dataset)

Frames analysed: 55 from 4 scenario folders, 3 volunteers, recorded at home on ordinary webcams (1280×720). Dataset: Mendeley Data, CC BY 4.0, DOI 10.17632/mjrfmvsh7d.1.

This dataset has no honest-vs-cheating label. Every frame is annotated with head, eye and mouth states, so it is used here to test two parts of FairProctor, not to train the integrity score.

## 1. Would the pre-check give sensible advice on real home frames?

| Check | Frames that would be asked to fix it |
|---|---|
| Too dark (face brightness < 70) | 0% |
| Too bright (> 215) | 0% |
| Light behind the candidate (background brighter than face by > 45) | 7% |
| Blurry (sharpness < 35 at 160×120) | 0% |
| "Move closer" with the old size rule (face < 20% of frame width) | 36% |
| "Move closer" with the new size rule (face < 13%) | 0% |

Median face width in these normal sittings is 21% of the frame (head box). The old "move closer" rule would have nagged 36% of perfectly usable frames, so the pre-check now uses 13% (a face detector's box is smaller than this dataset's head box). Light, backlight and blur checks gave advice only where it was warranted: the backlight warning fired on the volunteer sitting against a bright wall.

## 2. Can eye direction be read on a 2G video feed?

At full resolution an eye is about 69 px wide. At the 160×120 resolution a 2G link realistically sends, the same eye is **9 px wide** (range 5–11 px). See `docs/eyes_full_vs_2g.jpg`: eye direction is unreadable, while a turned head is still obvious.

This is why FairProctor:

- uses only a coarse head direction (centre / down / left / right / away), never eye gaze, as a camera signal;
- compares head-down with the candidate's *own* baseline and only counts it during silent pauses followed by correct answers;
- treats missing or unreadable video as *no evidence*, never as suspicion.

## Per-volunteer summary

| Volunteer | Face brightness | Background | Sharpness @160×120 | Face width | Eye width full / 2G (px) |
|---|---|---|---|---|---|
| S1 | 118 | 151 | 586 | 22% | 66 / 8.2 |
| S2 | 87 | 72 | 984 | 20% | 65 / 8.1 |
| S3 | 84 | 80 | 312 | 30% | 74 / 9.2 |

Images from this dataset are used under CC BY 4.0 with attribution; volunteers are not identified.

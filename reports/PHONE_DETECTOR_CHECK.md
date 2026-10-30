# Check: can we see a phone in the frame?

Detector: MediaPipe EfficientDet-Lite0 (COCO, class "cell phone"), the model the browser would run on the candidate's device. Each frame is scored at full size and at 2G size (160×120). Only scores are kept.

## No phone in view (false alarms)

| Set | Resolution | Frames | flagged as phone ≥ 0.3 | flagged as phone ≥ 0.4 | flagged as phone ≥ 0.5 | flagged as phone ≥ 0.6 |
|---|---|---|---|---|---|---|
| COCO val2017 — COCO people, no phone | 2G + brightened | 36 | 0.0% | 0.0% | 0.0% | 0.0% |
| COCO val2017 — COCO people, no phone | 2G 160x120 | 36 | 0.0% | 0.0% | 0.0% | 0.0% |
| COCO val2017 — COCO people, no phone | brightened | 36 | 0.0% | 0.0% | 0.0% | 0.0% |
| COCO val2017 — COCO people, no phone | full | 36 | 0.0% | 0.0% | 0.0% | 0.0% |
| Cheating Scenario Dataset in Online Exam | 2G + brightened | 55 | 1.8% | 1.8% | 0.0% | 0.0% |
| Cheating Scenario Dataset in Online Exam | 2G 160x120 | 55 | 0.0% | 0.0% | 0.0% | 0.0% |
| Cheating Scenario Dataset in Online Exam | brightened | 55 | 1.8% | 0.0% | 0.0% | 0.0% |
| Cheating Scenario Dataset in Online Exam | full | 55 | 0.0% | 0.0% | 0.0% | 0.0% |
| own_shared_room_videos_sample | 2G + brightened | 500 | 0.0% | 0.0% | 0.0% | 0.0% |
| own_shared_room_videos_sample | 2G 160x120 | 500 | 0.2% | 0.0% | 0.0% | 0.0% |
| own_shared_room_videos_sample | brightened | 500 | 0.0% | 0.0% | 0.0% | 0.0% |
| own_shared_room_videos_sample | full | 500 | 0.0% | 0.0% | 0.0% | 0.0% |

## Look-alikes: calculator, remote (false alarms)

| Set | Resolution | Frames | flagged as phone ≥ 0.3 | flagged as phone ≥ 0.4 | flagged as phone ≥ 0.5 | flagged as phone ≥ 0.6 |
|---|---|---|---|---|---|---|
| COCO val2017 — COCO remote, no phone | 2G + brightened | 50 | 8.0% | 4.0% | 2.0% | 0.0% |
| COCO val2017 — COCO remote, no phone | 2G 160x120 | 50 | 4.0% | 0.0% | 0.0% | 0.0% |
| COCO val2017 — COCO remote, no phone | brightened | 50 | 2.0% | 2.0% | 0.0% | 0.0% |
| COCO val2017 — COCO remote, no phone | full | 50 | 2.0% | 2.0% | 0.0% | 0.0% |

## Phone in view (detection rate)

| Set | Resolution | Frames | phone detected ≥ 0.3 | phone detected ≥ 0.4 | phone detected ≥ 0.5 | phone detected ≥ 0.6 |
|---|---|---|---|---|---|---|
| COCO val2017 — large phone (>5%) | 2G + brightened | 17 | 64.7% | 58.8% | 47.1% | 41.2% |
| COCO val2017 — large phone (>5%) | 2G 160x120 | 17 | 70.6% | 64.7% | 52.9% | 41.2% |
| COCO val2017 — large phone (>5%) | brightened | 17 | 58.8% | 58.8% | 52.9% | 47.1% |
| COCO val2017 — large phone (>5%) | full | 17 | 64.7% | 58.8% | 58.8% | 58.8% |
| COCO val2017 — medium phone (1–5%) | 2G + brightened | 26 | 46.2% | 42.3% | 26.9% | 23.1% |
| COCO val2017 — medium phone (1–5%) | 2G 160x120 | 26 | 53.8% | 46.2% | 30.8% | 7.7% |
| COCO val2017 — medium phone (1–5%) | brightened | 26 | 57.7% | 46.2% | 30.8% | 15.4% |
| COCO val2017 — medium phone (1–5%) | full | 26 | 61.5% | 46.2% | 34.6% | 23.1% |
| COCO val2017 — small phone (<1% of image) | 2G + brightened | 71 | 7.0% | 2.8% | 2.8% | 0.0% |
| COCO val2017 — small phone (<1% of image) | 2G 160x120 | 71 | 5.6% | 2.8% | 2.8% | 0.0% |
| COCO val2017 — small phone (<1% of image) | brightened | 71 | 14.1% | 5.6% | 4.2% | 0.0% |
| COCO val2017 — small phone (<1% of image) | full | 71 | 9.9% | 7.0% | 4.2% | 0.0% |
| phone_in_hand_dark_room | 2G + brightened | 379 | 20.6% | 7.9% | 0.5% | 0.0% |
| phone_in_hand_dark_room | 2G 160x120 | 379 | 0.8% | 0.0% | 0.0% | 0.0% |
| phone_in_hand_dark_room | brightened | 379 | 32.5% | 11.9% | 1.8% | 0.3% |
| phone_in_hand_dark_room | full | 379 | 0.5% | 0.0% | 0.0% | 0.0% |
| phone_in_hand_good_light | 2G + brightened | 496 | 7.1% | 1.0% | 0.0% | 0.0% |
| phone_in_hand_good_light | 2G 160x120 | 496 | 5.2% | 0.8% | 0.0% | 0.0% |
| phone_in_hand_good_light | brightened | 496 | 11.9% | 4.2% | 0.6% | 0.0% |
| phone_in_hand_good_light | full | 496 | 11.1% | 4.0% | 0.6% | 0.0% |

## Cheating with the phone below the camera (not in view)

| Set | Resolution | Frames | phone detected ≥ 0.3 | phone detected ≥ 0.4 | phone detected ≥ 0.5 | phone detected ≥ 0.6 |
|---|---|---|---|---|---|---|
| phone_below_camera | 2G + brightened | 836 | 0.0% | 0.0% | 0.0% | 0.0% |
| phone_below_camera | 2G 160x120 | 836 | 0.0% | 0.0% | 0.0% | 0.0% |
| phone_below_camera | brightened | 836 | 0.0% | 0.0% | 0.0% | 0.0% |
| phone_below_camera | full | 836 | 0.0% | 0.0% | 0.0% | 0.0% |

## Lab dataset: Students Suspicious Behaviors (features only)

5,500 frames; the CSV holds another detector's output, not images, so it cannot test our detector. What it shows:

| | Value |
|---|---|
| Frames with a phone, honest | 0.0% |
| Frames with a phone, cheating | 29.6% |
| Phone confidence when present (5% / median / 95%) | 0.63 / 0.8 / 0.91 |
| Phone below the face box | 29.1% (the rest: beside or in front of the face) |
| Face still visible when a phone is seen | 92.8% |

Every honest frame is phone-free because the lab staged it that way. Trained on this, a model would learn
"phone in view = cheating" — wrong for a candidate who takes the test on a phone or has one lying on the desk.

## What this means

- **phone_in_hand_dark_room** (full, brightness 8/255): phone seen in 0.0% of frames but in 0.0% of the 16 seconds; the '2 seconds in 10' rule fires in 0 of 7 ten-second windows.
- **phone_in_hand_dark_room** (brightened, brightness 8/255): phone seen in 11.9% of frames but in 68.8% of the 16 seconds; the '2 seconds in 10' rule fires in 7 of 7 ten-second windows.
- **phone_in_hand_dark_room** (2G + brightened, brightness 8/255): phone seen in 7.9% of frames but in 50.0% of the 16 seconds; the '2 seconds in 10' rule fires in 7 of 7 ten-second windows.
- **phone_in_hand_good_light** (full, brightness 167/255): phone seen in 4.0% of frames but in 35.3% of the 17 seconds; the '2 seconds in 10' rule fires in 8 of 8 ten-second windows.
- **phone_in_hand_good_light** (brightened, brightness 167/255): phone seen in 4.2% of frames but in 29.4% of the 17 seconds; the '2 seconds in 10' rule fires in 8 of 8 ten-second windows.
- **phone_in_hand_good_light** (2G + brightened, brightness 167/255): phone seen in 1.0% of frames but in 23.5% of the 17 seconds; the '2 seconds in 10' rule fires in 7 of 8 ten-second windows.
- **Phone below the camera** (1 clip(s)): detected in 0.0% of frames — as expected, the camera cannot show what it cannot see. These cases are caught by behaviour (silent pauses followed by correct answers), not by the detector.
- **False alarms, brightened, threshold 0.4:** 0.2% of 641 phone-free or look-alike frames.
- **False alarms, 2G + brightened, threshold 0.4:** 0.5% of 641 phone-free or look-alike frames.
- COCO large phones, brightened, 0.4: 58.8% of 17 (2G: 58.8% of 17).
- COCO medium phones, brightened, 0.4: 46.2% of 26 (2G: 42.3% of 26).
- COCO small phones, brightened, 0.4: 5.6% of 71 (2G: 2.8% of 71).
- A small or distant phone is rarely seen, and a phone *below* the camera never is: missing a phone proves nothing.
- Groups are small and partly not webcam footage: treat rates as indicative and repeat with more webcam clips.

## How FairProctor uses it (implemented)

- On the device (`frontend/src/lib/camera.ts`): only on a fast link (pre-check above 1.5 Mbps) the browser loads
  `/models/efficientdet_lite0.tflite`, brightens the frame (level stretch + gamma), runs the detector about once a
  second at threshold 0.4, and sends only the *share of seconds* with a phone in view in each 5 s frame — never the image.
- On the server (`fairproctor/features.py`, `phone_on_correct`): an item counts when a phone was in view for at
  least 2 seconds while it was being answered *and* the answer was a correct one the candidate was unlikely to get.
- Phone-in-view is **supporting evidence only** and is kept out of the trained model, so the validated numbers in
  `reports/RESULTS.md` do not change. Rule (`fairproctor/explain.py`, `phone_band`): 2 or more such items lift a
  session to at least **Review** (a person looks); it never makes *Review first* on its own and never lowers a band.
- A phone seen at other times is listed under "Not counted against the candidate".
- Frames where the detector cannot run (2G, no model downloaded) give **no evidence**, never suspicion.
- The most common real method — a phone *below* the camera — stays invisible to any detector; behaviour
  signals remain the main evidence.

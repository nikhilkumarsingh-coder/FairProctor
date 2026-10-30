# Check: our own test videos in a real shared room

Two short videos recorded by the team in a real shared room, with people walking past, the candidate looking down, leaning in, and hand on chin or mouth. Frames were analysed with an open face *detector* (YuNet; boxes and five landmarks, no recognition). No frame images are stored in this report.

| Video | Length | Frames | Face found | 2+ faces visible | Looking away from own usual position |
|---|---|---|---|---|---|
| webcam_video | 64 s | 963 | 100% | 8% | 38% |
| whatsapp_video | 121 s | 1813 | 97% | 1% | 35% |
| cs_video | 123 s | 1837 | 99% | 5% | 4% |

"Looking away" is measured against the candidate's own head position in the first 15 s. "2+ faces" counts faces turned towards the camera; people walking past with their back turned are not counted, and single-frame blips are ignored.

## People walking past

| Video | Times a second face appeared | Longest stay | Counted by FairProctor (25 s+ rule) |
|---|---|---|---|
| webcam_video | 5 | 1.9 s | 0 |
| whatsapp_video | 2 | 1.5 s | 0 |
| cs_video | 4 | 2.8 s | 0 |

## A "flag everything" proctor vs FairProctor

A typical rule-based proctor raises an alert for every second face and for every 2 s+ spell of looking away or face missing. FairProctor counts a second person only if they stay 25 s+ while answers are given, and counts head-down only against the candidate's own baseline during a silent pause followed by a correct answer on a hard item. These videos have no exam answers, and nothing in them is malpractice on its own.

| Video | Alerts from a typical proctor | Evidence counted by FairProctor |
|---|---|---|
| webcam_video | 7 (5 second face, 2 looking away) → about 390 in a 60-minute exam | 0 |
| whatsapp_video | 11 (2 second face, 9 looking away) → about 330 in a 60-minute exam | 0 |
| cs_video | 4 (4 second face, 0 looking away) → about 120 in a 60-minute exam | 0 |

## Pre-check advice on these rooms

| Video | Face brightness (median) | Too dark | Backlit | Blurry (160×90) | Face too small |
|---|---|---|---|---|---|
| webcam_video | 73 | 1% | 100% | 0% | 0% |
| whatsapp_video | 104 | 0% | 31% | 0% | 31% |
| cs_video | 116 | 4% | 0% | 2% | 7% |

## What survives on 2G (one 160×90 frame every 5 s)

| Video | Frames sent | Face found | Second person seen | Eye size |
|---|---|---|---|---|
| webcam_video | 13 | 100% (full video 100%) | 1 of 5 walk-pasts | about 8 px wide |
| whatsapp_video | 25 | 96% (full video 97%) | 0 of 2 walk-pasts | about 4 px wide |
| cs_video | 25 | 100% (full video 99%) | 1 of 4 walk-pasts | about 5 px wide |

## What this shows

- In a real shared room, people walk behind the candidate many times in two minutes, each for a few seconds. A proctor that flags every second face would flag an honest candidate repeatedly; the 25 s persistence rule ignores all of them.
- The candidates looked away from their own usual position for 23% of the time while simply thinking, reading and resting a hand on the face. A gaze or head rule would flag a large share of every honest sitting; in FairProctor head-down only matters during a silent pause that ends in a fast correct answer on a hard item.
- On a 2G feed most walk-pasts are never seen at all and eyes are a few pixels wide, which is why FairProctor never relies on gaze and treats missing video as no evidence.
- When the light changed or the room went dim (cs_video), the face was still found in 99% of frames; the pre-check only advised more light for 4% of them. Dim light is advice to the candidate, never suspicion.

Timeline chart: `docs/own_video_timeline.png`.

# Check: a public lab-recorded proctoring dataset

Dataset: Students suspicious behaviors detection dataset (Mendeley, CC BY 4.0). 5,500 frames, 2,619 labelled cheating, 2,881 honest.

## What honest behaviour looks like in this dataset

| Signal | Honest frames | Cheating frames |
|---|---|---|
| Head not facing forward | 0.0% | 38.0% |
| Eyes not on centre of screen | 0.0% | 32.8% |
| Two faces in frame | 0.0% | 4.4% |
| Phone visible | 0.0% | 29.6% |
| Hand holding an object | 0.0% | 32.0% |

Every honest frame faces forward, looks at the centre, and is alone. The dataset was recorded in ideal conditions, so **any** looking down, looking aside or second person is labelled cheating.

## What a model learns from it

A CPU gradient-boosted model reaches **AUC 0.9991** (accuracy 99.6%) with clip-grouped cross-validation. It looks excellent, and it is the wrong model for our candidates:

| Frame | Model's cheating probability |
|---|---|
| A typical honest frame from the dataset | 0% |
| Same frame, head tilted down — phone held low, or writing rough work | 100% |
| Same frame, eyes bottom-left — reading the question on a phone held low | 100% |
| Same frame, a second face — sibling walking past in a shared room | 100% |

An honest candidate on a phone propped low, writing rough work, or with a sibling walking past is scored as cheating with near certainty. This is exactly the failure the Integraminds problem describes.

## How FairProctor uses this

- **Not as training labels** for the integrity score.
- **As evidence for the design.** Head-down is compared with the candidate's *own* baseline and only counts during silent pauses followed by correct answers on hard items. A second face only counts if it stays 25 s+ while answers are given. Missing video is treated as no evidence. On our labelled sample, honest phone and desktop candidates are sent to review at the same rate.
- **As a signal library.** A *visible* phone in hand or a hand–object interaction never appears in an honest frame here. When the camera actually sees one, it is strong evidence, worth adding to the frame schema as `phone_visible`, gated by persistence across frames.

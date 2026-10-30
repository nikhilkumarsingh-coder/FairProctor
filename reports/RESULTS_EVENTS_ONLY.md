# Results on event logs only (no video)

5,000 sessions, 294 confirmed malpractice, scored from answer timing, focus changes, paste events and identical wrong answers only: the shape of the problem statement's labelled dataset, which has no video. Every number is **out of fold** (5-fold, grouped by sitting). On the synthetic data the video frames were removed before building features and the model was trained without the camera inputs.

## Done-when: cut the queue by at least half while surfacing every confirmed case

**Not met on event logs alone.** All 294 confirmed cases are in the top 87.7% of sessions (stricter test, threshold set without seeing the fold: 89.2% queued, 0 missed). With video the same pipeline needs 44.9% (`RESULTS.md`).

| Confirmed cases caught | Share of sessions to review |
|---|---|
| 80% | 28.3% |
| 90% | 53.3% |
| 95% | 70.3% |
| 100% | 87.7% |

Reviewing the top half of the queue catches **87.8%** of confirmed cases.

| Pattern | Caught in the top half |
|---|---|
| collusion | 95.7% |
| helper | 62.5% |
| second phone | 86.4% |
| tab search | 100.0% |

## Top of the queue

| First N sessions | Precision | Old rules (flag rate) |
|---|---|---|
| 25 | 88.0% | 96.0% |
| 50 | 90.0% | 98.0% |
| 100 | 89.0% | 54.0% |
| 200 | 73.5% | 30.5% |
| 294 | 53.7% | 23.8% |

Review first: top 91 sessions at 90.1% precision. AUC 0.8613, average precision 0.5687.
Without video the old rules reduce to counting focus losses. At the very top of the queue that can be more precise, because searching in another tab always leaves focus losses; further down the queue the model is far ahead.

## Fairness: honest sessions sent to review (at the catch-everything threshold)

Low bandwidth: 87.9%; normal: 88.8%. Bandwidth and device are not model inputs.

## Why event logs alone cannot surface every case

Answers relayed from a second phone or a helper are mostly *correct*, so they raise the candidate's own estimated ability, and on event logs alone that candidate looks like a strong honest one. Collusion (shared wrong answers) and tab searching with pastes leave clear traces in the logs; a second phone and a helper mostly do not. We tried answer-timing features from the test-security literature on top of these (a block of answers far above the candidate's level, long pauses then correct answers on hard questions); out of fold they did not move the catch-everything queue below half, so they were not added. Reaching the target on real event logs would need signals the synthetic logs do not carry, or the video and frame samples. This is reported, not tuned around.


# Coding integrity model — results on synthetic coding sittings

5125 candidates in 30 synthetic sittings of the demo coding test (3 problems, Python and C++), 292 with malpractice on 1–3 problems. Programs are real source code built from interchangeable parts; typing, pastes, tab switches, runs and submits are simulated over time. Scores are out-of-fold (each sitting scored by a model that never saw it). **These are synthetic results and are optimistic: real candidates and real cheating are more varied.**

| Measure | Value |
|---|---|
| AUC | 0.9885 |
| Average precision | 0.9471 |
| Precision in the top 50 / 100 | 1.0 / 1.0 |
| Review line: malpractice caught | 95% |
| Review line: share of all candidates in the queue | 8.9% |
| Review first: candidates / precision | 295 / 90% |

Caught at the review line, by kind of malpractice:

| Web paste | Copied from a partner (both) | Typed from a phone or helper | Injected text |
|---|---|---|---|
| 100% | 88% | 91% | 100% |

Honest candidates sent to review (false flags):

| Group | FairProctor | Simple rule: any 50+ char paste or tab switch |
|---|---|---|
| All honest candidates | 3.7% | 79.2% |
| Fast experts | 18.7% | |
| Moved their own lines with small pastes | 3.7% | |
| Left the tab briefly (no paste after) | 3.1% | |

The simple rule catches 75% of malpractice but flags 79% of honest candidates; FairProctor reviews 9% of candidates to catch 95%.

Known limits: the partner who *shared* code behaves honestly and is found only through the similarity of the two programs; very short programs give little to compare; a cheater who retypes a solution slowly with deliberate mistakes looks like an honest candidate. Similarity, paste and typing are evidence for a human reviewer, never a verdict.

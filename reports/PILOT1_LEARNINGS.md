# First hostel pilot: what it showed and what changed

**29 Oct 2026 · 10 participants (4 acted malpractice, 6 honest in a hard situation) · question test.**
The full per-person table is produced by `python -m pilot.report --dir pilot\out\hostel-pilot` into `PILOT_RESULTS.md`.

## 1. Result as run (scoring as it was on pilot day, plus the crash fix only)

| | FairProctor | Old rules, same number of flags |
|---|---|---|
| Malpractice sent to review | 3 of 4 (75%) · 95% CI 30–95% | 4 of 4 |
| Honest sent to review | 3 of 6 (50%) · 95% CI 19–81% | 2 of 6 |
| Ranking (AUC) | **0.54** | 0.81 |

Honest people in a shared room, with the phone held low, or interrupted were cleared (the old rules ranked the shared
room 10th and phone-held-low 7th of 10, so they stayed clear there too at this workload). FairProctor did **not**
beat the old rules in this pilot.

## 2. What went wrong

| Problem | What we saw | Change |
|---|---|---|
| **Scoring crashed** on the first real data | Real people change answers and go back to questions; the code assumed one answer per question | Final answer counts; time runs from first view to final answer (coming back can only make it slower). `Retry scoring` button for a failed run. Tests: `test_real_answers.py` |
| **Common human mistakes looked rare** | Three participants (two of them honest) chose the same wrong option on Q14, Q17, Q21, Q22. Measured against 200 synthetic reference candidates, whose wrong answers are spread evenly, that looked like collusion | A real candidate's wrong answer counts as rare only if it is rare among the **real** candidates too (Laplace-smoothed, so 10 people can never make an answer look rarer than about 1 in 7). With hundreds of real candidates nothing changes |
| **Clicking through looked like relaying answers** | Some people finished a 45-minute paper in 1–2 minutes with answers at chance level | Under a fifth of the typical time **and** accuracy no better than guessing + 20 points: answer timing is not counted, and the reviewer sees a note. Fast *and* mostly right is still counted |

Neither rule changes a single one of the 5,000 synthetic training sessions, so the model and `RESULTS.md` are unchanged.

## 3. The same pilot re-scored with the changes — **not evidence**

| | Before | After |
|---|---|---|
| Ranking (AUC) | 0.54 | 0.77 |
| Malpractice sent to review | 3 of 4 | 3 of 4 (now ranks 1–3) |
| Honest sent to review | 3 of 6 | 3 of 6 |

These changes were designed while looking at this pilot, so this table only shows that they do what they were meant
to do on the data that motivated them. Whether they help must be shown on a **new** pilot.

## 4. Not fixed, and why

- **Two participants submitted identical, fully correct sheets** (one honest role, one acting a partner). Copying a
  complete correct key fast leaves almost no trace: everyone who knows the answers gives the same ones. This is the
  known limit in the README. Ask the participants where the answers came from.
- **The partner pair did not share answers**, so the role was not acted out.
- **Six of ten sessions had no camera numbers** (the camera was optional on pilot day; it is now required).
- **Honest people still matched each other.** With 10 people we cannot tell a shared misconception from sharing.

## 5. Next pilot (to test the changes)

15–20 people from different rooms; at least 20 minutes on the paper; no answer key anywhere; camera on; each malpractice
role acted by 2–3 people; a reviewer records decisions afterwards. Report both pilots, whatever the numbers.

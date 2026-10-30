# Check: answer timing against real learners (EdNet-KT1)

Real data: 599,640 single-question answers from 1,256 EdNet learners on 5,804 questions, cut into 19,988 windows of 30 answers (one window ≈ one test). EdNet is a practice app, so this is treated as honest behaviour. KT1 has no answer key; the most popular answer stands in for "correct".

## Is the synthetic timing realistic?

| | Real learners (EdNet) | Synthetic honest candidates |
|---|---|---|
| Spread of answer time on one question (robust SD of log-time) | 0.50 | 0.51 |
| Answers flagged "fast" by our rule (z < -1.5) | 7.9% | 7.4% |
| Tests with 2+ fast correct answers | 40.5% | 27.5% |
| Tests with 3+ fast correct answers | 26.4% | 18.2% |
| Tests with 4+ fast correct answers | 17.1% | 13.3% |
| Tests with 6+ fast correct answers | 7.7% | 7.6% |
| Tests with 3+ fast correct answers **in a row** | 5.1% | 3.6% |
| Tests with 4+ fast correct answers **in a row** | 1.8% | 1.6% |
| Tests with 6+ fast correct answers **in a row** | 0.3% | 0.3% |

Real answer times: median 19 s per question (1% under 4 s, 99% under 90 s); a typical question takes 20 s. The synthetic paper is a harder aptitude test with longer items, but the scorer only uses time *relative to each item's own typical time*, so the absolute scale does not matter. What matters, the spread and the rate of fast answers, matches closely.

## What this means for the scoring

- A single fast correct answer is normal: it happens in most real tests. Even 17.1% of honest real tests have 4+ of them, so counting fast answers alone would flood the queue.
- Runs of fast correct answers are rarer (1.8% of real tests have 4+ in a row) but still happen to honest people. A timing burst on its own is a reason to look, never proof.
- This is why FairProctor never flags on timing alone. Timing has to line up with another signal (a silent pause, leaving the window, matching another candidate's answers) to rank high, and the explanation shows the reviewer the actual seconds.

EdNet data: Riiid, https://github.com/riiid/ednet (licence CC BY-NC 4.0; research and non-commercial use).

# Check: does the phone-side detector match the validated one? (ESC-50 + MUSAN)

The detector that runs in the candidate's browser (`frontend/src/lib/speech.ts`) was run, as bundled for the browser, on the same audio as the Python checks, including the browser's own resampling to 16 kHz. Every clip's verdict is compared with the Python detector's (`reports/esc50_clip_results.csv`, `reports/musan_window_results.csv`).

## ESC-50 (no speech: every "yes" is a false alarm)

| | Browser detector | Python detector |
|---|---|---|
| Clips | 500 | 500 |
| False alarms | 23% (113) | 23% (114) |
| Same verdict as Python | **99.8%** (499 of 500) | — |

Clips where the two differ: glass breaking (browser no). These sit on a threshold; the 44.1 → 16 kHz resampling differs slightly from scipy's.

## MUSAN

| Audio | Windows | Browser: speech-like | Python: speech-like | Same verdict |
|---|---|---|---|---|
| Speech (reading aloud, speeches) | 706 | 87% | 87% | 100% |
| Music | 300 | 2% | 2% | 100% |
| Noise | 665 | 8% | 8% | 100% |

Same verdict as Python on **100%** of 1671 windows.

## Cost on the device

2171 windows of 5 s took 58 ms each on this machine (one core, Node), about 1.2% of one core while listening. On the phone the work is spread over each window (a little every quarter second) and quiet frames are skipped. A low-end phone is roughly 5–10× slower; if the check would take more than a third of the time it listens, the page switches it off by itself (`frontend/src/lib/mic.ts`), so the test stays smooth, and the reviewer sees "the microphone check stopped (not counted)".

## What this means

- The phone runs the same detector that was measured in `ESC50_NOISE_CHECK.md` and `MUSAN_SPEECH_CHECK.md`, so those numbers (about 87% of talking caught, about a quarter of home sounds mistaken for talking) describe what the product does.
- Because of those false alarms, speech-like sound never raises a score by itself. The server uses it only to support a long silent pause followed by a correct answer on a hard question (`backend/services/audio.py`); otherwise the candidate and the reviewer see it as "not counted".
- No audio leaves the phone. Every 5 s the page keeps a yes/no and the voiced seconds, and sends an event only for a yes.

Datasets: K. J. Piczak, ESC-50 (ACM MM 2015, CC BY-NC 3.0); D. Snyder, G. Chen, D. Povey, MUSAN (arXiv:1510.08484).

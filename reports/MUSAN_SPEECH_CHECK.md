# Check: does the detector hear real talking? (MUSAN)

1,671 windows of up to 5 s from 202 MUSAN recordings (20 speech, 10 music, 172 noise). Same detector and thresholds as the ESC-50 check; nothing was tuned on this data.

| Audio | Windows | Marked speech-like |
|---|---|---|
| Reading aloud (LibriVox) | 341 | 85% |
| Speeches and hearings (US gov) | 365 | 89% |
| Music (FMA) | 300 | 2% |
| Noise (freesound) | 426 | 6% |
| Noise (soundbible) | 239 | 10% |

- **Detection of real speech: 87%** of 5-second speech windows (per recording: lowest 28%, highest 100%).
- **False alarms on MUSAN noise: 8%**, on music: 2%.

## Speech in harder conditions

| Condition | Speech windows detected |
|---|---|
| Clean recording | 87% |
| mixed with home noise, 10 dB | 79% |
| mixed with home noise, 0 dB | 41% |
| 20 dB quieter (across the room) | 73% |

## What this means for FairProctor

- The detector does hear people talking (87% of speech windows), so it is not useless. But it also fires on 23% of ESC-50 home and street sounds and 8% of MUSAN noise. Music alone is rarely marked (2%), but a TV is mostly people talking (news, serials, cricket commentary), and that is detected exactly like a helper's voice.
- Speech 20 dB quieter (across the room) is still caught 73% of the time, because the rule is relative to the room's own background. The detector cannot tell *who* is talking or to whom: a helper reading out answers and a parent on the phone in the next room look the same. In a loud home (0 dB) it misses most speech, so silence from the detector proves nothing either.
- Whispering is mostly unvoiced, and MUSAN has no whispered speech, so detection of whispering is unmeasured and probably low. The system must not be described as catching whispered help.
- So the rule stays: audio is opt-in, runs on the phone, sends only seconds of speech-like sound, and can only **support** another signal (a silent pause on screen followed by a fast correct answer on a hard item). On its own it never raises the priority, and the candidate sees it under "not counted".

Dataset: D. Snyder, G. Chen, D. Povey, MUSAN: A Music, Speech, and Noise Corpus, arXiv:1510.08484 (2015). Creative Commons / US public domain; per-file attribution in the corpus LICENSE files.

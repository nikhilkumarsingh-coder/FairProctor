# Check: would everyday noise be mistaken for talking? (ESC-50)

500 clips of 5 s from 50 sound types (ESC-50, CC BY-NC 3.0). ESC-50 contains **no speech**, so every clip marked speech-like is a false alarm.

The detector is deliberately simple so it can run in a phone browser without sending audio anywhere. It marks a clip speech-like only when five things hold together: loud enough above the room's own background, voiced in the human pitch range, a syllable-like 2–8 Hz rhythm, moving pitch (intonation), and short voiced bursts.

**Overall false-alarm rate: 23%** (114 of 500 clips).

| Group | False alarms |
|---|---|
| Animals | 46% (46/100) |
| Nature | 15% (15/100) |
| Human, not speech | 26% (26/100) |
| Inside the home | 17% (17/100) |
| Outside / traffic | 10% (10/100) |

## Sounds most often mistaken for talking

| Sound | Clips | Marked speech-like |
|---|---|---|
| rooster | 10 | 90% |
| dog | 10 | 70% |
| laughing | 10 | 70% |
| sneezing | 10 | 60% |
| clock alarm | 10 | 60% |
| hen | 10 | 50% |
| cow | 10 | 50% |
| coughing | 10 | 50% |
| water drops | 10 | 50% |
| insects | 10 | 40% |
| frog | 10 | 40% |
| pig | 10 | 40% |

Never mistaken (14 sound types): brushing teeth, airplane, crackling fire, clapping, fireworks, footsteps, helicopter, engine, sea waves, rain, train, vacuum cleaner, washing machine, wind.

## What this means for FairProctor

- Even a careful five-part rule mistakes about 23% of ordinary home and street sounds for talking. Steady sounds were rarely or never mistaken (washing machine, vacuum cleaner, engine, train, helicopter, airplane, rain, wind, sea waves: 5% or less), but the sounds of a lived-in home often were: rooster, dog, laughing, sneezing, clock alarm, hen.
- A shared home has all of these. A phone-side sound detector therefore cannot tell "someone is helping" from "the rooster outside" or "a sibling laughing", and treating it as evidence would punish exactly the candidates this project protects.
- So audio, if used at all, stays opt-in, runs on the phone, sends only seconds of speech-like sound, and can only **support** a timing signal (for example, speech-like sound during a silent pause followed by a correct answer). On its own it is never evidence, and the candidate sees it listed under "not counted" when nothing else lines up.
- ESC-50 has no speech, so detection of real talking is measured separately on MUSAN (`analysis/musan_speech_check.py`); whispering still needs own recordings (`--speech`).

Dataset: K. J. Piczak, ESC: Dataset for Environmental Sound Classification, ACM Multimedia 2015.

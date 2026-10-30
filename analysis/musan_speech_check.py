"""Does the phone-side "speech-like sound" detector actually hear people talking?

ESC-50 (see esc50_noise_check.py) has no speech, so it only measures false alarms.
MUSAN (D. Snyder, G. Chen, D. Povey, 2015; arXiv:1510.08484; Creative Commons / US public
domain, no non-commercial restriction) has real speech, music and noise, so it measures
both sides with the *same* detector and the *same* thresholds:

  * speech/librivox  - people reading books aloud (many voices, home microphones)
  * speech/us-gov    - US government speeches and hearings (room recordings)
  * music/fma        - music, some with vocals (stands in for a TV or radio in the room)
  * noise/*          - everyday noises (freesound.org, soundbible.com)

Every recording is cut into 5-second windows (the same unit as an ESC-50 clip); long
recordings are capped so one file cannot dominate. Speech is also re-tested mixed with
real MUSAN noise (10 dB and 0 dB SNR, a noisy shared home) and turned down by 20 dB
(someone talking across the room).

    python analysis/musan_speech_check.py path/to/musan

Works on the whole corpus or any sample of it. Writes reports/MUSAN_SPEECH_CHECK.md.
"""
import glob
import importlib.util
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("esc50_noise_check", os.path.join(HERE, "esc50_noise_check.py"))
det = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(det)

WIN = 5 * det.SR
MIN_LEN = 2 * det.SR
CAP = {"speech": 40, "music": 30, "noise": 20}   # max windows per recording
SOURCE = {"librivox": "Reading aloud (LibriVox)", "us-gov": "Speeches and hearings (US gov)",
          "fma": "Music (FMA)", "free-sound": "Noise (freesound)", "sound-bible": "Noise (soundbible)"}


def windows(x, cap):
    if len(x) < MIN_LEN:
        return []
    starts = list(range(0, max(len(x) - MIN_LEN, 0) + 1, WIN))
    if len(starts) > cap:
        starts = [starts[i] for i in np.linspace(0, len(starts) - 1, cap).astype(int)]
    return [x[s:s + WIN] for s in starts]


def rms(x):
    return float(np.sqrt(np.mean(x ** 2) + 1e-12))


def mix(speech, noise, snr_db, rng):
    if len(noise) < len(speech):
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    s0 = rng.integers(0, len(noise) - len(speech) + 1)
    n = noise[s0:s0 + len(speech)]
    n = n * rms(speech) / (rms(n) * 10 ** (snr_db / 20))
    y = speech + n
    return y / max(1.0, float(np.abs(y).max()))


def main(root):
    rng = np.random.default_rng(7)
    rows, speech_w, noise_pool = [], [], []
    for kind in ("speech", "music", "noise"):
        for path in sorted(glob.glob(os.path.join(root, kind, "*", "*.wav"))):
            src = os.path.basename(os.path.dirname(path))
            x = det.load(path)
            for i, w in enumerate(windows(x, CAP[kind])):
                f = det.features(w)
                if not f:
                    continue
                rows.append(dict(f, kind=kind, source=src, file=os.path.basename(path), win=i,
                                 speech_like=det.is_speech_like(f)))
                if kind == "speech":
                    speech_w.append(w)
                elif kind == "noise" and len(w) >= MIN_LEN and rms(w) > 1e-3:
                    noise_pool.append(w)
    d = pd.DataFrame(rows)
    if d.empty:
        sys.exit(f"No MUSAN wav files found under {root}")

    hard = []
    if speech_w and noise_pool:
        for w in speech_w:
            nz = noise_pool[rng.integers(len(noise_pool))]
            for cond, y in (("mixed with home noise, 10 dB", mix(w, nz, 10, rng)),
                            ("mixed with home noise, 0 dB", mix(w, nz, 0, rng)),
                            ("20 dB quieter (across the room)", w * 0.1)):
                f = det.features(y)
                if f:
                    hard.append(dict(cond=cond, speech_like=det.is_speech_like(f)))
    h = pd.DataFrame(hard)

    pct = lambda v: f"{100 * v:.0f}%"
    sp, mu, no = d[d.kind == "speech"], d[d.kind == "music"], d[d.kind == "noise"]
    by_file = sp.groupby("file").speech_like.mean()
    lines = [
        "# Check: does the detector hear real talking? (MUSAN)",
        "",
        f"{len(d):,} windows of up to 5 s from {d.file.nunique()} MUSAN recordings "
        f"({sp.file.nunique()} speech, {mu.file.nunique()} music, {no.file.nunique()} noise). "
        "Same detector and thresholds as the ESC-50 check; nothing was tuned on this data.",
        "",
        "| Audio | Windows | Marked speech-like |",
        "|---|---|---|",
    ]
    for src, g in d.groupby("source", sort=False):
        lines.append(f"| {SOURCE.get(src, src)} | {len(g):,} | {pct(g.speech_like.mean())} |")
    lines += [
        "",
        f"- **Detection of real speech: {pct(sp.speech_like.mean())}** of 5-second speech windows "
        f"(per recording: lowest {pct(by_file.min())}, highest {pct(by_file.max())}).",
        f"- **False alarms on MUSAN noise: {pct(no.speech_like.mean())}**, on music: {pct(mu.speech_like.mean())}.",
        "",
    ]
    if not h.empty:
        lines += ["## Speech in harder conditions", "", "| Condition | Speech windows detected |", "|---|---|",
                  f"| Clean recording | {pct(sp.speech_like.mean())} |"]
        for c, g in h.groupby("cond", sort=False):
            lines.append(f"| {c} | {pct(g.speech_like.mean())} |")
        lines.append("")

    esc = os.path.join("reports", "esc50_clip_results.csv")
    esc_fa = pd.read_csv(esc).speech_like.mean() if os.path.exists(esc) else None
    music_note = (f"Music alone is rarely marked ({pct(mu.speech_like.mean())}), but a TV is mostly people talking (news, "
                  "serials, cricket commentary), and that is detected exactly like a helper's voice."
                  if mu.speech_like.mean() < 0.1 else
                  f"Music is marked speech-like {pct(mu.speech_like.mean())} of the time, so a TV, radio or a song in the "
                  "next room looks like talking.")
    lines += [
        "## What this means for FairProctor",
        "",
        f"- The detector does hear people talking ({pct(sp.speech_like.mean())} of speech windows), so it is not useless. "
        + (f"But it also fires on {pct(esc_fa)} of ESC-50 home and street sounds and {pct(no.speech_like.mean())} of MUSAN "
           "noise. " if esc_fa is not None else f"But it also fires on {pct(no.speech_like.mean())} of MUSAN noise. ")
        + music_note,
        (f"- Speech 20 dB quieter (across the room) is still caught {pct(h[h.cond.str.startswith('20 dB')].speech_like.mean())} "
         "of the time, because the rule is relative to the room's own background. " if not h.empty else "- ")
        + "The detector cannot tell *who* is talking or to whom: a helper reading out answers and a parent on the phone in "
          "the next room look the same. In a loud home (0 dB) it misses most speech, so silence from the detector proves "
          "nothing either.",
        "- Whispering is mostly unvoiced, and MUSAN has no whispered speech, so detection of whispering is unmeasured and "
          "probably low. The system must not be described as catching whispered help.",
        "- So the rule stays: audio is opt-in, runs on the phone, sends only seconds of speech-like sound, and can only "
          "**support** another signal (a silent pause on screen followed by a fast correct answer on a hard item). "
          "On its own it never raises the priority, and the candidate sees it under \"not counted\".",
        "",
        "Dataset: D. Snyder, G. Chen, D. Povey, MUSAN: A Music, Speech, and Noise Corpus, arXiv:1510.08484 (2015). "
        "Creative Commons / US public domain; per-file attribution in the corpus LICENSE files.",
        "",
    ]
    os.makedirs("reports", exist_ok=True)
    with open("reports/MUSAN_SPEECH_CHECK.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    d.to_csv("reports/musan_window_results.csv", index=False)
    print("\n".join(lines))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/external/musan")

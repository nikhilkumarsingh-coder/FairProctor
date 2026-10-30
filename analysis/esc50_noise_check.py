"""Would everyday noise be mistaken for someone talking?

Tests a lightweight, phone-friendly "speech-like sound" detector on ESC-50
(K. J. Piczak, 2015; 2,000 five-second environmental clips in 50 classes;
CC BY-NC 3.0, ESC-10 subset CC BY). ESC-50 contains NO speech, so every clip the
detector marks as speech-like is a false alarm. Recall on real speech must be
measured separately with recordings of talking / whispering (see the report).

The detector uses only cheap signal features that run in a browser on a phone
(Web Audio), never transmits audio, and outputs a yes/no plus seconds:
  1. active frames: loudness at least 10 dB above the clip's own noise floor
  2. voiced frames: clear periodicity in the human pitch range (80-400 Hz)
  3. syllable rhythm: loudness envelope modulated at 2-8 Hz, like syllables
  4. pitch movement: pitch varies like intonation, not a fixed tone (alarm, siren, engine)
  5. short voiced bursts: voiced runs mostly shorter than 0.6 s, like syllables
A clip is "speech-like" only when all five hold.

    python analysis/esc50_noise_check.py path/to/ESC-50-master [--speech path/to/own/recordings]
"""
import argparse
import glob
import os

import numpy as np
import pandas as pd
from scipy.io import wavfile
from scipy.signal import resample_poly

SR = 16000
FRAME, HOP = 512, 256          # 32 ms frames, 16 ms hop
F0_MIN, F0_MAX = 80, 400


def load(path):
    sr, x = wavfile.read(path)
    x = x.astype(np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if np.abs(x).max() > 1.5:
        x /= 32768.0
    if sr != SR:
        g = np.gcd(sr, SR)
        x = resample_poly(x, SR // g, sr // g).astype(np.float32)
    return x


def features(x):
    n = 1 + max(0, (len(x) - FRAME) // HOP)
    if n < 10:
        return None
    idx = np.arange(FRAME)[None, :] + HOP * np.arange(n)[:, None]
    fr = x[idx] * np.hanning(FRAME)[None, :]
    rms = np.sqrt((fr ** 2).mean(axis=1) + 1e-12)
    db = 20 * np.log10(rms)
    floor = np.percentile(db, 10)
    active = (db > floor + 10) & (db > -50)
    # periodicity via normalised autocorrelation in the pitch range
    lo, hi = SR // F0_MAX, SR // F0_MIN
    spec = np.fft.rfft(fr, 2 * FRAME, axis=1)
    ac = np.fft.irfft(np.abs(spec) ** 2, axis=1)[:, :FRAME]
    ac = ac / (ac[:, :1] + 1e-12)
    lag = lo + np.argmax(ac[:, lo:hi], axis=1)
    peak = ac[np.arange(n), lag]
    voiced = active & (peak > 0.45)
    f0 = SR / lag
    # syllable rhythm: share of envelope modulation energy at 2-8 Hz
    env = rms[active] if active.sum() > 8 else rms
    env = env - env.mean()
    m = np.abs(np.fft.rfft(env, 512)) ** 2
    fm = np.fft.rfftfreq(512, d=HOP / SR)
    band = m[(fm >= 2) & (fm <= 8)].sum() / (m[(fm > 0.5) & (fm <= 30)].sum() + 1e-12)
    # pitch movement within voiced runs
    runs, cur = [], []
    for i in range(n):
        if voiced[i]:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    lens = np.array([len(r) * HOP / SR for r in runs]) if runs else np.array([])
    movs = [np.std(np.log(f0[r])) for r in runs if len(r) >= 4]
    pitch_move = float(np.median(movs)) if movs else 0.0
    return dict(active_s=active.sum() * HOP / SR, voiced_frac=voiced.sum() / max(active.sum(), 1),
                syllable_rhythm=band, pitch_move=pitch_move,
                short_runs=float((lens < 0.6).mean()) if len(lens) else 0.0, n_runs=len(runs),
                voiced_s=voiced.sum() * HOP / SR)


def is_speech_like(f):
    return (f["voiced_frac"] >= 0.30 and f["syllable_rhythm"] >= 0.30 and 0.02 <= f["pitch_move"] <= 0.35
            and f["short_runs"] >= 0.6 and f["n_runs"] >= 3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("esc50")
    ap.add_argument("--speech", help="folder of your own speech recordings (wav), to measure detection")
    a = ap.parse_args()
    meta = pd.read_csv(os.path.join(a.esc50, "meta", "esc50.csv"))
    rows = []
    for _, r in meta.iterrows():
        p = os.path.join(a.esc50, "audio", r.filename)
        if not os.path.exists(p):
            continue
        f = features(load(p))
        if f:
            rows.append(dict(f, category=r.category, file=r.filename, speech_like=is_speech_like(f)))
    d = pd.DataFrame(rows)
    by = d.groupby("category").agg(clips=("file", "size"), false_alarm=("speech_like", "mean"),
                                   voiced=("voiced_frac", "mean")).sort_values("false_alarm", ascending=False)
    groups = {
        "Animals": ["dog", "rooster", "pig", "cow", "frog", "cat", "hen", "insects", "sheep", "crow"],
        "Nature": ["rain", "sea_waves", "crackling_fire", "crickets", "chirping_birds", "water_drops", "wind",
                   "pouring_water", "toilet_flush", "thunderstorm"],
        "Human, not speech": ["crying_baby", "sneezing", "clapping", "breathing", "coughing", "footsteps",
                              "laughing", "brushing_teeth", "snoring", "drinking_sipping"],
        "Inside the home": ["door_wood_knock", "mouse_click", "keyboard_typing", "door_wood_creaks", "can_opening",
                            "washing_machine", "vacuum_cleaner", "clock_alarm", "clock_tick", "glass_breaking"],
        "Outside / traffic": ["helicopter", "chainsaw", "siren", "car_horn", "engine", "train", "church_bells",
                              "airplane", "fireworks", "hand_saw"],
    }
    pct = lambda v: f"{100 * v:.0f}%"
    lines = [
        "# Check: would everyday noise be mistaken for talking? (ESC-50)",
        "",
        f"{len(d)} clips of 5 s from {d.category.nunique()} sound types (ESC-50, CC BY-NC 3.0). ESC-50 contains **no speech**, "
        "so every clip marked speech-like is a false alarm.",
        "",
        "The detector is deliberately simple so it can run in a phone browser without sending audio anywhere. It marks a clip "
        "speech-like only when five things hold together: loud enough above the room's own background, voiced in the human "
        "pitch range, a syllable-like 2–8 Hz rhythm, moving pitch (intonation), and short voiced bursts.",
        "",
        f"**Overall false-alarm rate: {pct(d.speech_like.mean())}** ({int(d.speech_like.sum())} of {len(d)} clips).",
        "",
        "| Group | False alarms |",
        "|---|---|",
    ]
    for g, cats in groups.items():
        sub = d[d.category.isin(cats)]
        if len(sub):
            lines.append(f"| {g} | {pct(sub.speech_like.mean())} ({int(sub.speech_like.sum())}/{len(sub)}) |")
    worst = by[by.false_alarm > 0]
    lines += ["", "## Sounds most often mistaken for talking", "", "| Sound | Clips | Marked speech-like |", "|---|---|---|"]
    for c, r in worst.head(12).iterrows():
        lines.append(f"| {c.replace('_', ' ')} | {int(r.clips)} | {pct(r.false_alarm)} |")
    clean = [c.replace('_', ' ') for c, r in by.iterrows() if r.false_alarm == 0]
    lines += ["", f"Never mistaken ({len(clean)} sound types): " + ", ".join(clean) + ".", ""]

    if a.speech:
        if not glob.glob(os.path.join(a.speech, "*.wav")):
            print(f"WARNING: no .wav files in {a.speech}; the 'Own speech recordings' section is skipped.")
        sp = []
        for p in sorted(glob.glob(os.path.join(a.speech, "*.wav"))):
            f = features(load(p))
            if f:
                sp.append(dict(f, file=os.path.basename(p), speech_like=is_speech_like(f)))
        if sp:
            s = pd.DataFrame(sp)
            lines += ["## Own speech recordings", "", "| Recording | Marked speech-like | Voiced seconds |", "|---|---|---|"]
            lines += [f"| {r.file} | {'yes' if r.speech_like else 'no'} | {r.voiced_s:.1f} |" for r in s.itertuples()]
            lines.append("")

    steady = ["washing_machine", "vacuum_cleaner", "engine", "train", "helicopter", "airplane", "rain", "wind", "sea_waves"]
    rate = by.false_alarm
    low = [c.replace("_", " ") for c in steady if c in rate.index and rate[c] <= 0.05]
    top = [c.replace("_", " ") for c in rate.sort_values(ascending=False).index[:6]]
    lines += [
        "## What this means for FairProctor",
        "",
        f"- Even a careful five-part rule mistakes about {pct(d.speech_like.mean())} of ordinary home and street sounds for "
        "talking. "
        + (f"Steady sounds were rarely or never mistaken ({', '.join(low)}: 5% or less), but " if low else "")
        + f"the sounds of a lived-in home often were: {', '.join(top)}.",
        "- A shared home has all of these. A phone-side sound detector therefore cannot tell \"someone is helping\" from "
        "\"the rooster outside\" or \"a sibling laughing\", and treating it as evidence would punish exactly the candidates "
        "this project protects.",
        "- So audio, if used at all, stays opt-in, runs on the phone, sends only seconds of speech-like sound, and can only "
        "**support** a timing signal (for example, speech-like sound during a silent pause followed by a correct answer). "
        "On its own it is never evidence, and the candidate sees it listed under \"not counted\" when nothing else lines up.",
        "- ESC-50 has no speech, so detection of real talking is measured separately on MUSAN "
        "(`analysis/musan_speech_check.py`); whispering still needs own recordings (`--speech`).",
        "",
        "Dataset: K. J. Piczak, ESC: Dataset for Environmental Sound Classification, ACM Multimedia 2015.",
        "",
    ]
    os.makedirs("reports", exist_ok=True)
    with open("reports/ESC50_NOISE_CHECK.md", "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print("\n".join(lines))
    d.to_csv("reports/esc50_clip_results.csv", index=False)


if __name__ == "__main__":
    main()

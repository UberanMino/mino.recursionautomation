#!/usr/bin/env python3
"""Beat / energy analysis for mino.recursion edits (numpy only).

Usage: python3 engine/analyze_audio.py assets/audio/song.wav build/analysis/song.json

Output JSON:
  bpm, duration, beats[], downbeats[], bars[{t, energy}],
  drops[{t, score}]           -> bar times where energy jumps (best hook starts)
  frames{fps, bass[], mid[], high[], onset[], rms[]}  -> 0..1, one value per video frame
"""
import json
import subprocess
import sys

import numpy as np

SR = 22050
HOP = 512
NFFT = 2048
VIDEO_FPS = 30


def load_mono(path):
    raw = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
        check=True, capture_output=True,
    ).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def stft_mag(y):
    win = np.hanning(NFFT).astype(np.float32)
    n = 1 + (len(y) - NFFT) // HOP
    idx = np.arange(NFFT)[None, :] + HOP * np.arange(n)[:, None]
    frames = y[idx] * win
    return np.abs(np.fft.rfft(frames, axis=1)).astype(np.float32)  # (n, NFFT/2+1)


def band(mag, lo, hi):
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
    sel = (freqs >= lo) & (freqs < hi)
    return mag[:, sel].sum(axis=1)


def norm01(x, pct=98):
    x = np.asarray(x, dtype=np.float64)
    lo = np.percentile(x, 2)
    hi = np.percentile(x, pct)
    return np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1)


def smooth(x, n):
    if n <= 1:
        return x
    k = np.hanning(n + 2)[1:-1]
    k /= k.sum()
    return np.convolve(x, k, mode="same")


def estimate_tempo(onset, fps):
    o = onset - onset.mean()
    ac = np.correlate(o, o, mode="full")[len(o) - 1:]
    bpms = np.arange(70.0, 200.0, 0.25)
    scores = []
    for bpm in bpms:
        lag = 60.0 * fps / bpm
        s = 0.0
        # combine harmonics so half/double tempo agree
        for mult, w in ((1, 1.0), (2, 0.5), (4, 0.25)):
            l = lag * mult
            i = int(l)
            if i + 1 < len(ac):
                f = l - i
                s += w * ((1 - f) * ac[i] + f * ac[i + 1])
        # log-gaussian prior around 140 bpm (trance / hard house)
        prior = np.exp(-0.5 * (np.log2(bpm / 140.0) / 0.9) ** 2)
        scores.append(s * prior)
    bpm = float(bpms[int(np.argmax(scores))])
    # fold into the 110..180 range the channel's genres live in
    while bpm < 110:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return bpm


def track_beats(onset, fps, bpm, tightness=120.0):
    """Ellis (2007) dynamic-programming beat tracker."""
    period = 60.0 * fps / bpm
    n = len(onset)
    score = onset.astype(np.float64).copy()
    back = np.full(n, -1)
    lo, hi = int(round(period / 2)), int(round(period * 2))
    for i in range(n):
        start = max(0, i - hi)
        end = i - lo
        if end <= start:
            continue
        prev = np.arange(start, end)
        pen = -tightness * (np.log((i - prev) / period)) ** 2
        cand = score[prev] + pen
        j = int(np.argmax(cand))
        score[i] += cand[j]
        back[i] = prev[j]
    # best end point in last period
    tail = max(0, n - int(period))
    i = tail + int(np.argmax(score[tail:]))
    beats = []
    while i >= 0:
        beats.append(i)
        i = back[i]
    return np.array(beats[::-1])


def main(src, dst):
    y = load_mono(src)
    duration = len(y) / SR
    mag = stft_mag(y)
    fps = SR / HOP
    logmag = np.log1p(mag * 10)

    flux = np.maximum(np.diff(logmag, axis=0, prepend=logmag[:1]), 0)
    freqs = np.fft.rfftfreq(NFFT, 1.0 / SR)
    onset = flux.sum(axis=1)
    kick = flux[:, (freqs >= 30) & (freqs < 150)].sum(axis=1)
    onset = smooth(onset, 3)
    onset_n = onset / (onset.std() + 1e-9)

    bpm = estimate_tempo(onset_n, fps)
    beat_idx = track_beats(onset_n, fps, bpm)
    beats = beat_idx / fps

    # refine tempo from tracked beats (median IBI of the steady part)
    ibi = np.diff(beats)
    if len(ibi) > 8:
        bpm = float(60.0 / np.median(ibi))

    # downbeat phase: which of 4 beat phases carries the most kick energy
    kick_n = kick / (kick.max() + 1e-9)
    phase_energy = [kick_n[beat_idx[p::4]].mean() if len(beat_idx[p::4]) else 0 for p in range(4)]
    phase = int(np.argmax(phase_energy))
    downbeats = beats[phase::4]

    rms = np.sqrt((mag ** 2).mean(axis=1))
    bass = band(mag, 30, 150)
    mid = band(mag, 150, 2500)
    high = band(mag, 2500, 11000)

    # bar energies and drop detection
    bars = []
    for i, t in enumerate(downbeats):
        t2 = downbeats[i + 1] if i + 1 < len(downbeats) else duration
        a, b = int(t * fps), max(int(t2 * fps), int(t * fps) + 1)
        bars.append({"t": round(float(t), 4), "energy": float(rms[a:b].mean()), "bass": float(bass[a:b].mean())})
    e = np.array([b["energy"] for b in bars]) if bars else np.zeros(0)
    bb = np.array([b["bass"] for b in bars]) if bars else np.zeros(0)
    drops = []
    if len(e) > 8:
        en = norm01(e)
        bn = norm01(bb)
        for i in range(4, len(e) - 4):
            before = (en[i - 4:i].mean() + bn[i - 4:i].mean()) / 2
            after = (en[i:i + 4].mean() + bn[i:i + 4].mean()) / 2
            jump = after - before
            if jump > 0.15 and after > 0.55:
                drops.append({"t": bars[i]["t"], "bar": i, "score": round(float(jump * after), 4)})
        # keep local maxima, strongest first
        drops.sort(key=lambda d: -d["score"])
        kept = []
        for d in drops:
            if all(abs(d["bar"] - k["bar"]) >= 8 for k in kept):
                kept.append(d)
        drops = kept
        for i, b in enumerate(bars):
            b["energy_n"] = round(float(en[i]), 4)

    # per-video-frame features
    nvf = int(duration * VIDEO_FPS)
    tv = np.arange(nvf) / VIDEO_FPS
    ta = np.arange(len(rms)) / fps

    def resample(x, sm=1):
        x = smooth(np.asarray(x, dtype=np.float64), sm)
        return np.round(np.interp(tv, ta, x), 4).tolist()

    out = {
        "source": src,
        "duration": round(duration, 3),
        "bpm": round(bpm, 2),
        "beats": [round(float(b), 4) for b in beats],
        "downbeats": [round(float(b), 4) for b in downbeats],
        "bars": bars,
        "drops": drops,
        "frames": {
            "fps": VIDEO_FPS,
            "bass": resample(norm01(np.log1p(bass)), 3),
            "mid": resample(norm01(np.log1p(mid)), 3),
            "high": resample(norm01(np.log1p(high)), 3),
            "onset": resample(norm01(onset), 1),
            "kick": resample(norm01(kick), 1),
            "rms": resample(norm01(rms), 5),
        },
    }
    with open(dst, "w") as f:
        json.dump(out, f)
    print(json.dumps({k: out[k] for k in ("duration", "bpm")}), "beats", len(beats), "bars", len(bars),
          "drops", [(d["t"], d["score"]) for d in drops[:6]])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

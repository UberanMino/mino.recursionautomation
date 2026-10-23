"""Control signals at video rate, sorted by time scale.

Principle (rule T): a visual quantity is only driven by musical quantities of the same time
scale, and *changes* in the music drive *motion*, levels drive *appearance*.

  impulse  (< 100 ms)   onsets: kick / snare / hat, with loudness      -> thrust, flash, ribs, shake
  beat     (~ 0.4 s)    band loudness (fast envelope), timbre speed     -> brightness, colour drift
  bar      (~ 1.6 s)    loudness, harmonic share, stereo balance,
                        pitch movement, chaos                           -> speed, turning, trails, blur
  section  (8-32 bars)  novelty boundaries, kind (break/build/drop/groove),
                        tension of build-ups                            -> helix direction, roll, symmetry
"""
from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import gaussian_filter1d, maximum_filter1d, uniform_filter1d

from .features import FPS_A, one_pole, pnorm
from .rules import Rules, envelope, psi

BANDS = {"sub": (30, 60), "bass": (60, 250), "low": (250, 1000), "high": (1000, 4000), "air": (4000, 16000)}
CLASSES = {"kick": (30, 90), "snare": (1000, 4000), "hat": (6000, 16000)}
GOLDEN = np.pi * (3 - np.sqrt(5))          # 137.5 deg: successive sections turn as differently as possible


@dataclass
class Signals:
    fps: float
    n: int
    bar_s: float
    beats: np.ndarray
    downbeats: np.ndarray
    sections: list
    a: dict = field(default_factory=dict)      # per-video-frame arrays
    hits: dict = field(default_factory=dict)   # onset class -> [m, 3]: t, f, psi


def _to_video(x, edges, how):
    lo = np.minimum(edges[:-1], len(x) - 1)
    if how == "max":
        return np.maximum.reduceat(x, lo, axis=0)
    s = np.add.reduceat(x, lo, axis=0)
    cnt = np.maximum(np.diff(np.minimum(edges, len(x))), 1)
    return s / cnt.reshape((-1,) + (1,) * (x.ndim - 1))


def _trailing_slope(x, win):
    """(mean of the last quarter of the window - mean of its first quarter) / (3/4 window), per frame."""
    q = max(1, win // 4)
    m = uniform_filter1d(x, q, origin=(q - 1) // 2)       # trailing mean over q frames
    prev = np.concatenate([np.full(win - q, m[0]), m[:-(win - q)]])
    return (m - prev) / (0.75 * win)


def _hits_from_grid(lin, fr, lo, hi, r, ref_db, rise_db=6.0, min_gap=0.09):
    """Onsets of one drum class from the (time-sharpened) spectrum: peaks of the level rise in
    its band over 40 ms, at least rise_db, at least min_gap apart. Returns [m, 3]: t, f, psi."""
    sel = (fr >= lo) & (fr < hi)
    L = 10 * np.log10(lin[:, sel].mean(1) + 1e-20)
    prev = np.minimum.reduce([np.roll(L, i) for i in range(1, 5)])
    o = L - prev
    o[:5] = 0
    g = int(min_gap * FPS_A)
    pk = np.nonzero((o == maximum_filter1d(o, 2 * g + 1)) & (o > rise_db) & (L > ref_db - 35))[0]
    fc = float(np.sqrt(fr[sel][0] * fr[sel][-1]))
    out = []
    for i in pk:
        j = i
        while j > 0 and L[j - 1] < L[j] - 0.5 and i - j < 4:   # walk back to the start of the rise
            j -= 1
        lvl = L[i:i + 6].max()
        out.append([(j + 1) / FPS_A, fc, float(psi(lvl, ref_db, r))])
    return np.array(out, dtype=np.float64).reshape(-1, 3)


def sections_from(F, beat_vec, beats, downbeats, bar_s, min_bars=4):
    """Foote novelty on the beat-synchronous self-similarity matrix, peaks snapped to downbeats."""
    X = (beat_vec - beat_vec.mean(0)) / (beat_vec.std(0) + 1e-9)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-9
    S = X @ X.T
    L = 8
    g = np.exp(-0.5 * (np.arange(-L, L) + 0.5) ** 2 / (L / 2) ** 2)
    sign = np.sign(np.arange(-L, L) + 0.5)
    ker = np.outer(g * sign, g * sign)                     # checkerboard: +same block, -cross block
    n = len(S)
    nov = np.zeros(n)
    Sp = np.pad(S, L, mode="edge")
    for i in range(n):
        nov[i] = (Sp[i:i + 2 * L, i:i + 2 * L] * ker).sum()
    nov = np.maximum(nov, 0)
    pk = (nov == maximum_filter1d(nov, 4 * min_bars + 1)) & (nov > nov.mean() + 0.5 * nov.std())
    bounds = [0.0]
    for i in np.nonzero(pk)[0]:
        t = beats[i]
        d = downbeats[np.argmin(np.abs(downbeats - t))] if len(downbeats) else t
        if d - bounds[-1] >= min_bars * bar_s * 0.95:
            bounds.append(float(d))
    bounds.append(float(F.duration))
    return bounds, nov


def compute(F, r: Rules, fps=30):
    n = int(F.duration * fps)
    edges = np.ceil(np.arange(n + 1) / fps * FPS_A).astype(int)
    bar_s = 240.0 / F.bpm
    t = np.arange(n) / fps
    a = {}

    lin_l = 10 ** (F.db_l / 10)
    lin_r = 10 ** (F.db_r / 10)
    lin = 0.5 * (lin_l + lin_r)
    fr = F.freqs

    # beat scale: band loudness, instant attack (R3)
    for name, (lo, hi) in BANDS.items():
        sel = (fr >= lo) & (fr < hi)
        p = envelope(psi(10 * np.log10(lin[:, sel].mean(1) + 1e-20), F.ref_db, r)[:, None].astype(np.float32),
                     FPS_A, r)[:, 0]
        a["psi_" + name] = _to_video(p, edges, "max")
    tot = 10 * np.log10(lin.mean(1) + 1e-20)

    # full spectral profile per video frame (for the world geometry)
    a["prof_l"] = _to_video(envelope(psi(F.db_l, F.ref_db, r).astype(np.float32), FPS_A, r), edges, "max")
    a["prof_r"] = _to_video(envelope(psi(F.db_r, F.ref_db, r).astype(np.float32), FPS_A, r), edges, "max")
    a["harm"] = _to_video(F.harm, edges, "mean")
    a["z_h"] = _to_video(F.timbre_h, edges, "mean")
    a["z_p"] = _to_video(F.timbre_p, edges, "mean")
    a["chaos"] = _to_video(F.chaos, edges, "mean")

    # bar scale
    loud = one_pole(tot, bar_s / 4, bar_s / 2)
    a["loud_bar"] = _to_video(pnorm(loud, 5, 97), edges, "mean")
    hw = (F.harm * lin).sum(1) / (lin.sum(1) + 1e-20)
    a["harm_bar"] = _to_video(uniform_filter1d(hw, int(bar_s * FPS_A)), edges, "mean")
    bal = (lin_r.mean(1) - lin_l.mean(1)) / (lin_r.mean(1) + lin_l.mean(1) + 1e-20)
    a["balance"] = _to_video(uniform_filter1d(bal, int(bar_s * FPS_A)), edges, "mean")
    cen = np.log2(np.maximum(F.extra["centroid_h"], 50) / 1000.0)
    cen = gaussian_filter1d(cen, bar_s / 4 * FPS_A)
    a["pitch_rate"] = _to_video(np.gradient(cen) * FPS_A * bar_s, edges, "mean")     # octaves per bar
    zs = gaussian_filter1d(F.timbre_h, bar_s / 8 * FPS_A, axis=0)
    a["timbre_speed"] = _to_video(pnorm(np.linalg.norm(np.gradient(zs, axis=0), axis=1), 5, 98), edges, "mean")
    sharp = 0.5 * pnorm(F.timbre_h[:, 0]) + 0.5 * (1 - pnorm(hw))
    a["sharpness"] = _to_video(gaussian_filter1d(sharp, bar_s / 4 * FPS_A), edges, "mean")

    # tension: rising loudness, rising brightness, rising noise over the last 4 bars (build-ups)
    win = int(4 * bar_s * FPS_A)
    s_l = np.maximum(_trailing_slope(tot, win), 0)
    s_c = np.maximum(_trailing_slope(cen, win), 0)
    s_f = np.maximum(_trailing_slope(F.extra["flat"], win), 0)
    ten = 0.5 * pnorm(s_l, 50, 98) + 0.25 * pnorm(s_c, 50, 98) + 0.25 * pnorm(s_f, 50, 98)
    a["tension"] = _to_video(gaussian_filter1d(ten, bar_s / 4 * FPS_A), edges, "mean")

    # impulse scale: hits
    hits = {c: _hits_from_grid(lin, fr, lo, hi, r, F.ref_db) for c, (lo, hi) in CLASSES.items() if c != "kick"}
    # kicks: in four-on-the-floor music the kick sits on the beat and the offbeat bass shares its
    # band, so a kick = a tracked beat whose 30-60 Hz level is >= 3 dB above the level between beats
    sel = (fr >= 30) & (fr < 60)
    Lk = 10 * np.log10(lin[:, sel].mean(1) + 1e-20)
    kk = []
    for b in F.beats:
        i = int(round(b * FPS_A))
        if i < 4 or i + 30 >= len(Lk):
            continue
        on_b = Lk[i - 3:i + 9].max()
        off_b = Lk[i + 12:i + 29].min()
        if on_b - off_b > 3.0 and on_b > F.ref_db - 30:
            kk.append([b, 45.0, float(psi(on_b, F.ref_db, r))])
    hits["kick"] = np.array(kk, dtype=np.float64).reshape(-1, 3)

    beats = F.beats
    # section scale: beat-synchronous features -> novelty -> sections
    nb3 = F.db_l.shape[1] // 8
    v3 = (0.5 * (F.db_l + F.db_r))[:, :nb3 * 8].reshape(-1, nb3, 8).mean(2)
    v3 = np.maximum(v3, F.ref_db - 50)
    bidx = np.clip((beats * FPS_A).astype(int), 0, len(v3) - 1)
    bv = []
    for i in range(len(bidx)):
        j1 = bidx[i + 1] if i + 1 < len(bidx) else len(v3)
        sl = slice(bidx[i], max(j1, bidx[i] + 1))
        bv.append(np.concatenate([v3[sl].mean(0), 3 * F.timbre_h[sl].mean(0), 3 * F.timbre_p[sl].mean(0)]))
    # downbeats: the beat phase (mod 4) where the music changes most (new bar = new chord, crash, fill end)
    bva = np.array(bv)
    bvn = (bva - bva.mean(0)) / (bva.std(0) + 1e-9)
    ch = np.r_[0, np.linalg.norm(np.diff(bvn, axis=0), axis=1)]
    phase = int(np.argmax([ch[p::4].mean() for p in range(4)]))
    downbeats = beats[phase::4]
    bounds, nov = sections_from(F, np.array(bv), beats, downbeats, bar_s)
    bass_v = a["psi_bass"]
    secs = []
    for i in range(len(bounds) - 1):
        k0, k1 = int(bounds[i] * fps), max(int(bounds[i + 1] * fps), int(bounds[i] * fps) + 1)
        bm = float(bass_v[k0:k1].mean())
        lm = float(a["loud_bar"][k0:k1].mean())
        tm = float(a["tension"][k0 + (k1 - k0) // 2:k1].mean())
        secs.append({"start": bounds[i], "end": bounds[i + 1], "bass": bm, "loud": lm, "tension": tm})
    bq = np.array([s["bass"] for s in secs])
    for i, s in enumerate(secs):
        if s["bass"] >= np.percentile(bq, 55) and s["loud"] >= 0.5:
            kind = "drop"
        elif s["bass"] < max(0.15, np.percentile(bq, 30)):
            kind = "break"
        elif s["tension"] > 0.3:
            kind = "build"
        else:
            kind = "groove"
        s.update(kind=kind, index=i, dir=1 if i % 2 == 0 else -1, angle=float((i * GOLDEN) % (2 * np.pi)))
    for i, s in enumerate(secs):
        if s["kind"] == "build" and i + 1 < len(secs) and secs[i + 1]["kind"] != "drop":
            s["kind"] = "groove" if s["bass"] > 0.3 else "break"
    sec_of = np.zeros(n, int)
    for s in secs:
        sec_of[int(s["start"] * fps):int(s["end"] * fps) + 1] = s["index"]
    a["section"] = sec_of[:n]

    # tension (build-up) = approach to the next drop: (progress through the last <= 8 bars)^2,
    # plus half of the measured rise elsewhere; zero inside drops
    ramp = np.zeros(n)
    for i, s in enumerate(secs):
        if s["kind"] == "drop" and i > 0 and secs[i - 1]["kind"] != "drop":
            t1 = s["start"]
            L = min(8 * bar_s, t1 - secs[i - 1]["start"])
            k0, k1 = int((t1 - L) * fps), int(t1 * fps)
            ramp[k0:k1] = ((np.arange(k0, k1) / fps - (t1 - L)) / L) ** 2
            if secs[i - 1]["kind"] in ("break", "groove"):
                secs[i - 1]["kind"] = "build"
            s["entry"] = True
    in_drop = np.array([secs[i]["kind"] == "drop" for i in sec_of[:n]])
    a["tension"] = np.where(in_drop, 0.0, np.maximum(ramp, 0.5 * a["tension"]))
    return Signals(fps=fps, n=n, bar_s=bar_s, beats=beats, downbeats=downbeats, sections=secs, a=a, hits=hits)

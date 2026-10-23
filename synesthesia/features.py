"""Audio analysis for the music-to-visual mapping engine (numpy + scipy).

Everything is computed on one shared time grid: analysis frames every HOP samples
(10 ms), centred on their timestamp (frame i describes the audio around i*HOP/SR,
not the audio after it), so a feature at time t really belongs to the sound at t.

Output (`Features`):
  freqs[K]            centre frequencies of the log-frequency grid (1/24 octave, 30 Hz..16 kHz)
  db_l, db_r [T,K]    weighted level per channel in dB (energy per log-frequency unit + weighting)
  harm [T,K]          harmonic share 0..1 (1 = tonal/sustained, 0 = percussive/noise), HPSS
  width [T,K]         stereo width 0..1 (1 - inter-channel coherence)
  timbre_h, timbre_p [T,2]  timbre coordinates of the harmonic / percussive layer (PCA of MFCCs)
  chaos [T]           musical chaos 0..1 (+ its three components)
  onsets              percussive onsets per half-octave group: (t, group, f_centre, level_db)
  bpm, beats          tempo and beat times (beat tracker from engine/analyze_audio.py)
"""
import os
import subprocess
import sys
from dataclasses import dataclass, field

import numpy as np
from scipy.fft import dct, rfft
from scipy.ndimage import maximum_filter1d, median_filter, uniform_filter1d
from scipy.signal import butter, oaconvolve, sosfiltfilt

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine"))
from analyze_audio import estimate_tempo, track_beats  # noqa: E402  (reuse the channel engine's tracker)

SR = 44100
HOP = 441                     # 10 ms
FPS_A = SR / HOP              # 100 analysis frames per second
F_MIN, F_MAX = 30.0, 16000.0
BPO = 24                      # log-grid resolution: bins per octave
# multi-resolution STFT: long windows for the bass, short ones for the highs (constant-Q-like)
RES = (4096, 2048, 1024)
CROSS = ((300.0, 0.5), (2000.0, 0.5))  # crossover frequency, fade width in octaves
EPS = 1e-20
CHAOS_W = (0.55, 0.2, 0.25)   # weights: non-repetition, noisiness, off-grid rhythm


@dataclass
class Features:
    path: str
    duration: float
    freqs: np.ndarray
    db_l: np.ndarray
    db_r: np.ndarray
    harm: np.ndarray
    width: np.ndarray
    timbre_h: np.ndarray
    timbre_p: np.ndarray
    chaos: np.ndarray
    chaos_parts: dict
    onsets: np.ndarray            # [n, 4]: t, group, f_centre, level_db
    group_freqs: np.ndarray
    bpm: float
    beats: np.ndarray
    ref_db: float
    fps: float = FPS_A
    extra: dict = field(default_factory=dict)

    def save(self, path):
        np.savez_compressed(path, **{k: v for k, v in self.__dict__.items() if k not in ("chaos_parts", "extra")},
                            **{"cp_" + k: v for k, v in self.chaos_parts.items()},
                            **{"ex_" + k: v for k, v in self.extra.items()})

    @classmethod
    def load(cls, path):
        z = np.load(path, allow_pickle=False)
        d = {k: z[k] for k in z.files if not k.startswith(("cp_", "ex_"))}
        for k in ("path",):
            d[k] = str(d[k])
        for k in ("duration", "bpm", "ref_db", "fps"):
            d[k] = float(d[k])
        d["chaos_parts"] = {k[3:]: z[k] for k in z.files if k.startswith("cp_")}
        d["extra"] = {k[3:]: z[k] for k in z.files if k.startswith("ex_")}
        return cls(**d)


# ---------------------------------------------------------------- helpers

def load_stereo(path, sr=SR):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-ac", "2", "-ar", str(sr), "-f", "f32le", "-"],
                         check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).reshape(-1, 2).T.copy()


def stft(x, nfft, b0=0, b1=None, chunk=1500):
    """Centred STFT (frame i is centred on sample i*HOP), Hann window, bins [b0:b1].
    Returns complex64 [T, nb] scaled so that 2*|X|^2 is a one-sided power density per Hz."""
    win = np.hanning(nfft).astype(np.float32)
    scale = np.sqrt(1.0 / (SR * (win ** 2).sum()))
    n = len(x) // HOP + 1
    xp = np.pad(x, (nfft // 2, nfft // 2 + HOP), mode="reflect" if len(x) > nfft else "constant")
    b1 = nfft // 2 + 1 if b1 is None else b1
    out = np.empty((n, b1 - b0), dtype=np.complex64)
    view = np.lib.stride_tricks.sliding_window_view(xp, nfft)[::HOP][:n]
    for s in range(0, n, chunk):
        fr = view[s:s + chunk] * win
        out[s:s + chunk] = (rfft(fr, axis=1)[:, b0:b1] * scale).astype(np.complex64)
    return out


def log_grid():
    k = np.arange(int(np.floor(BPO * np.log2(F_MAX / F_MIN))) + 1)
    return F_MIN * 2.0 ** (k / BPO)


def grid_weights(freqs, nfft, b0, b1):
    """[K, b1-b0] weights that turn a linear-frequency density into the density at each log-grid bin:
    average over the FFT bins inside the 1/BPO-octave band, or linear interpolation where the band
    is narrower than one FFT bin (bass)."""
    df = SR / nfft
    fb = (np.arange(b0, b1)) * df
    w = np.zeros((len(freqs), b1 - b0), dtype=np.float32)
    half = 2.0 ** (0.5 / BPO)
    for i, f in enumerate(freqs):
        sel = np.nonzero((fb >= f / half) & (fb < f * half))[0]
        if len(sel):
            w[i, sel] = 1.0 / len(sel)
        else:
            p = f / df - b0
            j = int(np.floor(p))
            fr = p - j
            if 0 <= j < b1 - b0 - 1:
                w[i, j], w[i, j + 1] = 1 - fr, fr
    return w


def res_mix(freqs):
    """Cross-fade weights [len(RES), K] between the three resolutions (sum to 1)."""
    lf = np.log2(freqs)
    g = np.zeros((len(RES), len(freqs)))
    (c1, w1), (c2, w2) = CROSS
    a = np.clip((lf - (np.log2(c1) - w1 / 2)) / w1, 0, 1)   # 0 -> long window, 1 -> medium
    b = np.clip((lf - (np.log2(c2) - w2 / 2)) / w2, 0, 1)   # 0 -> medium, 1 -> short
    g[0] = 1 - a
    g[1] = a * (1 - b)
    g[2] = b
    return g


def weighting_db(f, curve="B"):
    """Frequency weighting (IEC 61672 A / C, and the classic B curve) in dB, 0 dB at 1 kHz."""
    f = np.asarray(f, dtype=np.float64)
    f2 = f ** 2
    if curve == "A":
        r = 12194 ** 2 * f2 ** 2 / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194 ** 2))
        return 20 * np.log10(r) + 2.00
    if curve == "B":
        r = 12194 ** 2 * f ** 3 / ((f2 + 20.6 ** 2) * np.sqrt(f2 + 158.5 ** 2) * (f2 + 12194 ** 2))
        return 20 * np.log10(r) + 0.17
    if curve == "C":
        r = 12194 ** 2 * f2 / ((f2 + 20.6 ** 2) * (f2 + 12194 ** 2))
        return 20 * np.log10(r) + 0.06
    return np.zeros_like(f)


def mel_filterbank(nfft, n_mels=40, fmin=30.0, fmax=16000.0):
    mel = lambda f: 2595 * np.log10(1 + f / 700.0)  # noqa: E731
    imel = lambda m: 700 * (10 ** (m / 2595.0) - 1)  # noqa: E731
    pts = imel(np.linspace(mel(fmin), mel(fmax), n_mels + 2))
    fb = np.arange(nfft // 2 + 1) * SR / nfft
    w = np.zeros((n_mels, len(fb)), dtype=np.float32)
    for m in range(n_mels):
        lo, c, hi = pts[m], pts[m + 1], pts[m + 2]
        w[m] = np.clip(np.minimum((fb - lo) / (c - lo), (hi - fb) / (hi - c)), 0, None)
    return w


def pnorm(x, lo=5, hi=95):
    """Song-relative normalisation: the song's p5 -> 0, p95 -> 1."""
    a, b = np.percentile(x, lo), np.percentile(x, hi)
    return np.clip((x - a) / max(b - a, 1e-9), 0, 1)


def one_pole(x, up_s, down_s, fps=FPS_A):
    """Asymmetric envelope follower: time constants for rising / falling (0 = instant)."""
    au = 0.0 if up_s <= 0 else np.exp(-1.0 / (up_s * fps))
    ad = 0.0 if down_s <= 0 else np.exp(-1.0 / (down_s * fps))
    y = np.empty_like(x)
    acc = x[0]
    for i, v in enumerate(x):
        a = au if v > acc else ad
        acc = a * acc + (1 - a) * v
        y[i] = acc
    return y



OCT_LO = F_MIN * 2.0 ** np.arange(9)  # octave bands 30-60, 60-120, ... 7680-15360 Hz


def band_power(x):
    """Instantaneous power (mid of L/R) per octave band, zero-phase filtered (no time shift)."""
    out = []
    for lo in OCT_LO:
        sos = butter(4, [lo, min(2 * lo, 0.45 * SR)], btype="band", fs=SR, output="sos")
        y = sosfiltfilt(sos, x, axis=1)
        out.append((0.5 * (y[0] ** 2 + y[1] ** 2)).astype(np.float32))
    return out


def sharpen_ratio(bp, nfft, n_frames, short=441):
    """Time sharpening for the long STFT windows. A window of nfft samples sees the band power
    smeared by w^2 (a kick shows up nfft/2 samples early). For every octave band the ratio
    (power seen through a 10 ms window) / (power seen through the STFT window) restores the
    sharp envelope; it multiplies the long-window spectrum, whose spectral shape is kept."""
    wl = np.hanning(nfft) ** 2
    wl /= wl.sum()
    ws = np.hanning(short)
    ws /= ws.sum()
    c = np.arange(n_frames) * HOP
    rat = np.empty((n_frames, len(bp)), np.float32)
    for b, p in enumerate(bp):
        el = oaconvolve(p, wl, mode="same")[np.minimum(c, len(p) - 1)]
        es = oaconvolve(p, ws, mode="same")[np.minimum(c, len(p) - 1)]
        d = 1e-4 * np.percentile(el, 99) + 1e-12
        rat[:, b] = np.clip((es + d) / (el + d), 0, 6)
    return rat


def ratio_on_grid(rat, freqs):
    """Octave-band ratios -> log-grid bins (linear interpolation in log-frequency)."""
    centres = np.log2(OCT_LO * np.sqrt(2))
    lf = np.log2(freqs)
    out = np.empty((rat.shape[0], len(freqs)), np.float32)
    for k, v in enumerate(lf):
        j = int(np.clip(np.searchsorted(centres, v) - 1, 0, len(centres) - 2))
        f = float(np.clip((v - centres[j]) / (centres[j + 1] - centres[j]), 0, 1))
        out[:, k] = (1 - f) * rat[:, j] + f * rat[:, j + 1]
    return out


def refine_onset(env1k, t, lo=0.06, hi=0.04):
    """Move a detected onset to the steepest rise of the band envelope (1 ms resolution)."""
    a, b = max(1, int((t - lo) * 1000)), min(len(env1k) - 1, int((t + hi) * 1000))
    if b - a < 3:
        return t
    d = np.diff(env1k[a - 1:b + 1])
    return (a + int(np.argmax(d))) / 1000.0


# ---------------------------------------------------------------- analysis

def analyze(path, weighting="B", tilt_comp=0.0, log=print):
    x = load_stereo(path)
    duration = x.shape[1] / SR
    freqs = log_grid()
    K = len(freqs)
    mix = res_mix(freqs)

    dens_l = np.zeros((x.shape[1] // HOP + 1, K), dtype=np.float32)
    dens_r = np.zeros_like(dens_l)
    cross = np.zeros(dens_l.shape, dtype=np.complex64)
    pm_full = None
    log("  band envelopes")
    bp = band_power(x)
    n_frames = dens_l.shape[0]
    env1k = [np.sqrt(uniform_filter1d(p, 88)[::44][: int(duration * 1000)]) for p in bp]   # 1 kHz, 2 ms smoothing
    for ri, nfft in enumerate(RES):
        ks = np.nonzero(mix[ri] > 0)[0]
        df = SR / nfft
        b0 = max(0, int(np.floor(freqs[ks[0]] / 2 ** (1 / BPO) / df)) - 1)
        b1 = min(nfft // 2 + 1, int(np.ceil(freqs[ks[-1]] * 2 ** (1 / BPO) / df)) + 2)
        if nfft == 2048:
            b0, b1 = 0, nfft // 2 + 1        # the medium resolution is kept whole (HPSS, MFCC, chaos)
        L = stft(x[0], nfft, b0, b1)
        R = stft(x[1], nfft, b0, b1)
        W = grid_weights(freqs, nfft, b0, b1)[ks]
        g = mix[ri, ks].astype(np.float32) * ratio_on_grid(sharpen_ratio(bp, nfft, n_frames), freqs[ks])
        pl = 2 * (L.real ** 2 + L.imag ** 2)
        pr = 2 * (R.real ** 2 + R.imag ** 2)
        dens_l[:, ks] += (pl @ W.T) * g
        dens_r[:, ks] += (pr @ W.T) * g
        cross[:, ks] += ((2 * L * np.conj(R)) @ W.T.astype(np.complex64)) * g
        if nfft == 2048:
            pm_full = 0.5 * (pl + pr)
            W2048 = grid_weights(freqs, nfft, 0, nfft // 2 + 1)
        del L, R, pl, pr
        log(f"  stft {nfft}: bins {b0}..{b1}")
    del bp
    T = dens_l.shape[0]

    # level: energy per log-frequency unit (density * f) in dB, plus the loudness weighting curve
    wdb = weighting_db(freqs, weighting) + tilt_comp * 3.0 * np.log2(freqs / 1000.0)
    db_l = (10 * np.log10(dens_l * freqs + EPS) + wdb).astype(np.float32)
    db_r = (10 * np.log10(dens_r * freqs + EPS) + wdb).astype(np.float32)
    db_m = 10 * np.log10(0.5 * (10 ** (db_l / 10) + 10 ** (db_r / 10)) + EPS)
    ref_db = float(np.percentile(db_m, 99.5))

    # stereo width = 1 - coherence, averaged over +-100 ms
    sm = lambda a: uniform_filter1d(a, 21, axis=0)  # noqa: E731
    coh = np.abs(sm(cross.real) + 1j * sm(cross.imag)) / np.sqrt(sm(dens_l) * sm(dens_r) + EPS)
    width = np.clip(1 - coh, 0, 1).astype(np.float32)
    del cross

    # harmonic / percussive separation (median filtering, Fitzgerald 2010) on the 2048 STFT
    log("  hpss")
    mag = np.sqrt(pm_full)
    H = median_filter(mag, size=(21, 1), mode="nearest")     # smooth along time  -> sustained
    P = median_filter(mag, size=(1, 17), mode="nearest")     # smooth along freq. -> transient
    mh = (H ** 2 / (H ** 2 + P ** 2 + EPS)).astype(np.float32)
    del H, P, mag
    ph = pm_full * mh
    pp = pm_full - ph
    harm = ((ph @ W2048.T) / (pm_full @ W2048.T + EPS)).astype(np.float32)
    harm = uniform_filter1d(harm, 5, axis=0)

    # timbre: MFCCs of each layer -> PCA plane of this song (whitened), signs fixed by
    # PC1 ~ spectral centroid (bright), PC2 ~ spectral flatness (noisy)
    log("  timbre")
    fb = np.arange(pm_full.shape[1]) * SR / 2048
    melw = mel_filterbank(2048)
    band = (fb > 100) & (fb < 10000)

    def layer_desc(p):
        e = p.sum(1) + EPS
        mel = np.log10(p @ melw.T + 1e-12 * pm_full.max())
        cc = dct(mel, type=2, norm="ortho", axis=1)[:, 1:13]
        centroid = (p * fb).sum(1) / e
        flat = np.exp(np.log(p[:, band] + EPS).mean(1)) / (p[:, band].mean(1) + EPS)
        return cc, e, centroid, flat

    cc_h, e_h, cen_h, fl_h = layer_desc(ph)
    cc_p, e_p, cen_p, fl_p = layer_desc(pp)
    cc_h = uniform_filter1d(cc_h, 21, axis=0)
    cc_p = uniform_filter1d(cc_p, 9, axis=0)
    act_h = e_h > np.percentile(e_h, 20)
    act_p = e_p > np.percentile(e_p, 20)
    X = np.vstack([cc_h[act_h], cc_p[act_p]])
    mu, sd = X.mean(0), X.std(0) + 1e-9
    U, S, Vt = np.linalg.svd((X - mu) / sd, full_matrices=False)
    comp = Vt[:2].T / (S[:2] / np.sqrt(len(X)))              # whitened projection
    zh = ((cc_h - mu) / sd) @ comp
    zp = ((cc_p - mu) / sd) @ comp
    cen = np.concatenate([cen_h[act_h], cen_p[act_p]])
    flt = np.concatenate([fl_h[act_h], fl_p[act_p]])
    zall = np.vstack([zh[act_h], zp[act_p]])
    for j, ref in ((0, cen), (1, flt)):
        if np.corrcoef(zall[:, j], ref)[0, 1] < 0:
            zh[:, j] *= -1
            zp[:, j] *= -1

    # tempo / beats (tracker reused from engine/analyze_audio.py)
    log("  tempo")
    logm = np.log1p(pm_full / (np.percentile(pm_full, 99) + EPS) * 100)
    flux = np.maximum(np.diff(logm, axis=0, prepend=logm[:1]), 0).sum(1)
    on = uniform_filter1d(flux, 3)
    on_n = on / (on.std() + 1e-9)
    bpm = estimate_tempo(on_n, FPS_A)
    beats = track_beats(on_n, FPS_A, bpm) / FPS_A
    if len(beats) > 8:
        bpm = float(60.0 / np.median(np.diff(beats)))
    beat_f = 60.0 / bpm * FPS_A

    # chaos 1: non-repetition. Distance (mean |dB| over 1/3-octave bands) between now and the same
    # moment 1 beat, 2 beats and 1 bar earlier; the best match counts (a repeating loop -> ~0).
    log("  chaos")
    nb3 = K // 8
    v = db_m[:, :nb3 * 8].reshape(T, nb3, 8).mean(2)
    v = np.maximum(v, ref_db - 50)
    v = uniform_filter1d(v, 5, axis=0)
    dists = []
    for mult in (1, 2, 4):
        lag = int(round(beat_f * mult))
        d = np.full(T, np.nan)
        d[lag:] = np.abs(v[lag:] - v[:-lag]).mean(1)
        dists.append(d)
    with np.errstate(all="ignore"):
        rep = np.nanmin(np.vstack(dists), axis=0)
    rep = np.where(np.isnan(rep), np.nanmax(rep), rep)
    rep = uniform_filter1d(rep, int(beat_f))
    # chaos 2: noisiness = spectral flatness (Wiener entropy), 100 Hz..10 kHz
    flat = np.exp(np.log(pm_full[:, band] + EPS).mean(1)) / (pm_full[:, band].mean(1) + EPS)
    flat = uniform_filter1d(flat, int(beat_f))
    # chaos 3: rhythmic irregularity = how far onsets sit from the 16th-note grid of the tracked
    # beats (0 = on the grid, 1 = exactly between two 16ths), strength-weighted over one bar
    thr = uniform_filter1d(on, int(beat_f)) + 0.5 * on.std()
    pk = np.nonzero((on == maximum_filter1d(on, 7)) & (on > thr))[0]
    per = float(np.median(np.diff(beats))) if len(beats) > 1 else 60.0 / bpm
    bx = np.concatenate([beats[0] - per * np.arange(8, 0, -1), beats, beats[-1] + per * np.arange(1, 9)])
    grid = (bx[:-1, None] + np.diff(bx)[:, None] * np.arange(4)[None, :] / 4).ravel()
    tp = pk / FPS_A
    j = np.clip(np.searchsorted(grid, tp), 1, len(grid) - 1)
    dev = np.minimum(np.abs(tp - grid[j - 1]), np.abs(grid[j] - tp)) / (per / 8)
    wsum = np.zeros(T)
    dsum = np.zeros(T)
    wsum[pk] = on[pk]
    dsum[pk] = on[pk] * np.clip(dev, 0, 1)
    nbar = int(beat_f * 4)
    offgrid = uniform_filter1d(dsum, nbar) / (uniform_filter1d(wsum, nbar) + 1e-9)
    offgrid *= np.clip(uniform_filter1d(wsum, nbar) / (np.median(on) + 1e-9), 0, 1)  # no onsets -> no rhythm chaos
    parts = {"repetition": pnorm(rep), "flatness": pnorm(flat), "offgrid": pnorm(offgrid)}
    raw = pnorm(CHAOS_W[0] * parts["repetition"] + CHAOS_W[1] * parts["flatness"] + CHAOS_W[2] * parts["offgrid"], 2, 98)
    bar_s = 4 * 60 / bpm
    chaos = one_pole(raw, 0.125 * bar_s, 0.5 * bar_s)   # rises within 1/8 bar, settles over 1/2 bar

    # percussive onsets per half-octave group (sparks)
    log("  onsets")
    dens_p = (pp @ W2048.T)
    G = K // (BPO // 2)
    gp = dens_p[:, :G * (BPO // 2)].reshape(T, G, BPO // 2).mean(2)
    gf = freqs[:G * (BPO // 2)].reshape(G, BPO // 2)
    gfc = np.sqrt(gf[:, 0] * gf[:, -1])
    gdb = 10 * np.log10(gp * gfc + EPS) + weighting_db(gfc, weighting) + tilt_comp * 3.0 * np.log2(gfc / 1000.0)
    od = np.maximum(gdb - np.roll(gdb, 2, axis=0), 0)
    od[:2] = 0
    ons = []
    for g in range(G):
        o = od[:, g]
        thr = max(4.0, np.percentile(o, 97))
        peak = (o == maximum_filter1d(o, 9)) & (o > thr) & (gdb[:, g] > ref_db - 45)
        for i in np.nonzero(peak)[0]:
            lvl = gdb[min(T - 1, i + 2), g]
            band = int(np.clip(np.floor(np.log2(gfc[g] / F_MIN)), 0, len(OCT_LO) - 1))
            ons.append((refine_onset(env1k[band], i / FPS_A), g, gfc[g], lvl))
    onsets = np.array(sorted(ons), dtype=np.float64).reshape(-1, 4)

    return Features(path=path, duration=duration, freqs=freqs, db_l=db_l, db_r=db_r, harm=harm, width=width,
                    timbre_h=zh.astype(np.float32), timbre_p=zp.astype(np.float32), chaos=chaos.astype(np.float32),
                    chaos_parts={k: v.astype(np.float32) for k, v in parts.items()}, onsets=onsets,
                    group_freqs=gfc, bpm=float(bpm), beats=beats, ref_db=ref_db,
                    extra={"e_h": e_h.astype(np.float32), "e_p": e_p.astype(np.float32),
                           "centroid_h": cen_h.astype(np.float32), "flat": flat.astype(np.float32)})

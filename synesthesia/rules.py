"""The mapping rules: audio features -> visual parameters.

Every rule is a small, explicit formula; all constants live in `Rules` so a different
look is a different parameter set, not different code. The rules are documented with
their reasoning in docs/MAPPING_RULES.md (same numbering R1..R8).
"""
import json
from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Rules:
    # R1 pitch height: log-frequency -> vertical position (top = high)
    f_min: float = 30.0
    f_max: float = 16000.0
    y_top: float = 0.07          # fraction of the frame height where f_max sits
    y_bottom: float = 0.93       # ... and f_min
    # R2 loudness -> strength
    sone_db: float = 10.0        # +10 dB = twice as loud (sone law) = twice as bright
    floor_db: float = -45.0      # below ref + floor_db nothing is drawn
    l_max: float = 0.88          # Oklab lightness of the loudest sound in the song
    # R3 timing
    release_s: float = 0.09      # fall time constant; the rise is always instant
    # R4 timbre -> colour (Oklab a/b plane)
    anchor_hue: float = 325.0    # colour of this song's average timbre (degrees, Oklab hue)
    anchor_chroma: float = 0.14
    radius: float = 0.15         # how far timbre can move the colour away from the anchor
    pc1_hue: float = 215.0       # bright timbres move towards this hue
    perc_chroma: float = 0.40    # percussive/noisy sound keeps this share of colour (rest -> white)
    # R5 stereo
    birth_gap: float = 0.05      # fully decorrelated (wide) sound is born this far from the centre line
    # R6 chaos
    turb_px: float = 3.2         # max. turbulent displacement per frame (px at 960 px height) at chaos 1
    turb_gamma: float = 1.1      # measured by synesthesia/calibrate.py: makes picture disorder linear in chaos
    glitch_from: float = 0.6     # chaos above this starts tearing the image into shifted slices
    glitch_px: float = 34.0
    # R7 tempo
    bar_width: float = 0.5       # one bar of music travels this fraction of the frame width
    trail_end: float = 0.18      # brightness left when a trace reaches the edge (memory fades)
    # R8 texture: percussive onsets -> sparks
    spark_max: int = 36          # sparks for an onset at full loudness
    spark_speed: float = 9.0     # px per frame at 960 px height for a full-loudness onset
    spark_life_bars: float = 0.22

    @classmethod
    def from_json(cls, path):
        return cls(**json.load(open(path))) if path else cls()

    def to_dict(self):
        return asdict(self)


# R1 ----------------------------------------------------------------------------------------
def y_of_freq(f, H, r: Rules):
    """y = top + (1 - log(f/f_min) / log(f_max/f_min)) * (bottom - top); equal height per octave."""
    u = np.log(np.asarray(f) / r.f_min) / np.log(r.f_max / r.f_min)
    return (r.y_top + (1 - u) * (r.y_bottom - r.y_top)) * H


def freq_of_y(y, H, r: Rules):
    u = 1 - (np.asarray(y) / H - r.y_top) / (r.y_bottom - r.y_top)
    return r.f_min * (r.f_max / r.f_min) ** u


# R2 ----------------------------------------------------------------------------------------
def psi(db, ref_db, r: Rules):
    """Perceived loudness relative to the song's loudest moment: psi = 2^((L - L_ref) / 10 dB).
    1 = loudest, 0.5 = 10 dB quieter, 0.25 = 20 dB quieter; soft fade to 0 over the last 6 dB."""
    d = np.asarray(db) - ref_db
    p = np.power(2.0, np.minimum(d, 6.0) / r.sone_db)
    fade = np.clip((d - r.floor_db) / 6.0, 0, 1)
    return p * fade


def lightness(p, r: Rules):
    """Oklab L is perceptually uniform, so perceived brightness grows linearly with psi."""
    return np.clip(r.l_max * np.asarray(p), 0, 1.0)


# R3 ----------------------------------------------------------------------------------------
def envelope(x, fps, r: Rules):
    """Instant attack, exponential release (applied along axis 0)."""
    a = np.exp(-1.0 / (r.release_s * fps))
    y = np.empty_like(x)
    acc = x[0].copy()
    for i in range(len(x)):
        acc = np.maximum(x[i], acc * a)
        y[i] = acc
    return y


def video_frame(t, fps):
    """A sound at time t is shown in frame floor(t * fps): the picture may come up to one frame
    before the sound, never after it (audio-after-video is the far less noticeable direction)."""
    return np.floor(np.asarray(t) * fps).astype(int)


# R4 ----------------------------------------------------------------------------------------
def _hue_vec(h_deg, c):
    h = np.deg2rad(h_deg)
    return np.array([c * np.cos(h), c * np.sin(h)])


def timbre_ab(z, r: Rules):
    """Linear, distance-preserving map from the song's timbre plane (whitened PCA of MFCCs)
    into the Oklab a/b plane: ab = anchor + radius * (z1 * u1 + z2 * u2), with a soft limit
    |z| -> tanh(|z|/2) so extreme timbres saturate instead of leaving the gamut."""
    z = np.atleast_2d(z).astype(np.float64)
    n = np.linalg.norm(z, axis=1, keepdims=True) + 1e-9
    zs = z * np.tanh(n / 2.0) / n
    anchor = _hue_vec(r.anchor_hue, r.anchor_chroma)
    d = _hue_vec(r.pc1_hue, r.anchor_chroma) - anchor
    u1 = d / (np.linalg.norm(d) + 1e-12)
    u2 = np.array([-u1[1], u1[0]])
    return anchor + r.radius * (zs[:, :1] * u1 + zs[:, 1:2] * u2)


def element_ab(harm, ab_h, ab_p, r: Rules):
    """Colour of one spot: harmonic share h picks between the colour of the harmonic layer and a
    paler version of the percussive layer's colour (noise -> white)."""
    h = np.asarray(harm)[..., None]
    return h * ab_h + (1 - h) * r.perc_chroma * ab_p


def oklab_to_linear_srgb(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    rgb = np.stack([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                    -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s], axis=-1)
    return np.clip(rgb, 0, None)


# R6 ----------------------------------------------------------------------------------------
def chaos_visual(c, r: Rules, H):
    """Visual chaos = musical chaos, spent on four visual degrees of freedom."""
    c = float(np.clip(c, 0, 1))
    return {
        "turb_px": r.turb_px * c ** r.turb_gamma * H / 960.0,   # laminar -> turbulent flow
        "fine": c,                                       # share of small-scale eddies
        "spark_spread": np.pi * c,                       # sparks: horizontal pairs -> any direction
        "pair_prob": 1.0 - c,                            # mirror-symmetric spark pairs
        "glitch_prob": max(0.0, (c - r.glitch_from) / (1 - r.glitch_from)) * 0.7,
        "glitch_px": r.glitch_px * c * H / 960.0,
    }

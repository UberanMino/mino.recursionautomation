"""Model D: Gray-Scott reaction-diffusion. The music sets the chemistry, the drums drop in the catalyst.

    du/dt = D_u lap u - u v^2 + F (1 - u),     dv/dt = D_v lap v + u v^2 - (F + k) v,   D_u = 0.21, D_v = 0.105

(grid units, dt = 1, Pearson 1993). Depending on (F, k) the same two equations make labyrinths, spots
that divide, or restless, chaotic spots and waves. Measured on this grid (see docs/MODELS.md):
    (0.055, 0.062) labyrinth,  (0.0367, 0.0649) spots,  (0.018, 0.051) chaotic spots/waves.
  * Regime <- music: (F, k) = (1 - c) [h * labyrinth + (1 - h) * spots] + c * chaotic, with h = tonal share
    (bar scale) and c = chaos (R6): legato music grows connected lines, percussive music dots, chaotic
    music boils.
  * Rows = frequency (R1): the feed rate of each row is F * (0.85 + 0.3 psi(f_row)), left half from the
    left channel, right half from the right (R5): loud frequencies feed their own row of the pattern.
  * Every drum hit drops catalyst v at its pitch height (kick at the bottom, snare in the middle, hats at
    the top), size ~ loudness. Patterns grow from the hits.
  * Reaction speed <- loudness: 10 + 22 loudness steps per frame.
  * The domain grows: every frame the fields are zoomed by 1 + 0.003 (0.5 + loudness) about the centre, so
    the camera always moves in and the stretched pattern keeps splitting to refill the space.
  * Kick bounce: the displayed picture punches in with the damped kick spring and its exposure follows it.
Brightness = v concentration x loudness of the row's frequency (R2), colour = timbre (R4).
"""
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d, map_coordinates

from ..render import _resize
from .base import Model, warp

LAB, SPOTS, CHAOS = (0.055, 0.062), (0.0367, 0.0649), (0.018, 0.051)
DU, DV = 0.2097, 0.105


def _lap(a):
    out = -4 * a
    out[1:] += a[:-1]
    out[:-1] += a[1:]
    out[:, 1:] += a[:, :-1]
    out[:, :-1] += a[:, 1:]
    out[0] += a[0]
    out[-1] += a[-1]
    out[:, 0] += a[:, 0]
    out[:, -1] += a[:, -1]
    return out


class GrayScott(Model):
    key = "grayscott"
    title = "D · Gray-Scott-Reaktion"
    laws = (
        "Zwei Stoffe reagieren und diffundieren; (F, k) aus der Musik: tonal = Labyrinth, perkussiv = Punkte, Chaos = brodelnde Wellen",
        "Zeilen = Frequenzen (oben hoch): laute Frequenzen füttern ihre Zeile stärker; links/rechts = Kanäle",
        "Jeder Drum-Schlag tropft Katalysator auf seiner Tonhöhe ein (Kick unten, Snare Mitte, Hats oben)",
        "Die Fläche wächst ständig (Zoom), das Muster teilt sich nach; Kick = gedämpfte Feder",
    )
    invert_entry = True

    def __init__(self, *args, gh=352, gw=198, seed=9, **kw):
        super().__init__(*args, **kw)
        self.gh, self.gw = gh, gw
        rng = np.random.default_rng(seed)
        self.rng = rng
        self.u = np.ones((gh, gw), np.float32)
        self.v = np.zeros((gh, gw), np.float32)
        for _ in range(60):
            self._drop(rng.integers(5, gh - 5), rng.integers(5, gw - 5), 4)
        r = self.r
        yrel = (np.arange(gh) + 0.5) / gh
        u = np.clip((yrel - r.y_top) / (r.y_bottom - r.y_top), 0, 1)
        self.row_f = r.f_max * (r.f_min / r.f_max) ** u            # R1: top = 16 kHz, bottom = 30 Hz
        self.row_bin = np.clip(np.searchsorted(self.freqs, self.row_f), 0, len(self.freqs) - 1)
        self.left = (np.arange(gw) < gw / 2)[None, :]
        hb = self.a["harm_bar"]
        lo, hi = np.percentile(hb, [5, 95])
        self.hn = np.clip((hb - lo) / (hi - lo + 1e-9), 0, 1)
        self.yy, self.xx = np.mgrid[0:gh, 0:gw].astype(np.float32)
        self.hits_at = {}
        for cls, f in (("kick", 50.0), ("snare", 1500.0), ("hat", 9000.0)):
            hh = self.S.hits[cls]
            if not len(hh):
                continue
            p90 = np.percentile(hh[:, 2], 90) + 1e-9
            row = int(np.argmin(np.abs(np.log(self.row_f / f))))
            for t, _, pw in hh:
                self.hits_at.setdefault(int(math.floor(t * self.fps)), []).append((cls, row, min(1.2, pw / p90)))

    def _drop(self, y, x, rad):
        y0, y1, x0, x1 = max(0, y - rad), min(self.gh, y + rad), max(0, x - rad), min(self.gw, x + rad)
        yy, xx = np.ogrid[y0:y1, x0:x1]
        m = (yy - y) ** 2 + (xx - x) ** 2 <= rad * rad
        self.v[y0:y1, x0:x1][m] = 0.5
        self.u[y0:y1, x0:x1][m] = 0.25

    def step(self, k):
        a = self.a
        C = float(np.clip((a["chaos"][k] - 0.2) / 0.6, 0, 1)) ** 1.1
        h = float(self.hn[k])
        loud = float(a["loud_bar"][k])
        Fb = (1 - C) * (h * LAB[0] + (1 - h) * SPOTS[0]) + C * CHAOS[0]
        kb = (1 - C) * (h * LAB[1] + (1 - h) * SPOTS[1]) + C * CHAOS[1]
        pl, pr = self.profile(k)
        sl = gaussian_filter1d(pl[self.row_bin], 5.0)                  # smooth over ~1/3 octave of rows
        sr = gaussian_filter1d(pr[self.row_bin], 5.0)
        prow = np.where(self.left, sl[:, None], sr[:, None]).astype(np.float32)
        Fm = (Fb * (0.85 + 0.3 * prow)).astype(np.float32)
        # drum hits drop catalyst at their pitch height
        for cls, row, pw in self.hits_at.get(k, ()):
            n = {"kick": 3, "snare": 2, "hat": 2}[cls]
            for _ in range(n):
                rad = int(2 + 5 * pw * {"kick": 1.0, "snare": 0.7, "hat": 0.4}[cls])
                self._drop(int(np.clip(row + self.rng.normal(0, 6), 3, self.gh - 4)), int(self.rng.integers(4, self.gw - 4)), rad)
        # growing domain: zoom the fields about the centre
        z = 1 + 0.003 * (0.5 + loud) + 0.02 * self.drop_env[k]
        cy, cx = self.gh / 2, self.gw / 2
        sy, sx = cy + (self.yy - cy) / z, cx + (self.xx - cx) / z
        self.u = map_coordinates(self.u, [sy, sx], order=1, mode="nearest").astype(np.float32)
        self.v = map_coordinates(self.v, [sy, sx], order=1, mode="nearest").astype(np.float32)
        u, v = self.u, self.v
        for _ in range(int(10 + 22 * loud)):
            uvv = u * v * v
            u += DU * _lap(u) - uvv + Fm * (1 - u)
            v += DV * _lap(v) + uvv - (Fm + kb) * v
        np.clip(u, 0, 1, out=u)
        np.clip(v, 0, 1, out=v)
        # picture
        L = self.lightness(prow) * np.clip(2.2 * v, 0, 1) ** 0.8 * 1.1
        harm = a["harm"][k][self.row_bin][:, None] * np.ones((1, self.gw))
        rgb = self.colour(k, L, harm=harm).astype(np.float32)
        img = _resize(rgb, self.W, self.H)
        b = float(self.bounce[k])
        img = warp(img, zoom=1 + 0.12 * b) * max(0.4, 1 + 0.35 * b)
        reg = "Chaos" if C > 0.5 else ("Labyrinth" if h > 0.5 else "Punkte")
        self.live = {"F": f"{Fb:.4f}", "k": f"{kb:.4f}", "Regime": reg, "Feder": f"{b:+.2f}"}
        return img

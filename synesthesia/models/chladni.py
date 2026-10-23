"""Model E: Chladni plate. The tonal content of the music makes a plate ring; sand gathers on the nodal lines.

Rectangular plate 1 x 16/9 (the frame), modes phi_nm(x, y) = cos(n pi x) cos(m pi y / B), B = 16/9. For a
thin plate the bending-wave frequency grows with the square of the wave number, f_nm ~ n^2 + (m / B)^2.
  * Pitch -> mode: the strongest tonal peaks of the spectrum (40 Hz .. 2 kHz, weighted by the harmonic
    share) each excite the mode with n^2 + (m/B)^2 closest to 2 f / 55 Hz. The same note always gives the
    same figure; a chord superposes its modes and makes curved, non-grid figures.
  * Amplitude of each mode <- loudness of its peak (instant attack, release 1/2 bar, so the sand has time to settle).
  * Sand: grains move down the gradient of the vibration energy phi^2 and are kicked around in proportion
    to the local amplitude |phi| x loudness (bouncing sand), so they collect where the plate stands still
    (nodal lines), as on a real Chladni plate. Chaos adds amplitude-independent jitter (R6): ordered music =
    sharp lines, chaotic music = blurred, wandering sand.
  * Kick bounce: every kick shakes the whole plate with the damped kick spring, the sand jumps off the
    lines and settles again; the picture punches in with the spring.
  * Brightness: sand ~ loudness (R2), plate glow = |phi| x loudness; colour = timbre (R4). The view zooms
    in over each section (16 bars). Height does not carry pitch here (pitch -> pattern instead of R1).
"""
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from .base import Model, splat, warp

B = 16.0 / 9.0


class ChladniPlate(Model):
    key = "chladni"
    title = "E · Chladni-Platte"
    laws = (
        "Platte schwingt in Moden cos(nπx)·cos(mπy/B); Frequenz ∝ n² + (m/B)²: jeder Ton hat seine Figur",
        "Die stärksten tonalen Spitzen (40 Hz–2 kHz) regen ihre Moden an, Akkorde überlagern sich",
        "Sand rutscht zu den Knotenlinien (wo die Platte still steht), Lautheit = Schüttelstärke",
        "Kick = gedämpfte Feder: der Sand springt von den Linien und setzt sich wieder; Chaos verwischt",
    )
    invert_entry = True

    def __init__(self, *args, grains=60000, n_max=14, peaks=3, seed=4, **kw):
        super().__init__(*args, **kw)
        rng = np.random.default_rng(seed)
        self.rng = rng
        self.P = np.c_[rng.uniform(0, 1, grains), rng.uniform(0, B, grains)]
        nm = np.array([(n, m) for n in range(1, n_max + 1) for m in range(1, int(n_max * B) + 1)])
        self.nm = nm
        self.lam = nm[:, 0] ** 2 + (nm[:, 1] / B) ** 2
        fr = self.freqs
        self.sel = np.nonzero((fr >= 40) & (fr <= 2000))[0]
        # mode amplitudes per frame: peaks of the tonal spectrum -> nearest mode
        n = self.S.n
        prof = 0.5 * (self.a["prof_l"] + self.a["prof_r"])[:, self.sel] * self.a["harm"][:, self.sel]
        amp = np.zeros((n, len(nm)), np.float32)
        tgt = 2 * fr[self.sel] / 55.0
        mode_of = np.argmin(np.abs(self.lam[None, :] - tgt[:, None]), axis=1)
        for k in range(n):
            p = prof[k]
            pk = np.nonzero((p[1:-1] > p[:-2]) & (p[1:-1] >= p[2:]))[0] + 1
            if not len(pk):
                continue
            pk = pk[np.argsort(p[pk])[::-1][:peaks]]
            for i in pk:
                amp[k, mode_of[i]] = max(amp[k, mode_of[i]], p[i])
        rel = math.exp(-1.0 / (self.bar_f / 2))
        for k in range(1, n):                                    # instant attack, release 1/2 bar
            amp[k] = np.maximum(amp[k], amp[k - 1] * rel)
        self.amp = amp
        self.prev = np.zeros((self.H, self.W, 3), np.float32)
        gy, gx = np.mgrid[0:self.H // 4, 0:self.W // 4].astype(np.float32)
        self.gx = (gx + 0.5) / (self.W // 4)
        self.gy = (gy + 0.5) / (self.H // 4) * B

    def field(self, x, y, k, grad=False):
        act = np.nonzero(self.amp[k] > 0.03)[0]
        phi = np.zeros_like(x)
        dx = np.zeros_like(x)
        dy = np.zeros_like(x)
        for j in act:
            n, m = self.nm[j]
            a, b = n * math.pi, m * math.pi / B
            w = float(self.amp[k, j])
            cx, cy = np.cos(a * x), np.cos(b * y)
            phi += w * cx * cy
            if grad:
                dx -= w * a * np.sin(a * x) * cy
                dy -= w * b * cx * np.sin(b * y)
        return phi, dx, dy, act

    def step(self, k):
        a = self.a
        loud = float(a["loud_bar"][k])
        C = float(np.clip(a["chaos"][k], 0, 1)) ** 1.1
        b = float(self.bounce[k])
        x, y = self.P[:, 0], self.P[:, 1]
        phi, dx, dy, act = self.field(x, y, k, grad=True)
        norm = float(np.sqrt((self.amp[k] ** 2).sum())) + 1e-6
        # down the gradient of phi^2, bounced in proportion to |phi|; kicks shake everything
        eta = 0.003 / norm ** 2
        shake = (0.0015 + 0.004 * loud) * np.abs(phi) / norm + 0.0015 * C + 0.02 * max(b, 0) ** 1.5
        x = x - eta * 2 * phi * dx + shake * self.rng.standard_normal(len(x))
        y = y - eta * 2 * phi * dy + shake * self.rng.standard_normal(len(y))
        x = np.abs(x)                                            # reflect at the plate edges
        x = np.where(x > 1, 2 - x, x)
        y = np.abs(y)
        y = np.where(y > B, 2 * B - y, y)
        self.P = np.c_[x, y]

        # picture: plate glow (|phi|) + sand
        pg, _, _, _ = self.field(self.gx, self.gy, k)
        glow = np.abs(pg) / norm * float(np.mean(self.amp[k][act])) if len(act) else np.zeros_like(pg)
        Lg = 0.35 * self.lightness(np.clip(glow, 0, 1))
        rgb = self.colour(k, Lg, harm=1.0).astype(np.float32)
        from ..render import _resize
        img = _resize(rgb, self.W, self.H)
        Ls = self.lightness(np.array([0.25 + 0.75 * loud]))[0]
        col = self.colour(k, np.array([Ls]), harm=0.3)[0] * (1 + 0.8 * max(b, 0))
        sx, sy = x * self.W, y / B * self.H
        img = splat(img, sx, sy, np.repeat(col[None] * 0.22, len(x), 0))
        # zoom in over the section, kick punch; short trails
        ph = min(1.0, self.section_phase(k, 16.0))
        zoom = (1 + 0.35 * ph * ph * (3 - 2 * ph)) * (1 + 0.1 * b)
        img = warp(img, zoom=zoom)
        g = math.exp(-1.0 / (self.fps * 0.06))
        out = np.maximum(img, g * self.prev)
        self.prev = out
        top = act[np.argsort(self.amp[k][act])[::-1][:2]] if len(act) else []
        self.live = {"Moden": " ".join(f"({self.nm[j][0]},{self.nm[j][1]})" for j in top) or "–", "Feder": f"{b:+.2f}"}
        return out

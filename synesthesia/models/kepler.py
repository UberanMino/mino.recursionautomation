"""Model C: Kepler system. Every frequency band is a ring of bodies on a Kepler orbit around a central mass.

  * Orbital rate <- pitch: band k (1/8 octave) circles at omega_k = omega_0 (f_k / 30 Hz)^(1/3), the nine
    audible octaves compressed to three octaves of orbital rate; omega_0 = one turn per 4 bars, so the
    lowest band turns once per 4 bars and the highest twice per bar (tempo-locked).
  * Orbit size <- Kepler's third law, T^2 ~ a^3:  a_k = a_0 (omega_k / omega_0)^(-2/3) ~ f^(-2/9).
    Bass orbits far out and slowly, treble close in and fast (replaces R1). Neighbouring rings drift
    against each other (differential rotation), so any alignment winds up into spiral arms.
  * Central mass <- loudness: M = 0.5 + loudness(bar); at fixed a, omega ~ sqrt(M): loud parts spin faster.
  * Brightness of a body = loudness of its band (R2), left half of the picture = left channel, right half =
    right channel (R5), colour = timbre (R4). The sun glows with the sub-bass.
  * Chaos -> eccentricity and inclination (R6): e_k = 0.6 C^1.1 n_k, i_k = 0.35 C n'_k with fixed random
    n_k. Positions follow Kepler's equation E - e sin E = M_anomaly, so bodies speed up at perihelion.
    Ordered music = flat, round, nested rings; chaotic music = crossing, tilted ellipses.
  * Kick bounce: every kick displaces a damped spring (half-beat period); all orbits expand with it
    (radius * (1 + 0.28 x)) and the camera punches in.
  * The camera circles the system and moves in over each section (16 bars); build-ups lift it to a top view.
"""
import math

import numpy as np

from .base import Model, look_at, project, splat, warp


class KeplerSystem(Model):
    key = "kepler"
    title = "C · Kepler-System"
    laws = (
        "Jedes Frequenzband ist ein Ring: Umlauf ω ∝ f^(1/3), Bahnradius nach Kepler a ∝ ω^(−2/3) (T² ∝ a³)",
        "Bass außen und langsam, Höhen innen und schnell; Zentralmasse = Lautheit (laut = schneller)",
        "Chaos → Exzentrizität und Neigung: Ordnung = flache runde Ringe, Chaos = gekreuzte Ellipsen",
        "Kick = gedämpfte Feder: alle Bahnen federn nach außen, Kamera stößt hinein",
    )
    invert_entry = True

    def __init__(self, *args, per_ring=40, bands_per_oct=8, seed=3, **kw):
        super().__init__(*args, **kw)
        rng = np.random.default_rng(seed)
        fr = self.freqs
        step = max(1, int(round(24 / bands_per_oct)))
        self.groups = [np.arange(i, min(i + step, len(fr))) for i in range(0, len(fr), step)]
        fc = np.array([np.exp(np.log(fr[g]).mean()) for g in self.groups])
        nb = len(fc)
        self.om = (fc / 30.0) ** (1 / 3)                       # in units of omega_0
        self.a0 = self.om ** (-2 / 3)                           # Kepler: a ~ omega^(-2/3)
        self.ring = np.repeat(np.arange(nb), per_ring)
        N = len(self.ring)
        self.phase0 = (np.tile(np.arange(per_ring), nb) / per_ring * 2 * np.pi
                       + rng.uniform(0, 2 * np.pi, nb)[self.ring] + rng.normal(0, 0.03, N))
        self.ne = rng.uniform(0.3, 1.0, nb)
        self.ni = rng.normal(0, 1.0, nb)
        self.peri = rng.uniform(0, 2 * np.pi, nb)
        self.node = rng.uniform(0, 2 * np.pi, nb)
        omega0 = 2 * np.pi / (4 * self.bar_f)                   # rad per frame
        M = 0.5 + self.a["loud_bar"]
        self.tau = np.cumsum(omega0 * np.sqrt(M / 1.0) * (1 + 0.6 * self.drop_env))   # integrated "mean motion" clock
        self.prev = np.zeros((self.H, self.W, 3), np.float32)
        self.az = 0.0
        self.focal = 0.9 * self.H
        self.N = N

    def step(self, k):
        a, fps = self.a, self.fps
        C = float(np.clip(a["chaos"][k], 0, 1)) ** 1.1
        loud = float(a["loud_bar"][k])
        b = float(self.bounce[k])
        r = self.ring
        e = np.clip(0.6 * C * self.ne, 0, 0.85)[r]
        inc = (0.35 * C * self.ni)[r]
        # motion blur: 6 samples along the orbit between the previous and the current frame
        dtau = self.tau[k] - self.tau[k - 1] if k > 0 else 0.0
        js = np.arange(6)[:, None] / 6.0
        Ma = (self.phase0 + self.om[r] * (self.tau[k] - js * dtau)).ravel()
        r = np.tile(r, 6)
        e, inc = np.tile(e, 6), np.tile(inc, 6)
        E = Ma.copy()
        for _ in range(4):                                      # Kepler's equation, Newton steps
            E -= (E - e * np.sin(E) - Ma) / (1 - e * np.cos(E))
        sc = self.a0[r] * (1 + 0.28 * b)
        x = sc * (np.cos(E) - e)
        y = sc * np.sqrt(1 - e * e) * np.sin(E)
        w = self.peri[r]
        x, y = x * np.cos(w) - y * np.sin(w), x * np.sin(w) + y * np.cos(w)
        nd = self.node[r]                                       # tilt about the node line
        cn, sn, ci, si = np.cos(nd), np.sin(nd), np.cos(inc), np.sin(inc)
        u = x * cn + y * sn
        v = -x * sn + y * cn
        P = np.stack([u * cn - v * ci * sn, u * sn + v * ci * cn, v * si], 1)

        # camera: circle the system, move in over the section, lift in build-ups
        sec = self.S.sections[int(a["section"][k])]
        self.az += sec["dir"] * 2 * math.pi / (24 * self.bar_f) * (0.3 + loud)
        ph = min(1.0, self.section_phase(k, 16.0))
        ph = ph * ph * (3 - 2 * ph)
        D = 2.3 * (1 - 0.45 * ph)
        el = 0.45 + 0.8 * float(a["tension"][k])
        cam = D * np.array([math.cos(el) * math.sin(self.az), -math.cos(el) * math.cos(self.az), math.sin(el)])
        B = look_at(cam, (0, 0, 0))
        focal = self.focal * (1 + 0.18 * b)
        xs, ys, z, ok = project(P, cam, B, focal, self.W, self.H)
        pl, pr = self.profile(k)
        gl = np.array([pl[g].mean() for g in self.groups])
        gr = np.array([pr[g].mean() for g in self.groups])
        p = np.where(xs < self.W / 2, gl[r], gr[r])
        L = self.lightness(p)
        hb = a["harm"][k]
        harm = np.array([hb[g].mean() for g in self.groups])[r]
        rgb = self.colour(k, L, harm=harm)
        wgt = (D / np.maximum(z, 0.2)) ** 2 * 0.5 * (1 + 1.5 * max(b, 0))
        on = ok & (xs > 0) & (xs < self.W - 1) & (ys > 0) & (ys < self.H - 1)
        img = splat(np.zeros((self.H, self.W, 3), np.float32), xs[on], ys[on], rgb[on] * wgt[on, None])
        # the sun: sub-bass glow at the centre
        sx, sy, sz, sok = project(np.zeros((1, 3)), cam, B, focal, self.W, self.H)
        if sok[0]:
            yy, xx = np.ogrid[0:self.H, 0:self.W]
            rad = (0.008 + 0.022 * float(a["psi_sub"][k]) * (1 + max(b, 0))) * self.H
            g = np.exp(-((xx - sx[0]) ** 2 + (yy - sy[0]) ** 2) / (2 * rad * rad)).astype(np.float32)
            img += g[..., None] * self.colour(k, np.array([0.9]), harm=0.2)[0] * (0.2 + 0.9 * float(a["psi_sub"][k]))
        # trails: memory grows with the tonal share, cut on the kick (the hit is clean)
        mem = 0.08 + 0.35 * float(a["harm_bar"][k])
        gm = math.exp(-1.0 / (fps * mem)) * (1 - 0.5 * min(1.0, max(0.0, b)))
        fb = warp(self.prev, zoom=1.0 + 0.002 + 0.01 * self.drop_env[k])
        out = np.maximum(img, gm * fb)
        self.prev = out
        self.live = {"Masse": f"{0.5 + loud:4.2f}", "Exzentr.": f"{0.6 * C:4.2f}", "Feder": f"{b:+.2f}"}
        return out

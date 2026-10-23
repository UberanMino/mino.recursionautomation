"""Model A: Lorenz flight. The music sets the control parameter of the Lorenz system.

    dx/dt = sigma (y - x),   dy/dt = x (rho - z) - y,   dz/dt = x y - beta z,   sigma = 10, beta = 8/3

For rho < 24.74 the two fixed points C+- = (+-sqrt(beta (rho - 1)), ..., rho - 1) are stable: every
trajectory spirals into one wing and stays there (order). Above 24.74 they lose stability (subcritical
Hopf bifurcation) and the trajectories wander on the strange attractor, switching wings irregularly
(chaos). Here rho = 24.74 + 40 (C - median C), with C the musical chaos (rule R6): the bifurcation lies
at the song's median chaos, so the more ordered half of the song literally falls into two calm whirls
and the more chaotic half opens the butterfly.

A cloud of particles is integrated and drawn with its trail in 3D (the last sub-steps). Each particle belongs to one frequency bin of the spectrum:
  * its brightness is the loudness of that bin (R2), the x < 0 wing shows the left channel and the
    x > 0 wing the right channel (R5), colour = timbre (R4);
  * its time runs at (f / 500 Hz)^0.2 times the common rate: high notes move faster (replaces R1);
  * the common rate is 1.2 Lorenz time units per bar times (0.6 + 0.8 loudness): louder = faster;
  * every kick adds a small random displacement to every particle. In the ordered regime it dies away
    (negative Lyapunov exponent), in the chaotic regime it grows by about e^(0.9 t) and scatters the
    cloud: the picture shows the sensitivity of the system to the beat;
  * weak noise of strength ~ loudness keeps the cloud from collapsing onto the fixed points.
Kick bounce: the focal length follows the damped kick spring (zoom punch, one overshoot).
The camera orbits the attractor and moves in over each section (16 bars from far to close); the frame
is fed back briefly with a slight zoom so the glow streams outward. Trail length grows with the tonal
share of the music (held notes = long lines).
"""
import math

import numpy as np

from .base import Model, splat, warp

SIGMA, BETA = 10.0, 8.0 / 3.0
RHO_C = 24.74


def lorenz(X, rho):
    x, y, z = X[:, 0], X[:, 1], X[:, 2]
    return np.stack([SIGMA * (y - x), x * (rho - z) - y, x * y - BETA * z], 1)


class LorenzFlight(Model):
    key = "lorenz"
    title = "A · Lorenz-Flug"
    laws = (
        "ρ = 24,74 + 40·(Chaos − Median): geordnete Hälfte = zwei ruhige Wirbel, chaotische = Schmetterling",
        "Teilchen = Frequenzen: Helligkeit = Lautheit, linker Flügel = linker Kanal, rechter = rechter",
        "Hohe Töne laufen schneller ((f/500 Hz)^0,2); jeder Kick stößt alle Teilchen an",
        "Im Chaos wächst der Stoß exponentiell (Lyapunov), in der Ordnung verschwindet er; Bild federt mit",
    )
    invert_entry = True

    def __init__(self, *args, n_particles=900, trail=160, seed=5, **kw):
        super().__init__(*args, **kw)
        rng = np.random.default_rng(seed)
        K = len(self.freqs)
        self.N = n_particles
        self.bin = np.arange(self.N) % K
        self.tmul = (self.freqs[self.bin] / 500.0) ** 0.2
        self.X = np.c_[rng.normal(0, 8, self.N), rng.normal(0, 8, self.N), rng.normal(25, 8, self.N)]
        self.hist = np.repeat(self.X[None], trail, 0)              # ring buffer of sub-step positions
        self.hpos = 0
        self.rng = rng
        self.prev = np.zeros((self.H, self.W, 3), np.float32)
        self.az = 0.0
        self.focal = 0.95 * self.H
        self.f_prev = self.focal
        self.c_med = float(np.median(self.a["chaos"]))

    def step(self, k):
        a, fps = self.a, self.fps
        C = float(a["chaos"][k])
        rho = RHO_C + 40.0 * (C - self.c_med)
        loud = float(a["loud_bar"][k])
        kick = float(self.env["kick"][k])
        rate = 1.2 / self.bar_f * (0.6 + 0.8 * loud) * (1 + 0.6 * kick + 1.5 * self.drop_env[k])
        dt = rate * self.tmul                                       # per particle
        nsub = max(1, int(math.ceil(dt.max() / 0.01)))
        h = (dt / nsub)[:, None]
        X = self.X
        if k > 0 and self.env["kick"][k] > self.env["kick"][k - 1] + 0.3:          # kick onset: shove
            X = X + 0.8 * self.rng.standard_normal(X.shape)
        noise = np.sqrt(h) * (0.05 + 0.25 * loud)
        T = len(self.hist)
        for _ in range(nsub):                                       # RK4 + weak noise
            k1 = lorenz(X, rho)
            k2 = lorenz(X + 0.5 * h * k1, rho)
            k3 = lorenz(X + 0.5 * h * k2, rho)
            k4 = lorenz(X + h * k3, rho)
            X = np.clip(X + h / 6 * (k1 + 2 * k2 + 2 * k3 + k4) + noise * self.rng.standard_normal(X.shape), -80, 120)
            self.hpos = (self.hpos + 1) % T
            self.hist[self.hpos] = X
        self.X = X

        # camera: orbit about the vertical axis, move in over each section
        sec = self.S.sections[int(a["section"][k])]
        self.az += sec["dir"] * 2 * math.pi / (16 * self.bar_f) * (0.4 + loud)
        ph = min(1.0, self.section_phase(k, 16.0))
        ph = ph * ph * (3 - 2 * ph)
        D = 80.0 * (1 - 0.5 * ph)
        el = 0.1 + 0.3 * float(a["tension"][k])
        ctr = np.array([0.0, 0.0, 23.0])
        cam = ctr + D * np.array([math.cos(el) * math.sin(self.az), -math.cos(el) * math.cos(self.az), math.sin(el)])
        fwd = (ctr - cam) / D
        right = np.cross(fwd, [0, 0, 1.0])
        right /= np.linalg.norm(right)
        up = np.cross(right, fwd)

        # trails: the last n_tr sub-steps of every particle, fading with age; tonal music = long trails
        n_tr = int(np.clip(T * (0.3 + 0.7 * float(a["harm_bar"][k])), 8, T))
        ages = np.arange(n_tr)
        idx = (self.hpos - ages) % T
        Hs = self.hist[idx]                                         # (n_tr, N, 3), newest first
        Hn = self.hist[(idx - 1) % T]                               # one sub-step older: fill the gap
        P = np.concatenate([Hs, Hs * (2 / 3) + Hn / 3, Hs / 3 + Hn * (2 / 3)]).reshape(-1, 3)
        fade = np.tile(np.repeat((1 - ages / n_tr) ** 1.5, self.N), 3)
        q = (P - cam) @ np.stack([right, up, fwd]).T
        z = q[:, 2]
        ok = z > 2
        bb = float(self.bounce[k])
        focal = self.focal * (1 + 0.18 * bb)                       # kick bounce: zoom punch, springs back
        xs = self.W / 2 + focal * q[ok, 0] / z[ok]
        ys = self.H / 2 - focal * q[ok, 1] / z[ok]

        # colour: bin loudness, wing = channel
        pl, pr = self.profile(k)
        b = np.tile(self.bin, 3 * n_tr)[ok]
        p = np.where(P[ok, 0] < 0, pl[b], pr[b])
        L = self.lightness(p)
        rgb = self.colour(k, L, harm=a["harm"][k][b])
        head = np.zeros(3 * n_tr * self.N)
        head[:self.N] = 1.0
        w = (D / z[ok]) ** 2 * fade[ok] * (0.3 + head[ok] * (2.0 + 4 * kick)) * (900.0 / self.N) * (60.0 / n_tr) ** 0.5
        img = splat(np.zeros((self.H, self.W, 3), np.float32), xs, ys, rgb * w[:, None])

        # short screen feedback: glow streams outward (zoom in)
        g = math.exp(-1.0 / (fps * 0.05)) * (1 - 0.5 * min(1.0, max(0.0, bb)))
        fb = warp(self.prev, zoom=(1.0 + 0.006 * (0.5 + loud) + 0.02 * self.drop_env[k]) * focal / self.f_prev, rot=0.0)
        self.f_prev = focal
        out = np.maximum(img, g * fb)
        self.prev = out
        self.live = {"ρ": f"{rho:4.1f}", "Regime": "Chaos" if rho > RHO_C else "Ordnung", "Tempo": f"{rate * self.bar_f:4.2f}/Takt"}
        return out

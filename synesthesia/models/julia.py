"""Model B: Julia zoom. An endless, tempo-locked zoom into a Julia set whose parameter is the music.

Quadratic map f(z) = z^2 + c. It is parametrised by the multiplier lambda of its attracting (or
indifferent) fixed point alpha = lambda / 2:

    c = lambda / 2 - lambda^2 / 4,   lambda = rho_m * exp(2 pi i theta)

  * rotation number theta <- timbre (bar-smoothed timbre plane, PC1 -> 0.30 .. 0.45, PC2 small offset):
    theta = 1/3 gives three-armed "rabbit" spirals, 2/5 five arms, irrational values Siegel-disk swirls;
  * modulus rho_m <- chaos: rho_m = 1 + 0.45 (C - median C), clipped to 0.88 .. 1.12.
    rho_m < 1: alpha attracts, the Julia set is a connected closed curve (order);
    rho_m > 1: for most theta, c leaves the Mandelbrot set and the Julia set breaks into dust (chaos).
A repelling periodic point beta is the zoom centre: the 2-cycle point beta = (-1 + sqrt(-3 - 4c)) / 2 with
f^2-multiplier mu = 4 (1 + c) (default), or the fixed point beta = 1 - lambda / 2 with mu = 2 - lambda. Near
beta the Julia set is self-similar: zooming by the complex factor mu (scale |mu|, turn arg mu) shows the
same picture.
The camera window is z = beta + mu^-(m + delta) * w0 * u, so the zoom depth delta can run forever (wrap
delta mod 1), and one period of delta is one exact self-similar step:
  * d delta / dt = (0.5 + 0.5 loudness) per beat + kick push + drop surge: one similarity step per beat.
Colour: smooth escape count chi = nu(z) - delta is invariant under the zoom (nu(f^p(z)) = nu(z) - p), and
chi is the "depth" of a pixel: far from the set = coarse bands = low frequencies, close to the set =
fine filigree = high frequencies. A pixel at chi is lit by the loudness of frequency
f = 30 Hz * 2^(chi - chi0) (R2: spatial frequency ~ audio frequency, replaces R1), left half = left
channel, right half = right channel, colour = timbre (R4). Kick bounce: the window shrinks by 14 % on the kick and springs back (damped
spring, half-beat period), exposure follows the spring. The interior is drawn in the Koenigs coordinate of the attracting fixed point
(log-spiral arms that turn with theta and with the zoom), lit by the low mids and pulsing with the kick.
"""
import math

import numpy as np
from scipy.ndimage import gaussian_filter1d

from ..render import _resize
from .base import Model


class JuliaZoom(Model):
    key = "julia"
    title = "B · Julia-Zoom"
    laws = (
        "z → z² + c,  c = λ/2 − λ²/4,  λ = ρ·e^(2πiθ): Klangfarbe → Drehzahl θ (Arme), Chaos → ρ",
        "ρ < 1: zusammenhängende Kurve (Ordnung),  ρ > 1: Staub (Chaos)",
        "Endloser Spiral-Zoom um einen abstoßenden Punkt, Faktor μ = 4(1+c): ein Selbstähnlichkeits-Schritt pro Beat",
        "Feine Struktur nah am Rand = hohe Frequenzen, grobe Bänder = Bass; Helligkeit = Lautheit",
        "Kick = gedämpfte Feder: Zoom-Punch und Belichtung federn mit",
    )
    invert_entry = True

    def __init__(self, *args, res=0.66, m=2, maxit=160, target=2, w0=3.5, **kw):
        super().__init__(*args, **kw)
        self.target = target
        self.w, self.h = int(self.W * res) // 2 * 2, int(self.H * res) // 2 * 2
        ys, xs = np.mgrid[0:self.h, 0:self.w].astype(np.float64)
        s = 1.0 / self.h
        self.u = ((xs - self.w / 2) + 1j * (self.h / 2 - ys)) * s * 2      # height spans -1 .. 1
        self.xside = np.clip(0.5 + (xs - self.w / 2) / (0.2 * self.w), 0, 1)  # 0 = left channel, 1 = right
        self.m, self.maxit = m, maxit
        a = self.a
        zs = gaussian_filter1d(a["z_h"], self.bar_f / 2, axis=0)
        self.theta = 0.375 + 0.075 * np.tanh(zs[:, 0]) + 0.02 * np.tanh(zs[:, 1])
        c = a["chaos"]
        self.rho = np.clip(1 + 0.45 * (gaussian_filter1d(c, self.bar_f / 4) - np.median(c)), 0.88, 1.12)
        beat_f = self.bar_f / 4
        rate = (0.5 + 0.5 * a["loud_bar"]) / beat_f + 0.06 * self.env["kick"] + 0.25 * self.drop_env / beat_f
        self.delta = np.cumsum(rate)
        self.w0 = w0
        K = len(self.freqs)
        self.oct = np.log2(self.freqs / 30.0)                                # 0 .. 9 octaves

    def escape(self, z, c):
        nu = np.full(z.shape, -1.0)
        idx = np.arange(z.size)
        zf = z.ravel().copy()
        for it in range(self.maxit):
            zf = zf * zf + c
            out = (zf.real * zf.real + zf.imag * zf.imag) > 1e4
            if out.any():
                az = np.abs(zf[out])
                nu.flat[idx[out]] = it + 1 - np.log2(np.log(az) / np.log(1e2))
                keep = ~out
                zf, idx = zf[keep], idx[keep]
                if not len(zf):
                    break
        zend = np.full(z.shape, np.nan + 0j)
        zend.flat[idx] = zf
        return nu, zend

    def step(self, k):
        a = self.a
        lam = self.rho[k] * np.exp(2j * np.pi * self.theta[k])
        c = lam / 2 - lam * lam / 4
        if self.target == 2:                            # repelling 2-cycle point, f^2-multiplier 4 (1 + c)
            beta = (-1 + np.sqrt(-3 - 4 * c + 0j)) / 2
            mu = 4 * (1 + c)
        else:
            beta = 1 - lam / 2
            mu = 2 - lam
        d = self.delta[k]
        ph = d % 1.0
        bb = float(self.bounce[k])
        z = beta + np.exp(-(self.m + ph) * np.log(mu)) * self.w0 * (1 - 0.14 * bb) * self.u     # kick: zoom punch
        nu, zend = self.escape(z, c)
        inside = nu < 0
        # interior: Koenigs coordinate w = (z_N - alpha) / lambda^N is invariant under f, so its angle and
        # log-modulus give a pattern that turns with theta (log-spiral arms)
        N = self.maxit
        wv = np.where(inside, zend - lam / 2, 1.0)
        ang = np.angle(wv) - N * np.angle(lam)
        lr = np.log(np.abs(wv) + 1e-12) - N * math.log(min(abs(lam), 0.999))
        swirl = 0.5 + 0.5 * np.cos(3 * ang + 2.5 * lr - 2 * np.pi * d)
        chi = nu - self.target * ph                     # zoom-invariant depth (one step = target iterations)
        # depth -> frequency: chi0 maps to 30 Hz, each step in chi one octave
        o = np.clip(chi - self.target * (self.m - 0.5), 0, 9.0)
        pl, pr = self.profile(k)
        p_l = np.interp(o, self.oct, pl)
        p_r = np.interp(o, self.oct, pr)
        p = (1 - self.xside) * p_l + self.xside * p_r
        bins = np.clip(np.searchsorted(self.oct, o), 0, len(self.oct) - 1)
        harm = a["harm"][k][bins]
        L = self.lightness(p) * (1 + 0.6 * self.env["snare"][k] * (o > 4))
        # thin outlines where chi crosses an integer: makes the self-similar structure readable
        edge = np.exp(-((chi - np.round(chi)) / 0.06) ** 2) * 0.25
        Lin = (0.1 + 0.45 * float(a["psi_low"][k]) * (0.5 + self.env["kick"][k])) * (0.35 + 0.65 * swirl)
        L = np.where(inside, Lin, L * (0.75 + edge)) * max(0.4, 1 + 0.3 * bb)
        harm = np.where(inside, 1.0, harm)
        rgb = self.colour(k, L, harm=harm).astype(np.float32)
        self.live = {"θ": f"{self.theta[k]:.3f}", "ρ": f"{self.rho[k]:.3f}",
                     "Form": "Kurve" if self.rho[k] < 1 else "Staub", "Tiefe": f"{d - self.delta[self.k_start]:.1f}"}
        return _resize(rgb, self.W, self.H)

    def compose_args(self):
        return ((0.12, 0.10), 1.6)

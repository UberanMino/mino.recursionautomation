"""Model F: Fractal flight. The camera glides forever through a 3D fractal world (kaleidoscopic IFS,
Menger family) that the music shapes, lights and colours.

World: a lattice of fractal cubes (period 2 in x, y, z). Each cube is a kaleidoscopic IFS (Knighty's KIFS):
    repeat n times:  p = |p|;  sort so p_x >= p_y >= p_z;  p = Rot p;
                     p = s p - c (s - 1)  (z: only above the middle plane);   distance = box(p) / s^n
With s = 3, c = (1, 1, 1) and Rot = identity this is the Menger sponge: through every cube runs an empty
corridor along the z axis, so the camera can fly forever. The distance estimate is ray-marched per pixel.

  * Order <-> chaos (R6): the fold rotation Rot turns by alpha = 0.9 C^1.1 n(t) about z and beta = 0.6 C^1.1 n'(t)
    about x (both clipped to 0.6 rad), applied from the second fold level on, and the scale is s = 3 + 0.35 C^1.1. Ordered music = exact, crystalline Menger architecture;
    chaotic music = twisted, broken, overgrown geometry.
  * Timbre -> architecture: c = (1, 1 + 0.25 |z1|, 1 + 0.25 |z2|) (bar-smoothed timbre plane; offsets >= 1 only
    widen the holes).
  * Time = forward flight (as in the tunnel): speed = 0.45 + 0.9 loudness + 0.8 tension + kick thrust
    (one cube per bar at speed 1). The "now" plane is d0 = 0.6 ahead of the camera.
  * Spectrum built into the world (R1, R2, R5): a surface point lights up with the loudness of the frequency
    that belongs to its height (floor = 30 Hz, ceiling = 16 kHz), left of the camera from the left channel,
    right from the right, and taken from the moment at which the camera will reach it. The future is visible
    ahead and arrives in time.
  * Kick rings: every kick is a ring of light in the world at the place the now-plane reaches on the kick.
  * Colour (R4, richer): orbit-trap colouring through a full-spectrum cosine palette
    rgb = 0.5 + 0.5 cos(2 pi (f * trap + hue + (0, 1/3, 2/3))). Hue <- timbre (PC1/PC2 angle), every section
    turns the palette by the golden ratio (a new colour world per section), chaos raises the palette frequency f
    (more colour bands); the hue also advances with distance, so the corridor ahead runs through the spectrum. Glow accumulates along the ray near surfaces.
  * Corridor: the first fold level is never rotated and the offsets are >= 1, so the large-scale z corridor of the
    Menger sponge stays; chaos only twists the finer levels. Checked on Digits: distance from the camera (and a
    ring of radius 0.06 around it) to the fractal >= 0.12 in every 3rd frame of the whole song (tested, not proven).
  * Path: slow lateral wander inside the corridor, roll = (0.3 + timbre speed) rad/bar, sign flips per section.
  * Kick bounce (damped spring, half beat): focal-length punch (1 + 0.25 x), the world breathes
    (scale s * (1 + 0.025 x)), exposure * (1 + 0.6 x); trails are cut by 30 % on the hit.
"""
import math

import numpy as np
from numba import njit, prange
from scipy.ndimage import gaussian_filter1d

from ..render import _resize
from .base import Model, impulses, warp

TAU = 2 * math.pi


@njit(fastmath=True, cache=True, inline="always")
def _de(px, py, pz, sc, cx, cy, cz, per, niter, r):
    px = px - per * math.floor(px / per + 0.5)
    py = py - per * math.floor(py / per + 0.5)
    pz = pz - per * math.floor(pz / per + 0.5)
    trap = 1e9
    k = sc - 1.0
    for it in range(niter):
        px = abs(px)
        py = abs(py)
        pz = abs(pz)
        if px < py:
            px, py = py, px
        if px < pz:
            px, pz = pz, px
        if py < pz:
            py, pz = pz, py
        if it >= 1:                       # the first fold keeps the corridor; chaos twists the finer levels
            qx = r[0] * px + r[1] * py + r[2] * pz
            qy = r[3] * px + r[4] * py + r[5] * pz
            qz = r[6] * px + r[7] * py + r[8] * pz
        else:
            qx, qy, qz = px, py, pz
        px = sc * qx - cx * k
        py = sc * qy - cy * k
        pz = sc * qz
        if pz > 0.5 * cz * k:
            pz -= cz * k
        d2 = px * px + py * py + pz * pz
        if d2 < trap:
            trap = d2
    dx = abs(px) - 1.0
    dy = abs(py) - 1.0
    dz = abs(pz) - 1.0
    ox = max(dx, 0.0)
    oy = max(dy, 0.0)
    oz = max(dz, 0.0)
    d = math.sqrt(ox * ox + oy * oy + oz * oz) + min(max(dx, max(dy, dz)), 0.0)
    return d * sc ** (-niter), trap


@njit(fastmath=True, cache=True, inline="always")
def _path_xy(z):
    return (0.09 * math.sin(TAU * z / 7.0) + 0.05 * math.sin(TAU * z / 3.1),
            0.07 * math.sin(TAU * z / 5.3 + 1.0))


@njit(fastmath=True, cache=True, inline="always")
def _scene(px, py, pz, sc, cx, cy, cz, per, niter, r, tube):
    d, trap = _de(px, py, pz, sc, cx, cy, cz, per, niter, r)
    ax, ay = _path_xy(pz)
    if tube <= 0.0:
        return d, trap
    dt = tube - math.sqrt((px - ax) ** 2 + (py - ay) ** 2)       # optional: carve a flight tube
    return max(d, dt), trap


@njit(parallel=True, fastmath=True, cache=True)
def _render(out, cam, B, focal, prm, r, profL, profR, kf0, f_per_unit, kick_s, kick_w, s_now, d0):
    H, W = out.shape[0], out.shape[1]
    sc, cx, cy, cz, per = prm[0], prm[1], prm[2], prm[3], prm[4]
    niter = int(prm[5])
    maxst = int(prm[6])
    hue, pfreq, fog, glowk, emk, corridor, tube = prm[7], prm[8], prm[9], prm[10], prm[11], prm[12], prm[13]
    nF, K = profL.shape[0], profL.shape[1]
    nk = kick_s.shape[0]
    for j in prange(H):
        for i in range(W):
            ux = (i + 0.5 - W * 0.5) / focal
            uy = -(j + 0.5 - H * 0.5) / focal
            dx = B[0, 0] * ux + B[1, 0] * uy + B[2, 0]
            dy = B[0, 1] * ux + B[1, 1] * uy + B[2, 1]
            dz = B[0, 2] * ux + B[1, 2] * uy + B[2, 2]
            nrm = math.sqrt(dx * dx + dy * dy + dz * dz)
            dx /= nrm
            dy /= nrm
            dz /= nrm
            t = 0.02
            glow = 0.0
            hit = False
            trap = 0.0
            st = 0
            for st in range(maxst):
                px = cam[0] + t * dx
                py = cam[1] + t * dy
                pz = cam[2] + t * dz
                d, trap = _scene(px, py, pz, sc, cx, cy, cz, per, niter, r, tube)
                glow += 1.0 / (1.0 + (d * 40.0) ** 2)
                if d < 0.0012 * t + 0.0002:
                    hit = True
                    break
                t += d * 0.85
                if t > 12.0:
                    break
            # palette hue from the orbit trap
            tr = math.log(trap + 1e-4) * pfreq + hue + 0.14 * t      # trap + distance: several hues per frame
            c0 = (0.5 + 0.5 * math.cos(TAU * (tr + 0.0))) ** 2.4          # ^1.8: towards pure hues
            c1 = (0.5 + 0.5 * math.cos(TAU * (tr + 0.333))) ** 2.4
            c2 = (0.5 + 0.5 * math.cos(TAU * (tr + 0.667))) ** 2.4
            fr = math.exp(-t * fog)
            g0 = (0.5 + 0.5 * math.cos(TAU * (hue + 0.15))) ** 2
            g1 = (0.5 + 0.5 * math.cos(TAU * (hue + 0.483))) ** 2
            g2 = (0.5 + 0.5 * math.cos(TAU * (hue + 0.817))) ** 2
            gl = glowk * glow / maxst
            if hit:
                px = cam[0] + t * dx
                py = cam[1] + t * dy
                pz = cam[2] + t * dz
                e = 0.0008 * (1.0 + t)
                a1, _ = _scene(px + e, py - e, pz - e, sc, cx, cy, cz, per, niter, r, tube)
                a2, _ = _scene(px - e, py - e, pz + e, sc, cx, cy, cz, per, niter, r, tube)
                a3, _ = _scene(px - e, py + e, pz - e, sc, cx, cy, cz, per, niter, r, tube)
                a4, _ = _scene(px + e, py + e, pz + e, sc, cx, cy, cz, per, niter, r, tube)
                nx = a1 - a2 - a3 + a4
                ny = -a1 - a2 + a3 + a4
                nz = -a1 + a2 - a3 + a4
                nn = math.sqrt(nx * nx + ny * ny + nz * nz) + 1e-12
                nx /= nn
                ny /= nn
                nz /= nn
                dif = max(0.0, -(nx * dx + ny * dy + nz * dz))
                top = 0.5 + 0.5 * (nx * B[1, 0] + ny * B[1, 1] + nz * B[1, 2])
                ao = 1.0 - st / maxst
                light = (0.04 + 0.96 * dif * dif) * (0.5 + 0.5 * top) * ao * ao
                # spectrum at this height, from the moment the now-plane reaches this point
                rx, ry, rz = px - cam[0], py - cam[1], pz - cam[2]
                hy = (rx * B[1, 0] + ry * B[1, 1] + rz * B[1, 2]) / corridor
                hx = rx * B[0, 0] + ry * B[0, 1] + rz * B[0, 2]
                depth = rx * B[2, 0] + ry * B[2, 1] + rz * B[2, 2]
                u = min(1.0, max(0.0, 0.5 + 0.5 * hy))
                b = int(u * (K - 1))
                kf = kf0 + int((depth - d0) * f_per_unit)
                if kf < 0:
                    kf = 0
                if kf > nF - 1:
                    kf = nF - 1
                p = profL[kf, b] if hx < 0 else profR[kf, b]
                if depth < d0:
                    p *= max(0.0, 1.0 + (depth - d0) * 3.0)
                em = emk * p ** 1.6
                # kick rings: world position along the flight = s_now + depth
                sp = s_now + depth
                ring = 0.0
                for q in range(nk):
                    dd = sp - kick_s[q]
                    if abs(dd) < 0.06:
                        ring += kick_w[q] * (1.0 - abs(dd) / 0.06)
                lv = min(1.1, light + em)
                c0 = c0 * lv + ring * (0.3 + 0.7 * c0)
                c1 = c1 * lv + ring * (0.3 + 0.7 * c1)
                c2 = c2 * lv + ring * (0.3 + 0.7 * c2)
                out[j, i, 0] = c0 * fr + g0 * gl
                out[j, i, 1] = c1 * fr + g1 * gl
                out[j, i, 2] = c2 * fr + g2 * gl
            else:
                out[j, i, 0] = g0 * gl
                out[j, i, 1] = g1 * gl
                out[j, i, 2] = g2 * gl


def _rot(ax, ay, az):
    ca, sa, cb, sb, cg, sg = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    Rx = np.array([[1, 0, 0], [0, ca, -sa], [0, sa, ca]])
    Ry = np.array([[cb, 0, sb], [0, 1, 0], [-sb, 0, cb]])
    Rz = np.array([[cg, -sg, 0], [sg, cg, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


class FractalFlight(Model):
    key = "fractal"
    title = "F · Fraktal-Flug"
    laws = (
        "Endloser Flug durch eine 3D-Fraktalwelt (Menger-Kaleidoskop, p → s·Rot|p| − c(s−1)); Zeit = vorwärts",
        "Ordnung = exakte Kristall-Architektur, Chaos dreht und verbiegt die Faltung (Rot, s = 3 + 0,35·Chaos)",
        "Wände leuchten auf der Höhe ihrer Frequenz (unten Bass, oben Höhen), aus dem Moment, in dem du dort bist",
        "Farbe: volles Spektrum, Klangfarbe dreht den Farbton, jeder Abschnitt eine neue Farbwelt; Kick = Ring + Feder",
    )
    invert_entry = True

    def __init__(self, *args, res=0.8, niter=4, maxsteps=110, seed=21, **kw):
        super().__init__(*args, **kw)
        self.w, self.h = int(self.W * res) // 2 * 2, int(self.H * res) // 2 * 2
        self.buf = np.zeros((self.h, self.w, 3), np.float32)
        self.niter, self.maxsteps = niter, maxsteps
        S, a, fps = self.S, self.a, self.fps
        n = S.n
        rng = np.random.default_rng(seed)
        bar = S.bar_s
        kick = S.hits["kick"]
        kw_ = np.clip(kick[:, 2] / (np.percentile(kick[:, 2], 90) + 1e-9), 0, 1.2) if len(kick) else np.zeros(0)
        entries = [s["start"] for s in S.sections if s.get("entry")]
        v = (0.45 + 0.9 * a["loud_bar"] + 0.8 * a["tension"]
             + impulses(kick[:, 0] if len(kick) else [], 0.55 * kw_, n, fps, bar / 8)
             + impulses(entries, [2.5] * len(entries), n, fps, bar / 2))
        self.ds = 2.0 * v / (bar * fps)                    # one cube (2 units) per bar at speed 1
        self.s = np.concatenate([[0.0], np.cumsum(self.ds[:-1])])
        self.d0 = 0.6
        kf = np.floor(kick[:, 0] * fps).astype(int) if len(kick) else np.zeros(0, int)
        ok = (kf >= 0) & (kf < n)
        self.kick_s = (self.s[kf[ok]] + self.d0).astype(np.float64)
        self.kick_w = (1.4 * kw_[ok]).astype(np.float64)
        sec = [S.sections[i] for i in a["section"]]
        self.sdir = np.array([s["dir"] for s in sec], float)
        self.roll = np.cumsum(self.sdir * (0.3 + 1.0 * a["timbre_speed"]) / (bar * fps))
        C = np.clip(a["chaos"], 0, 1) ** 1.1
        self.C = gaussian_filter1d(C, bar * fps / 4)
        nz1 = gaussian_filter1d(rng.standard_normal(n), bar * fps)
        nz2 = gaussian_filter1d(rng.standard_normal(n), bar * fps)
        self.n1, self.n2 = nz1 / (nz1.std() + 1e-9), nz2 / (nz2.std() + 1e-9)
        zs = gaussian_filter1d(a["z_h"], bar * fps / 2, axis=0)
        self.zs = np.tanh(zs / 1.5)
        # hue: timbre angle + golden-ratio turn per section, cross-faded over half a bar
        sec_hue = np.array([(s["index"] * 0.618) % 1.0 for s in sec])
        sec_hue = np.unwrap(sec_hue * TAU) / TAU
        sec_hue = gaussian_filter1d(sec_hue, bar * fps / 4)
        self.hue = sec_hue + 0.12 * np.arctan2(self.zs[:, 1], self.zs[:, 0]) / math.pi
        self.profL = np.ascontiguousarray(a["prof_l"], np.float64)
        self.profR = np.ascontiguousarray(a["prof_r"], np.float64)
        self.prev = np.zeros((self.H, self.W, 3), np.float32)
        self.focal0 = 0.6 * self.h
        self.f_prev = self.focal0

    def path(self, s):
        x = 0.09 * math.sin(TAU * s / 7.0) + 0.05 * math.sin(TAU * s / 3.1)
        y = 0.07 * math.sin(TAU * s / 5.3 + 1.0)
        return np.array([x, y, s])

    def step(self, k):
        a = self.a
        b = float(self.bounce[k])
        C = float(self.C[k])
        s_now = float(self.s[k])
        cam = self.path(s_now)
        ahead = self.path(s_now + 0.5)
        fwd = (ahead - cam) / np.linalg.norm(ahead - cam)
        up0 = np.array([0.0, 1.0, 0.0])
        right = np.cross(up0, fwd)
        right /= np.linalg.norm(right)
        up = np.cross(fwd, right)
        ro = float(self.roll[k])
        r2 = math.cos(ro) * right + math.sin(ro) * up
        u2 = -math.sin(ro) * right + math.cos(ro) * up
        Bm = np.stack([r2, u2, fwd])
        # the rotation acts only on the deeper fold levels (see _de), so the corridor stays open
        rot = _rot(float(np.clip(0.6 * C * self.n2[k], -0.6, 0.6)), 0.0,
                   float(np.clip(0.9 * C * self.n1[k], -0.6, 0.6))).ravel().astype(np.float64)
        sc = (3.0 + 0.35 * C) * (1 + 0.025 * b)
        z1, z2 = self.zs[k]
        prm = np.array([sc, 1.0, 1.0 + 0.25 * abs(z1), 1.0 + 0.25 * abs(z2), 2.0, self.niter, self.maxsteps,
                        float(self.hue[k]), 0.4 + 0.25 * C, 0.25, 0.3, 0.9, 0.34, 0.0])
        focal = self.focal0 * (1 + 0.25 * b)
        _render(self.buf, cam, Bm, focal, prm, rot, self.profL, self.profR, k, 1.0 / max(self.ds[k], 1e-4),
                self.kick_s, self.kick_w, s_now, self.d0)
        img = _resize(self.buf, self.W, self.H)
        # trails stream outward with the flight, cut on the kick
        g = math.exp(-1.0 / (self.fps * (0.02 + 0.06 * float(a["harm_bar"][k])))) * (1 - 0.3 * min(1.0, max(0.0, b)))
        fb = warp(self.prev, zoom=max(1.0, (1 + 0.3 * self.ds[k]) * focal / self.f_prev))   # never shrink: no seams
        self.f_prev = focal
        out = np.maximum(img, g * fb) * max(0.35, 1 + 0.6 * b)
        self.prev = out
        self.live = {"Chaos": f"{C:.2f}", "Skala": f"{sc:.2f}", "Tempo": f"{self.ds[k] * self.bar_f / 2:.2f} Würfel/Takt",
                     "Feder": f"{b:+.2f}"}
        return out

    def compose_args(self):
        return ((0.16, 0.12), 1.1)

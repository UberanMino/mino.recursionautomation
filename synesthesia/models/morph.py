"""Model G: Shape-shifter world. The flight of model F, but the fractal itself is plastic: it morphs without seams
between whole families of 3D fractals in reaction to the music, the walls breathe and flow, and the trails are
rainbow tracers.

One generalised fold formula covers all shape families; every one of its parameters reaches the identity at an end
of its range, so any two shapes are joined by a continuous path (seamless morphs, no cuts):
    p <- warp(p):  p + A (sin(W p_y + ph), sin(W p_z + 1.3 ph), sin(W p_x + 0.7 ph))     (breathing, flowing walls)
    p <- p mod 2   (endless lattice of cells)
    level 0: Menger (as in F), keeps the large halls open
    levels 1..n-1:
        p <- |p|;  sort x >= y >= z (three plane reflections)
        p <- box fold (Mandelbox)    clamp(p, -L, L) 2 - p,   L = 1 + 10 (1 - w_box)^3      (w_box = 0: identity)
        p <- sphere fold             r^2 < m^2: p / m^2,  r^2 < 1: p / r^2,  m^2 = 1 - 0.75 w_inv  (0: identity)
        p <- Rot p;  p <- s p - c (s - 1);   dr <- dr |s| (and the sphere-fold factor)
    distance = mix(box(p), |p| - 1, w_round) / dr
Reflections and folds are piecewise isometries, so the distance estimate stays valid through every morph; the
warp has Lipschitz constant <= 1 + A W, the ray step is divided by it.

  * Shape <- sound: six shapes (Menger, twisted crystal, cave halls, bubble sponge, coral, temple; see PRESETS)
    sit at fixed angles on the timbre plane (bar-smoothed MFCC-PCA). The weight of a shape is a Gaussian
    of its distance to the current timbre; every section adds its own home shape (+1.2), and an anchor
    drift of one turn per 8 bars x (0.25 + tension) keeps the world moving even in steady music.
  * Morph speed <- change of sound: the shape vector follows its target through a critically damped filter with
    time constant tau = bar x (1.2 - 0.9 timbre speed), on section entries 1/4 bar (a new part = a new world).
  * Breathing walls: A = 0.012 + 0.035 harmonic share + 0.02 tension, swelling with every beat
    (x (1 + 0.35 sin(pi beat))) and with the kick spring; the phase flows with loudness. Tonal pads melt the world,
    dry drums keep it crisp.
  * Chaos (R6): twists the fold rotation of the deeper levels (as in F) and raises the scale.
  * Spectrum in the walls, kick rings, flight speed and path: as in F (R1, R2, R5).
  * Colour (R4): full-spectrum orbit-trap palette, hue <- timbre + golden-ratio turn per section, and the
    colours crawl over the surfaces (stripe phase advances with hi-hat density).
  * Tracers: the previous frame is hue-rotated about the grey axis by 0.006 + 0.018 harmonic share turns per
    frame, zoomed with the flight and turned slightly with the section direction, then max-blended: every edge
    leaves a rainbow trail. Kick: trails cut by 35 %, focal punch, exposure spring, the world breathes.
  * Corridor: a thin flight channel (radius 0.11) is blended into the geometry with a smooth maximum, so no shape
    can close over the camera. Measured on Digits: the geometry comes closer than 0.11 in 53 % of the frames
    (the channel then shapes the walls around the camera), and would enclose it in 7.8 %.
"""
import math

import numpy as np
from numba import njit, prange
from scipy.ndimage import gaussian_filter1d

from ..render import _resize
from .base import Model, impulses, warp
from .fractal import _path_xy, _rot

TAU = 2 * math.pi
S2, S3 = 1 / math.sqrt(2), 1 / math.sqrt(3)

# shape presets (deeper fold levels): fold rotation about x and z (rad), w_box, w_inv, w_round, scale, offset c (3)
PRESETS = {
    "menger":   [0.0, 0.0, 0.0, 0.0, 0.0, 3.0, (1.0, 1.0, 1.0)],
    "kristall": [0.35, 0.25, 0.0, 0.0, 0.0, 2.7, (1.0, 1.1, 0.9)],
    "hoehle":   [0.0, 0.0, 0.5, 1.0, 0.0, 2.8, (1.2, 1.2, 1.2)],
    "blasen":   [0.0, 0.0, 0.0, 0.8, 1.0, 2.7, (1.0, 1.0, 1.0)],
    "koralle":  [0.2, -0.3, 0.4, 0.4, 0.4, 2.3, (1.0, 0.7, 1.2)],
    "tempel":   [0.0, 0.0, 0.6, 0.0, 0.0, 3.3, (1.0, 1.3, 1.0)],
}
ORDER = ("menger", "kristall", "hoehle", "blasen", "koralle", "tempel")
MENGER_N = (S2, -S2, 0.0, S2, 0.0, -S2, 0.0, S2, -S2)        # reflections that sort x >= y >= z


def _vec(p):
    return np.array([*p[:6], *p[6]], float)


@njit(fastmath=True, cache=True, inline="always")
def _reflect(px, py, pz, nx, ny, nz):
    t = px * nx + py * ny + pz * nz
    if t < 0.0:
        px -= 2.0 * t * nx
        py -= 2.0 * t * ny
        pz -= 2.0 * t * nz
    return px, py, pz


@njit(fastmath=True, cache=True, inline="always")
def _de(px, py, pz, g, r, niter):
    # g: 0-8 normals, 9 L, 10 m2, 11 w_round, 12 s, 13-15 c, 16 per, 17 A, 18 W, 19 ph, 20 tube, 21 tube k,
    #    22 s0, 23-24 c0 (level 0)
    A, Wf, ph = g[17], g[18], g[19]
    wx = px + A * math.sin(Wf * py + ph)
    wy = py + A * math.sin(Wf * pz + 1.3 * ph)
    wz = pz + A * math.sin(Wf * px + 0.7 * ph)
    per = g[16]
    px = wx - per * math.floor(wx / per + 0.5)
    py = wy - per * math.floor(wy / per + 0.5)
    pz = wz - per * math.floor(wz / per + 0.5)
    L, m2, sc = g[9], g[10], g[12]
    k = sc - 1.0
    dr = 1.0
    trap = 1e9
    r2 = 0.0
    for it in range(niter):
        px = abs(px)
        py = abs(py)
        pz = abs(pz)
        if it == 0:                       # level 0 stays Menger (sort): keeps the large halls and the corridor
            if px < py:
                px, py = py, px
            if px < pz:
                px, pz = pz, px
            if py < pz:
                py, pz = pz, py
            s0 = g[22]
            k0 = s0 - 1.0
            px = s0 * px - k0
            py = s0 * py - g[23] * k0
            pz = s0 * pz
            if pz > 0.5 * g[24] * k0:
                pz -= g[24] * k0
            dr *= s0
            continue
        px, py, pz = _reflect(px, py, pz, g[0], g[1], g[2])
        px, py, pz = _reflect(px, py, pz, g[3], g[4], g[5])
        px, py, pz = _reflect(px, py, pz, g[6], g[7], g[8])
        if px > L:
            px = 2.0 * L - px
        elif px < -L:
            px = -2.0 * L - px
        if py > L:
            py = 2.0 * L - py
        elif py < -L:
            py = -2.0 * L - py
        if pz > L:
            pz = 2.0 * L - pz
        elif pz < -L:
            pz = -2.0 * L - pz
        r2 = px * px + py * py + pz * pz
        if r2 < m2:
            f = 1.0 / m2
        elif r2 < 1.0:
            f = 1.0 / r2
        else:
            f = 1.0
        px *= f
        py *= f
        pz *= f
        dr *= f
        qx = r[0] * px + r[1] * py + r[2] * pz
        qy = r[3] * px + r[4] * py + r[5] * pz
        qz = r[6] * px + r[7] * py + r[8] * pz
        px = sc * qx - g[13] * k
        py = sc * qy - g[14] * k
        pz = sc * qz
        if pz > 0.5 * g[15] * k:
            pz -= g[15] * k
        dr *= abs(sc)
        r2 = px * px + py * py + pz * pz
        if r2 < trap:
            trap = r2
    dx = abs(px) - 1.0
    dy = abs(py) - 1.0
    dz = abs(pz) - 1.0
    ox = max(dx, 0.0)
    oy = max(dy, 0.0)
    oz = max(dz, 0.0)
    dbox = math.sqrt(ox * ox + oy * oy + oz * oz) + min(max(dx, max(dy, dz)), 0.0)
    dsph = math.sqrt(r2) - 1.0
    d = (dbox + g[11] * (dsph - dbox)) / dr
    return d, trap


@njit(fastmath=True, cache=True, inline="always")
def _scene(px, py, pz, g, r, niter):
    d, trap = _de(px, py, pz, g, r, niter)
    ax, ay = _path_xy(pz)
    a = d
    b = g[20] - math.sqrt((px - ax) ** 2 + (py - ay) ** 2)      # flight channel, blended in by a smooth max
    kk = g[21]
    h = max(kk - abs(a - b), 0.0) / kk
    return max(a, b) + h * h * kk * 0.25, trap


@njit(parallel=True, fastmath=True, cache=True)
def _render(out, cam, B, focal, g, r, prm, profL, profR, kf0, f_per_unit, kick_s, kick_w, s_now, d0):
    H, W = out.shape[0], out.shape[1]
    niter, maxst = int(prm[0]), int(prm[1])
    hue, pfreq, fog, glowk, emk, corridor, stripe, crawl = prm[2], prm[3], prm[4], prm[5], prm[6], prm[7], prm[8], prm[9]
    lip = 1.0 + g[17] * g[18]
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
                d, trap = _scene(px, py, pz, g, r, niter)
                glow += 1.0 / (1.0 + (d * 40.0) ** 2)
                if d < 0.0012 * t + 0.0002:
                    hit = True
                    break
                t += d * 0.85 / lip
                if t > 12.0:
                    break
            lt = math.log(trap + 1e-4)
            tr = lt * pfreq + hue + 0.14 * t
            c0 = (0.5 + 0.5 * math.cos(TAU * (tr + 0.0))) ** 2.4
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
                a1, _ = _scene(px + e, py - e, pz - e, g, r, niter)
                a2, _ = _scene(px - e, py - e, pz + e, g, r, niter)
                a3, _ = _scene(px - e, py + e, pz - e, g, r, niter)
                a4, _ = _scene(px + e, py + e, pz + e, g, r, niter)
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
                # crawling colour stripes over the surfaces
                light *= 1.0 - stripe + stripe * (0.5 + 0.5 * math.cos(TAU * (lt * 1.7 - crawl)))
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


def _hue_rot(turns):
    """RGB rotation about the grey axis (Rodrigues)."""
    a = TAU * turns
    c, s = math.cos(a), math.sin(a)
    u = np.full(3, 1 / math.sqrt(3))
    K = np.array([[0, -u[2], u[1]], [u[2], 0, -u[0]], [-u[1], u[0], 0]])
    return (c * np.eye(3) + s * K + (1 - c) * np.outer(u, u)).astype(np.float32)


def _damp(target, tau_f):
    """Critically damped follower (two cascaded one-pole filters) with a time constant per frame (frames)."""
    al = 1 - np.exp(-2.0 / np.maximum(tau_f, 1.0))
    y1 = np.empty_like(target)
    y2 = np.empty_like(target)
    y1[0] = y2[0] = target[0]
    for k in range(1, len(target)):
        y1[k] = y1[k - 1] + al[k] * (target[k] - y1[k - 1])
        y2[k] = y2[k - 1] + al[k] * (y1[k] - y2[k - 1])
    return y2


class MorphWorld(Model):
    key = "morph"
    title = "G · Gestaltwandler-Welt"
    laws = (
        "Eine Faltungsformel, sechs Fraktal-Familien (Menger, Kristall, Höhle, Blasen, Koralle, Tempel), stufenlos verbunden",
        "Klangfarbe wählt die Form, jeder Abschnitt hat seine Heimat-Form; je schneller der Klang wechselt, desto schneller das Morphen",
        "Wände atmen mit jedem Beat und zerfließen bei tonalen Flächen; Chaos verdreht die Faltung",
        "Regenbogen-Tracer, Farben kriechen über die Flächen; Kick = Lichtring, Atemstoß, Zoom-Punch",
    )
    invert_entry = True

    def __init__(self, *args, res=0.8, niter=4, maxsteps=120, seed=21, preset=None, **kw):
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
        self.ds = 2.0 * v / (bar * fps)
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
        nz = [gaussian_filter1d(rng.standard_normal(n), bar * fps) for _ in range(2)]
        self.nz = [x / (x.std() + 1e-9) for x in nz]
        zs = np.tanh(gaussian_filter1d(a["z_h"], bar * fps / 2, axis=0) / 1.5)
        self.zs = zs
        sec_hue = np.unwrap(np.array([(s["index"] * 0.618) % 1.0 for s in sec]) * TAU) / TAU
        self.hue = gaussian_filter1d(sec_hue, bar * fps / 4) + 0.12 * np.arctan2(zs[:, 1], zs[:, 0]) / math.pi

        # --- shape: weights on the timbre plane + section home shape + drift, then a critically damped morph
        P = np.stack([_vec(PRESETS[k]) for k in ORDER])
        nP = len(ORDER)
        tension = a["tension"]
        drift = TAU * np.cumsum((0.25 + tension) / (8 * bar * fps))
        ang = TAU * np.arange(nP) / nP
        ax_ = np.cos(ang[None, :] + drift[:, None])
        ay_ = np.sin(ang[None, :] + drift[:, None])
        rad = np.clip(np.hypot(zs[:, 0], zs[:, 1]), 0.35, 1.0)
        d2 = (zs[:, :1] - rad[:, None] * ax_) ** 2 + (zs[:, 1:] - rad[:, None] * ay_) ** 2
        wgt = np.exp(-d2 / 0.35)
        home = np.array([(s["index"] * 5 + 2) % nP for s in sec])
        wgt[np.arange(n), home] += 1.2
        if preset is not None:
            wgt[:] = 0.0
            wgt[:, ORDER.index(preset)] = 1.0
        wgt /= wgt.sum(1, keepdims=True)
        target = wgt @ P
        ent = impulses(entries, [1.0] * len(entries), n, fps, bar / 2)
        tau = bar * fps * np.clip(1.2 - 0.9 * a["timbre_speed"], 0.35, 1.2)
        tau = tau * (1 - 0.8 * np.clip(ent, 0, 1))
        self.shape = _damp(target, tau)
        self.wgt = _damp(wgt, tau)

        # breathing: beat phase from the tracked beats
        beats = np.asarray(S.beats, float)
        tt = np.arange(n) / fps
        self.beat = np.interp(tt, beats, np.arange(len(beats))) if len(beats) > 1 else tt / (bar / 4)
        self.A = 0.012 + 0.035 * a["harm_bar"] + 0.02 * tension
        self.ph = np.cumsum(TAU * (0.15 + 0.5 * a["loud_bar"]) / (bar / 4 * fps))
        hat = S.hits["hat"]
        dens = impulses(hat[:, 0] if len(hat) else [], [1.0] * len(hat), n, fps, bar / 4) if len(hat) else np.zeros(n)
        self.crawl = np.cumsum((0.15 + 0.25 * np.clip(dens / (np.percentile(dens, 95) + 1e-9), 0, 1.5)) / fps)

        self.profL = np.ascontiguousarray(a["prof_l"], np.float64)
        self.profR = np.ascontiguousarray(a["prof_r"], np.float64)
        self.prev = np.zeros((self.H, self.W, 3), np.float32)
        self.focal0 = 0.6 * self.h
        self.f_prev = self.focal0

    def path(self, s):
        x, y = _path_xy(s)
        return np.array([x, y, s])

    def geometry(self, k, b):
        C = float(self.C[k])
        sh = self.shape[k]
        rx, rz, wbox, winv, wround, sc = sh[:6]
        L = 1.0 + 10.0 * (1.0 - min(1.0, max(0.0, wbox))) ** 3
        m2 = 1.0 - 0.75 * min(1.0, max(0.0, winv))
        sc = (sc + 0.3 * C) * (1 + 0.025 * b)
        A = float(self.A[k]) * (1 + 0.35 * math.sin(math.pi * self.beat[k])) * (1 + 0.8 * max(b, 0.0))
        z1, z2 = self.zs[k]
        g = np.array([*MENGER_N, L, m2, wround, sc, sh[6], sh[7], sh[8], 2.0,
                      A, TAU / 0.7, float(self.ph[k]), 0.11, 0.08,
                      (3.0 + 0.2 * C) * (1 + 0.025 * b), 1.0 + 0.25 * abs(z1), 1.0 + 0.25 * abs(z2)])
        rot = _rot(rx + float(np.clip(0.6 * C * self.nz[1][k], -0.6, 0.6)), 0.0,
                   rz + float(np.clip(0.9 * C * self.nz[0][k], -0.6, 0.6))).ravel().astype(np.float64)
        return g, rot

    def step(self, k):
        a = self.a
        b = float(self.bounce[k])
        C = float(self.C[k])
        s_now = float(self.s[k])
        cam = self.path(s_now)
        ahead = self.path(s_now + 0.5)
        fwd = (ahead - cam) / np.linalg.norm(ahead - cam)
        right = np.cross(np.array([0.0, 1.0, 0.0]), fwd)
        right /= np.linalg.norm(right)
        up = np.cross(fwd, right)
        ro = float(self.roll[k])
        Bm = np.stack([math.cos(ro) * right + math.sin(ro) * up, -math.sin(ro) * right + math.cos(ro) * up, fwd])
        g, rot = self.geometry(k, b)
        harm = float(a["harm_bar"][k])
        prm = np.array([self.niter, self.maxsteps, float(self.hue[k]), 0.4 + 0.25 * C, 0.25, 0.2, 0.9, 0.34,
                        0.35, float(self.crawl[k])])
        focal = self.focal0 * (1 + 0.25 * b)
        _render(self.buf, cam, Bm, focal, g, rot, prm, self.profL, self.profR, k, 1.0 / max(self.ds[k], 1e-4),
                self.kick_s, self.kick_w, s_now, self.d0)
        img = _resize(self.buf, self.W, self.H)
        # rainbow tracers: hue-rotated, zoomed, slightly turned feedback, cut on the kick
        gk = 0.92 * math.exp(-1.0 / (self.fps * (0.03 + 0.07 * harm))) * (1 - 0.35 * min(1.0, max(0.0, b)))
        fb = warp(self.prev, zoom=max(1.0, (1 + 0.3 * self.ds[k]) * focal / self.f_prev),
                  rot=0.004 * float(self.sdir[k]))
        fb = fb @ _hue_rot(0.006 + 0.018 * harm).T
        self.f_prev = focal
        out = np.maximum(img, gk * np.clip(fb, 0, None)) * max(0.35, 1 + 0.6 * b)
        self.prev = out
        top = np.argsort(self.wgt[k])[::-1][:2]
        names = {"menger": "Menger", "kristall": "Kristall", "hoehle": "Höhle", "blasen": "Blasen",
                 "koralle": "Koralle", "tempel": "Tempel"}
        self.live = {"Form": " ".join(f"{names[ORDER[i]]} {100 * self.wgt[k][i]:.0f}%" for i in top),
                     "Atem": f"{g[17]:.3f}", "Chaos": f"{C:.2f}", "Feder": f"{b:+.2f}"}
        return out

    def compose_args(self):
        return ((0.16, 0.12), 1.1)

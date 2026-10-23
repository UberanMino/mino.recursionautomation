"""3D world: the camera flies along a space curve that the music steers.

World (rule W):
  * The flight path is integrated like a vehicle: speed v and the body-frame turn rates
    (pitch, yaw, roll) are functions of the music; position and orientation follow from
    dX/dt = v T and dM/dt = M [w]x (Frenet-style frame M = [R U T]).
      - constant turn + constant roll gives a helix, so a steady, repetitive groove becomes a
        regular coil; build-ups climb, drops dive and coil; chaos adds a random walk.
  * At the point the camera reaches at time t, the spectrum of time t is built as a cross-section
    (R1 height = pitch in the local up direction, left/right channel = left/right wall): the
    camera flies through a tunnel made of the song. The future is visible ahead, and every
    slice reaches the camera's "now" distance exactly when it sounds.
  * Drum hits are ribs across the tunnel at their pitch height (kick floor, snare middle,
    hats ceiling); a dust field around the path makes the motion readable.
The 2D frame is then run through a chain of video feedback loops (FB1-FB12, see Feedback).
"""
import math
import subprocess
from dataclasses import asdict, dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.signal import lfilter

from .render import FONT, FONT_B, _resize
from .rules import Rules, element_ab, lightness, oklab_to_linear_srgb, timbre_ab, video_frame


@dataclass
class World3D:
    d0: float = 2.0             # camera distance behind "now" (world units); the now-slice fills the frame
    unit: float = 2.0           # depth per bar at speed 1 -> one bar ahead = half size
    a: float = 0.59             # cross-section half width (b = 1 is the half height)
    v0: float = 0.45            # speed = v0 + v_loud * loudness(bar) + v_tension * tension + kick thrust
    v_loud: float = 0.9
    v_tension: float = 0.8
    thrust: float = 0.55        # speed added by a full-strength kick, decays over 1/8 bar
    drop_thrust: float = 2.5
    pitch_k: float = 0.25       # rad/bar per tanh(pitch movement): brighter/higher music -> climb
    climb_k: float = 0.35       # rad/bar climb at full tension (build-ups)
    dive: float = 0.7           # rad nose-down impulse at a drop entry (decays over 1/2 bar)
    yaw_k: float = 0.35         # rad/bar per tanh(6 * stereo balance): steer to the louder side
    helix_k: float = 0.3        # rad/bar steady turn in drops/grooves (direction rotates by the golden angle per section)
    roll0: float = 0.3          # rad/bar roll, sign flips every section
    roll_timbre: float = 1.0    # extra roll per unit timbre speed
    chaos_turn: float = 0.6     # rad/bar random-walk turning at chaos 1
    lookahead_bars: float = 7.0
    fog: float = 7.0
    anticip: float = 0.35       # brightness of the future relative to the present
    # K kick bounce: every kick displaces a damped spring, x(t) = sum_i w_i e^(-zeta w t) cos(w_d t), t = t - t_i
    bounce_beats: float = 0.5   # spring period in beats (settles before the next kick)
    bounce_zeta: float = 0.3    # damping ratio: one overshoot, then calm
    bounce_wall: float = 0.3    # tunnel cross-section grows by this factor at x = 1 (walls punch out)
    bounce_zoom: float = 0.22   # focal length punch (picture jumps toward the viewer)
    bounce_cam: float = 0.15    # camera jolts down (units) and springs back
    bounce_cut: float = 0.6     # trails are cut by this share at the kick peak (visual sidechain: the hit is clean)
    bounce_expo: float = 0.35   # exposure follows the spring: brighter on the hit, darker in the overshoot
    spark_n: int = 90           # sparks per full kick (snare 0.5x, hat 0.2x), as in version 1
    spark_speed: float = 3.2    # units per second, radially out of the tunnel and back past the camera
    spark_life_bars: float = 0.25
    seed: int = 11


def _rot(w):
    """Rodrigues rotation matrix for rotation vector w."""
    th = float(np.linalg.norm(w))
    if th < 1e-12:
        return np.eye(3)
    k = w / th
    K = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    return np.eye(3) + math.sin(th) * K + (1 - math.cos(th)) * K @ K


def _impulses(times, weights, n, fps, tau_s):
    x = np.zeros(n)
    for t, w in zip(times, weights):
        k = int(video_frame(t, fps))
        if 0 <= k < n:
            x[k] += w
    a = math.exp(-1.0 / (tau_s * fps))
    return lfilter([1.0], [1.0, -a], x)


def _smooth_noise(n, sigma, rng):
    from scipy.ndimage import gaussian_filter1d
    z = gaussian_filter1d(rng.standard_normal(n), sigma)
    return z / (z.std() + 1e-9)


class Path:
    def __init__(self, S, w: World3D):
        fps, n, bar = S.fps, S.n, S.bar_s
        A = S.a
        rng = np.random.default_rng(w.seed)
        kick = S.hits["kick"]
        kn = kick[:, 2] / (np.percentile(kick[:, 2], 90) + 1e-9) if len(kick) else kick[:, 2]
        entries = [s["start"] for s in S.sections if s.get("entry")]
        imp = _impulses(kick[:, 0], w.thrust * np.clip(kn, 0, 1.2), n, fps, bar / 8)
        imp += _impulses(entries, [w.drop_thrust] * len(entries), n, fps, bar / 2)
        v = w.v0 + w.v_loud * A["loud_bar"] + w.v_tension * A["tension"] + imp       # depth-bars per bar
        self.v = v
        ds = w.unit * v / (bar * fps)                                                    # units per frame

        sec = [S.sections[i] for i in A["section"]]
        groove = np.array([s["kind"] in ("drop", "groove") for s in sec], float)
        ang = np.array([s["angle"] for s in sec])
        sdir = np.array([s["dir"] for s in sec], float)
        c = np.clip(A["chaos"], 0, 1) ** 1.1
        hel = w.helix_k * A["loud_bar"] * (1 - c) * groove
        dive = _impulses(entries, [2 * w.dive] * len(entries), n, fps, bar / 2)   # rad/bar, integrates to w.dive
        pitch = (w.pitch_k * np.tanh(0.8 * A["pitch_rate"]) + w.climb_k * A["tension"] + hel * np.sin(ang)
                 - dive + w.chaos_turn * c * _smooth_noise(n, bar / 4 * fps, rng))
        yaw = (w.yaw_k * np.tanh(6 * A["balance"]) + hel * np.cos(ang)
               + w.chaos_turn * c * _smooth_noise(n, bar / 4 * fps, rng))
        roll = sdir * (w.roll0 + w.roll_timbre * A["timbre_speed"]) * (1 - 0.5 * c)
        self.rates = np.stack([pitch, yaw, roll], 1)

        X = np.zeros((n, 3))
        M = np.zeros((n, 3, 3))
        m = np.eye(3)                       # columns: R (right), U (up), T (forward)
        x = np.zeros(3)
        for k in range(n):
            M[k], X[k] = m, x
            wb = np.array([-pitch[k], yaw[k], roll[k]]) / (bar * fps)   # body-frame rotation per frame
            m = m @ _rot(wb)
            if k % 64 == 0:
                u, _, vt = np.linalg.svd(m)
                m = u @ vt
            x = x + m[:, 2] * ds[k]
        self.X, self.M = X, M
        self.s = np.concatenate([[0], np.cumsum(ds[:-1])])
        self.ds = ds

    def at_arc(self, s):
        """Interpolated position and orthonormal frame at arc length s."""
        i = int(np.clip(np.searchsorted(self.s, s) - 1, 0, len(self.s) - 2))
        f = float(np.clip((s - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-9), 0, 1))
        X = (1 - f) * self.X[i] + f * self.X[i + 1]
        m = (1 - f) * self.M[i] + f * self.M[i + 1]
        u, _, vt = np.linalg.svd(m)
        return X, u @ vt


@dataclass
class Feedback:
    """FB loops: out = render + g * FB(prev). Every gain is a formula of the control signals."""
    zoom_k: float = 0.9          # FB1 zoom per frame = 1 + zoom_k * (path advance / d0): trails stream outwards with the flight
    hue_k: float = 1.6           # FB3 rad per bar of trail hue rotation at full timbre speed
    disp_k: float = 0.012        # FB4 R/B zoom difference at full air-band loudness (prism)
    swirl_px: float = 3.2        # FB5 self-advection along the image's own contours, * chaos^1.1
    diff_k: float = 0.5          # FB6 blur (legato) / sharpen (percussive)
    mem_min: float = 0.07        # FB7 trail memory in seconds: mem_min + mem_harm * harmonic share
    mem_harm: float = 0.3
    fold_k: float = 1.0          # FB8 kaleidoscope on the trails in calm, ordered passages
    echo_k: float = 0.22         # FB9 ghost of the frame one bar ago, if still in the same section
    flash_kick: float = 0.8      # FB10 exposure punch per (normalised) kick, 60 ms
    flash_drop: float = 2.2      #      and at a drop entry, 250 ms
    shake_px: float = 9.0        # FB11 camera shake at full sub-bass
    invert_drop: bool = True     # FB12 one negative frame on a drop entry


RIB_GAIN = {"kick": 0.9, "snare": 0.55, "hat": 0.3}


class Tunnel:
    def __init__(self, F, S, r: Rules, w: World3D, fb: Feedback, t0, dur, fps=30, W=540, H=960):
        self.F, self.S, self.r, self.w, self.fb = F, S, r, w, fb
        self.fps, self.W, self.H = fps, W, H
        self.path = Path(S, w)
        self.f = 0.43 * H * w.d0                     # focal length: the now-slice spans y_top..y_bottom
        self.k_start = int(video_frame(t0, fps))
        self.k_end = min(S.n - 1, self.k_start + int(round(dur * fps)))
        self.k_pre = max(0, self.k_start - int(1.0 * S.bar_s * fps))
        self.t0 = self.k_start / fps
        K = len(F.freqs)
        u = np.log(F.freqs / r.f_min) / np.log(r.f_max / r.f_min)
        self.h = (2 * u - 1).astype(np.float32)              # -1 = 30 Hz (floor) .. +1 = 16 kHz (ceiling)
        self.dh = 2.0 / K
        rng = np.random.default_rng(w.seed + 1)
        self.jag = gaussian_filter(rng.standard_normal((S.n, K)), (2, 5)).astype(np.float32)
        self.jag /= self.jag.std() + 1e-9
        # colours per frame (R2 + R4), both walls
        A = S.a
        ab_h = timbre_ab(A["z_h"], r)
        ab_p = timbre_ab(A["z_p"], r)
        self.ab_h, self.ab_p = ab_h.astype(np.float32), ab_p.astype(np.float32)
        ab = element_ab(A["harm"], ab_h[:, None, :], ab_p[:, None, :], r).astype(np.float32)   # (n, K, 2)
        self.rgb_l = oklab_to_linear_srgb(lightness(A["prof_l"], r), ab[..., 0], ab[..., 1]).astype(np.float32)
        self.rgb_r = oklab_to_linear_srgb(lightness(A["prof_r"], r), ab[..., 0], ab[..., 1]).astype(np.float32)
        sharp = A["sharpness"]
        self.n_exp = 2.0 ** (1.8 - 2.4 * np.clip(sharp, 0, 1))    # superellipse: soft = round, sharp = pointy (bouba/kiki)
        # drum ribs
        self.ribs = []
        for cls, f in (("kick", 45.0), ("snare", 2000.0), ("hat", 9800.0)):
            hh = S.hits[cls]
            if not len(hh):
                continue
            p90 = np.percentile(hh[:, 2], 90) + 1e-9
            hy = 2 * np.log(f / r.f_min) / np.log(r.f_max / r.f_min) - 1
            for t, _, p in hh:
                self.ribs.append((int(video_frame(t, fps)), hy, min(1.0, p / p90), cls))
        self.rib_k = np.array([x[0] for x in self.ribs]) if self.ribs else np.zeros(0, int)
        # dust: fixed points around the path
        ks = np.arange(0, S.n, 2)
        nd = 4
        kk = np.repeat(ks, nd)
        rho = rng.uniform(1.8, 5.0, len(kk))
        th = rng.uniform(0, 2 * np.pi, len(kk))
        Mx = self.path.M[kk]
        self.dust_k = kk
        self.dust = (self.path.X[kk] + (rho * np.cos(th))[:, None] * Mx[:, :, 0] + (rho * np.sin(th))[:, None] * Mx[:, :, 1]
                     + rng.uniform(0, 1, len(kk))[:, None] * Mx[:, :, 2] * self.path.ds[kk, None] * 2)
        self.dust_tw = rng.uniform(0.3, 1.0, len(kk))
        # feedback state
        self.prev = np.zeros((H, W, 3), np.float32)
        self.echo = {}
        self.yy, self.xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.rng = np.random.default_rng(w.seed + 2)
        self.cam_prev = None
        self.shake = np.zeros(2)
        self.entry_frames = {int(video_frame(s["start"], fps)) for s in S.sections if s.get("entry")}
        self.state = {}
        self.world_gain = 0.45
        # K kick bounce: damped spring driven by the kicks (peak in the kick's own frame, R3)
        beat = S.bar_s / 4
        om = 2 * np.pi / (w.bounce_beats * beat)
        wd = om * math.sqrt(1 - w.bounce_zeta ** 2)
        kick = S.hits["kick"]
        self.bounce = np.zeros(S.n)
        if len(kick):
            kw = np.clip(kick[:, 2] / (np.percentile(kick[:, 2], 90) + 1e-9), 0, 1.2)
            tt = np.arange(int(3 * w.bounce_beats * beat * fps) + 1) / fps
            resp = np.exp(-w.bounce_zeta * om * tt) * np.cos(wd * tt)
            for tk, wk in zip(kick[:, 0], kw):
                k0 = int(video_frame(tk, fps))
                k1 = min(S.n, k0 + len(resp))
                if k0 >= 0:
                    self.bounce[k0:k1] += wk * resp[:k1 - k0]
        self.f0 = self.f
        self.sparks = np.zeros((0, 12), np.float32)     # pos 3, vel 3, age, life, rgb 3, unused
        self.hit_frames = {}
        for cls in ("kick", "snare", "hat"):
            hh = S.hits[cls]
            if not len(hh):
                continue
            p90 = np.percentile(hh[:, 2], 90) + 1e-9
            for t, _, pw in hh:
                self.hit_frames.setdefault(int(video_frame(t, fps)), []).append((cls, min(1.2, pw / p90)))

    # ---------------------------------------------------------------- camera + projection
    def camera(self, k):
        p = self.path
        s_now = p.s[k]
        C, Mc = p.at_arc(s_now - self.w.d0)
        if s_now < self.w.d0:                         # start of the song: back off along the first tangent
            C = p.X[0] - p.M[0][:, 2] * (self.w.d0 - s_now)
            Mc = p.M[0]
        fwd = p.X[k] - C
        fwd /= np.linalg.norm(fwd) + 1e-12
        up = Mc[:, 1] - fwd * (Mc[:, 1] @ fwd)
        up /= np.linalg.norm(up) + 1e-12
        right = np.cross(up, fwd)
        C = C - self.w.bounce_cam * self.bounce[k] * up        # K: camera jolts down on the kick, springs back
        return C, np.stack([right, up, fwd])          # rows

    def project(self, P, C, B):
        q = (P - C) @ B.T
        z = q[..., 2]
        ok = z > 0.12
        zs = np.where(ok, z, 1.0)
        x = self.W / 2 + self.f * q[..., 0] / zs
        y = self.H / 2 - self.f * q[..., 1] / zs
        return x, y, z, ok

    # ---------------------------------------------------------------- splatting (4 levels)
    def _splat(self, bufs, x, y, val, area):
        lvl = np.clip(np.floor(np.log(np.maximum(area, 1e-6)) / np.log(4.0)), 0, 3).astype(int)
        for l in range(4):
            m = lvl == l
            if not m.any():
                continue
            sc = 2 ** l
            Hl, Wl = bufs[l].shape[1:]
            xl, yl = x[m] / sc - 0.5, y[m] / sc - 0.5
            v = val[m] * (area[m] / (4 ** l))[:, None]
            x0, y0 = np.floor(xl).astype(int), np.floor(yl).astype(int)
            fx, fy = (xl - x0)[:, None], (yl - y0)[:, None]
            for dx, dy, wgt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                xs, ys = x0 + dx, y0 + dy
                ok = (xs >= 0) & (xs < Wl) & (ys >= 0) & (ys < Hl)
                idx = ys[ok] * Wl + xs[ok]
                vv = v[ok] * wgt[ok]
                for ch in range(3):
                    bufs[l][ch] += np.bincount(idx, vv[:, ch], minlength=Hl * Wl).reshape(Hl, Wl)

    # ---------------------------------------------------------------- one frame
    def render_world(self, k):
        S, w, p, F = self.S, self.w, self.path, self.F
        H, W, f = self.H, self.W, self.f
        C, B = self.camera(k)
        s_c = p.s[k] - w.d0
        bar_f = S.bar_s * self.fps
        j1 = min(S.n - 1, k + int(w.lookahead_bars * bar_f))
        j0 = max(0, k - int(bar_f / 4))
        js = np.arange(j0, j1)
        js = js[(p.s[js] > s_c + 0.15) & (p.s[js] - s_c < w.fog * 2.2)]
        bufs = [np.zeros((3, H // 2 ** l, W // 2 ** l), np.float32) for l in range(4)]
        tau = (js - k) / self.fps
        A = np.where(tau >= 0, w.anticip + (1 - w.anticip) * np.exp(-tau / (S.bar_s / 4)),
                     np.exp(tau / (S.bar_s / 16)))
        A = A * np.where(np.abs(js - k) <= 1, 1.5, 1.0)
        chaos = np.clip(S.a["chaos"][js], 0, 1) ** 1.1
        n_e = self.n_exp[js][:, None]
        hh = self.h[None, :]
        xr = np.power(np.clip(1 - np.abs(hh) ** n_e, 0, 1), 1 / n_e)
        jag = (1 + 0.35 * chaos[:, None] * self.jag[js]) * (1 + w.bounce_wall * self.bounce[k])   # K: walls punch out
        X = p.X[js][:, None, :]
        R = p.M[js][:, None, :, 0]
        U = p.M[js][:, None, :, 1]
        dsj = np.maximum(p.ds[js], 1e-4)
        for side, rgb in ((-1, self.rgb_l), (1, self.rgb_r)):
            P = X + (side * w.a * xr * jag)[..., None] * R + (hh * jag)[..., None] * U
            x, y, z, ok = self.project(P, C, B)
            fog = np.exp(-np.maximum(z - w.d0, 0) / w.fog)
            val = rgb[js] * (A[:, None] * fog)[..., None]
            area = (dsj[:, None] * f / np.maximum(z, 0.1)) * (self.dh * f / np.maximum(z, 0.1))
            on = ok & (val.max(-1) > 1e-4) & (x > -4) & (x < W + 4) & (y > -4) & (y < H + 4)
            self._splat(bufs, x[on], y[on], val[on], np.minimum(area[on], 400.0))
        # ribs
        if len(self.rib_k):
            sel = np.nonzero((self.rib_k >= j0) & (self.rib_k < j1))[0]
            if len(sel):
                xs = np.linspace(-1, 1, 41)[None, :]
                pts, vals, areas = [], [], []
                for i in sel:
                    kj, hy, pw, cls = self.ribs[i]
                    if p.s[kj] <= s_c + 0.15:
                        continue
                    tj = (kj - k) / self.fps
                    Aj = (w.anticip + (1 - w.anticip) * math.exp(-tj / (S.bar_s / 4))) if tj >= 0 else math.exp(tj / (S.bar_s / 16))
                    ne = self.n_exp[kj]
                    half = (max(0.0, 1 - abs(hy) ** ne)) ** (1 / ne)
                    sc = 1 + w.bounce_wall * self.bounce[k]
                    P = p.X[kj] + (xs.T * w.a * half * sc) * p.M[kj][:, 0] + hy * sc * p.M[kj][:, 1]
                    ab = element_ab(0.35, self.ab_h[kj], self.ab_p[kj], self.r)
                    col = oklab_to_linear_srgb(np.array([lightness(pw, self.r)]), ab[..., 0:1], ab[..., 1:2])[0]
                    pts.append(P)
                    vals.append(np.repeat((col * Aj * RIB_GAIN[cls])[None, :], len(P), 0))
                    areas.append(0.07)
                if pts:
                    P = np.concatenate(pts)
                    V = np.concatenate(vals)
                    x, y, z, ok = self.project(P, C, B)
                    fog = np.exp(-np.maximum(z - w.d0, 0) / w.fog)
                    a2 = (0.015 * f / np.maximum(z, 0.1)) * (0.05 * f / np.maximum(z, 0.1))
                    on = ok & (x > -4) & (x < W + 4) & (y > -4) & (y < H + 4)
                    self._splat(bufs, x[on], y[on], V[on] * fog[on, None], np.minimum(a2[on], 300.0))
        # sparks (as in version 1): bursts from every drum hit, flying out of the tunnel wall
        self._sparks(k, bufs, C, B)
        # dust: brightness follows the air band (hats, shimmer)
        dm = (self.dust_k >= j0) & (self.dust_k < j1)
        if dm.any():
            x, y, z, ok = self.project(self.dust[dm], C, B)
            air = float(S.a["psi_air"][k])
            ab = 0.3 * self.ab_h[k]
            col = oklab_to_linear_srgb(np.array([0.85]), ab[None, 0:1][0], ab[None, 1:2][0])[0]
            b = (0.03 + 0.5 * air) * self.dust_tw[dm] * np.exp(-np.maximum(z - w.d0, 0) / w.fog)
            on = ok & (x > 0) & (x < W - 1) & (y > 0) & (y < H - 1)
            self._splat(bufs, x[on], y[on], b[on, None] * col[None, :], np.full(on.sum(), 1.0))
        img = bufs[0].transpose(1, 2, 0).copy()
        for l in range(1, 4):
            img += _resize(gaussian_filter(bufs[l], (0, 0.6, 0.6)).transpose(1, 2, 0), W, H)
        return img, C, B

    def _sparks(self, k, bufs, C, B):
        w, p, fps = self.w, self.path, self.fps
        c = float(np.clip(self.S.a["chaos"][k], 0, 1))
        new = []
        for cls, pw in self.hit_frames.get(k, ()):
            n = int(round(w.spark_n * {"kick": 1.0, "snare": 0.5, "hat": 0.2}[cls] * pw))
            if n == 0:
                continue
            hy = {"kick": -0.9, "snare": 0.0, "hat": 0.85}[cls]
            ne = self.n_exp[k]
            half = (max(0.0, 1 - abs(hy) ** ne)) ** (1 / ne)
            xq = self.rng.uniform(-1, 1, n) * half
            if cls == "snare":                               # snare: from the side walls
                xq = np.sign(xq + 1e-9) * half
                hy_v = self.rng.uniform(-0.5, 0.5, n)
            else:
                hy_v = np.full(n, hy)
            R, U, T = p.M[k][:, 0], p.M[k][:, 1], p.M[k][:, 2]
            pos = p.X[k] + np.outer(xq * w.a, R) + np.outer(hy_v, U)
            rad = np.outer(xq, R) + np.outer(hy_v, U)
            rad /= np.linalg.norm(rad, axis=1, keepdims=True) + 1e-9
            rad += (0.15 + 1.2 * c) * self.rng.standard_normal((n, 3))          # chaos spreads the burst
            sp = w.spark_speed * (0.35 + pw) * self.rng.uniform(0.4, 1.0, (n, 1))
            vel = sp * (0.75 * rad - 0.65 * T) / fps
            ab = element_ab(0.0, self.ab_h[k], self.ab_p[k], self.r)
            col = oklab_to_linear_srgb(np.array([lightness(pw, self.r)]), ab[..., 0:1], ab[..., 1:2])[0] * 1.6
            life = w.spark_life_bars * self.S.bar_s * fps * self.rng.uniform(0.6, 1.4, n)
            new.append(np.c_[pos, vel, np.zeros(n), life, np.repeat(col[None], n, 0), np.zeros(n)])
        if new:
            self.sparks = np.vstack([self.sparks] + [x.astype(np.float32) for x in new])
        S_ = self.sparks
        if not len(S_):
            return
        alpha = np.clip(1 - S_[:, 6] / S_[:, 7], 0, 1) ** 1.5
        for sub in (0.0, 0.33, 0.66):                        # motion blur
            x, y, z, ok = self.project(S_[:, 0:3] + sub * S_[:, 3:6], C, B)
            on = ok & (x > 0) & (x < self.W - 1) & (y > 0) & (y < self.H - 1)
            val = S_[on, 8:11] * (alpha[on] / 3)[:, None]
            self._splat(bufs, x[on], y[on], val, np.full(on.sum(), 1.5))
        S_[:, 0:3] += S_[:, 3:6]
        S_[:, 3:6] *= 0.9
        S_[:, 6] += 1
        self.sparks = S_[S_[:, 6] < S_[:, 7]]

    # ---------------------------------------------------------------- feedback chain
    def feedback(self, k, C, B):
        S, fb, H, W = self.S, self.fb, self.H, self.W
        A = S.a
        prev = self.prev
        bar_f = S.bar_s * self.fps
        c = float(np.clip(A["chaos"][k], 0, 1)) ** 1.1
        hb = float(np.clip((A["harm_bar"][k] - np.percentile(A["harm_bar"], 5))
                           / (np.ptp(np.percentile(A["harm_bar"], [5, 95])) + 1e-9), 0, 1))
        sec = S.sections[A["section"][k]]
        # FB1 zoom about the projected "now" point, FB2 roll with the camera
        x0, y0, _, _ = self.project(self.path.X[k][None, :], C, B)
        cx, cy = float(np.clip(x0[0], W * 0.2, W * 0.8)), float(np.clip(y0[0], H * 0.2, H * 0.8))
        zoom = 1 + fb.zoom_k * self.path.ds[k] / self.w.d0
        zoom *= self.f / getattr(self, "f_prev", self.f)          # trails follow the kick zoom punch
        self.f_prev = self.f
        roll = 0.0
        if self.cam_prev is not None:
            up0 = self.cam_prev[1]
            u_in = np.array([up0 @ B[0], up0 @ B[1]])
            roll = math.atan2(u_in[0], u_in[1])
        self.cam_prev = B
        disp = fb.disp_k * float(A["psi_air"][k])                                            # FB4
        # FB5 self-advection: move along the contours of the blurred trail luminance
        vx = vy = 0.0
        if c > 0.02:
            lum = gaussian_filter(prev[::4, ::4].mean(2), 2.0)
            gy, gx = np.gradient(lum)
            nrm = np.sqrt((gx ** 2 + gy ** 2).mean()) + 1e-9
            vx = _resize((gy / nrm).astype(np.float32), W, H)
            vy = _resize((-gx / nrm).astype(np.float32), W, H)
        sw = fb.swirl_px * c * H / 960
        # FB8 kaleidoscope weight: calm (low loudness), ordered (low chaos) passages
        beta = float(np.clip(fb.fold_k * (1 - c) * (1 - A["loud_bar"][k]) * 1.6 - 0.3, 0, 1))
        nfold = (4, 6, 8, 3)[sec["index"] % 4]
        dxp, dyp = self.xx - cx, self.yy - cy
        cr, sr = math.cos(-roll), math.sin(-roll)
        out = np.empty_like(prev)
        for ch, ez in enumerate((1 + disp, 1.0, 1 - disp)):
            z = zoom * ez
            qx = (cr * dxp - sr * dyp) / z
            qy = (sr * dxp + cr * dyp) / z
            srcx = cx + qx - sw * vx
            srcy = cy + qy - sw * vy
            res = map_coordinates(prev[..., ch], [srcy, srcx], order=1, mode="constant", prefilter=False)
            if beta > 0.02:
                rr = np.hypot(qx, qy)
                th = np.arctan2(qy, qx)
                seg = 2 * np.pi / nfold
                tf = np.abs(np.mod(th, seg) - seg / 2)
                fx_, fy_ = cx + rr * np.cos(tf), cy + rr * np.sin(tf)
                res2 = map_coordinates(prev[..., ch], [fy_, fx_], order=1, mode="constant", prefilter=False)
                res = (1 - beta) * res + beta * res2
            out[..., ch] = res
        # FB3 hue rotation about the grey axis
        dh = fb.hue_k * float(A["timbre_speed"][k]) / bar_f * float(sec["dir"])
        if abs(dh) > 1e-4:
            cth, sth = math.cos(dh), math.sin(dh)
            kx = np.ones(3) / math.sqrt(3)
            Kx = np.array([[0, -kx[2], kx[1]], [kx[2], 0, -kx[0]], [-kx[1], kx[0], 0]])
            Rm = (np.eye(3) * cth + sth * Kx + (1 - cth) * np.outer(kx, kx)).astype(np.float32)
            out = np.clip(out @ Rm.T, 0, None)
        # FB6 diffusion: legato blurs, percussive sharpens
        kap = float(np.clip(fb.diff_k * (2 * hb - 1), -0.45, 0.25))
        if abs(kap) > 0.02:
            out = np.clip(out + kap * (gaussian_filter(out, (1.2, 1.2, 0)) - out), 0, None)
        # FB7 memory
        mem = fb.mem_min + fb.mem_harm * hb
        g = math.exp(-1.0 / (self.fps * mem)) * (1 - self.w.bounce_cut * min(1.0, max(0.0, float(self.bounce[k]))))
        self.state.update(chaos=c ** (1 / 1.1), zoom=zoom, roll=roll, fold=beta, nfold=nfold, mem=mem, kappa=kap,
                          kind=sec["kind"], speed=float(self.path.v[k]), tension=float(A["tension"][k]),
                          rates=self.path.rates[k], bounce=float(self.bounce[k]))
        return g * out

    def step(self, k):
        S, fb = self.S, self.fb
        self.f = self.f0 * (1 + self.w.bounce_zoom * self.bounce[k])          # K: zoom punch on the kick
        img, C, B = self.render_world(k)
        lin = np.maximum(self.world_gain * img, self.feedback(k, C, B))   # "lighten": trails never pile up
        lin = np.minimum(lin, 6.0)
        self.prev = lin
        # FB9 bar echo
        bar_f = int(round(S.bar_s * self.fps))
        out = lin
        old = self.echo.get(k - bar_f)
        sec_now = S.a["section"][k]
        if old is not None and S.a["section"][max(0, k - bar_f)] == sec_now:
            out = out + fb.echo_k * (1 - self.state["chaos"]) * old.astype(np.float32)
        self.echo[k] = lin.astype(np.float16)
        self.echo.pop(k - bar_f - 1, None)
        # FB10 exposure punches
        t = k / self.fps
        E = 1.0
        kick = S.hits["kick"]
        if len(kick):
            near = kick[(kick[:, 0] <= t + 1 / self.fps) & (kick[:, 0] > t - 0.3)]
            p90 = np.percentile(kick[:, 2], 90) + 1e-9
            for tk, _, pk in near:
                E += fb.flash_kick * min(1.2, pk / p90) * math.exp(-max(0.0, t - tk) / 0.06)
        for s in S.sections:
            if s.get("entry") and 0 <= t - s["start"] < 1.0:
                E += fb.flash_drop * math.exp(-(t - s["start"]) / 0.25)
        E *= max(0.3, 1 + self.w.bounce_expo * float(self.bounce[k]))                       # K
        # FB11 shake from sub-bass
        sub = float(S.a["psi_sub"][k])
        self.shake = 0.5 * self.shake + 0.5 * self.rng.standard_normal(2)
        sh = (fb.shake_px * self.H / 960 * sub ** 2 * self.shake).round().astype(int)
        out = np.roll(out, (int(sh[1]), int(sh[0])), axis=(0, 1)) if sh.any() else out
        frame = self._compose(out * E)
        if fb.invert_drop and k in self.entry_frames:                                       # FB12
            frame = 255 - frame
        self.state.update(exposure=E)
        return frame

    def _compose(self, img):
        H, W = self.H, self.W
        small = gaussian_filter(img[::2, ::2], (3, 3, 0))
        big = gaussian_filter(img[::8, ::8], (3, 3, 0))
        out = img + 0.18 * _resize(small, W, H) + 0.15 * _resize(big, W, H)
        out = 1 - np.exp(-1.4 * out)
        srgb = np.where(out <= 0.0031308, 12.92 * out, 1.055 * np.power(np.maximum(out, 0), 1 / 2.4) - 0.055)
        return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)


# ---------------------------------------------------------------- explainer overlay

class Overlay3D:
    KIND = {"drop": "DROP", "build": "BUILD-UP", "break": "BREAK", "groove": "GROOVE"}

    def __init__(self, W, H, bpm):
        self.W, self.H, self.bpm = W, H, bpm
        self.f_s = ImageFont.truetype(FONT, int(H * 0.0115))
        self.f_m = ImageFont.truetype(FONT, int(H * 0.0135))
        self.f_b = ImageFont.truetype(FONT_B, int(H * 0.016))

    def draw(self, frame, T: Tunnel, k):
        W, H = self.W, self.H
        st = T.state
        img = Image.fromarray(frame).convert("RGBA")
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        d.text((14, H * 0.012), "Vorwärts = Zeit · Querschnitt = Spektrum (oben = hoch)",
               font=self.f_m, fill=(255, 255, 255, 170))
        d.text((14, H * 0.012 + H * 0.019), "Rippen = Drums · Kurs = Musik (Steigen, Kurven, Rollen)",
               font=self.f_m, fill=(255, 255, 255, 170))
        y = H * 0.905
        d.text((14, y), self.KIND.get(st["kind"], st["kind"]), font=self.f_b, fill=(255, 255, 255, 230))
        rows = [("Chaos", st["chaos"], 1.0), ("Spannung", st["tension"], 1.0), ("Tempo", st["speed"], 3.0)]
        for i, (lab, v, mx) in enumerate(rows):
            yy = y + H * 0.024 + i * H * 0.019
            d.text((14, yy), lab, font=self.f_s, fill=(255, 255, 255, 200))
            bx, bw, bh = int(W * 0.16), int(W * 0.22), int(H * 0.009)
            d.rectangle([bx, yy + 5, bx + bw, yy + 5 + bh], outline=(255, 255, 255, 120))
            d.rectangle([bx, yy + 5, bx + int(bw * min(1, v / mx)), yy + 5 + bh], fill=(255, 255, 255, 200))
        p, yw, rl = st["rates"]
        txt = f"Steigen {p:+.1f}  Kurve {yw:+.1f}  Rollen {rl:+.1f} rad/Takt"
        d.text((int(W * 0.43), y + H * 0.024), txt, font=self.f_s, fill=(255, 255, 255, 190))
        txt = f"Gedächtnis {st['mem']:.2f}s  Unschärfe {st['kappa']:+.2f}  Kaleido {st['fold']:.2f}×{st['nfold']}"
        d.text((int(W * 0.43), y + H * 0.043), txt, font=self.f_s, fill=(255, 255, 255, 160))
        d.text((int(W * 0.43), y + H * 0.062), f"{self.bpm:.0f} BPM   {k / T.fps:5.1f} s", font=self.f_s,
               fill=(255, 255, 255, 150))
        # minimap: the path seen from above (camera right / forward plane), +-6 bars
        m0, ms = (int(W * 0.74), int(H * 0.07)), int(W * 0.23)
        d.rectangle([m0[0], m0[1], m0[0] + ms, m0[1] + ms], outline=(255, 255, 255, 80), fill=(0, 0, 0, 90))
        C, Bm = T.camera(k)
        bar_f = int(T.S.bar_s * T.fps)
        ks = np.arange(max(0, k - 6 * bar_f), min(T.S.n, k + 6 * bar_f), 3)
        q = (T.path.X[ks] - T.path.X[k]) @ Bm.T
        sc = ms / 2 / (np.abs(q[:, [0, 2]]).max() + 1e-6)
        for j in range(len(ks) - 1):
            a1 = (m0[0] + ms / 2 + q[j, 0] * sc, m0[1] + ms / 2 - q[j, 2] * sc)
            a2 = (m0[0] + ms / 2 + q[j + 1, 0] * sc, m0[1] + ms / 2 - q[j + 1, 2] * sc)
            fut = ks[j] >= k
            alt = float(np.clip(q[j, 1] * sc / (ms / 2), -1, 1))
            col = (int(150 + 100 * max(alt, 0)), 200, int(150 + 100 * max(-alt, 0)), 230) if fut else (150, 150, 150, 120)
            d.line([a1, a2], fill=col, width=2)
        d.ellipse([m0[0] + ms / 2 - 4, m0[1] + ms / 2 - 4, m0[0] + ms / 2 + 4, m0[1] + ms / 2 + 4], fill=(255, 255, 255, 255))
        d.text((m0[0] + 4, m0[1] + ms + 2), "Kurs von oben (±6 Takte)", font=self.f_s, fill=(255, 255, 255, 140))
        img.alpha_composite(lay)
        return np.asarray(img.convert("RGB"))


def render(F, S, r: Rules, song, t0, dur, out, fps=30, scale=0.5, overlay=False, stills=None,
           world: World3D = None, fb: Feedback = None, log=print):
    W, H = int(1080 * scale) // 2 * 2, int(1920 * scale) // 2 * 2
    T = Tunnel(F, S, r, world or World3D(), fb or Feedback(), t0, dur, fps, W, H)
    ow, oh = 1080, 1920
    ov = Overlay3D(ow, oh, F.bpm) if overlay else None
    size = f"{ow}x{oh}" if overlay else f"{W}x{H}"
    vf = "format=yuv420p" if overlay else f"scale={ow}:{oh}:flags=lanczos,format=yuv420p"
    n = T.k_end - T.k_start
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(fps),
           "-i", "-", "-ss", f"{T.t0:.6f}", "-t", f"{n / fps:.6f}", "-i", song,
           "-filter_complex", f"[0:v]{vf}[v];[1:a]afade=t=in:st=0:d=0.03,afade=t=out:st={n / fps - 0.4:.3f}:d=0.4[a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(fps),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    kept = []
    for k in range(T.k_pre, T.k_end):
        frame = T.step(k)
        if k < T.k_start:
            continue
        if ov is not None:
            frame = ov.draw(np.asarray(Image.fromarray(frame).resize((ow, oh), Image.BICUBIC)), T, k)
        proc.stdin.write(frame.tobytes())
        if stills is not None and (k - T.k_start) in stills:
            kept.append(frame.copy())
        if (k - T.k_start) % 90 == 0:
            log(f"  frame {k - T.k_start}/{n}  {T.state['kind']}  chaos {T.state['chaos']:.2f}  v {T.state['speed']:.2f}")
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    return kept


def params_dict(w: World3D, fb: Feedback):
    return {"world": asdict(w), "feedback": asdict(fb)}

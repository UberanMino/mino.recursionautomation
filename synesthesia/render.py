"""Reference renderer for the mapping rules: the "spectral butterfly".

The centre line of the frame is "now". Every frame, the current sound is painted onto the
centre line as a vertical spectrum (R1 height, R2 brightness, R4 colour, R5 left/right) and
the picture flows outwards, so each half shows the last half bar to one bar of music (R7).
Percussive onsets throw sparks (R8). Musical chaos turns the laminar outflow turbulent, breaks
the mirror symmetry and finally tears the image (R6).
"""
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter, map_coordinates

from .features import BPO, FPS_A
from .rules import (Rules, chaos_visual, element_ab, envelope, freq_of_y, lightness, oklab_to_linear_srgb, psi,
                    timbre_ab, video_frame, y_of_freq)

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_B = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _resize(a, W, H, method=Image.BILINEAR):
    """Fast float resize (PIL, per channel)."""
    if a.ndim == 2:
        return np.asarray(Image.fromarray(np.ascontiguousarray(a, np.float32), "F").resize((W, H), method))
    return np.stack([_resize(a[..., c], W, H, method) for c in range(a.shape[2])], axis=-1)


def _smoothstep(x):
    return x * x * (3 - 2 * x)


class Flow:
    """Divergence-free (curl) noise at two scales, evolving smoothly from beat to beat."""

    def __init__(self, H, W, beat_frames, seed):
        self.H, self.W, self.bf, self.seed = H, W, beat_frames, seed
        self.shapes = {"coarse": (9, 6), "fine": (26, 15)}
        self.cache = {}

    def _key(self, name, j):
        if (name, j) not in self.cache:
            rng = np.random.default_rng((self.seed, j, 0 if name == "coarse" else 1))
            self.cache[(name, j)] = rng.standard_normal(self.shapes[name])
        return self.cache[(name, j)]

    def _vel(self, name, k):
        u = k / self.bf
        j = math.floor(u)
        f = _smoothstep(u - j)
        phi = (1 - f) * self._key(name, j) + f * self._key(name, j + 1)
        gy, gx = np.gradient(phi)
        vx, vy = gy, -gx
        s = np.sqrt((vx ** 2 + vy ** 2).mean()) + 1e-9
        return _resize(vx / s, self.W, self.H, Image.BICUBIC), _resize(vy / s, self.W, self.H, Image.BICUBIC)

    def velocity(self, k, fine):
        cx, cy = self._vel("coarse", k)
        if fine <= 0.01:
            return cx, cy
        fx, fy = self._vel("fine", k)
        return (1 - fine) * cx + fine * fx, (1 - fine) * cy + fine * fy


class Renderer:
    def __init__(self, F, r: Rules, t0, dur, fps=30, W=540, H=960, seed=7, preroll_bars=1.2):
        self.F, self.r, self.fps, self.W, self.H = F, r, fps, W, H
        self.cx = W // 2
        self.rng = np.random.default_rng(seed)
        bar_s = 240.0 / F.bpm
        self.speed = r.bar_width * W / (bar_s * fps)                 # px per frame (R7)
        self.decay = r.trail_end ** (self.speed / (W / 2))           # per frame, edge -> trail_end
        self.k_start = int(video_frame(t0, fps))
        self.k_end = self.k_start + int(round(dur * fps))
        self.k_pre = max(0, self.k_start - int(preroll_bars * bar_s * fps))
        self.t0 = self.k_start / fps                                  # audio starts exactly on a frame

        T = F.db_l.shape[0]
        self.a0 = max(0, int(self.k_pre / fps * FPS_A) - 60)
        self.a1 = min(T, int(math.ceil((self.k_end + 1) / fps * FPS_A)) + 2)
        sl = slice(self.a0, self.a1)
        self.psi_l = envelope(psi(F.db_l[sl], F.ref_db, r).astype(np.float32), FPS_A, r)
        self.psi_r = envelope(psi(F.db_r[sl], F.ref_db, r).astype(np.float32), FPS_A, r)
        self.harm = F.harm[sl]
        self.width = F.width[sl]
        self.ab_h = timbre_ab(F.timbre_h[sl], r)
        self.ab_p = timbre_ab(F.timbre_p[sl], r)
        self.chaos = F.chaos[sl]

        # pixel row -> position on the analysis' log-frequency grid (R1)
        fr = freq_of_y(np.arange(H) + 0.5, H, r)
        self.row_ok = ((fr >= max(r.f_min, F.freqs[0])) & (fr <= min(r.f_max, F.freqs[-1]))).astype(np.float32)
        g = np.clip(np.log2(fr / F.freqs[0]) * BPO, 0, len(F.freqs) - 1.001)
        self.gi = np.floor(g).astype(int)
        self.gf = (g - self.gi).astype(np.float32)

        self.trail = np.zeros((H, W, 3), np.float32)
        self.flow = Flow(H, W, 60.0 / F.bpm * fps, seed)
        self.yy, self.xx = np.mgrid[0:H, 0:W].astype(np.float32)
        self.sparks = np.zeros((0, 10), np.float32)  # x y vx vy age life r g b _
        self.shift_acc = 0.0
        self.onsets = F.onsets
        self.state = {}
        self.chaos_override = None

    # -- per-frame parameters -------------------------------------------------------------
    def _span(self, k):
        i0 = int(math.ceil(k / self.fps * FPS_A)) - self.a0
        i1 = int(math.ceil((k + 1) / self.fps * FPS_A)) - self.a0
        i0 = min(max(i0, 0), len(self.chaos) - 1)
        return i0, max(i0 + 1, min(i1, len(self.chaos)))

    def _rows(self, v):
        return ((1 - self.gf) * v[self.gi] + self.gf * v[self.gi + 1]) * self.row_ok

    def params(self, k):
        i0, i1 = self._span(k)
        pl = self.psi_l[i0:i1].max(0)
        pr = self.psi_r[i0:i1].max(0)
        h = self.harm[i0:i1].mean(0)
        w = self.width[i0:i1].mean(0)
        abh = self.ab_h[i0:i1].mean(0)
        abp = self.ab_p[i0:i1].mean(0)
        c = float(self.chaos[i0:i1].mean()) if self.chaos_override is None else self.chaos_override
        return dict(psi_l=self._rows(pl), psi_r=self._rows(pr), harm=np.clip(self._rows(h), 0, 1),
                    width=np.clip(self._rows(w), 0, 1), ab_h=abh, ab_p=abp, chaos=c)

    def _colors(self, p, side):
        ab = element_ab(p["harm"], p["ab_h"], p["ab_p"], self.r)                  # (H, 2)
        L = lightness(p["psi_" + side], self.r)
        return oklab_to_linear_srgb(L, ab[:, 0] * (L > 0), ab[:, 1] * (L > 0)).astype(np.float32)

    # -- simulation step -------------------------------------------------------------------
    def step(self, k):
        r, H, W, cx = self.r, self.H, self.W, self.cx
        p = self.params(k)
        cv = chaos_visual(p["chaos"], r, H)
        T = self.trail

        # R7 outflow: integer shift (no numerical blur), sub-pixel remainder carried over
        self.shift_acc += self.speed
        s = int(self.shift_acc)
        self.shift_acc -= s
        if s:
            T[:, :cx - s] = T[:, s:cx]
            T[:, cx - s:cx] = 0
            T[:, cx + s:] = T[:, cx:W - s]
            T[:, cx:cx + s] = 0

        # R6 turbulence (and with it: broken symmetry, because the field is not mirror-symmetric)
        vx = vy = None
        if cv["turb_px"] > 0.05:
            vx, vy = self.flow.velocity(k, cv["fine"])
            d = cv["turb_px"]
            coords = [self.yy - d * vy, self.xx - d * vx]
            for ch in range(3):
                T[..., ch] = map_coordinates(T[..., ch], coords, order=1, mode="constant", prefilter=False)
        # R6 tearing
        if self.rng.random() < cv["glitch_prob"]:
            for _ in range(self.rng.integers(1, 4)):
                y0 = int(self.rng.integers(0, H - 8))
                hh = int(self.rng.integers(4, 40) * H / 960)
                T[y0:y0 + hh] = np.roll(T[y0:y0 + hh], int(self.rng.normal(0, cv["glitch_px"])), axis=1)

        T *= self.decay

        # R1/R2/R4/R5 inject "now" at the centre line: left channel left, right channel right,
        # wide (decorrelated) sound born away from the centre
        if s:
            gap = np.round(p["width"] * r.birth_gap * W).astype(int)
            gmax = int(r.birth_gap * W) + s + 1
            dcol = np.arange(gmax)[None, :]
            m = ((dcol >= gap[:, None]) & (dcol < gap[:, None] + s)).astype(np.float32)[..., None]
            cl, cr = self._colors(p, "l"), self._colors(p, "r")
            T[:, cx - 1 - np.arange(gmax)] += m * cl[:, None, :]
            T[:, cx + np.arange(gmax)] += m * cr[:, None, :]

        # R8 sparks from percussive onsets in this frame's time span
        t_a, t_b = k / self.fps, (k + 1) / self.fps
        sel = self.onsets[(self.onsets[:, 0] >= t_a) & (self.onsets[:, 0] < t_b)]
        new = []
        for t, g, f, lvl in sel:
            po = float(psi(lvl, self.F.ref_db, r))
            n = int(round(r.spark_max * po))
            if n == 0:
                continue
            y = float(y_of_freq(f, H, r))
            L = lightness(po, r)
            ab = element_ab(0.0, p["ab_h"], p["ab_p"], r)
            rgb = oklab_to_linear_srgb(np.array([L]), ab[..., 0], ab[..., 1])[0] * 1.6
            life = r.spark_life_bars * 240.0 / self.F.bpm * self.fps
            sp = r.spark_speed * H / 960 * (0.35 + po)
            for _ in range(n):
                spd = sp * self.rng.uniform(0.4, 1.0)
                ang = self.rng.normal(0, 0.10 + cv["spark_spread"])
                yy = y + self.rng.normal(0, 4 * H / 960)
                lf = life * self.rng.uniform(0.6, 1.4)
                if self.rng.random() < cv["pair_prob"]:
                    new.append((cx + 1, yy, spd * math.cos(ang), spd * math.sin(ang), 0, lf, *rgb, 0))
                    new.append((cx - 2, yy, -spd * math.cos(ang), spd * math.sin(ang), 0, lf, *rgb, 0))
                else:
                    a2 = ang + (math.pi if self.rng.random() < 0.5 else 0)
                    new.append((cx, yy, spd * math.cos(a2), spd * math.sin(a2), 0, lf, *rgb, 0))
        if new:
            self.sparks = np.vstack([self.sparks, np.array(new, np.float32)])
        P = np.zeros_like(T)
        sp = self.sparks
        if len(sp):
            if vx is not None:
                xi = np.clip(sp[:, 0].astype(int), 0, W - 1)
                yi = np.clip(sp[:, 1].astype(int), 0, H - 1)
                sp[:, 2] += 0.35 * cv["turb_px"] * vx[yi, xi]
                sp[:, 3] += 0.35 * cv["turb_px"] * vy[yi, xi]
            alpha = np.clip(1 - sp[:, 4] / sp[:, 5], 0, 1) ** 1.5
            for sub in (0.0, 0.33, 0.66):                       # motion blur
                x = sp[:, 0] + sub * sp[:, 2]
                y = sp[:, 1] + sub * sp[:, 3]
                x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
                fx, fy = x - x0, y - y0
                for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
                    xs, ys = x0 + dx, y0 + dy
                    ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
                    np.add.at(P, (ys[ok], xs[ok]), (sp[ok, 6:9] * (alpha[ok] * w[ok] / 3)[:, None]))
            sp[:, 0] += sp[:, 2]
            sp[:, 1] += sp[:, 3]
            sp[:, 2:4] *= 0.90
            sp[:, 4] += 1
            self.sparks = sp[(sp[:, 4] < sp[:, 5]) & (sp[:, 0] > -20) & (sp[:, 0] < W + 20)]
            P = gaussian_filter(P, (0.7, 0.7, 0))
        self.state = p
        return self._compose(T + P)

    def _compose(self, img):
        small = gaussian_filter(img[::2, ::2], (3, 3, 0))
        big = gaussian_filter(img[::8, ::8], (3, 3, 0))
        H, W = self.H, self.W
        glow = _resize(small, W, H)
        glow2 = _resize(big, W, H)
        out = img + 0.40 * glow + 0.30 * glow2
        out = 1 - np.exp(-1.7 * out)                              # soft tone mapping
        srgb = np.where(out <= 0.0031308, 12.92 * out, 1.055 * np.power(out, 1 / 2.4) - 0.055)
        return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)


# ---------------------------------------------------------------- overlay (explainer version)

class Overlay:
    def __init__(self, r: Rules, W, H, bpm):
        self.W, self.H, self.r, self.bpm = W, H, r, bpm
        self.f_s = ImageFont.truetype(FONT, int(H * 0.0115))
        self.f_m = ImageFont.truetype(FONT, int(H * 0.0135))
        self.f_b = ImageFont.truetype(FONT_B, int(H * 0.0135))
        base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(base)
        for n in range(0, 10):
            f = 27.5 * 2 ** n
            if not (r.f_min <= f <= r.f_max):
                continue
            y = float(y_of_freq(f, H, r))
            for x0 in range(0, W, 18):
                d.line([(x0, y), (x0 + 8, y)], fill=(255, 255, 255, 38), width=1)
            d.text((14, y - H * 0.016), f"{f:g} Hz", font=self.f_s, fill=(255, 255, 255, 110))
        d.line([(W // 2, H * r.y_top - 10), (W // 2, H * r.y_top - 30)], fill=(255, 255, 255, 90), width=2)
        d.text((W // 2 + 8, H * r.y_top - 34), "jetzt", font=self.f_s, fill=(255, 255, 255, 120))
        d.text((14, H * 0.012), "Höhe = Tonhöhe   Helligkeit = Lautheit   Farbe = Klangfarbe",
               font=self.f_m, fill=(255, 255, 255, 170))
        d.text((14, H * 0.012 + H * 0.019), "links/rechts = Stereo   Turbulenz = Chaos   ← Zeit fließt nach außen →",
               font=self.f_m, fill=(255, 255, 255, 170))
        self.base = base

    def draw(self, frame, p, t):
        r, W, H = self.r, self.W, self.H
        img = Image.fromarray(frame).convert("RGBA")
        img.alpha_composite(self.base)
        d = ImageDraw.Draw(img)
        y = H * 0.952
        c = p["chaos"]
        d.text((14, y), f"Chaos {c:.2f}", font=self.f_b, fill=(255, 255, 255, 220))
        bx, bw, bh = int(W * 0.2), int(W * 0.28), int(H * 0.011)
        d.rectangle([bx, y + 6, bx + bw, y + 6 + bh], outline=(255, 255, 255, 140))
        d.rectangle([bx, y + 6, bx + int(bw * c), y + 6 + bh], fill=(255, 255, 255, 200))
        sx = int(W * 0.53)
        for label, ab in (("tonal", p["ab_h"]), ("perkussiv", r.perc_chroma * p["ab_p"])):
            rgb = oklab_to_linear_srgb(np.array([0.75]), np.array([ab[0]]), np.array([ab[1]]))[0]
            rgb = np.clip(rgb, 0, 1) ** (1 / 2.2)
            d.rectangle([sx, y + 2, sx + int(H * 0.018), y + 2 + int(H * 0.018)],
                        fill=tuple(int(v * 255) for v in rgb) + (255,))
            d.text((sx + int(H * 0.024), y), label, font=self.f_s, fill=(255, 255, 255, 200))
            sx += int(W * 0.2)
        d.text((W - int(W * 0.2), H * 0.975), f"{self.bpm:.0f} BPM  {t:5.1f}s", font=self.f_s,
               fill=(255, 255, 255, 150))
        return np.asarray(img.convert("RGB"))


# ---------------------------------------------------------------- driver

def render(F, r: Rules, song, t0, dur, out, fps=30, scale=0.5, overlay=False, stills=None, log=print):
    W, H = int(1080 * scale) // 2 * 2, int(1920 * scale) // 2 * 2
    R = Renderer(F, r, t0, dur, fps, W, H)
    ow, oh = (1080, 1920)
    ov = Overlay(r, ow, oh, F.bpm) if overlay else None
    size = f"{ow}x{oh}" if overlay else f"{W}x{H}"
    vf = "format=yuv420p" if overlay else f"scale={ow}:{oh}:flags=lanczos,format=yuv420p"
    n = R.k_end - R.k_start
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(fps),
           "-i", "-", "-ss", f"{R.t0:.6f}", "-t", f"{n / fps:.6f}", "-i", song,
           "-filter_complex", f"[0:v]{vf}[v];[1:a]afade=t=in:st=0:d=0.03,afade=t=out:st={n / fps - 0.4:.3f}:d=0.4[a]",
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-r", str(fps),
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    kept = []
    for k in range(R.k_pre, R.k_end):
        frame = R.step(k)
        if k < R.k_start:
            continue
        if ov is not None:
            big = np.asarray(Image.fromarray(frame).resize((ow, oh), Image.BICUBIC))
            frame = ov.draw(big, R.state, k / fps)
        proc.stdin.write(frame.tobytes())
        if stills is not None and (k - R.k_start) in stills:
            kept.append(frame.copy())
        if (k - R.k_start) % 60 == 0:
            log(f"  frame {k - R.k_start}/{n}  chaos {R.state['chaos']:.2f}")
    proc.stdin.close()
    if proc.wait() != 0:
        raise SystemExit("ffmpeg failed")
    return kept

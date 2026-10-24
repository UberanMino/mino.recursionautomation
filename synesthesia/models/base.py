"""Shared parts of the alternative models: colours per frame, splatting, feedback warp,
tone mapping, caption overlay and the ffmpeg driver.

A model is a dynamical system (attractor, fractal, orbits, reaction-diffusion, plate, ...) whose
parameters are driven by the same analysed signals as the tunnel (synesthesia/signals.py). Every
model keeps R3 (a sound at time t is shown in frame floor(t * fps)) and R4 (colour = timbre in
Oklab); which of the other rules it keeps is written in its LAWS.
"""
import math
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter, map_coordinates
from scipy.signal import lfilter

from ..render import FONT, FONT_B, _resize
from ..rules import Rules, element_ab, lightness, oklab_to_linear_srgb, timbre_ab, video_frame


def impulses(times, weights, n, fps, tau_s):
    """Sum of decaying exponentials exp(-(t - t_i)/tau) starting at the frame of each event."""
    x = np.zeros(n)
    for t, w in zip(times, weights):
        k = int(video_frame(t, fps))
        if 0 <= k < n:
            x[k] += w
    a = math.exp(-1.0 / (tau_s * fps))
    return lfilter([1.0], [1.0, -a], x)


def splat(buf, x, y, val):
    """Bilinear point splat into buf (H, W, 3), additive."""
    H, W = buf.shape[:2]
    x0, y0 = np.floor(x - 0.5).astype(int), np.floor(y - 0.5).astype(int)
    fx, fy = (x - 0.5 - x0)[:, None], (y - 0.5 - y0)[:, None]
    flat = buf.reshape(-1, 3)
    for dx, dy, w in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xs, ys = x0 + dx, y0 + dy
        ok = (xs >= 0) & (xs < W) & (ys >= 0) & (ys < H)
        idx = ys[ok] * W + xs[ok]
        v = val[ok] * w[ok]
        for c in range(3):
            flat[:, c] += np.bincount(idx, v[:, c], minlength=H * W)
    return buf


def warp(img, zoom=1.0, rot=0.0, cx=None, cy=None, shift=(0.0, 0.0)):
    """Feedback warp: content moves outward by `zoom` and turns by `rot` about (cx, cy)."""
    H, W = img.shape[:2]
    cx = W / 2 if cx is None else cx
    cy = H / 2 if cy is None else cy
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    c, s = math.cos(-rot) / zoom, math.sin(-rot) / zoom
    dx, dy = xx - cx, yy - cy
    sx = cx + c * dx - s * dy - shift[0]
    sy = cy + s * dx + c * dy - shift[1]
    return np.stack([map_coordinates(img[..., ch], [sy, sx], order=1, mode="constant") for ch in range(3)], -1)


def spring(times, weights, n, fps, period_s, zeta=0.3):
    """Kick bounce: every event displaces a damped spring, x(t) = sum w_i e^(-zeta w t) cos(w_d t).
    The peak is in the event's own frame (R3), then one overshoot, then calm."""
    om = 2 * math.pi / period_s
    wd = om * math.sqrt(1 - zeta ** 2)
    tt = np.arange(int(3 * period_s * fps) + 1) / fps
    resp = np.exp(-zeta * om * tt) * np.cos(wd * tt)
    x = np.zeros(n)
    for t, w in zip(times, weights):
        k0 = int(video_frame(t, fps))
        if 0 <= k0 < n:
            k1 = min(n, k0 + len(resp))
            x[k0:k1] += w * resp[:k1 - k0]
    return x


def look_at(cam, target, up=(0.0, 0.0, 1.0)):
    fwd = np.asarray(target, float) - cam
    fwd /= np.linalg.norm(fwd) + 1e-12
    right = np.cross(fwd, up)
    right /= np.linalg.norm(right) + 1e-12
    return np.stack([right, np.cross(right, fwd), fwd])


def project(P, cam, B, focal, W, H, near=0.05):
    q = (P - cam) @ B.T
    z = q[:, 2]
    ok = z > near
    zs = np.where(ok, z, 1.0)
    return W / 2 + focal * q[:, 0] / zs, H / 2 - focal * q[:, 1] / zs, z, ok


def compose(img, bloom=(0.18, 0.15), expo=1.4):
    """Bloom + filmic tone map + sRGB encode (as in the tunnel)."""
    H, W = img.shape[:2]
    out = img
    if bloom[0] or bloom[1]:
        small = gaussian_filter(img[::2, ::2], (3, 3, 0))
        big = gaussian_filter(img[::8, ::8], (3, 3, 0))
        out = img + bloom[0] * _resize(small, W, H) + bloom[1] * _resize(big, W, H)
    out = 1 - np.exp(-expo * out)
    srgb = np.where(out <= 0.0031308, 12.92 * out, 1.055 * np.power(np.maximum(out, 0), 1 / 2.4) - 0.055)
    return (np.clip(srgb, 0, 1) * 255 + 0.5).astype(np.uint8)


class Model:
    """Base class: holds the song, the signals and the per-frame colours."""
    key = "base"
    title = ""
    laws = ()                         # caption lines (German, shown in the video)

    def __init__(self, F, S, r: Rules, t0, dur, fps=30, W=540, H=960, preroll_bars=2.0):
        self.F, self.S, self.r = F, S, r
        self.fps, self.W, self.H = fps, W, H
        self.a = S.a
        self.k_start = int(video_frame(t0, fps))
        self.k_end = min(S.n - 1, self.k_start + int(round(dur * fps)))
        self.k_pre = max(0, self.k_start - int(preroll_bars * S.bar_s * fps))
        self.t0 = self.k_start / fps
        self.bar_f = S.bar_s * fps
        self.freqs = F.freqs
        self.ab_h = timbre_ab(self.a["z_h"], r).astype(np.float32)          # (n, 2) tonal colour
        self.ab_p = timbre_ab(self.a["z_p"], r).astype(np.float32)          # (n, 2) percussive colour
        n = S.n
        self.env = {}
        for cls, tau in (("kick", 0.06), ("snare", 0.08), ("hat", 0.05)):
            hh = S.hits[cls]
            w = hh[:, 2] / (np.percentile(hh[:, 2], 90) + 1e-9) if len(hh) else []
            self.env[cls] = np.minimum(impulses(hh[:, 0] if len(hh) else [], np.minimum(w, 1.2), n, fps, tau), 1.5)
        entries = [s["start"] for s in S.sections if s.get("entry")]
        self.drop_env = impulses(entries, [1.0] * len(entries), n, fps, S.bar_s / 2)
        self.entry_frames = {int(video_frame(t, fps)) for t in entries}
        kk = S.hits["kick"]
        kw = np.clip(kk[:, 2] / (np.percentile(kk[:, 2], 90) + 1e-9), 0, 1.2) if len(kk) else []
        self.bounce = spring(kk[:, 0] if len(kk) else [], kw, n, fps, S.bar_s / 8)      # half-beat spring
        self.sec_start = np.zeros(n)
        self.sec_kind = [""] * n
        for s in S.sections:
            k0, k1 = int(s["start"] * fps), min(n, int(s["end"] * fps) + 1)
            self.sec_start[k0:k1] = s["start"]
            for k in range(k0, k1):
                self.sec_kind[k] = s["kind"]
        self.live = {}

    # colours -------------------------------------------------------------------------------
    def colour(self, k, L, harm=None):
        """Linear RGB for lightness L (any shape) in the colour of frame k (R4)."""
        h = float(np.mean(self.a["harm"][k])) if harm is None else harm
        ab = element_ab(h, self.ab_h[k], self.ab_p[k], self.r)
        L = np.asarray(L, np.float32)
        return oklab_to_linear_srgb(L, np.broadcast_to(ab[..., 0], L.shape), np.broadcast_to(ab[..., 1], L.shape))

    def lightness(self, p):
        return lightness(p, self.r)

    def profile(self, k):
        """psi per log-frequency bin for both channels, (K,), (K,)."""
        return self.a["prof_l"][k], self.a["prof_r"][k]

    def section_phase(self, k, bars=8.0):
        """Bars since the start of the current section / `bars`."""
        return (k / self.fps - self.sec_start[k]) / (bars * self.S.bar_s)

    # interface -----------------------------------------------------------------------------
    def step(self, k):
        """Return the frame for video frame k as linear RGB float32 (H, W, 3)."""
        raise NotImplementedError

    def frame(self, k):
        img = self.step(k)
        out = compose(img, *self.compose_args())
        if k in self.entry_frames and getattr(self, "invert_entry", False):
            out = 255 - out
        return out

    def compose_args(self):
        return ((0.18, 0.15), 1.4)


class Caption:
    """Model name + its laws at the bottom, live values in one line."""

    def __init__(self, W, H):
        self.W, self.H = W, H
        self.f_s = ImageFont.truetype(FONT, int(H * 0.0118))
        self.f_b = ImageFont.truetype(FONT_B, int(H * 0.017))

    def draw(self, frame, M: Model, k):
        W, H = self.W, self.H
        img = Image.fromarray(frame).convert("RGBA")
        lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        lines = []
        for law in M.laws:                               # wrap to the frame width
            cur = ""
            for word in law.split(" "):
                t = (cur + " " + word).strip()
                if cur and d.textlength(t, font=self.f_s) > W - 32:
                    lines.append(cur)
                    cur = "   " + word
                else:
                    cur = t if not cur.startswith("   ") else cur + " " + word
            lines.append(cur)
        n = len(lines)
        y0 = H - int(H * (0.05 + 0.018 * (n + 1)))
        d.rectangle([0, y0 - 12, W, H], fill=(0, 0, 0, 120))
        d.text((16, y0), M.title, font=self.f_b, fill=(255, 255, 255, 235))
        for i, line in enumerate(lines):
            d.text((16, y0 + H * 0.024 + i * H * 0.018), line, font=self.f_s, fill=(255, 255, 255, 200))
        live = "   ".join(f"{a} {b}" for a, b in M.live.items())
        d.text((16, H - H * 0.022), f"{k / M.fps:5.1f} s   {M.sec_kind[k].upper():7s}  {live}", font=self.f_s,
               fill=(255, 255, 255, 160))
        img.alpha_composite(lay)
        return np.asarray(img.convert("RGB"))


def render(model_cls, F, S, r: Rules, song, t0, dur, out, fps=30, scale=0.5, caption=True, stills=None,
           log=print, clean_out=None, **kw):
    """Render a model to `out`; with `clean_out`, the same frames also go to a second video without the caption."""
    W, H = int(1080 * scale) // 2 * 2, int(1920 * scale) // 2 * 2
    M = model_cls(F, S, r, t0, dur, fps, W, H, **kw)
    ow, oh = 1080, 1920
    cap = Caption(ow, oh) if caption else None
    size = f"{ow}x{oh}" if caption else f"{W}x{H}"
    vf = "format=yuv420p" if caption else f"scale={ow}:{oh}:flags=lanczos,format=yuv420p"
    n = M.k_end - M.k_start

    def ffmpeg(size, vf, path):
        cmd = ["ffmpeg", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", size, "-r", str(fps),
               "-i", "-", "-ss", f"{M.t0:.6f}", "-t", f"{n / fps:.6f}", "-i", song,
               "-filter_complex", f"[0:v]{vf}[v];[1:a]afade=t=in:st=0:d=0.03,afade=t=out:st={n / fps - 0.4:.3f}:d=0.4[a]",
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(fps),
               "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", path]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE)

    proc = ffmpeg(size, vf, out)
    clean = ffmpeg(f"{W}x{H}", f"scale={ow}:{oh}:flags=lanczos,format=yuv420p", clean_out) if clean_out else None
    kept = []
    for k in range(M.k_pre, M.k_end):
        frame = M.frame(k)
        if k < M.k_start:
            continue
        if clean is not None:
            clean.stdin.write(frame.tobytes())
        if cap is not None:
            frame = cap.draw(np.asarray(Image.fromarray(frame).resize((ow, oh), Image.BICUBIC)), M, k)
        proc.stdin.write(frame.tobytes())
        if stills is not None and (k - M.k_start) in stills:
            kept.append(frame.copy())
        if (k - M.k_start) % 90 == 0:
            log(f"  frame {k - M.k_start}/{n}  " + "  ".join(f"{a} {b}" for a, b in M.live.items()))
    for p in (proc, clean):
        if p is not None:
            p.stdin.close()
            if p.wait() != 0:
                raise SystemExit("ffmpeg failed")
    return kept

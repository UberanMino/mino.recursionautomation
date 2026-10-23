#!/usr/bin/env python3
"""uberanmino.core "cannon" format (prototype): hero clips + hype VFX on the beat.

Inspired by the structure of @alaskancannon reels (looked at via Business Discovery
on 23.10.2026): one hero doing something physical, a calm intro with a small
caption, then on the drop explosions, lightning, energy beams, ghost trails,
shake, and big glowing all-caps title slams. All effects here are procedural,
no third-party VFX footage.

  python3 engine/core/cannon.py --song song.wav --out out.mp4 \
      --hero clipA.mp4@0.45:"CAPTAIN CHAOS" --hero clipB.mp4:"SPIDER DAD" ... \
      --intro "Monday morning"

Each --hero is path[@start_seconds][:TITLE]. The first hero carries the intro
and lands on the drop; the rest take one bar (4 beats) each, then loop.
"""
import argparse
import json
import math
import os
import random
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_core import Clip, analysis_for, kick_grid  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FPS = 30
W, H = 720, 1280
TITLE_FONT = os.path.join(ROOT, "assets", "fonts", "anton-latin-400-normal.woff2")
CAPTION_FONT = "/usr/share/fonts/opentype/inter/Inter-SemiBold.otf"


# ---------------------------------------------------------------- sources

def load_frames(path, crop, start, seconds):
    vf = (f"crop={crop}," if crop else "") + \
        f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},format=rgb24"
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", path, "-t", f"{seconds:.3f}",
                          "-vf", vf, "-f", "rawvideo", "-"], check=True, capture_output=True).stdout
    fr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, H, W, 3)
    return fr.astype(np.float32) / 255.0


def parse_hero(spec):
    title = None
    if ":" in spec.split("/")[-1]:
        spec, title = spec.rsplit(":", 1)
    start = None
    if "@" in spec.split("/")[-1]:
        spec, s = spec.rsplit("@", 1)
        start = float(s)
    return spec, start, title


# ---------------------------------------------------------------- effects

YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)


def screen(a, b):
    return 1.0 - (1.0 - a) * (1.0 - np.clip(b, 0, 1))


def noise_tex(rng, scale=40):
    small = rng.random((H // scale + 2, W // scale + 2)).astype(np.float32)
    im = Image.fromarray((small * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC).filter(ImageFilter.GaussianBlur(18))
    return np.asarray(im, dtype=np.float32) / 255.0


def fireball(age, cx, cy, size, tex):
    """Expanding fire burst; age in seconds."""
    if age > 0.55:
        return None
    rad = size * (0.25 + 3.2 * age)
    d = np.sqrt((XX - cx) ** 2 + (YY - cy) ** 2) / rad
    d = d * (0.8 + 0.4 * tex)
    fade = max(0.0, 1.0 - age / 0.55) ** 0.7
    core = np.exp(-(d ** 2) * 2.2) * fade
    col = np.stack([np.clip(core * 2.6, 0, 1),
                    np.clip(core * 2.0 - 0.35, 0, 1),
                    np.clip(core * 2.2 - 1.25, 0, 1)], axis=-1)
    return col


def bolt_points(rng, x0, y0, x1, y1, depth=6, rough=0.28):
    pts = [(x0, y0), (x1, y1)]
    for _ in range(depth):
        new = [pts[0]]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            mx, my = (ax + bx) / 2, (ay + by) / 2
            ln = math.hypot(bx - ax, by - ay)
            nx, ny = -(by - ay) / (ln + 1e-6), (bx - ax) / (ln + 1e-6)
            off = rng.gauss(0, ln * rough)
            new += [(mx + nx * off, my + ny * off), (bx, by)]
        pts = new
    return pts


def lightning_layer(rng, target):
    """One strike from the top edge to the target, with branches. Returns HxWx3 glow."""
    im = Image.new("L", (W, H), 0)
    dr = ImageDraw.Draw(im)
    tx, ty = target
    for _ in range(rng.choice([1, 2])):
        x0 = tx + rng.uniform(-260, 260)
        pts = bolt_points(rng, x0, -20, tx + rng.uniform(-40, 40), ty)
        dr.line(pts, fill=255, width=9)
        for _ in range(3):
            i = rng.randrange(len(pts) // 4, len(pts) - 1)
            bx, by = pts[i]
            br = bolt_points(rng, bx, by, bx + rng.uniform(-220, 220), by + rng.uniform(80, 300), depth=4)
            dr.line(br, fill=190, width=5)
    core = np.asarray(im, dtype=np.float32) / 255.0
    glow = np.asarray(im.filter(ImageFilter.GaussianBlur(22)), dtype=np.float32) / 255.0 * 4.0
    return np.stack([np.clip(core + glow * 0.25, 0, 1),
                     np.clip(core + glow * 0.75, 0, 1),
                     np.clip(core + glow * 1.0, 0, 1)], axis=-1)


def beam(age, cx):
    if age > 0.35:
        return None
    w = 18 + 260 * age
    f = max(0.0, 1 - age / 0.35)
    g = np.exp(-((XX - cx) / w) ** 2) * f
    core = np.exp(-((XX - cx) / (w * 0.18)) ** 2) * f
    return np.stack([g * 0.35 + core, g * 0.85 + core, g * 1.0 + core], axis=-1)


def grade(img):
    lum = img.mean(axis=-1, keepdims=True)
    img = lum + (img - lum) * 1.4                          # saturation
    img = (img - 0.5) * 1.12 + 0.5                         # contrast
    img = img * np.array([0.96, 1.0, 1.08], dtype=np.float32)  # cool
    return np.clip(img, 0, 1)


def shift(img, dx, dy):
    return np.roll(np.roll(img, int(dy), axis=0), int(dx), axis=1)


def zoom(img, z):
    if abs(z - 1) < 1e-3:
        return img
    im = Image.fromarray((img * 255).astype(np.uint8))
    nw, nh = int(W * z), int(H * z)
    im = im.resize((nw, nh), Image.BILINEAR)
    x, y = (nw - W) // 2, (nh - H) // 2
    return np.asarray(im.crop((x, y, x + W, y + H)), dtype=np.float32) / 255.0


# ---------------------------------------------------------------- text

def text_layer(text, font_path, size, y, scale=1.0, glow=True, caption=False):
    """RGBA float layer with the text centred at height y."""
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    dr = ImageDraw.Draw(im)
    lines = text.split("\\n") if "\\n" in text else [text]
    base = ImageFont.truetype(font_path, size)
    widest = max(dr.textbbox((0, 0), ln, font=base)[2] for ln in lines)
    fit = min(1.0, W * 0.9 / max(1, widest))               # long titles shrink to fit the frame
    font = ImageFont.truetype(font_path, max(8, int(size * fit * scale)))
    hs = [dr.textbbox((0, 0), ln, font=font) for ln in lines]
    total = sum(b[3] - b[1] for b in hs) + 8 * (len(lines) - 1)
    cy = y - total / 2
    for ln, b in zip(lines, hs):
        tw = b[2] - b[0]
        x = (W - tw) / 2 - b[0]
        if caption:
            dr.text((x + 2, cy - b[1] + 2), ln, font=font, fill=(0, 0, 0, 160))
        dr.text((x, cy - b[1]), ln, font=font, fill=(255, 255, 255, 255))
        cy += b[3] - b[1] + 8
    arr = np.asarray(im, dtype=np.float32) / 255.0
    if not glow:
        return arr
    a = Image.fromarray((arr[..., 3] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(10))
    g = np.asarray(a, dtype=np.float32)[..., None] / 255.0 * 1.6
    glowc = np.clip(g * np.array([0.25, 0.65, 1.0], dtype=np.float32), 0, 1)
    return arr, glowc


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--hero", action="append", required=True)
    ap.add_argument("--intro", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--bars", type=int, default=6, help="bars after the drop")
    ap.add_argument("--intro-beats", type=int, default=4)
    ap.add_argument("--near", type=float, help="song second to look for the drop near (default: analysis drop)")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    nrng = np.random.default_rng(a.seed)
    an = analysis_for(a.song)
    near = a.near if a.near is not None else an["drops"][0]["t"]
    grid, drop, period = kick_grid(a.song, an, near)
    di = int(np.argmin([abs(b - drop) for b in grid]))
    beats = grid[di - a.intro_beats: di + a.bars * 4 + 1]
    t0 = beats[0]
    total = beats[-1] - t0
    nframes = int(round(total * FPS))
    bt = [b - t0 for b in beats]
    drop_t = bt[a.intro_beats]

    heroes = [parse_hero(h) for h in a.hero]
    # segments: (start_time, end_time, hero_index)
    segs = [(0.0, bt[a.intro_beats + 4], 0)]
    k = 1
    for bar in range(1, a.bars):
        i0 = a.intro_beats + bar * 4
        segs.append((bt[i0], bt[min(i0 + 4, len(bt) - 1)], k % len(heroes)))
        k += 1
    frames_by_seg, clips = [], {}
    for s0, s1, hi in segs:
        path, st, _ = heroes[hi]
        c = clips.setdefault(path, Clip(path))
        need = (s1 - s0) * 1.6 + 0.5                      # slack for speed ramps
        if st is None or s0 > 0:
            st = c.best_start(min(need, max(0.5, c.dur - 0.2)), rng)
        fr = load_frames(path, c.crop, st, min(need, c.dur - st))
        frames_by_seg.append(fr)

    # beat events after the drop
    kinds = ["fire", "bolt", "beam", "ghost", "bolt", "fire", "warp", "bolt"]
    events = []
    for j, t in enumerate(bt[a.intro_beats:-1]):
        kind = "fire" if j == 0 else (kinds[(j + a.seed) % len(kinds)] if rng.random() > 0.15 else rng.choice(kinds))
        events.append({"t": t, "kind": kind, "cx": rng.uniform(W * 0.3, W * 0.7), "cy": rng.uniform(H * 0.35, H * 0.6),
                       "bolt": lightning_layer(rng, (rng.uniform(W * 0.3, W * 0.7), rng.uniform(H * 0.45, H * 0.75)))
                       if kind == "bolt" else None})
    tex = noise_tex(nrng)

    cap = text_layer(a.intro, CAPTION_FONT, 40, H * 0.80, glow=False, caption=True) if a.intro else None
    title_cache = {}

    out_tmp = os.path.splitext(a.out)[0] + ".video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                            "-crf", "17", "-pix_fmt", "yuv420p", out_tmp], stdin=subprocess.PIPE)
    history = []
    pos = [0.0] * len(segs)
    for f in range(nframes):
        t = f / FPS
        si = max(i for i, s in enumerate(segs) if s[0] <= t + 1e-6)
        s0, s1, hi = segs[si]
        last = max([e for e in events if e["t"] <= t + 1e-6], key=lambda e: e["t"], default=None)
        age = t - last["t"] if last else 9.0
        speed = 1.0
        if last and last["kind"] == "warp":
            speed = 0.3 if age < period * 0.6 else 2.2      # time warp: slow, then catch up
        fr = frames_by_seg[si]
        img = fr[min(int(pos[si]), len(fr) - 1)].copy()
        pos[si] += speed
        img = grade(img)

        if t >= drop_t:
            # ghost trails on ghost beats
            if last and last["kind"] == "ghost" and age < 0.45 and len(history) >= 6:
                for n, back in enumerate((2, 4, 6)):
                    g = history[-back] * np.array([0.35, 0.75, 1.0], dtype=np.float32) * (0.55 - n * 0.12)
                    img = np.maximum(img, shift(g, (n + 1) * 14, -(n + 1) * 10))
            punch = 1.0 + 0.12 * math.exp(-age * 14)
            img = zoom(img, punch)
            if last["kind"] == "fire":
                fb = fireball(age, last["cx"], last["cy"], 420 if events.index(last) else 640, tex)
                if fb is not None:
                    img = screen(img, fb)
            elif last["kind"] == "bolt" and age < 0.3 and (int(age * FPS) % 3 != 1):
                img = img * np.array([0.75, 0.88, 1.15], dtype=np.float32)
                img = screen(img, last["bolt"] * (1 - age / 0.3) ** 0.5)
            elif last["kind"] == "beam":
                bm = beam(age, last["cx"])
                if bm is not None:
                    img = screen(img, bm)
            img = screen(img, np.float32(math.exp(-age * 22) * 0.85))   # hit flash
            amp = 26 * math.exp(-age * 12)
            img = shift(img, rng.uniform(-amp, amp), rng.uniform(-amp, amp))
            title = heroes[hi][2]
            if title:
                ts = t - s0
                sc = 1.0 + 0.7 * math.exp(-ts * 22)
                key = (title, round(sc, 2))
                if key not in title_cache:
                    title_cache[key] = text_layer(title.upper(), TITLE_FONT, 112, H * 0.80, scale=sc)
                tl, gl = title_cache[key]
                img = screen(img, gl)
                img = img * (1 - tl[..., 3:]) + tl[..., :3] * tl[..., 3:]
        elif cap is not None:
            img = img * (1 - cap[..., 3:]) + cap[..., :3] * cap[..., 3:]

        history.append(img)
        if len(history) > 8:
            history.pop(0)
        enc.stdin.write((np.clip(img, 0, 1) * 255).astype(np.uint8).tobytes())
    enc.stdin.close()
    enc.wait()

    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", out_tmp, "-ss", f"{t0:.3f}", "-t", f"{nframes / FPS:.3f}",
                    "-i", a.song, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                    "-af", f"afade=t=out:st={max(0, nframes / FPS - 0.3):.3f}:d=0.3", "-movflags", "+faststart",
                    a.out], check=True)
    os.remove(out_tmp)
    json.dump({"song": os.path.basename(a.song), "t0": t0, "drop": drop_t, "period": period,
               "heroes": a.hero, "events": [{"t": round(e["t"], 3), "kind": e["kind"]} for e in events]},
              open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"{a.out}: {nframes / FPS:.2f}s, drop at {drop_t:.2f}s, {60 / period:.1f} BPM")


if __name__ == "__main__":
    main()

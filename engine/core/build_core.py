#!/usr/bin/env python3
"""uberanmino.core: beat-cut clip edit (prototype).

Format measured from Raphael's finished edits (Dropbox /Dont touch/All edits core):
7-10 s, a hook clip that holds ~3 beats, then a cut on (almost) every beat,
white flashes, colour casts, RGB split, saturated grade, mostly no text.

  python3 engine/core/build_core.py --song song.wav --clips DIR --hook DIR/h03.mp4 --out out.mp4
  python3 engine/core/build_core.py ... --seed 4 --length 8 --res 1080

Clips come from a folder of mp4s. The hook clip is passed explicitly (or picked
from files starting with "h"). Every other mp4 in --clips is a cut candidate.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FPS = 30


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def probe_duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                         check=True, capture_output=True, text=True).stdout
    return float(out.strip())


def analysis_for(song):
    js = os.path.splitext(song)[0] + ".json"
    if not os.path.exists(js):
        run([sys.executable, os.path.join(ROOT, "engine", "analyze_audio.py"), song, js])
    return json.load(open(js))


def detect_crop(path):
    """Content box without letterbox bars, as ffmpeg crop args (w:h:x:y)."""
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", "fps=2,cropdetect=limit=24:round=2:reset=0",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    crops = [l.split("crop=")[-1].strip() for l in err.splitlines() if "crop=" in l]
    return crops[-1] if crops else None


def motion_profile(path, crop):
    """Mean absolute frame difference at 10 fps on a tiny grey image."""
    vf = (f"crop={crop}," if crop else "") + "fps=10,scale=36:64,format=gray"
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-vf", vf, "-f", "rawvideo", "-"],
                         check=True, capture_output=True).stdout
    fr = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 64, 36).astype(np.float32)
    if len(fr) < 2:
        return np.zeros(1)
    return np.concatenate([[0.0], np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))])


class Clip:
    def __init__(self, path):
        self.path = path
        self.dur = probe_duration(path)
        self.crop = detect_crop(path)
        self.motion = motion_profile(path, self.crop)
        self.used = []

    def best_start(self, length, rng, payoff=False):
        """Start of the most active window of `length` s that does not overlap earlier picks.

        payoff=True (hook): weight the end of the window, so the clip's big moment
        (fall, jump, crash) lands right on the drop where the fast cuts begin.
        """
        n = len(self.motion)
        w = max(1, int(round(length * 10)))
        best, best_s = None, -1.0
        for i in range(0, max(1, n - w)):
            t = i / 10.0
            if t + length > self.dur - 0.05:
                break
            if any(abs(t - u) < length + 0.3 for u in self.used):
                continue
            win = self.motion[i:i + w]
            if payoff:
                s = float(win[-max(1, w // 3):].mean()) * 2 - float(win[:max(1, w // 3)].mean()) * 0.5
            else:
                s = float(win.mean()) * rng.uniform(0.85, 1.15)
            if s > best_s:
                best, best_s = t, s
        if best is None:
            best = rng.uniform(0, max(0.0, self.dur - length - 0.05))
        self.used.append(best)
        return best


def plan_cuts(an, length, rng, hook_beats=3):
    beats = [b for b in an["beats"]]
    drops = an.get("drops") or [{"t": beats[len(beats) // 3]}]
    drop = rng.choice(drops[:2])["t"]
    di = int(np.argmin([abs(b - drop) for b in beats]))
    start_i = max(0, di - hook_beats)
    t0 = beats[start_i]
    cuts = [(t0, beats[di], "hook")]
    i = di
    while beats[i] - t0 < length and i + 1 < len(beats):
        r = rng.random()
        if r < 0.12 and i + 2 < len(beats):           # hold a clip for two beats
            j = i + 2
        elif r < 0.22:                                  # half-beat burst
            mid = (beats[i] + beats[i + 1]) / 2
            cuts.append((beats[i], mid, "cut"))
            cuts.append((mid, beats[i + 1], "cut"))
            i += 1
            continue
        else:
            j = i + 1
        cuts.append((beats[i], beats[j], "cut"))
        i = j
    return t0, cuts


def grade_filter(kind, k, rng, res):
    w, h = res, res * 16 // 9
    f = []
    # zoom punch on every cut: starts ~8 % in, settles within a few frames
    z = 1.10 if kind == "hook" else rng.uniform(1.06, 1.14)
    f.append(f"scale=w='trunc({w}*({z}-({z}-1)*min(1\\,t*{6 if kind != 'hook' else 1.2}))/2)*2':"
             f"h='trunc({h}*({z}-({z}-1)*min(1\\,t*{6 if kind != 'hook' else 1.2}))/2)*2':eval=frame")
    f.append(f"crop={w}:{h}")
    sat = 1.45 if kind == "hook" else rng.uniform(1.5, 1.95)
    f.append(f"eq=saturation={sat:.2f}:contrast=1.12:brightness=0.03:gamma=1.05")
    if kind != "hook":
        look = rng.random()
        if look < 0.18:      # cold blue cast
            f.append("colorbalance=rs=-0.25:bs=0.35:rm=-0.15:bm=0.25")
        elif look < 0.32:    # magenta cast
            f.append("colorbalance=rs=0.25:bs=0.3:gs=-0.25:gm=-0.2")
        elif look < 0.42:    # pushed highlights
            f.append("curves=all='0/0 0.5/0.62 0.9/1 1/1'")
        if rng.random() < 0.45:
            s = rng.choice([6, 10, 14])
            f.append(f"rgbashift=rh={s}:bh=-{s}")
        if k > 0 and look >= 0.42 and rng.random() < 0.38:
            f.append(f"fade=t=in:st=0:d={rng.choice([0.07, 0.1, 0.13])}:color=white")
    f.append("unsharp=5:5:0.6")
    f.append("format=yuv420p")
    return ",".join(f)


def render_segment(clip, start, frames, kind, k, rng, res, dst):
    pre = []
    if clip.crop:
        pre.append(f"crop={clip.crop}")
    w, h = res, res * 16 // 9
    pre.append(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,fps={FPS}")
    vf = ",".join(pre) + ",setpts=PTS-STARTPTS," + grade_filter(kind, k, rng, res)
    run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{start:.3f}", "-i", clip.path, "-an", "-vf", vf,
         "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "17", "-r", str(FPS), dst])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--hook")
    ap.add_argument("--hook-start", type=float, help="second in the hook clip to start from (default: auto)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--length", type=float, default=8.0)
    ap.add_argument("--res", type=int, default=1080, help="output width; height = 16/9 of it")
    a = ap.parse_args()

    rng = random.Random(a.seed)
    an = analysis_for(a.song)
    t0, cuts = plan_cuts(an, a.length, rng)
    files = sorted(os.path.join(a.clips, f) for f in os.listdir(a.clips) if f.endswith(".mp4"))
    hook_path = a.hook or rng.choice([f for f in files if os.path.basename(f).startswith("h")])
    pool = [f for f in files if f != hook_path and not os.path.basename(f).startswith("h")]
    rng.shuffle(pool)
    clips = {}

    def clip(p):
        if p not in clips:
            clips[p] = Clip(p)
        return clips[p]

    tmp = tempfile.mkdtemp(prefix="core-")
    segs, order = [], []
    for k, (ta, tb, kind) in enumerate(cuts):
        fa, fb = round((ta - t0) * FPS), round((tb - t0) * FPS)
        frames = max(1, fb - fa)
        c = clip(hook_path) if kind == "hook" else clip(pool[(k - 1) % len(pool)])
        if kind == "hook" and a.hook_start is not None:
            st = a.hook_start
        else:
            st = c.best_start(frames / FPS, rng, payoff=(kind == "hook"))
        dst = os.path.join(tmp, f"{k:03d}.mp4")
        render_segment(c, st, frames, kind, k, rng, a.res, dst)
        segs.append(dst)
        order.append({"k": k, "kind": kind, "clip": os.path.basename(c.path), "src_start": round(st, 2),
                      "t": round(ta - t0, 3), "frames": frames})
    lst = os.path.join(tmp, "list.txt")
    with open(lst, "w") as fh:
        fh.writelines(f"file '{s}'\n" for s in segs)
    total = sum(o["frames"] for o in order) / FPS
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst,
         "-ss", f"{t0:.3f}", "-t", f"{total:.3f}", "-i", a.song,
         "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
         "-af", f"afade=t=out:st={max(0, total - 0.25):.3f}:d=0.25", "-c:a", "aac", "-b:a", "256k",
         "-movflags", "+faststart", a.out])
    json.dump({"song": os.path.basename(a.song), "t0": t0, "length": total, "seed": a.seed, "cuts": order},
              open(os.path.splitext(a.out)[0] + ".json", "w"), indent=1)
    print(f"{a.out}: {total:.2f}s, {len(order)} shots, song from {t0:.2f}s")


if __name__ == "__main__":
    main()

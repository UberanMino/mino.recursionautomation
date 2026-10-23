"""Music -> visual mapping engine.

  python3 -m synesthesia SONG.wav --start 18.7 --dur 22 --out out.mp4 [--overlay] [--rules my_rules.json]
  python3 -m synesthesia SONG.wav --analyze-only          # print song structure (chaos, timbre) per 2 bars
  python3 -m synesthesia SONG.wav --export score.json     # mapped parameters per video frame, for other renderers
"""
import argparse
import hashlib
import json
import os
import time

import numpy as np

from .features import Features, analyze
from .render import render
from .rules import Rules, element_ab, lightness, psi, timbre_ab

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def features_for(song, weighting):
    st = os.stat(song)
    key = hashlib.sha1(f"{os.path.abspath(song)}|{st.st_size}|{st.st_mtime}|{weighting}|v3".encode()).hexdigest()[:12]
    cache = os.path.join(ROOT, "build", "synesthesia", f"{os.path.splitext(os.path.basename(song))[0]}-{key}.npz")
    if os.path.exists(cache):
        return Features.load(cache)
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    t = time.time()
    print("analysing", song)
    F = analyze(song, weighting=weighting)
    F.save(cache)
    print(f"  done in {time.time() - t:.0f}s  bpm {F.bpm:.1f}  onsets {len(F.onsets)}")
    return F


def summary(F):
    bar = 240.0 / F.bpm
    db = 10 * np.log10(0.5 * (10 ** (F.db_l / 10) + 10 ** (F.db_r / 10)).sum(1))
    for t0 in np.arange(0, F.duration, 2 * bar):
        a, b = int(t0 * F.fps), int((t0 + 2 * bar) * F.fps)
        print(f"{t0:6.1f}s  level {db[a:b].mean() - db.max():6.1f} dB  chaos {F.chaos[a:b].mean():.2f}  "
              f"timbre(tonal) {F.timbre_h[a:b].mean(0).round(2)}")


def export(F, r, path, fps=30, bands_per_oct=6):
    """Per video frame: chaos, timbre colours and a 1/6-octave loudness/colour profile per channel."""
    step = 24 // bands_per_oct
    n = int(F.duration * fps)
    frames = []
    for k in range(n):
        i0, i1 = int(np.ceil(k / fps * F.fps)), int(np.ceil((k + 1) / fps * F.fps))
        i1 = max(i0 + 1, min(i1, len(F.chaos)))
        sl = slice(i0, i1)
        abh = timbre_ab(F.timbre_h[sl].mean(0), r)[0]
        abp = timbre_ab(F.timbre_p[sl].mean(0), r)[0]
        h = F.harm[sl].mean(0)[::step]
        ab = element_ab(h, abh, abp, r)
        frames.append({
            "t": round(k / fps, 4), "chaos": round(float(F.chaos[sl].mean()), 3),
            "ab_tonal": abh.round(4).tolist(), "ab_perc": abp.round(4).tolist(),
            "L_left": lightness(psi(F.db_l[sl].max(0)[::step], F.ref_db, r), r).round(3).tolist(),
            "L_right": lightness(psi(F.db_r[sl].max(0)[::step], F.ref_db, r), r).round(3).tolist(),
            "ab": ab.round(4).tolist(),
        })
    on = [{"t": round(float(t), 4), "f": round(float(f), 1), "L": round(float(lightness(psi(l, F.ref_db, r), r)), 3)}
          for t, g, f, l in F.onsets]
    json.dump({"fps": fps, "bpm": F.bpm, "beats": np.round(F.beats, 4).tolist(),
               "band_freqs": F.freqs[::step].round(2).tolist(), "rules": r.to_dict(),
               "frames": frames, "onsets": on}, open(path, "w"), separators=(",", ":"))
    print("wrote", path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=20.0)
    ap.add_argument("--out")
    ap.add_argument("--overlay", action="store_true", help="draw the explainer overlay (axes, chaos meter)")
    ap.add_argument("--rules", help="JSON with rule constants to override (see synesthesia/rules.py)")
    ap.add_argument("--weighting", default="B", choices=["A", "B", "C", "Z"])
    ap.add_argument("--scale", type=float, default=0.5, help="internal render scale of 1080x1920")
    ap.add_argument("--sheet", help="also save a contact sheet of 6 stills (jpg)")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--export")
    a = ap.parse_args()
    r = Rules.from_json(a.rules)
    F = features_for(a.song, a.weighting)
    if a.analyze_only:
        summary(F)
        return
    if a.export:
        export(F, r, a.export)
    if a.out:
        t = time.time()
        n = int(a.dur * 30)
        picks = [int(n * q) for q in (0.08, 0.25, 0.42, 0.58, 0.75, 0.92)] if a.sheet else None
        stills = render(F, r, a.song, a.start, a.dur, a.out, scale=a.scale, overlay=a.overlay, stills=picks)
        print(f"wrote {a.out} in {time.time() - t:.0f}s")
        if a.sheet and stills:
            from PIL import Image
            ims = [Image.fromarray(s).resize((360, 640)) for s in stills]
            sheet = Image.new("RGB", (360 * 6 + 50, 640 + 20), (20, 20, 20))
            for i, im in enumerate(ims):
                sheet.paste(im, (10 + i * 368, 10))
            sheet.save(a.sheet, quality=90)
            print("wrote", a.sheet)


if __name__ == "__main__":
    main()

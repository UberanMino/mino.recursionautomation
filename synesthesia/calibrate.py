"""Calibrate visual chaos against musical chaos.

Renders the same passage with the chaos input forced to c = 0, 0.1, ..., 1 and measures how
disordered the picture is: D = 1 - correlation(frame, mirrored frame), averaged over the
passage (the left and right channels of a centred mix are nearly identical, so with chaos 0
the picture is mirror-symmetric and D ~ 0). Prints the exponent turb_gamma that makes D grow
linearly with c.

  python3 -m synesthesia.calibrate SONG.wav --start 31 --dur 4
"""
import argparse

import numpy as np

from . import __main__ as cli
from .render import Renderer
from .rules import Rules


def disorder(frame):
    a = frame.astype(np.float64).mean(2)
    b = a[:, ::-1]
    a, b = a - a.mean(), b - b.mean()
    return 1 - (a * b).sum() / np.sqrt((a * a).sum() * (b * b).sum() + 1e-9)


def measure(F, r, start, dur, c):
    R = Renderer(F, r, start, dur)
    R.chaos_override = c
    ds = []
    for k in range(R.k_pre, R.k_end):
        fr = R.step(k)
        if k >= R.k_start:
            ds.append(disorder(fr))
    return float(np.mean(ds))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("song")
    ap.add_argument("--start", type=float, default=31.0)
    ap.add_argument("--dur", type=float, default=4.0)
    a = ap.parse_args()
    F = cli.features_for(a.song, "B")
    r = Rules()
    r.turb_gamma = 1.0
    cs = np.linspace(0, 1, 11)
    D = np.array([measure(F, r, a.start, a.dur, c) for c in cs])
    for c, d in zip(cs, D):
        print(f"chaos {c:.1f}  disorder {d:.3f}")
    # we want D(c_eff) = D0 + (D1 - D0) * c with c_eff = c^gamma: invert the measured curve
    target = D[0] + (D[-1] - D[0]) * cs[1:-1]
    c_eff = np.interp(target, D, cs)
    ok = (c_eff > 0) & (c_eff < 1)
    gamma = float(np.sum(np.log(c_eff[ok]) * np.log(cs[1:-1][ok])) / np.sum(np.log(cs[1:-1][ok]) ** 2))
    print(f"turb_gamma (least squares in log-log) = {gamma:.2f}")


if __name__ == "__main__":
    main()

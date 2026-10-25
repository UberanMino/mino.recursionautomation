#!/usr/bin/env python3
"""Contact sheet of line-art shots from the catalogue (engine/shots.py) -> build/linesheet.jpg

  python3 engine/tools/line_sheet.py                    # one cell per scene family
  python3 engine/tools/line_sheet.py --sil              # every silhouette shape (fills rotate)
  python3 engine/tools/line_sheet.py --since 2026-10-21 # shots added on/after a date (review new shots)
  python3 engine/tools/line_sheet.py --keys globe,silhouette/alien/echo --white --out build/x.jpg
"""
import argparse
import os
import random
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build as B  # noqa: E402
import shots as S  # noqa: E402
from PIL import Image  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--sil", action="store_true")
ap.add_argument("--since")
ap.add_argument("--keys")
ap.add_argument("--white", action="store_true", help="every other cell on the off-white ground")
ap.add_argument("--at", type=float, default=0.5, help="time inside each shot")
ap.add_argument("--cols", type=int, default=7)
ap.add_argument("--out", default=os.path.join(B.ROOT, "build", "linesheet.jpg"))
a = ap.parse_args()

if a.keys:
    keys = a.keys.split(",")
elif a.sil:
    keys = [f"silhouette/{sh}/{S.SIL_FILLS[i % len(S.SIL_FILLS)]}" for i, sh in enumerate(S.SIL_SHAPES)]
elif a.since:
    keys = [k for k, v in S.CATALOG.items() if v["added"] >= a.since and not (S.is_sil(k) and not k.endswith("/echo"))]
else:
    seen, keys = set(), []
    for k in S.CATALOG:
        if S.family(k).split("/")[0] not in seen:
            seen.add(S.family(k).split("/")[0])
            keys.append(k)
r = random.Random(3)
segs = []
for i, k in enumerate(keys):
    sid = S.CATALOG[k]["scene"]
    white = a.white and i % 2 == 1 and sid in S.LINE_WHITE_OK
    pal = [0, 1, 2, 3, 5, 4][i % 6] if not white else [6, 3, 2][i % 3]
    segs.append({"t0": i, "t1": i + 1, "scene": sid, "lib": "lines", "pal": pal, "prm": S.params(r, k) + [1 if white else 0],
                 "offset": 2.0, "energy": 0.5, "shot": k})
n = len(segs)
plan = {"id": "linesheet", "width": 1080, "height": 1920, "fps": 30, "duration": float(n), "seed": 3, "render": {"sceneScale": 1},
        "song": {"bpm": 152}, "beats": [], "downbeats": [], "audio": {}, "segments": segs, "transitions": [],
        "overlays": [], "post": {"grain": 0.0, "vignette": 0.0, "rgbBase": 0.0, "rgbBeat": 0, "rgbOnset": 0}}
proj = os.path.join(B.ROOT, "build", "projects", "linesheet")
os.makedirs(proj, exist_ok=True)
B.assemble(plan, proj)
out = os.path.join(proj, "snaps")
subprocess.run(["rm", "-rf", out])
res = subprocess.run([B.HF, "snapshot", proj, "--at", ",".join(f"{i + a.at}" for i in range(n)), "--no-end", "-o", out,
                      "--describe", "false", "--timeout", "60000"], env=B.hf_env(), capture_output=True, text=True)
fs = sorted(f for f in os.listdir(out) if f.endswith(".png")) if os.path.isdir(out) else []
if len(fs) != n:
    sys.stderr.write(res.stdout[-3000:] + res.stderr[-3000:])
cols = min(a.cols, n)
cell = (216, 384)
sheet = Image.new("RGB", (cell[0] * cols, cell[1] * ((n + cols - 1) // cols)))
for k, f in enumerate(fs):
    sheet.paste(Image.open(os.path.join(out, f)).convert("RGB").resize(cell), ((k % cols) * cell[0], (k // cols) * cell[1]))
os.makedirs(os.path.dirname(a.out), exist_ok=True)
sheet.save(a.out, quality=88)
print(f"{len(fs)}/{n} cells -> {a.out}")
for i, k in enumerate(keys):
    print(f"  {i + 1:2d}. {k}")

#!/usr/bin/env python3
"""Contact sheet of the line-art scene library (build/linesheet.jpg)."""
import os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build as B
from PIL import Image
D = {0: ([5, 0, 0, 1], 6), 1: ([8, 0.6, 1, 0], 0), 2: ([6, 1, 0, 0], 1), 3: ([0.5, 0, 0, 0], 3), 4: ([0.55, 1.0, 0, 1], 3),
     5: ([0.7, 1.0, 0, 0], 0), 6: ([6, 0.6, 0, 0], 2), 7: ([3, 1, 0, 0], 0), 8: ([0.35, 0, 0, 0], 1), 9: ([5, 0.8, 1, 0], 4),
     10: ([8, 2.5, 0, 0], 2), 11: ([1, 0, 0, 0], 3), 12: ([34, 1, 0, 0], 7)}
SIL = [(13, [sh, fill, 0.9, w], pal) for sh, fill, pal, w in [(0,1,2,0),(1,0,0,0),(2,3,1,0),(3,2,3,0),(4,4,4,0),(5,0,5,1),(6,1,1,0),(7,3,0,0),(8,2,2,0),(9,0,5,0),(10,3,3,0),(0,2,1,0),(1,1,6,1)]] + [(14, [3, 1, 0, 0], 0)]
if "--sil" in sys.argv:
    entries = SIL
else:
    entries = [(s_, D[s_][0], D[s_][1]) for s_ in D]
ids = list(range(len(entries)))
segs = [{"t0": i, "t1": i + 1, "scene": e[0], "lib": "lines", "pal": e[2], "prm": e[1], "offset": 2.0, "energy": 0.5} for i, e in enumerate(entries)]
n = len(ids)
plan = {"id": "linesheet", "width": 1080, "height": 1920, "fps": 30, "duration": float(n), "seed": 3, "render": {"sceneScale": 1},
        "song": {"bpm": 152}, "beats": [], "downbeats": [], "audio": {}, "segments": segs, "transitions": [],
        "overlays": [], "post": {"grain": 0.0, "vignette": 0.0, "rgbBase": 0.0, "rgbBeat": 0, "rgbOnset": 0}}
proj = os.path.join(B.ROOT, "build", "projects", "linesheet"); os.makedirs(proj, exist_ok=True)
B.assemble(plan, proj)
out = os.path.join(proj, "snaps"); subprocess.run(["rm", "-rf", out])
subprocess.run([B.HF, "snapshot", proj, "--at", ",".join(f"{i+0.5}" for i in range(n)), "--no-end", "-o", out, "--describe", "false", "--timeout", "20000"], env=B.hf_env(), capture_output=True)
fs = sorted(f for f in os.listdir(out) if f.endswith(".png"))
cell = (216, 384); sh = Image.new("RGB", (cell[0] * 7, cell[1] * 2))
for k, f in enumerate(fs): sh.paste(Image.open(os.path.join(out, f)).convert("RGB").resize(cell), ((k % 7) * cell[0], (k // 7) * cell[1]))
sh.save(os.path.join(B.ROOT, "build", "linesheet.jpg"), quality=88); print(len(fs))

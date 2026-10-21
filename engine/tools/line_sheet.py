#!/usr/bin/env python3
"""Contact sheet of the line-art scene library (build/linesheet.jpg)."""
import os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build as B
from PIL import Image
D = {0: ([5, 0, 0, 1], 6), 1: ([8, 0.6, 1, 0], 0), 2: ([6, 1, 0, 0], 1), 3: ([0.5, 0, 0, 0], 3), 4: ([0.55, 1.0, 0, 1], 3),
     5: ([0.7, 1.0, 0, 0], 0), 6: ([6, 0.6, 0, 0], 2), 7: ([3, 1, 0, 0], 0), 8: ([0.35, 0, 0, 0], 1), 9: ([5, 0.8, 1, 0], 4),
     10: ([8, 2.5, 0, 0], 2), 11: ([1, 0, 0, 0], 3), 12: ([34, 1, 0, 0], 7)}
ids = list(D)
segs = [{"t0": i, "t1": i + 1, "scene": s, "lib": "lines", "pal": D[s][1], "prm": D[s][0], "offset": 2.0, "energy": 0.5} for i, s in enumerate(ids)]
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

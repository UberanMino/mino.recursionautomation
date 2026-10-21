#!/usr/bin/env python3
"""Render one still per scene (default params) into a contact sheet for visual QA."""
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build as B
from PIL import Image

DEFAULTS = {  # scene: (prm, pal)
    0: ([3, 4, 6, 1], 0), 1: ([36, 0.55, 1, 0], 2), 2: ([4, 1, 1, 0], 3), 3: ([1.4, 1, 6, 0.8], 1),
    4: ([8, 1.5, 1, 0], 5), 5: ([8, 0.9, 0.6, 0], 1), 6: ([1.3, 1, 0.6, 0], 0), 7: ([9, 1, 0, 0], 6),
    8: ([0.8, 0.6, 1, 0], 0), 9: ([1.5, 1, 0, 0], 4), 10: ([22, 1, 0, 0], 2), 11: ([5, 1, 1, 0], 7),
    12: ([0.3, 2.4, 1, 0], 5), 13: ([7, 1, 1, 0], 1), 14: ([0.8, 0.35, 0, 0], 2),
}
ids = [int(x) for x in sys.argv[1].split(",")] if len(sys.argv) > 1 and sys.argv[1] != "all" else list(DEFAULTS)
SCALE = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
SNAP = "--perf" not in sys.argv
T = 3.0
segs = []
for i, sid in enumerate(ids):
    prm, pal = DEFAULTS[sid]
    segs.append({"t0": i * 1.0, "t1": (i + 1) * 1.0, "scene": sid, "pal": pal, "prm": prm, "offset": 2.0, "energy": 0.6})
dur = len(ids) * 1.0
plan = {"id": "scenesheet", "width": 1080, "height": 1920, "fps": 30, "duration": dur, "seed": 7,
        "render": {"sceneScale": SCALE}, "song": {"bpm": 152, "file": "", "start": 0},
        "beats": [i * 60 / 152 for i in range(int(dur * 152 / 60) + 1)], "downbeats": [],
        "audio": {"bass": [0.5] * int(dur * 30 + 1), "onset": [0.3] * int(dur * 30 + 1)},
        "segments": segs, "transitions": [], "overlays": [{"kind": "watermark", "text": "@mino.recursion"}],
        "post": {"grain": 0.03, "vignette": 0.3}}
proj = os.path.join(B.ROOT, "build", "projects", "scenesheet")
os.makedirs(proj, exist_ok=True)
B.assemble(plan, proj)
if not SNAP:
    r = subprocess.run(["node", os.path.join(B.ROOT, "engine", "tools", "perf_page.mjs"), proj, str(len(ids))], capture_output=True, text=True)
    print(r.stdout[-3000:], r.stderr[-2000:])
    sys.exit(0)
at = ",".join(f"{i + 0.5:.2f}" for i in range(len(ids)))
out = os.path.join(proj, "snaps")
r = subprocess.run([B.HF, "snapshot", proj, "--at", at, "--no-end", "-o", out, "--describe", "false"], env=B.hf_env(),
                   capture_output=True, text=True)
print(r.stdout[-1500:], r.stderr[-1500:])
files = sorted([f for f in os.listdir(out) if f.endswith(".png")])
print(files)
cell = (270, 480)
cols = 5
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cell[0] * cols, cell[1] * rows))
for k, f in enumerate(files):
    im = Image.open(os.path.join(out, f)).convert("RGB").resize(cell)
    sheet.paste(im, ((k % cols) * cell[0], (k // cols) * cell[1]))
sheet.save(os.path.join(B.ROOT, "build", "scenesheet.jpg"), quality=88)

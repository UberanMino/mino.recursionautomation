#!/usr/bin/env python3
"""Quick visual QA of a plan without a full render: N snapshots -> build/review/<id>.jpg"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import build as B
from PIL import Image
plan_path = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 8
plan = json.load(open(plan_path))
proj = os.path.join(B.ROOT, "build", "projects", plan["id"])
os.makedirs(proj, exist_ok=True)
B.assemble(plan, proj)
D = plan["duration"]
ts = [round(D * (i + 0.5) / n, 3) for i in range(n)]
out = os.path.join(proj, "snaps")
subprocess.run(["rm", "-rf", out])
r = subprocess.run([B.HF, "snapshot", proj, "--at", ",".join(map(str, ts)), "--no-end", "-o", out, "--describe", "false", "--timeout", "20000"],
                   env=B.hf_env(), capture_output=True, text=True)
files = sorted(f for f in os.listdir(out) if f.endswith(".png"))
cell = (216, 384)
sheet = Image.new("RGB", (cell[0] * min(n, 8), cell[1] * ((len(files) + 7) // 8)))
for k, f in enumerate(files):
    sheet.paste(Image.open(os.path.join(out, f)).convert("RGB").resize(cell), ((k % 8) * cell[0], (k // 8) * cell[1]))
dst = os.path.join(B.ROOT, "build", "review", plan["id"] + ".jpg")
os.makedirs(os.path.dirname(dst), exist_ok=True)
sheet.save(dst, quality=85)
print(dst, ts)

#!/usr/bin/env python3
"""Assemble a HyperFrames project from an edit plan, render it, mux the song.

  python3 engine/build.py build/plans/<id>.json            # -> build/out/<id>.mp4
  python3 engine/build.py plan.json --quality draft --no-audio
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(ROOT, "engine")
HF = os.path.join(ROOT, "node_modules", ".bin", "hyperframes")
HEADLESS = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"


def hf_env():
    env = dict(os.environ)
    env.update({"DO_NOT_TRACK": "1", "HYPERFRAMES_NO_TELEMETRY": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
                "HYPERFRAMES_SKIP_SKILLS": "1", "HYPERFRAMES_RENDER_DETACHED": "1"})
    if os.path.exists(HEADLESS) and "HYPERFRAMES_BROWSER_PATH" not in env:
        env["HYPERFRAMES_BROWSER_PATH"] = HEADLESS
    return env


def assemble(plan, project_dir):
    os.makedirs(os.path.join(project_dir, "fonts"), exist_ok=True)
    for f in os.listdir(os.path.join(ROOT, "assets", "fonts")):
        if f.endswith(".woff2"):
            shutil.copy(os.path.join(ROOT, "assets", "fonts", f), os.path.join(project_dir, "fonts", f))
    shutil.copy(os.path.join(ENGINE, "vendor", "gsap.min.js"), project_dir)
    html = open(os.path.join(ENGINE, "template.html")).read()
    scenes = open(os.path.join(ENGINE, "shaders", "scenes.glsl")).read()
    comp = open(os.path.join(ENGINE, "shaders", "composite.glsl")).read()
    html = (html.replace("__TITLE__", plan.get("id", "mino.recursion"))
            .replace("__DURATION__", f"{plan['duration']:.3f}")
            .replace("__PLAN_JSON__", json.dumps(plan, separators=(",", ":")))
            .replace("__SCENES_GLSL__", json.dumps(scenes))
            .replace("__COMPOSITE_GLSL__", json.dumps(comp))
            .replace("__RUNTIME_JS__", open(os.path.join(ENGINE, "runtime.js")).read()))
    with open(os.path.join(project_dir, "index.html"), "w") as f:
        f.write(html)
    with open(os.path.join(project_dir, "meta.json"), "w") as f:
        json.dump({"id": plan.get("id", "mr"), "name": plan.get("id", "mr")}, f)


def render(project_dir, out_mp4, quality="looks", workers="auto"):
    cmd = [HF, "render", project_dir, "-o", out_mp4, "-q", quality, "-w", str(workers), "--quiet"]
    r = subprocess.run(cmd, env=hf_env(), capture_output=True, text=True, cwd=project_dir)
    if r.returncode != 0 or not os.path.exists(out_mp4):
        sys.stderr.write(r.stdout[-4000:] + "\n" + r.stderr[-4000:])
        raise SystemExit(f"render failed for {project_dir}")
    return out_mp4


def mux(silent_mp4, plan, out_mp4):
    """Final Instagram-safe encode: H.264 high, yuv420p, 30fps, <=5 Mbps, AAC 48k stereo, faststart."""
    song = plan["song"]
    dur = plan["duration"]
    fade = min(0.25, dur * 0.05)
    afilter = f"atrim=start={song['start']:.4f}:duration={dur:.4f},asetpts=PTS-STARTPTS," \
              f"afade=t=in:st=0:d=0.02,afade=t=out:st={dur - fade:.4f}:d={fade:.4f},loudnorm=I=-11:TP=-1.0:LRA=9"
    cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", silent_mp4, "-i", os.path.join(ROOT, song["file"]),
           "-filter_complex", f"[1:a]{afilter},aresample=48000[a]", "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-pix_fmt", "yuv420p", "-r", "30",
           "-b:v", "4.6M", "-maxrate", "5M", "-bufsize", "9M", "-g", "60", "-bf", "2",
           "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
           "-t", f"{dur:.4f}", "-movflags", "+faststart", out_mp4]
    subprocess.run(cmd, check=True)
    return out_mp4


def build(plan_path, quality="looks", audio=True, workers="auto"):
    plan = json.load(open(plan_path))
    pid = plan["id"]
    proj = os.path.join(ROOT, "build", "projects", pid)
    os.makedirs(proj, exist_ok=True)
    assemble(plan, proj)
    os.makedirs(os.path.join(ROOT, "build", "out"), exist_ok=True)
    silent = os.path.join(proj, "silent.mp4")
    render(proj, silent, quality, workers)
    final = os.path.join(ROOT, "build", "out", f"{pid}.mp4")
    if audio:
        mux(silent, plan, final)
    else:
        shutil.copy(silent, final)
    return final


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("plan")
    ap.add_argument("--quality", default="looks")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--workers", default="auto")
    a = ap.parse_args()
    print(build(a.plan, a.quality, not a.no_audio, a.workers))

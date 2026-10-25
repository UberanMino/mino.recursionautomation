#!/usr/bin/env python3
"""Daily content run: plan -> render -> upload -> queue, for one calendar day (Europe/Berlin).

  python3 engine/daily.py --date 2026-10-22            # 7 posts at the default slots
  python3 engine/daily.py --date 2026-10-22 --count 8
  python3 engine/daily.py --now --count 1 --format drop  # render one and queue it for immediate posting
  python3 engine/daily.py --date 2026-10-22 --dry-run    # only print the schedule

State lives in build/daily/<date>.json so an interrupted run resumes where it stopped.
"""
import argparse
import datetime as dt
import json
import os
import random
import re
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B  # noqa: E402
import plan as P  # noqa: E402
import publish as PUB  # noqa: E402
import shots as S  # noqa: E402

ROOT = B.ROOT
TZ = ZoneInfo("Europe/Berlin")
SLOTS = ["07:40", "10:15", "12:40", "15:10", "17:45", "19:50", "21:40", "23:05"]
# weighted rotation; "drop" is the core format, the others keep the feed from feeling samey
# the channel runs the minimal neon line-art format; the older formats stay available via --format
FORMATS = ["line"] * 8


def norm(name):
    return re.sub(r"(final|master|stereo|\d+|\.wav$|\.mp3$|[^a-z])", "", name.lower())


def available_songs():
    songs = json.load(open(os.path.join(ROOT, "engine", "songs.json")))
    have = []
    remote = None
    for key, s in songs.items():
        local = os.path.join(ROOT, s["file"])
        if not os.path.exists(local):
            if remote is None:
                try:
                    remote = set(PUB.listdir("/mino.recursion/songs"))
                except Exception as e:  # noqa: BLE001
                    print("warn: cannot list Dropbox songs:", e)
                    remote = set()
            # accept the original master file names, e.g. "My mind master.wav" -> my_mind
            match = [n for n in remote if norm(n) == norm(key)]
            if match:
                print("downloading", match[0])
                PUB.download(f"/mino.recursion/songs/{match[0]}", local)
        if os.path.exists(local):
            an = os.path.join(ROOT, "build", "analysis", f"{key}.json")
            if not os.path.exists(an):
                os.makedirs(os.path.dirname(an), exist_ok=True)
                subprocess.run([sys.executable, os.path.join(ROOT, "engine", "analyze_audio.py"), local, an], check=True)
            have.append(key)
    return have


def schedule(day, count, songs, fmt=None):
    r = random.Random(day.toordinal())
    fmts = FORMATS[:count] if count <= len(FORMATS) else (FORMATS * 2)[:count]
    r.shuffle(fmts)
    if fmt:
        fmts = [fmt] * count
    slots = SLOTS[:count] if count <= 7 else SLOTS[:count]
    out = []
    for i in range(count):
        hh, mm = map(int, slots[i % len(slots)].split(":"))
        when = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=TZ) + dt.timedelta(minutes=r.randint(-6, 6))
        song = songs[(day.toordinal() + i) % len(songs)]
        seed = (day.toordinal() % 10000) * 10 + i
        out.append({"slot": i, "due": when.isoformat(), "due_ts": int(when.timestamp()), "format": fmts[i], "song": song, "seed": seed})
    return out


def run(day, count, dry=False, now=False, fmt=None, quality="looks"):
    songs = available_songs()
    if not songs:
        raise SystemExit("no songs available locally or in Dropbox /mino.recursion/songs")
    state_path = os.path.join(ROOT, "build", "daily", f"{day.isoformat()}{'-now' if now else ''}.json")
    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    state = json.load(open(state_path)) if os.path.exists(state_path) else {"day": day.isoformat(), "items": schedule(day, count, songs, fmt)}
    if now:
        for it in state["items"]:
            it["due_ts"] = int(time.time()) - 60
    json.dump(state, open(state_path, "w"), indent=1)
    for it in state["items"]:
        print(f"[{it['slot']}] {it['due']}  {it['format']:6s} {it['song']:15s} seed {it['seed']}  status={it.get('status', 'todo')}")
    if dry:
        return state
    hist = S.load_history()
    for it in state["items"]:
        if it.get("status") == "queued":
            continue
        t0 = time.time()
        plan = P.Director(it["song"], it["format"], it["seed"], history=hist).build()
        # shot memory: the next reel already knows what this one used (commit engine/shot_history.json after the run)
        S.record(hist, plan, day.isoformat())
        S.save_history(hist)
        plan_path = os.path.join(ROOT, "build", "plans", plan["id"] + ".json")
        os.makedirs(os.path.dirname(plan_path), exist_ok=True)
        json.dump(plan, open(plan_path, "w"), indent=1)
        mp4 = B.build(plan_path, quality=quality, workers=4)
        remote = f"/mino.recursion/queue/{day.isoformat()}/{plan['id']}.mp4"
        PUB.upload(mp4, remote)
        thumb = {"stare": 800, "line": 300}.get(plan["format"], 600)
        title = plan["hook"].title() or f"mino.recursion — {plan['song']['title']}"
        PUB.enqueue(plan["id"], it["due_ts"], plan["id"], remote, plan["caption"], title, thumb)
        it.update({"status": "queued", "id": plan["id"], "dropbox": remote, "hook": plan["hook"], "caption": plan["caption"],
                   "render_s": round(time.time() - t0, 1)})
        json.dump(state, open(state_path, "w"), indent=1)
        print(f"queued {plan['id']} for {it['due']} ({it['render_s']}s)")
    return state


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (Europe/Berlin), default: tomorrow")
    ap.add_argument("--count", type=int, default=7)
    ap.add_argument("--format", choices=["drop", "stare", "error", "eyes", "words", "line"])
    ap.add_argument("--now", action="store_true", help="queue for immediate posting")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quality", default="looks")
    a = ap.parse_args()
    day = dt.date.fromisoformat(a.date) if a.date else (dt.datetime.now(TZ) + dt.timedelta(days=1)).date()
    run(day, a.count, a.dry_run, a.now, a.format, a.quality)

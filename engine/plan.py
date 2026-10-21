#!/usr/bin/env python3
"""Creative director: turns (song analysis, format, seed) into an edit plan JSON + post caption.

  python3 engine/plan.py --song not_just_music --format drop --seed 11
  -> build/plans/<id>.json  (render with engine/build.py)

Formats
  drop    "recursion drop": 1 bar of build-up, then beat-cut chaos for 7 bars, loops seamlessly
  stare   motion-aftereffect illusion: stare at an expanding spiral, the drop freezes the frame
          and the still image keeps moving in the viewer's eyes ("now look at your hand")
  error   reality.exe: Win98 error popups pile up on every beat until the drop shatters them
  eyes    eye recursion loop: every cut goes through a pupil into the next eye
  words   the song title hits one word per beat over the drop
"""
import argparse
import json
import math
import os
import random
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# scene id -> (name, param sampler, palettes, family)
SCENES = {
    0: ("spiral", lambda r: [r.choice([2, 3, 4, 5]), r.uniform(1.2, 2.6), r.choice([6, 8, 10, 12]), r.uniform(0.3, 1.4)], [0, 1, 5, 7, 4], "hypno"),
    1: ("opradial", lambda r: [r.choice([24, 32, 40, 48]), r.choice([0.0, 0.45, 0.55, 0.65]), r.choice([0, 1]), 0], [2, 6, 3], "eye"),
    2: ("eyes", lambda r: [r.uniform(3.0, 5.5), r.uniform(0.4, 1.4), r.uniform(0, 1), 0], [3, 1, 7, 0], "eye"),
    3: ("liquid", lambda r: [r.uniform(1.0, 2.0), r.uniform(0.6, 1.6), r.uniform(3, 9), r.uniform(0, 1)], [1, 5, 0, 4, 7], "color"),
    4: ("tunnel", lambda r: [r.choice([6, 8, 10, 12]), r.uniform(0.8, 2.0), r.uniform(0, 1.5), r.choice([0, 0, 1])], [5, 1, 7, 0, 2], "motion"),
    5: ("kaleido", lambda r: [r.choice([6, 8, 10, 12]), r.uniform(0.75, 1.0), r.uniform(0.4, 0.8), 0], [1, 5, 4, 0], "color"),
    6: ("julia", lambda r: [r.uniform(0.6, 0.95), r.uniform(0.6, 1.5), r.uniform(0.5, 1.0), 0], [0, 1, 5, 7], "color"),
    7: ("rings", lambda r: [r.uniform(6, 12), r.uniform(0.5, 1.5), 0, 0], [6, 2, 3, 1], "hypno"),
    8: ("smiley", lambda r: [r.uniform(0.65, 0.95), r.uniform(0.2, 1.0), r.uniform(0.6, 1.5), 0], [0, 1, 7, 3], "wtf"),
    9: ("warp", lambda r: [r.uniform(1.0, 2.5), r.uniform(0.6, 1.5), 0, 0], [4, 1, 5], "motion"),
    10: ("moire", lambda r: [r.uniform(14, 26), r.choice([0, 1]), 0, 0], [2, 7, 6, 3], "hypno"),
    11: ("truchet", lambda r: [r.uniform(3, 7), r.uniform(0.5, 1.5), r.uniform(0, 1), 0], [7, 1, 0, 2], "motion"),
    12: ("droste", lambda r: [r.uniform(0.15, 0.5), r.uniform(1.8, 3.0), r.uniform(0.6, 1.5), 0], [5, 0, 1, 7], "hypno"),
    13: ("melt", lambda r: [r.uniform(2, 5), r.uniform(0.4, 1.2), r.uniform(0.6, 1.5), 0], [1, 5, 0, 4], "color"),
    14: ("bigeye", lambda r: [r.uniform(0.7, 0.95), r.uniform(0.25, 0.5), 0, 0], [2, 6, 3], "eye"),
}
# minimal line-art library (engine/shaders/lines.glsl): one accent colour, black or off-white ground
LINE_SCENES = {
    0: ("weave", lambda r: [r.uniform(6, 9), 0, 0]),
    1: ("wiretunnel", lambda r: [r.uniform(14, 24), r.uniform(0.5, 1.0), r.choice([0, 1])]),
    2: ("wireroom", lambda r: [r.choice([6, 8, 10]), r.uniform(0.6, 1.2), 0]),
    3: ("tesseract", lambda r: [r.uniform(0.8, 1.05), 0, 0]),
    4: ("stripesphere", lambda r: [r.uniform(0.45, 0.65), r.uniform(0.8, 1.4), 0]),
    5: ("dashsphere", lambda r: [r.uniform(0.6, 0.8), r.uniform(1.6, 2.4), 0]),
    6: ("wormhole", lambda r: [r.uniform(9, 13), r.uniform(0.4, 0.9), 0]),
    7: ("isocubes", lambda r: [r.uniform(2.5, 4.0), r.uniform(0.6, 1.4), 0]),
    8: ("burst", lambda r: [r.uniform(0.28, 0.4), 0, 0]),
    9: ("dots", lambda r: [r.uniform(4, 6), r.uniform(0.6, 1.0), r.choice([0, 1])]),
    10: ("zigzag", lambda r: [r.choice([6, 8, 10]), r.uniform(2.0, 3.0), 0]),
    11: ("lasers", lambda r: [r.uniform(0.8, 1.3), 0, 0]),
    12: ("ridges", lambda r: [r.choice([28, 34, 40]), r.uniform(0.8, 1.3), 0]),
    13: ("silhouette", lambda r: [r.randint(0, 10), r.randint(0, 4), r.uniform(1.0, 1.35)]),
    14: ("cubes", lambda r: [r.choice([2, 2.5, 3]), r.uniform(0.5, 1.2), 0]),
}
LINE_WHITE_OK = {0, 4, 6, 7, 9, 10, 3, 8, 13, 14}   # scenes that also read well on off-white
TRANS = {"cut": 0, "zoom": 1, "iris": 2, "glitch": 3, "swirl": 4, "kaleido": 5, "melt": 6, "pixel": 7, "slit": 8, "liquid": 9}
PAL_RGB = {0: [1.0, 0.8, 0.0], 1: [1.0, 0.15, 0.8], 2: [0.96, 0.92, 0.82], 3: [0.88, 0.06, 0.16],
           4: [0.45, 0.76, 1.0], 5: [0.6, 1.0, 0.2], 6: [0.96, 0.55, 0.42], 7: [0.2, 1.0, 0.35]}

STYLES = {
    "impact": {"font": "Anton", "size": 190, "color": "#ffffff", "stroke": "#000000", "extrude": 10,
               "extrudeColors": ["#000000", "#7a00cc", "#ffc400"]},
    "acid": {"font": "Shrikhand", "size": 150, "gradient": ["#ff2bd6", "#ffe600", "#00e5ff", "#b6ff00"], "stroke": "#000000",
             "extrude": 9, "extrudeColors": ["#000000", "#2b00ff"]},
    "mono": {"font": "Rubik Mono One", "size": 120, "color": "#ffe600", "stroke": "#000000", "extrude": 7,
             "extrudeColors": ["#000000", "#ff2bd6"]},
    "neon": {"font": "Monoton", "size": 140, "color": "#ff7af0", "stroke": "#14001f", "strokeW": 10, "extrude": 0},
    "terminal": {"font": "VT323", "size": 120, "color": "#39ff6a", "stroke": "#000000", "extrude": 4,
                 "extrudeColors": ["#003b12"]},
    "caption": {"font": "Anton", "size": 78, "color": "#ffffff", "stroke": "#000000", "strokeW": 9, "extrude": 0},
}

HOOKS = {
    "drop": ["DON'T BLINK", "WAIT FOR\nTHE DROP", "YOUR BRAIN\nAT {bpm} BPM", "DO NOT\nWATCH TWICE",
             "THIS IS YOUR\nDOPAMINE", "WHAT DID\nI JUST SEE", "REALITY\nIS OPTIONAL", "3 AM\nBRAIN", "RECURSION\nLEVEL 99"],
    "stare": ["STARE AT\nTHE DOT"],
    "error": ["reality.exe", "SYSTEM\nOVERLOAD", "BRAIN.EXE"],
    "eyes": ["IT SEES YOU", "DON'T LOOK\nBACK", "WHO IS\nWATCHING WHO", "OPEN YOUR\nTHIRD EYE"],
    "words": [],
}
CAPTION_LINES = {
    "drop": ["(the bass is coming)", "(volume up)", "(you were warned)", "(loop it)", "(it gets worse)"],
    "eyes": ["(it blinked first)", "(look closer)", "(they multiply)"],
}
POPUP_TITLES = ["reality.exe", "brain.exe", "ego.sys", "perception.dll", "bass_driver.exe", "mind.exe"]
POPUP_MSGS = ["reality.exe has stopped responding", "Too much bass detected. Continue?", "ego.sys could not be found",
              "perception.dll is corrupted", "Your third eye needs an update", "Cannot close: you are the window",
              "Error 999: sanity not found", "Recursion depth exceeded", "The walls are breathing (again)"]

CAPTION_HOOKS = {
    "drop": ["Turn the volume up and don't blink.", "Your brain on {bpm} BPM.", "Watched it once. Watched it again. Still don't know what happened.",
             "This loop has no exit.", "Recursion level: unhealthy.", "Somewhere between a dream and a bass drop."],
    "stare": ["Stare at the dot until the drop. Then look at your hand. 👁", "Illusion: the last frame is NOT moving. Your brain is.",
              "Don't look away before the drop."],
    "error": ["reality.exe has stopped responding.", "Ctrl+Alt+Delete won't save you this time.", "Too much bass detected. Continue? [YES]"],
    "eyes": ["Who is watching who?", "Every pupil is a door.", "It blinked first."],
    "words": ["{title}. Say less.", "It's not just music.", "Read it on the beat."],
    "line": ["Sound on.", "Lines, loops and {bpm} BPM.", "Recursion, frame by frame."],
}
CAPTION_ASKS = {
    "drop": ["Rate this trip 1–10 👇", "What did you see first?", "How many times did you loop it?"],
    "stare": ["Did it move for you? 👇", "How long did the effect last for you?"],
    "error": ["Which error did your brain throw?", "Did you click OK?"],
    "eyes": ["How many eyes did you count?", "Did it blink at you too?"],
    "words": ["Did you read it on the beat?", "Say it with the drop."],
    "line": ["Which frame got you?", "Loop count?"],
}
BASE_TAGS = ["#psychedelic", "#trippy", "#opticalillusion", "#visualart", "#rave", "#edm", "#hypnotic", "#trance",
             "#acidart", "#loop", "#mindbending", "#abstractart"]


def load(path):
    with open(path) as f:
        return json.load(f)


def rel(times, t0, t1):
    return [round(t - t0, 4) for t in times if t0 - 1e-6 <= t < t1 - 1e-6]


class Director:
    def __init__(self, song_key, fmt, seed):
        self.songs = load(os.path.join(ROOT, "engine", "songs.json"))
        self.key = song_key
        self.song = self.songs[song_key]
        self.an = load(os.path.join(ROOT, "build", "analysis", f"{song_key}.json"))
        self.fmt = fmt
        self.seed = seed
        self.r = random.Random(seed * 7919 + zlib.crc32(f"{song_key}/{fmt}".encode()))
        self.bpm = self.an["bpm"]
        self.bar = 4 * 60.0 / self.bpm
        self.used_scenes = []

    # ----- helpers -----
    def pick_window(self, pre_bars, total_bars):
        """Start `pre_bars` before a drop; prefer drops not used recently (seed rotates through them)."""
        drops = self.an["drops"] or [{"t": self.an["downbeats"][min(8, len(self.an["downbeats"]) - 1)], "bar": 8, "score": 0}]
        drops = sorted(drops, key=lambda d: d["t"])
        d = drops[self.seed % len(drops)]
        bars = self.an["bars"]
        bi = next((i for i, b in enumerate(bars) if abs(b["t"] - d["t"]) < 0.05), d.get("bar", 8))
        start_i = max(0, bi - pre_bars)
        end_i = min(len(bars) - 1, start_i + total_bars)
        start = bars[start_i]["t"]
        end = bars[end_i]["t"] if end_i > start_i else start + total_bars * self.bar
        return start, end, bars[bi]["t"], start_i

    def energy_at(self, t_abs):
        bars = self.an["bars"]
        e = 0.6
        for b in bars:
            if b["t"] <= t_abs + 1e-3:
                e = b.get("energy_n", 0.6)
        return round(e, 3)

    def new_scene(self, allowed=None, avoid_family=None):
        pool = [s for s in (allowed or SCENES) if s not in self.used_scenes[-3:]]
        if avoid_family:
            pool2 = [s for s in pool if SCENES[s][3] != avoid_family]
            pool = pool2 or pool
        sid = self.r.choice(pool)
        self.used_scenes.append(sid)
        return sid

    def segment(self, sid, t0, t1, start_abs, pal_avoid=None, **kw):
        name, sampler, pals, fam = SCENES[sid]
        pals2 = [p for p in pals if p != pal_avoid] or pals
        seg = {"t0": round(t0, 4), "t1": round(t1, 4), "scene": sid, "name": name, "pal": self.r.choice(pals2),
               "prm": [round(x, 4) for x in sampler(self.r)], "offset": round(self.r.uniform(0, 20), 3),
               "speed": round(self.r.uniform(0.85, 1.25), 3), "zoom": round(self.r.uniform(0.85, 1.2), 3),
               "rot": round(self.r.uniform(-0.4, 0.4), 3), "spin": round(self.r.choice([0, 0, self.r.uniform(-0.25, 0.25)]), 3),
               "zoomPulse": round(self.r.uniform(0.04, 0.12), 3), "mirror": self.r.choice([0] * 8 + [1, 3]),
               "energy": self.energy_at(start_abs + t0), "seed": round(self.r.uniform(0, 10), 3)}
        seg.update(kw)
        return seg

    def base_plan(self, start, end):
        dur = round(end - start, 4)
        fr = self.an["frames"]
        f0, f1 = int(round(start * fr["fps"])), int(round(end * fr["fps"])) + 2
        audio = {k: fr[k][f0:f1] for k in ("bass", "onset", "high", "rms", "kick")}
        return {
            "id": f"{self.key}-{self.fmt}-{self.seed:03d}",
            "format": self.fmt, "width": 1080, "height": 1920, "fps": 30, "duration": dur, "seed": self.seed,
            "render": {"sceneScale": 0.75},
            "song": {"key": self.key, "title": self.song["title"], "file": self.song["file"], "start": round(start, 4), "bpm": self.bpm},
            "beats": rel(self.an["beats"], start, end), "downbeats": rel(self.an["downbeats"], start, end),
            "audio": audio, "segments": [], "transitions": [],
            "overlays": [{"kind": "watermark", "text": "@mino.recursion", "y": 0.128, "size": 44, "alpha": 0.92},
                         {"kind": "watermark", "text": f"~ {self.song['title'].lower()} ~", "y": 0.152, "size": 34, "alpha": 0.8}],
            "post": {"punch": 0.05, "punchDecay": 9, "rgbBase": 0.0015, "rgbBeat": 0.008, "rgbOnset": 0.004, "shake": 0.02,
                     "grain": 0.035, "scan": self.r.choice([0, 0, 0.5]), "vignette": 0.35, "hueSpeed": 0,
                     "barrel": self.r.choice([0, 0.04, 0.08]), "inverts": [], "flashes": [], "glitches": [], "pixelate": [],
                     "overlayFx": 0.2},
        }

    def close_loop(self, plan):
        """Make the last segment continue into frame 0: same look, time arriving exactly at the opening state."""
        segs = plan["segments"]
        first, last = segs[0], segs[-1]
        L = plan["duration"] - last["t0"]
        clone = {k: v for k, v in first.items() if k not in ("t0", "t1")}
        clone["offset"] = round(first["offset"] - L * first["speed"], 4)
        last.update(clone)
        last["t1"] = plan["duration"]

    def flash(self, plan, t, amt=0.45, dur=0.12, pal=None):
        plan["post"]["flashes"].append({"t": round(t, 4), "dur": dur, "amt": amt, "color": PAL_RGB.get(pal, [1, 1, 1])})

    def beat_cuts(self, plan, t0, t1, every, trans_pool, scene_pool=None, start_abs=0.0):
        """Cut on every `every` beats between t0..t1 (relative)."""
        beats = [b for b in plan["beats"] if t0 - 1e-4 <= b < t1 - 1e-4]
        cuts = beats[::every]
        segs = plan["segments"]
        for i, c in enumerate(cuts):
            if i == 0 and abs(c - t0) < 1e-3 and segs and abs(segs[-1]["t0"] - c) < 1e-3:
                continue
            prev = segs[-1] if segs else None
            sid = self.new_scene(scene_pool, prev and SCENES[prev["scene"]][3])
            nxt = cuts[i + 1] if i + 1 < len(cuts) else t1
            if prev:
                prev["t1"] = round(c, 4)
            segs.append(self.segment(sid, c, nxt, start_abs, pal_avoid=prev and prev["pal"]))
            # on single-beat cuts most changes are hard cuts; a transition never eats more than ~35% of a shot
            tname = "cut" if (every == 1 and self.r.random() < 0.5) else self.r.choice(trans_pool)
            dur = {"cut": 0.07, "glitch": 0.22, "zoom": 0.3, "iris": 0.32, "swirl": 0.3, "kaleido": 0.3, "melt": 0.32,
                   "pixel": 0.24, "slit": 0.26, "liquid": 0.3}[tname]
            shot = 60.0 / self.bpm * every
            dur = round(min(dur, 0.35 * shot), 3) if tname != "cut" else dur
            if prev:
                plan["transitions"].append({"t": round(c, 4), "dur": dur, "type": TRANS[tname], "name": tname})
                if tname == "glitch":
                    plan["post"]["glitches"].append([round(c - dur / 2, 4), round(c + dur / 2, 4), 0.7])

    def hook_overlay(self, text, t0, t1, style=None, anim="punch", y=0.40, glitch=0.15, bounce=0.06):
        return {"kind": "hook", "text": text, "t0": round(t0, 4), "t1": round(t1, 4), "style": STYLES[style or self.r.choice(["impact", "acid", "mono"])],
                "anim": anim, "y": y, "glitch": glitch, "beatBounce": bounce, "tilt": round(self.r.uniform(-4, 4), 2)}

    # ----- formats -----
    def fmt_drop(self):
        start, end, drop, _ = self.pick_window(1, 8)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        dr = round(drop - start, 4)
        # build-up bar: one hypnotic scene accelerating
        sid = self.new_scene([0, 7, 10, 12, 1, 14])
        plan["segments"].append(self.segment(sid, 0, dr, start, speed=1.6, zoomPulse=0.1))
        hook = self.r.choice(HOOKS["drop"]).format(bpm=int(round(self.bpm)))
        plan["overlays"].append(self.hook_overlay(hook, 0, dr, glitch=0.2))
        # the drop: invert flash, then beat cuts
        plan["post"]["inverts"].append([dr, round(dr + 2 / 30, 4)])
        every = self.r.choice([1, 1, 2])
        pool = self.r.choice([["cut", "glitch", "zoom", "slit"], ["zoom", "iris", "swirl", "cut"], ["glitch", "pixel", "kaleido", "cut", "melt"],
                              ["liquid", "swirl", "zoom", "glitch"]])
        self.beat_cuts(plan, dr, D - self.bar * 0.5, every, pool, start_abs=start)
        # final half bar returns to the opening scene -> seamless loop
        last_cut = D - self.bar * 0.5
        plan["segments"][-1]["t1"] = round(last_cut, 4)
        plan["segments"].append(dict(plan["segments"][0], t0=round(last_cut, 4), t1=D))
        plan["transitions"].append({"t": round(last_cut, 4), "dur": 0.3, "type": TRANS["zoom"], "name": "zoom"})
        self.close_loop(plan)
        # tinted flashes on downbeats after the drop (<= 1 per bar: photosensitivity-safe)
        for db in plan["downbeats"]:
            if dr <= db < D - 0.5:
                self.flash(plan, db, amt=0.35, pal=self.r.choice(list(PAL_RGB)))
        # mid-drop WTF moment
        mid = dr + 4 * self.bar
        wtf = self.r.choice(["popups", "words", "caption"])
        if wtf == "popups":
            times = [b for b in plan["beats"] if mid <= b < mid + self.bar]
            plan["overlays"].append({"kind": "popups", "t0": round(mid, 4), "t1": round(mid + self.bar, 4), "times": times,
                                     "titles": self.r.sample(POPUP_TITLES, 4), "msgs": self.r.sample(POPUP_MSGS, 4)})
        elif wtf == "words":
            times = [b for b in plan["beats"] if mid <= b < mid + self.bar]
            words = self.song["words"][:len(times)] or ["WHAT"]
            st = dict(STYLES[self.r.choice(["impact", "mono", "acid"])])
            st["size"] = 300
            plan["overlays"].append({"kind": "words", "t0": round(mid, 4), "t1": round(mid + self.bar, 4), "times": times,
                                     "words": words, "style": st, "glitch": True, "y": 0.45, "maxW": 0.92})
        else:
            plan["overlays"].append({"kind": "caption", "text": self.r.choice(CAPTION_LINES["drop"]), "t0": round(dr, 4),
                                     "t1": round(dr + 2 * self.bar, 4), "style": STYLES["caption"], "anim": "rise", "y": 0.62})
        plan["post"]["shake"] = 0.025
        return plan, hook

    def fmt_stare(self):
        start, end, drop, _ = self.pick_window(6, 9)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        dr = round(drop - start, 4)
        # adaptation phase: expanding spiral, no cuts, no camera fx
        prm = [self.r.choice([3, 4]), 2.0, 8, 0.0]
        plan["segments"].append(self.segment(0, 0, dr, start, prm=prm, pal=self.r.choice([0, 7, 2]), speed=1.0, zoom=1.0, rot=0, spin=0,
                                             zoomPulse=0.0, mirror=0, energy=0.2))
        plan["overlays"].append(self.hook_overlay("STARE AT\nTHE DOT", 0, 2.2, style="impact", glitch=0.0, bounce=0.0, y=0.30))
        plan["overlays"].append({"kind": "countdown", "t0": 2.2, "t1": dr, "from": math.floor(dr - 2.2), "y": 0.27,
                                 "style": dict(STYLES["impact"], size=200)})
        plan["overlays"].append({"kind": "dot", "t0": 0, "t1": dr, "r": 22, "color": "#ff2bd6"})
        # reveal: a frozen frame that keeps "moving" (motion aftereffect)
        still_scene = self.r.choice([10, 2, 11, 7, 1])
        plan["segments"][-1]["t1"] = dr
        plan["segments"].append(self.segment(still_scene, dr, D, start, still=True, speed=0, offset=0.0, spin=0, zoomPulse=0, mirror=0))
        plan["transitions"].append({"t": dr, "dur": 0.07, "type": TRANS["cut"], "name": "cut"})
        plan["overlays"].append(self.hook_overlay(self.r.choice(["NOW LOOK AT\nYOUR HAND", "IT'S NOT\nMOVING", "WHY IS IT\nMOVING?"]),
                                                  dr + 0.2, D, style="impact", glitch=0.0, bounce=0.0, y=0.33))
        p = plan["post"]
        p.update({"punch": 0.0, "shake": 0.0, "rgbBeat": 0.0, "rgbOnset": 0.0, "rgbBase": 0.001, "barrel": 0.0, "scan": 0, "grain": 0.02})
        return plan, "STARE AT THE DOT"

    def fmt_error(self):
        start, end, drop, _ = self.pick_window(4, 9)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        dr = round(drop - start, 4)
        sid = self.new_scene([3, 5, 9, 4, 13])
        plan["segments"].append(self.segment(sid, 0, dr, start))
        times = [b for b in plan["beats"] if 0.6 <= b < dr - 0.05][::1]
        plan["overlays"].append({"kind": "progress", "t0": 0, "t1": 1.8, "from": 0.0, "to": 0.99, "y": 0.36,
                                 "title": "consciousness.exe", "text": "loading consciousness..."})
        plan["overlays"].append({"kind": "popups", "t0": 1.8, "t1": dr, "times": [t for t in times if t >= 1.8],
                                 "titles": self.r.sample(POPUP_TITLES, 5), "msgs": self.r.sample(POPUP_MSGS, 6)})
        plan["post"]["glitches"].append([round(dr - 0.2, 4), round(dr + 0.08, 4), 1.0])
        plan["post"]["inverts"].append([dr, round(dr + 2 / 30, 4)])
        self.beat_cuts(plan, dr, D - self.bar * 0.5, self.r.choice([1, 2]), ["glitch", "pixel", "slit", "cut"], start_abs=start)
        last_cut = D - self.bar * 0.5
        plan["segments"][-1]["t1"] = round(last_cut, 4)
        plan["segments"].append(dict(plan["segments"][0], t0=round(last_cut, 4), t1=D))
        plan["transitions"].append({"t": round(last_cut, 4), "dur": 0.22, "type": TRANS["glitch"], "name": "glitch"})
        self.close_loop(plan)
        plan["overlays"].append(self.hook_overlay(self.r.choice(["CTRL+ALT+\nDELETE", "FATAL\nERROR", "TOO MUCH\nBASS"]), dr, dr + self.bar,
                                                  style="terminal", glitch=0.5))
        plan["post"]["scan"] = 0.6
        return plan, "reality.exe"

    def fmt_eyes(self):
        start, end, drop, _ = self.pick_window(1, 6)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        dr = round(drop - start, 4)
        plan["segments"].append(self.segment(14, 0, dr, start, pal=2))
        hook = self.r.choice(HOOKS["eyes"])
        plan["overlays"].append(self.hook_overlay(hook, 0, dr, style=self.r.choice(["impact", "acid"])))
        plan["post"]["inverts"].append([dr, round(dr + 2 / 30, 4)])
        self.beat_cuts(plan, dr, D - self.bar * 0.5, 2, ["iris", "iris", "zoom"], scene_pool=[1, 2, 14, 12, 0, 8], start_abs=start)
        last_cut = D - self.bar * 0.5
        plan["segments"][-1]["t1"] = round(last_cut, 4)
        plan["segments"].append(dict(plan["segments"][0], t0=round(last_cut, 4), t1=D))
        plan["transitions"].append({"t": round(last_cut, 4), "dur": 0.32, "type": TRANS["iris"], "name": "iris"})
        self.close_loop(plan)
        plan["overlays"].append({"kind": "caption", "text": self.r.choice(CAPTION_LINES["eyes"]), "t0": round(dr + self.bar, 4),
                                 "t1": round(dr + 3 * self.bar, 4), "style": STYLES["caption"], "anim": "rise", "y": 0.64})
        for db in plan["downbeats"]:
            if dr <= db < D - 0.5:
                self.flash(plan, db, amt=0.3, pal=3)
        return plan, hook

    def fmt_words(self):
        start, end, drop, _ = self.pick_window(0, 6)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        words = self.song["words"]
        self.beat_cuts(plan, 0, D - self.bar * 0.5, 1, ["cut", "glitch", "zoom", "slit"], start_abs=start)
        last_cut = D - self.bar * 0.5
        plan["segments"][-1]["t1"] = round(last_cut, 4)
        plan["segments"].append(dict(plan["segments"][0], t0=round(last_cut, 4), t1=D))
        plan["transitions"].append({"t": round(last_cut, 4), "dur": 0.3, "type": TRANS["zoom"], "name": "zoom"})
        self.close_loop(plan)
        times = [b for b in plan["beats"] if b < D - self.bar * 0.5]
        seq = (words * 20)[:len(times)]
        st = dict(STYLES[self.r.choice(["impact", "mono", "acid"])])
        st["size"] = 330
        plan["overlays"].append({"kind": "words", "t0": 0, "t1": round(D - self.bar * 0.5, 4), "times": times, "words": seq,
                                 "style": st, "glitch": True, "y": 0.45, "maxW": 0.92})
        plan["post"]["inverts"].append([0, round(2 / 30, 4)])
        return plan, " ".join(words)

    def fmt_line(self):
        """Line-art montage in the style of the reference: geometry changes on 8th notes (16th bursts),
        a 16th-note flicker of invert / hue / mirror tiles / stutter on top, strobe on the kicks,
        zoom + glow pulse on every beat. Silhouettes and cubes are the hero shots."""
        start, end, drop, _ = self.pick_window(0, 8)
        plan = self.base_plan(start, end)
        D = plan["duration"]
        plan["overlays"] = [{"kind": "watermark", "text": "mino.recursion", "y": 0.80, "size": 40, "alpha": 0.45}]
        plan["post"].update({"punch": 0.06, "punchDecay": 11, "rgbBase": 0.0012, "rgbBeat": 0.005, "rgbOnset": 0.002, "shake": 0.0,
                             "grain": 0.015, "scan": 0, "vignette": 0.1, "barrel": 0.0, "overlayFx": 0.0, "bloom": 0.8, "bloomPulse": 1.2})
        plan["render"]["sceneScale"] = 1.0
        beats = plan["beats"]
        per8 = 60.0 / self.bpm / 2
        first = beats[0] % per8 if beats else 0.0
        grid = [round(first + i * per8, 4) for i in range(int(D / per8) + 2) if first + i * per8 < D - 0.1]
        cuts, hold = [0.0], 0
        for t in grid[1:]:
            e = self.energy_at(start + t)
            if hold > 0:
                hold -= 1
                continue
            if self.r.random() < 0.55 + 0.4 * e:
                cuts.append(t)
                if self.r.random() < 0.18 * e:                       # 16th-note burst
                    cuts.append(round(t + per8 / 2, 4))
            if self.r.random() < 0.12:
                hold = self.r.choice([1, 2, 3])                      # let a hero shot breathe
        cuts = sorted(set(c for c in cuts if c < D - 0.05))
        weights = {13: 6, 14: 3, 2: 3, 3: 2, 0: 2, 6: 2, 1: 2, 8: 2, 5: 2, 4: 1, 7: 1, 10: 1, 9: 1, 11: 1, 12: 1}
        last = None
        for k, c in enumerate(cuts):
            t1 = cuts[k + 1] if k + 1 < len(cuts) else D
            pool = [x for x in weights if x != last or x == 13]
            sid = self.r.choices(pool, [weights[x] for x in pool])[0]
            white = sid in LINE_WHITE_OK and self.r.random() < 0.3
            pal = self.r.choice([0, 1, 2, 3, 5]) if not white else self.r.choice([6, 3, 2])
            prm = [round(x, 4) for x in LINE_SCENES[sid][1](self.r)] + [1 if white else 0]
            plan["segments"].append({"t0": round(c, 4), "t1": round(t1, 4), "scene": sid, "lib": "lines", "name": LINE_SCENES[sid][0],
                                     "pal": pal, "prm": prm, "offset": round(self.r.uniform(0, 20), 3), "speed": round(self.r.uniform(0.9, 1.4), 3),
                                     "zoom": 1.0, "rot": 0.0, "spin": 0.0, "zoomPulse": 0.05,
                                     "mirror": 4 if (sid in (6, 2, 14) and self.r.random() < 0.5) else 0, "energy": self.energy_at(start + c)})
            if k > 0:
                plan["transitions"].append({"t": round(c, 4), "dur": 0.034, "type": TRANS["cut"], "name": "cut"})
            last = sid
        # strobe: a 1-2 frame flash on every kick; in some bars on every 8th (max one bar in a row)
        burst_bars = set(self.r.sample(range(8), 2))
        downs = plan["downbeats"]
        def bar_of(t):
            return max([i for i, d0 in enumerate(downs) if d0 <= t + 1e-4] or [0])
        for b in beats:
            if b >= D - 0.05:
                continue
            col = self.r.choice([[1, 1, 1], [1, 1, 1], [0.6, 0.4, 1.0], [1.0, 0.3, 0.8], [0.3, 1.0, 0.6]])
            plan["post"]["flashes"].append({"t": round(b, 4), "dur": 0.05, "amt": 0.85, "color": col})
            if bar_of(b) in burst_bars:
                plan["post"]["flashes"].append({"t": round(b + per8, 4), "dur": 0.04, "amt": 0.7, "color": [1, 1, 1]})
        # 16th-note flicker states: [t, invert, hue, mirror(0=segment default), time jump]
        per = per8 / 2
        steps = [round(first + i * per, 4) for i in range(int(D / per) + 2) if first + i * per < D]
        inv, hue, tile, jump, last_toggle = 0, 0.0, 0, 0.0, -1.0
        flick = []
        for t in steps:
            e = self.energy_at(start + t)
            p = 0.3 + 0.5 * e
            if self.r.random() < p * 0.8 and t - last_toggle >= 0.2:
                inv ^= 1
                last_toggle = t
            if self.r.random() < p * 0.6:
                hue = self.r.choice([0.0, 0.0, 1.0, -1.0, 2.1, -2.1, 3.14])
            if self.r.random() < 0.15:
                tile = self.r.choice([0, 0, 4, 4, 5])
            if self.r.random() < p * 0.35:
                jump += self.r.choice([-1, 1]) * self.r.uniform(0.15, 0.6)
            flick.append([t, inv, hue, tile, round(jump, 3)])
        if flick:
            flick[-1] = [flick[-1][0]] + flick[0][1:]
        plan["post"]["flicker"] = flick
        self.close_loop(plan)
        return plan, ""

    def build(self):
        plan, hook = getattr(self, f"fmt_{self.fmt}")()
        plan["hook"] = hook.replace("\n", " ")
        plan["caption"] = self.caption(hook)
        return plan

    def caption(self, hook):
        line = self.r.choice(CAPTION_HOOKS[self.fmt]).format(bpm=int(round(self.bpm)), title=self.song["title"])
        ask = self.r.choice(CAPTION_ASKS[self.fmt])
        tags = self.r.sample(BASE_TAGS, 5) + ["#" + self.song["tags"][0], "#minorecursion"]
        warn = "⚠️ flashing lights\n" if self.fmt == "line" else ""
        return (f"{warn}{line}\n{ask}\n\n"
                f"🎧 mino.recursion — {self.song['title']} (full track on Spotify, link in bio)\n"
                f"↻ it loops. use the sound for your own edits.\n\n" + " ".join(tags))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--song", required=True)
    ap.add_argument("--format", required=True, choices=["drop", "stare", "error", "eyes", "words", "line"])
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out")
    a = ap.parse_args()
    plan = Director(a.song, a.format, a.seed).build()
    out = a.out or os.path.join(ROOT, "build", "plans", plan["id"] + ".json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump(plan, f, indent=1)
    print(out)
    print(f"duration {plan['duration']}s, segments {len(plan['segments'])}, transitions {len(plan['transitions'])}, hook: {plan['hook']}")


if __name__ == "__main__":
    main()

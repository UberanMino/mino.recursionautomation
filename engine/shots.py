#!/usr/bin/env python3
"""Shot catalogue + usage memory for the line format, so reels stop looking alike.

A *shot* is one look from engine/shaders/lines.glsl: a scene, optionally pinned to a variant
(silhouette shape + fill, polygon of the tunnel, figure of the harmonograph ...). Every reel casts
a handful of shots (its "cast") and cuts between them on the beat. Which shots get cast depends on
how often they were used in the last reels:

  * a shot that was in one of the last COOLDOWN reels is unlikely to be cast again (weight x0.15)
  * a shot is in at most MAX_REELS_IN_WINDOW of the last WINDOW reels, a family (all variants of a
    scene, or one silhouette shape) in at most MAX_FAMILY_IN_WINDOW (hard limits; relaxed only
    when the catalogue would otherwise run dry)
  * every reel casts at least FRESH_MIN shots that were not used in the window at all
  * shots that were used rarely so far get a novelty boost, so new shots reach the feed quickly
  * the hero (longest on screen) of a reel is not the hero again within HERO_COOLDOWN reels
  * within a reel one shot fills at most MAX_SHARE of the cuts

Reuse is allowed, just spread out. The memory is engine/shot_history.json (committed, so the
daily session in a fresh container still knows what ran the days before).

  python3 engine/shots.py report          # usage table + whether new shots are due
  python3 engine/shots.py list            # all shot keys
"""
import datetime as dt
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY = os.path.join(ROOT, "engine", "shot_history.json")
PERF = os.path.join(ROOT, "engine", "analytics", "weights.json")   # written by engine/analytics.py

RULES = {
    "cast_size": (7, 9),          # distinct shots per reel
    "silhouettes_per_cast": (2, 3),
    "window": 21,                 # reels looked back (= 3 days at 7 per day)
    "max_reels_in_window": 4,     # hard cap per shot within the window
    "max_family_in_window": 5,    # ... and per family (all variants of a scene / one silhouette shape)
    "cooldown": 2,                # shot was in one of the last 2 reels -> weight x0.15
    "hero_cooldown": 7,
    "fresh_min": 3,               # shots per reel that were not used within the window
    "novelty_uses": 3,            # shots used fewer times than this (ever) get the boost
    "novelty_boost": 2.5,
    "max_share": 0.24,            # one shot fills at most 24% of the cuts of a reel
    "keep_reels": 400,            # history length
    "new_shots_every_days": 4,    # report says "new shots due" when the newest shot is older
    "min_free_shots": 30,         # ... or when fewer shots than this are free to cast
}

# scene id -> (name, param sampler). prm[3] (background) is added by the director.
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
    13: ("silhouette", lambda r: [r.randint(0, 14), r.randint(0, 4), r.uniform(1.0, 1.35)]),
    14: ("cubes", lambda r: [r.choice([2, 2.5, 3]), r.uniform(0.5, 1.2), 0]),
    15: ("globe", lambda r: [r.uniform(0.55, 0.8), r.choice([-1, 1]) * r.uniform(0.3, 0.8), r.choice([8, 10, 12, 14])]),
    16: ("terrain", lambda r: [r.choice([8, 10, 12]), r.uniform(0.8, 1.6), r.uniform(0.7, 1.2)]),
    17: ("vortex", lambda r: [r.choice([3, 4, 5, 6, 7]), r.uniform(1.2, 2.2), r.uniform(0.6, 1.4)]),
    18: ("harmono", lambda r: [3, 2, r.uniform(1, 3)]),
    19: ("polytunnel", lambda r: [3, r.choice([-1, 1]) * r.uniform(0.05, 0.3), r.uniform(0.5, 1.0)]),
    20: ("strings", lambda r: [r.randint(7, 14), r.uniform(0.8, 1.4), 0]),
    21: ("helix", lambda r: [r.uniform(0.3, 0.5), r.uniform(0.8, 1.4), r.choice([8, 10, 12])]),
    22: ("rain", lambda r: [r.choice([20, 28, 36]), r.uniform(0.8, 1.4), 0]),
    23: ("topo", lambda r: [r.uniform(1.2, 2.2), r.uniform(0.8, 1.3), 0]),
    24: ("orbits", lambda r: [r.choice([3, 4, 5]), r.uniform(0.7, 0.9), 0]),
    25: ("icosa", lambda r: [r.uniform(0.6, 0.85), 0, r.choice([0, 1])]),
    26: ("gyro", lambda r: [r.uniform(0.8, 0.95), r.choice([3, 4, 5]), 0]),
    27: ("moire", lambda r: [r.uniform(12, 22), r.uniform(0.04, 0.12), 1]),   # radial only: linear gratings shimmer into noise
}
# scenes that also read well on off-white
LINE_WHITE_OK = {0, 3, 4, 6, 7, 8, 9, 10, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26}

# scenes added by the shot workshop (date = novelty clock in the report)
SCENE_ADDED = {26: "2026-10-25", 27: "2026-10-25"}

SIL_SHAPES = ["bust", "profile", "figure", "hand", "mushroom", "cat", "eye", "pyramid", "planet", "heart", "star",
              "alien", "moon", "crystal", "keyhole"]
SIL_FILLS = ["contour", "scribble", "scan", "echo", "halftone"]


def _catalog():
    """key -> {scene, fix {prm index: value}, weight (how often it is cast), hero (cut weight inside a reel), added}"""
    cat = {}

    def add(key, scene, fix=None, weight=1.0, hero=1.0, added="2026-10-21"):
        cat[key] = {"key": key, "scene": scene, "fix": fix or {}, "weight": weight, "hero": hero, "added": added}

    for sid, (name, _) in LINE_SCENES.items():
        if sid in (13, 9, 18, 19):
            continue
        add(name, sid, weight={14: 1.6, 2: 1.4, 3: 1.2}.get(sid, 1.0), hero={14: 2.0, 2: 2.0}.get(sid, 1.5),
            added=SCENE_ADDED.get(sid, "2026-10-21"))
    add("dots/round", 9, {2: 0}, 0.5)
    add("dots/square", 9, {2: 1}, 0.5)
    for a, b in [(3, 2), (5, 4), (3, 4), (5, 2), (1, 3)]:
        add(f"harmono/{a}-{b}", 18, {0: a, 1: b}, 0.22)
    for n, nm in [(0, "arch"), (3, "tri"), (4, "square"), (6, "hex")]:
        add(f"polytunnel/{nm}", 19, {0: n}, 0.3)
    for si, sh in enumerate(SIL_SHAPES):
        for fi, fl in enumerate(SIL_FILLS):
            add(f"silhouette/{sh}/{fl}", 13, {0: si, 1: fi}, 1.0, hero=3.0)
    return cat


CATALOG = _catalog()


def is_sil(key):
    return key.startswith("silhouette/")


def family(key):
    """silhouettes group by shape (a bust stays a bust whatever the fill), everything else by scene"""
    parts = key.split("/")
    return "/".join(parts[:2]) if is_sil(key) else parts[0]


def perf_weights(path=PERF):
    """performance multipliers from the daily analysis (families, first shot); neutral when missing"""
    try:
        with open(path) as f:
            w = json.load(f)
        return {"families": w.get("families", {}), "first": w.get("first", {})}
    except (OSError, ValueError):
        return {"families": {}, "first": {}}


# ---------------------------------------------------------------- history
def load_history(path=HISTORY):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {"version": 1, "reels": []}


def save_history(hist, path=HISTORY):
    hist["reels"] = hist["reels"][-RULES["keep_reels"]:]
    with open(path, "w") as f:
        json.dump(hist, f, indent=1)
        f.write("\n")


def record(hist, plan, date=None):
    """Store which shots a line plan uses (idempotent per plan id). first/open feed the analytics (skip rate)."""
    segs = [s for s in plan["segments"] if s.get("shot")]
    if not segs:
        return
    body = segs[:-1] if len(segs) > 1 else segs           # the last segment repeats the first (seamless loop)
    shots = Counter(s["shot"] for s in body)
    screen = Counter()
    for s in body:
        screen[s["shot"]] += s["t1"] - s["t0"]
    opening = []
    for s in segs:
        if s["t0"] < 3.0 and s["shot"] not in opening:
            opening.append(s["shot"])
    entry = {"id": plan["id"], "date": date or dt.date.today().isoformat(), "shots": dict(sorted(shots.items())),
             "hero": screen.most_common(1)[0][0], "first": segs[0]["shot"], "open": opening}
    hist["reels"] = [r for r in hist["reels"] if r["id"] != plan["id"]] + [entry]


# ---------------------------------------------------------------- casting
class Picker:
    def __init__(self, r, hist=None, exclude_ids=()):
        self.r = r
        reels = [x for x in (hist or {"reels": []})["reels"] if x["id"] not in exclude_ids]
        self.window = reels[-RULES["window"]:]
        self.recent = reels[-RULES["cooldown"]:]
        self.heroes = {x["hero"] for x in reels[-RULES["hero_cooldown"]:]}
        self.in_window = Counter(k for x in self.window for k in x["shots"])
        self.fam_window = Counter(f for x in self.window for f in {family(k) for k in x["shots"]})
        self.ever = Counter(k for x in reels for k in x["shots"])
        self.recent_keys = {k for x in self.recent for k in x["shots"]}
        self.perf = perf_weights()

    def freshness(self, key):
        w = 1.0 / (1.0 + self.in_window[key])
        w *= 1.0 / (1.0 + 0.5 * self.fam_window[family(key)])
        if key in self.recent_keys:
            w *= 0.15
        if self.ever[key] < RULES["novelty_uses"]:
            w *= RULES["novelty_boost"]
        return w * self.perf["families"].get(family(key), 1.0)   # what performed (analytics), gently

    def _draw(self, pool, n, taken):
        out = []
        pool = [k for k in pool if k not in taken]
        while pool and len(out) < n:
            k = self.r.choices(pool, [CATALOG[x]["weight"] * self.freshness(x) for x in pool])[0]
            out.append(k)
            fam = family(k)
            pool = [x for x in pool if x != k and family(x) != fam]   # one look per family and reel
        return out

    def cast(self):
        lo, hi = RULES["cast_size"]
        size = self.r.randint(lo, hi)
        n_sil = self.r.randint(*RULES["silhouettes_per_cast"])
        allowed = [k for k in CATALOG if self.in_window[k] < RULES["max_reels_in_window"]
                   and self.fam_window[family(k)] < RULES["max_family_in_window"]]
        sils = [k for k in allowed if is_sil(k)]
        rest = [k for k in allowed if not is_sil(k)]
        unused = {k for k in allowed if self.in_window[k] == 0}
        cast = []
        # fresh shots first (split between silhouettes and the rest)
        f_sil = min(n_sil, max(1, RULES["fresh_min"] // 2))
        cast += self._draw([k for k in sils if k in unused], f_sil, cast)
        cast += self._draw([k for k in rest if k in unused], RULES["fresh_min"] - len(cast), cast)
        fams = {family(k) for k in cast}
        cast += self._draw([k for k in sils if family(k) not in fams], n_sil - sum(map(is_sil, cast)), cast)
        fams = {family(k) for k in cast}
        cast += self._draw([k for k in rest if family(k) not in fams], size - len(cast), cast)
        # hard caps left too little: top up from the whole catalogue (freshness weighting still applies)
        for want, pool in ((n_sil - sum(map(is_sil, cast)), [k for k in CATALOG if is_sil(k)]),
                           (size - len(cast), [k for k in CATALOG if not is_sil(k)])):
            if want > 0:
                fams = {family(k) for k in cast}
                cast += self._draw([k for k in pool if family(k) not in fams], want, cast)
        return cast

    def first_weights(self, cast):
        """weight for the opening cut: families with a lower skip rate open more often (analytics)"""
        return {k: self.perf["first"].get(family(k), 1.0) for k in cast}

    def cut_weights(self, cast):
        """weight per shot for the cuts inside one reel; the hero of recent reels may not lead again"""
        return {k: CATALOG[k]["hero"] * (0.4 if k in self.heroes else 1.0) for k in cast}


def sequence(r, cast, weights, n_cuts, first=None):
    """Assign a shot to each cut: no shot twice in a row, none above MAX_SHARE of the cuts.
    `first` (optional) multiplies the weights of the opening cut (the first 3 s decide the skip rate)."""
    cap = max(2, int(RULES["max_share"] * n_cuts + 0.999))
    used, out, last = Counter(), [], None
    for i in range(n_cuts):
        pool = [k for k in cast if k != last and used[k] < cap] or [k for k in cast if k != last] or cast
        k = r.choices(pool, [weights[x] * (first.get(x, 1.0) if (first and i == 0) else 1.0) for x in pool])[0]
        out.append(k)
        used[k] += 1
        last = k
    return out


def params(r, key):
    shot = CATALOG[key]
    prm = [round(x, 4) for x in LINE_SCENES[shot["scene"]][1](r)]
    for i, v in shot["fix"].items():
        prm[int(i)] = v
    return prm


# ---------------------------------------------------------------- report
def report(hist=None):
    hist = hist or load_history()
    p = Picker(__import__("random").Random(0), hist)
    reels = hist["reels"]
    free = [k for k in CATALOG if p.in_window[k] < RULES["max_reels_in_window"] and k not in p.recent_keys]
    lines = [f"Shots im Katalog: {len(CATALOG)}  (Szenen: {len(LINE_SCENES)}, Silhouetten: {len(SIL_SHAPES)} Formen x {len(SIL_FILLS)} Füllungen)",
             f"Reels im Log: {len(reels)}  | Fenster: letzte {len(p.window)} Reels",
             f"frei castbar: {len(free)}  | nie benutzt: {sum(1 for k in CATALOG if p.ever[k] == 0)}"]
    top = p.in_window.most_common(12)
    if top:
        lines.append("am häufigsten im Fenster: " + ", ".join(f"{k} ({n})" for k, n in top))
    fam = Counter(family(k) for x in p.window for k in x["shots"])
    if fam:
        lines.append("Familien im Fenster: " + ", ".join(f"{k} {n}" for k, n in fam.most_common(10)))
    newest = max(dt.date.fromisoformat(s["added"]) for s in CATALOG.values())
    age = (dt.date.today() - newest).days
    due = age >= RULES["new_shots_every_days"] or len(free) < RULES["min_free_shots"]
    lines.append(f"neuester Shot: {newest} ({age} Tage alt)")
    lines.append("=> NEUE SHOTS FÄLLIG: 1-2 neue Szenen oder Silhouetten in engine/shaders/lines.glsl entwickeln "
                 "(siehe docs/DAILY_RUN.md, Schritt Shot-Werkstatt)" if due else "=> Katalog frisch genug, keine neuen Shots nötig")
    return "\n".join(lines), due


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "list":
        for k, v in CATALOG.items():
            print(f"{k:34s} scene {v['scene']:2d}  weight {v['weight']:.2f}  added {v['added']}")
    else:
        print(report()[0])

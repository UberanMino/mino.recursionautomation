#!/usr/bin/env python3
"""Daily performance loop for @mino.recursion: which songs, shots, openers, captions and slots work.

  python3 engine/analytics.py fetch     # pull IG insights of the posted reels -> engine/analytics/insights.json
  python3 engine/analytics.py report    # link metrics to song / shots / caption / slot, write
                                        #   build/analytics/report.md + engine/analytics/weights.json
  python3 engine/analytics.py daily     # fetch + report (what the scheduled analysis runs)

Insights come from the Make scenario "mino.recursion – Insights lesen (Claude)" (webhook 3975180, read only,
uses the Facebook connection 5649789). Its URL comes from env MR_INSIGHTS_HOOK or config.local.json
"insights_hook" (gitignored, the repo is public). Facebook has no insights module in Make, so only IG is measured.

How a reel is scored (all numbers on the IG reel):
  * hook   = -skip rate (share of views skipped within the first 3 s)
  * hold   = average watch time
  * love   = (likes + 2 shares + 2 saves + 2 comments) / reach
  * reach  = log views minus the mean of that posting day (removes account growth and post age)
  each turned into a z-score over the mature reels (>= MATURE_H hours old), score = mean of the four.

Effects per song / shot family / opener / caption opener / hashtag set / slot are shrunk towards 0
(effect = sum of scores / (n + PRIOR_N)), so a feature seen in 2 reels barely moves. weights.json turns them
into gentle multipliers (WEIGHT_RANGE) that daily.py and shots.py apply: the look (line V4) never changes,
only how often songs / shots are picked and which shot opens a reel. Exploration stays (cooldown, caps,
novelty boost, every song at least once a day).
"""
import datetime as dt
import json
import math
import os
import random
import re
import subprocess
import sys
from collections import defaultdict
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))
import shots as S  # noqa: E402

TZ = ZoneInfo("Europe/Berlin")
DIR = os.path.join(ROOT, "engine", "analytics")
INSIGHTS = os.path.join(DIR, "insights.json")
WEIGHTS = os.path.join(DIR, "weights.json")
LEGACY = os.path.join(DIR, "legacy_shots.json")
REPORT = os.path.join(ROOT, "build", "analytics", "report.md")

SLOTS = ["07:40", "10:15", "12:40", "15:10", "17:45", "19:50", "21:40", "23:05"]   # same as daily.py
FETCH_DAYS = 14        # posts older than this are treated as final and not fetched again
MATURE_H = 18          # a reel counts once it is this old (small account: most views come on day 1)
MIN_SIGNAL_N = 3       # fewer reels than this never count as a signal in the report
PRIOR_N = 4            # shrinkage: a group needs ~4 reels before its effect counts half
WEIGHT_GAIN = 0.35     # multiplier = 1 + gain * effect ...
WEIGHT_RANGE = (0.7, 1.45)
METRICS = ["views", "reach", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time", "reels_skip_rate",
           "likes", "comments", "shares", "saved", "total_interactions"]


# ---------------------------------------------------------------- fetch
def hook_url():
    url = os.environ.get("MR_INSIGHTS_HOOK")
    p = os.path.join(ROOT, "config.local.json")
    if not url and os.path.exists(p):
        url = json.load(open(p)).get("insights_hook")
    if not url:
        raise SystemExit("missing insights hook: set MR_INSIGHTS_HOOK or \"insights_hook\" in config.local.json "
                         "(Make hook 3975180, read its URL with the Make MCP hooks_get)")
    return url


def load_insights():
    if os.path.exists(INSIGHTS):
        return json.load(open(INSIGHTS))
    return {"version": 1, "posts": {}}


def save_json(obj, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False, sort_keys=True)
        f.write("\n")


def fetch(now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    since = int((now - dt.timedelta(days=FETCH_DAYS)).timestamp())
    db = load_insights()
    if not db["posts"]:
        since = 0                                   # first run: everything that was ever posted
    r = subprocess.run(["curl", "-sS", "-m", "600", "-X", "POST", "-H", "Content-Type: application/json",
                        "--data-binary", json.dumps({"since": since}), hook_url()], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"insights hook failed: {r.stderr[:300]}")
    try:
        rows = json.loads(r.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"insights hook: unexpected response {r.stdout[:300]!r}")
    day = now.astimezone(TZ).date().isoformat()
    got = defaultdict(dict)
    for x in rows:
        p = db["posts"].setdefault(x["key"], {})
        p.update({"ig": x.get("ig"), "fb": x.get("fb"), "posted_ts": int(x["posted_ts"])})
        if x.get("caption"):
            p["caption"] = x["caption"]
        if x.get("name") in METRICS and x.get("value") is not None:
            got[x["key"]][x["name"]] = x["value"]
    for key, m in got.items():
        p = db["posts"][key]
        p["latest"] = m
        p["fetched_at"] = int(now.timestamp())
        p.setdefault("history", {})[day] = {k: m[k] for k in ("views", "reach", "reels_skip_rate", "ig_reels_avg_watch_time",
                                                              "likes", "shares", "saved") if k in m}
    save_json(db, INSIGHTS)
    print(f"insights: {len(got)} reels updated ({len(db['posts'])} known)")
    return db


# ---------------------------------------------------------------- features
def opener_of(caption):
    c = (caption or "").strip().lower()
    for pat, name in [(r"^so there i was", "so there I was"), (r"^yo so basically", "yo so basically"),
                      (r"^yo check it", "yo check it"), (r"^okay so", "okay so")]:
        if re.match(pat, c):
            return name
    return "other"


def hashtags_of(caption):
    tags = re.findall(r"#\w+", caption or "")
    return " ".join(t for t in tags if t not in ("#minorecursion",)) or "-"


def slot_of(ts):
    t = dt.datetime.fromtimestamp(ts, TZ)
    mins = t.hour * 60 + t.minute
    best = min(range(len(SLOTS)), key=lambda i: abs(int(SLOTS[i][:2]) * 60 + int(SLOTS[i][3:]) - mins))
    return SLOTS[best]


def shot_info():
    info = {}
    if os.path.exists(LEGACY):
        info.update(json.load(open(LEGACY))["reels"])
    for r in S.load_history()["reels"]:
        info[r["id"]] = r
    return info


def features(db, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    shots = shot_info()
    rows = []
    for key, p in db["posts"].items():
        m = p.get("latest")
        if not m or "-line-" not in key:          # only the approved line format is compared
            continue
        song = key.rsplit("-", 2)[0]
        age_h = ((p.get("fetched_at") or now.timestamp()) - p["posted_ts"]) / 3600
        info = shots.get(key, {})
        reach = max(1, m.get("reach", 0))
        rows.append({
            "key": key, "song": song, "posted_ts": p["posted_ts"], "age_h": age_h,
            "day": dt.datetime.fromtimestamp(p["posted_ts"], TZ).date().isoformat(),
            "slot": slot_of(p["posted_ts"]), "opener": opener_of(p.get("caption")), "tags": hashtags_of(p.get("caption")),
            "words": len(re.split(r"\n\n", p.get("caption", ""))[0].split()),
            "families": sorted({S.family(k) for k in info.get("shots", {})}),
            "first": S.family(info["first"]) if info.get("first") else None,
            "hero": S.family(info["hero"]) if info.get("hero") else None,
            "views": m.get("views", 0), "skip": m.get("reels_skip_rate"), "watch": m.get("ig_reels_avg_watch_time"),
            "love": (m.get("likes", 0) + 2 * m.get("shares", 0) + 2 * m.get("saved", 0) + 2 * m.get("comments", 0)) / reach,
            "shares": m.get("shares", 0), "saved": m.get("saved", 0), "likes": m.get("likes", 0),
        })
    return rows


def z(vals):
    xs = [v for v in vals if v is not None]
    if len(xs) < 2:
        return [0.0 if v is not None else None for v in vals]
    mu = sum(xs) / len(xs)
    sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1)) or 1.0
    return [None if v is None else (v - mu) / sd for v in vals]


def score(rows):
    """composite score per mature reel (mean of 4 z-scores), stored in row['score'] and the parts"""
    mature = [r for r in rows if r["age_h"] >= MATURE_H]
    by_day = defaultdict(list)
    for r in mature:
        by_day[r["day"]].append(math.log1p(r["views"]))
    for r in mature:
        d = by_day[r["day"]]
        r["reach_resid"] = math.log1p(r["views"]) - sum(d) / len(d) if len(d) >= 3 else None
    parts = {"hook": z([None if r["skip"] is None else -r["skip"] for r in mature]),
             "hold": z([r["watch"] for r in mature]),
             "love": z([r["love"] for r in mature]),
             "reach": z([r["reach_resid"] for r in mature])}
    for i, r in enumerate(mature):
        vals = {k: v[i] for k, v in parts.items() if v[i] is not None}
        r.update({f"z_{k}": v for k, v in vals.items()})
        r["score"] = sum(vals.values()) / len(vals) if vals else 0.0
    return mature


def effects(mature, field, target="score", multi=False):
    """shrunk mean effect + rough 80% bootstrap interval per value of `field`"""
    groups = defaultdict(list)
    for r in mature:
        v = r.get(field)
        for g in (v if multi else [v]):
            if g is not None and r.get(target) is not None:
                groups[g].append(r[target])
    rng = random.Random(1)
    out = {}
    for g, xs in groups.items():
        n = len(xs)
        eff = sum(xs) / (n + PRIOR_N)
        boots = sorted(sum(rng.choice(xs) for _ in range(n)) / (n + PRIOR_N) for _ in range(400))
        out[g] = {"n": n, "effect": round(eff, 3), "lo": round(boots[40], 3), "hi": round(boots[359], 3),
                  "mean": round(sum(xs) / n, 3)}
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["effect"]))


def mult(eff):
    lo, hi = WEIGHT_RANGE
    return round(min(hi, max(lo, 1 + WEIGHT_GAIN * eff)), 3)


# ---------------------------------------------------------------- report
def fmt_table(title, eff, unit="Score"):
    lines = [f"### {title}", "", f"| | n | Effekt ({unit}) | 80 %-Band | Signal |", "|---|---:|---:|---|---|"]
    for g, e in eff.items():
        sig = ("zu wenig" if e["n"] < MIN_SIGNAL_N else "↑ eher gut" if e["lo"] > 0 else "↓ eher schwach" if e["hi"] < 0 else "–")
        lines.append(f"| {g} | {e['n']} | {e['effect']:+.2f} | {e['lo']:+.2f} … {e['hi']:+.2f} | {sig} |")
    return "\n".join(lines) + "\n"


def report(db=None, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    db = db or load_insights()
    rows = features(db, now)
    mature = score(rows)
    eff = {
        "song": effects(mature, "song"),
        "family": effects(mature, "families", multi=True),
        "first": effects(mature, "first", target="z_hook"),
        "hero": effects(mature, "hero"),
        "slot": effects(mature, "slot"),
        "opener": effects(mature, "opener"),
        "tags": effects(mature, "tags"),
    }
    weights = {
        "_note": "written by engine/analytics.py report; multipliers for daily.py (songs) and shots.py (families, "
                 "first shot). 1.0 = neutral. Effects are shrunk towards 0, so few reels = little change.",
        "updated": now.astimezone(TZ).isoformat(timespec="minutes"),
        "reels_scored": len(mature),
        "songs": {k: mult(v["effect"]) for k, v in eff["song"].items()},
        "families": {k: mult(v["effect"]) for k, v in eff["family"].items()},
        "first": {k: mult(v["effect"]) for k, v in eff["first"].items()},
    }
    save_json(weights, WEIGHTS)

    tot = defaultdict(lambda: [0, 0, 0.0])
    for r in rows:
        t = tot[r["day"]]
        t[0] += 1
        t[1] += r["views"]
        t[2] += r["skip"] or 0
    best = sorted(mature, key=lambda r: -r["score"])
    md = [f"# Reel-Analyse {now.astimezone(TZ).date().isoformat()}", "",
          f"Gemessen: {len(rows)} Line-Reels auf IG, davon {len(mature)} alt genug (≥ {MATURE_H} h) für den Vergleich. "
          "Facebook liefert über Make keine Reel-Insights, daher nur IG.", "",
          "**Unsicherheit:** bei so wenigen Reels sind fast alle Unterschiede noch Rauschen. Ein Effekt zählt erst, "
          "wenn das 80 %-Band nicht über 0 reicht (Spalte Signal). Die Gewichte sind entsprechend vorsichtig "
          f"({WEIGHT_RANGE[0]}–{WEIGHT_RANGE[1]}×, auf 0 geschrumpft).", "",
          "## Verlauf pro Tag", "", "| Tag | Reels | Aufrufe | Ø Skip-Rate |", "|---|---:|---:|---:|"]
    for d in sorted(tot):
        n, v, s = tot[d]
        md.append(f"| {d} | {n} | {v} | {s / n:.1f} % |")
    md += ["", "## Beste und schwächste Reels (Score)", "", "| Reel | Song | Slot | Aufrufe | Skip | Ø Watch | Likes/Shares/Saves | Score |",
           "|---|---|---|---:|---:|---:|---|---:|"]
    for r in best[:5] + ([None] if len(best) > 10 else []) + best[-5:]:
        if r is None:
            md.append("| … | | | | | | | |")
            continue
        md.append(f"| {r['key']} | {r['song']} | {r['slot']} | {r['views']} | {r['skip']} % | {r['watch'] / 1000:.1f} s | "
                  f"{r['likes']}/{r['shares']}/{r['saved']} | {r['score']:+.2f} |")
    md += ["", "## Muster", "",
           fmt_table("Song", eff["song"]),
           fmt_table("Erster Shot (nur Hook = –Skip-Rate)", eff["first"], "Hook-z"),
           fmt_table("Shot-Familien im Reel", dict(list(eff["family"].items())[:8] + list(eff["family"].items())[-6:])),
           fmt_table("Hero-Shot (am längsten im Bild)", eff["hero"]),
           fmt_table("Slot (Berlin)", eff["slot"]),
           fmt_table("Caption-Einstieg", eff["opener"]),
           fmt_table("Hashtag-Set", eff["tags"]),
           "## Was die Pipeline daraus macht", "",
           "- Songs (`daily.py`): jeder Song bleibt mindestens 1× pro Tag drin, die übrigen Slots gehen gewichtet an: "
           + ", ".join(f"{k} {v}×" for k, v in weights["songs"].items()),
           "- Shots (`shots.py`): Familien-Gewichte im Casting (Cooldown, Caps und Neuheits-Bonus bleiben): stärkste "
           + ", ".join(f"{k} {v}×" for k, v in list(weights["families"].items())[:4]) + "; schwächste "
           + ", ".join(f"{k} {v}×" for k, v in list(weights["families"].items())[-3:]),
           "- Erster Shot: Familien mit niedriger Skip-Rate eröffnen öfter: "
           + ", ".join(f"{k} {v}×" for k, v in list(weights["first"].items())[:4]),
           "- Slots, Captions, Hashtags: nur Bericht. Caption-Schreiber (Daily Run, Schritt 5) kann sich am "
           "Caption-Einstieg oben orientieren; Slot-Zeiten ändern nur nach Rücksprache mit Raphael.", ""]
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    open(REPORT, "w").write("\n".join(md))
    print("\n".join(md))
    return weights


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    if cmd in ("fetch", "daily"):
        fetch()
    if cmd in ("report", "daily"):
        report()

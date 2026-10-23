# mino.recursion — automatisierte Psychedelic-Edits für Instagram & Facebook

Prozedural generierte, beat-synchrone Reels (9:16, 1080×1920, 30 fps) zu den mino.recursion-Tracks.
Alles Visuelle wird im Code erzeugt (WebGL-Shader + Canvas-Overlays in einer HyperFrames-Komposition) —
keine fremden Bilder, kein Copyright-Risiko. Die Referenzbilder aus `mino.recursion.visuell` dienen nur als Stilvorgabe.

## Pipeline

```
songs (Dropbox /mino.recursion/songs)
  └─ engine/analyze_audio.py   BPM, Beat-Grid, Downbeats, Drops, Bass/Onset pro Frame
      └─ engine/plan.py        "Creative Director": Format, Hook, Szenen, Cuts auf Beats, Übergänge, Caption
          └─ engine/build.py   baut das HyperFrames-Projekt, rendert (headless Chrome), muxed Audio (IG-konform)
              └─ engine/publish.py  Upload nach Dropbox /mino.recursion/queue/<datum>/ + Eintrag in Make-Queue
                  └─ Make: "mino.recursion – Reel-Queue posten FB+IG (Claude)" postet alle 15 min fällige Reels
engine/daily.py  = alles zusammen für einen Tag (7–8 Slots, Europe/Berlin)
```

### Render-Engine
- `engine/shaders/scenes.glsl` — 15 Szenen: Zigzag-Hypnospirale, Op-Art-Sunburst mit Auge, Augen-Raster
  (blinzeln auf dem Beat), Acid-Marmor, Checker-Tunnel/-Boden, Kaleidoskop-Fraktal, Julia-Set, Ringe + Mond,
  schmelzender Acid-Smiley, Hyperspace, Moiré, Truchet, Droste-„Recursion"-Zoom, Regenbogen-Drips, Riesen-Hypno-Auge.
  Jede Szene wird als eigenes kleines Programm kompiliert (`#define SCENE n`) — SwiftShader führt sonst alle
  Branches einer Laufzeit-if-Kette aus.
- `engine/shaders/composite.glsl` — 10 Übergänge (Zoom-Through, Iris/Pupille, Glitch-Blöcke, Swirl, Kaleido-Fold,
  Melt, Pixel, Slit, Liquid, Hard-Cut) + Post-FX (Beat-Zoom-Punch, RGB-Split, Shake, Invert/Flash, Grain, Scanlines).
- `engine/runtime.js` — rendert jeden Frame als reine Funktion der Zeit (seek-sicher für HyperFrames),
  Overlays: Hook-Text mit Glitch/Extrude, Wort-pro-Beat, Win98-Fehler-Popups, Ladebalken, Countdown, Wasserzeichen.

### Formate
**Aktiver Kanal-Stil: `line`** (freigegeben, Version 4) — minimale Neon-Line-Art nach Referenz-Clip:
Silhouetten (Köpfe, Figur, Hand, Pilz, Katze, Auge, Planet …), Wireframe-Würfel/-Räume/-Tunnel, Weave, Checker-Wurmloch,
Partikel-Kugel, Faser-Burst. Cuts auf Achteln (16tel-Bursts), 16tel-Flackern (Invert / Tint / kurze Spiegel-Hits / Stutter),
harter Strobe auf jedem Kick, Zoom-/Glow-Puls, Kamerafahrt pro Shot, Neon-Gradient-Map-Grading, kein Text, kein Wasserzeichen.
Szenen: `engine/shaders/lines.glsl`. Ältere Formate (unten) bleiben per `--format` verfügbar.

| Format | Idee |
|---|---|
| `drop`  | 1 Takt Build-up mit Hook-Text, dann Schnitte auf jeden (2.) Beat, WTF-Moment in der Mitte, nahtloser Loop |
| `stare` | Bewegungsnacheffekt-Illusion: auf den Punkt starren, beim Drop friert das Bild ein und „bewegt sich weiter" |
| `error` | reality.exe: Win98-Fehlerfenster stapeln sich auf jedem Beat, der Drop zerschlägt sie |
| `eyes`  | Augen-Recursion: jeder Schnitt geht durch eine Pupille in die nächste Szene |
| `words` | Songtitel / Wortkette, ein Wort pro Beat |

Retention-Regeln, die der Director einhält: Hook-Text ab Frame 0 (kein Fade-in), Drop nach ~1,6 s,
Szenenwechsel alle 0,4–0,8 s, Loop-Ende = erster Frame (Rewatches), Flashes max. 1× pro Takt (fotosensitiv-sicher),
Text in der IG-Safe-Zone.

## Benutzen

```bash
npm ci
python3 engine/daily.py --date 2026-10-22 --dry-run     # Plan anzeigen
python3 engine/daily.py --date 2026-10-22               # 7 Reels rendern + einplanen
python3 engine/daily.py --now --count 1 --format stare  # eins sofort posten
python3 engine/tools/scene_sheet.py                     # Kontaktbogen aller Szenen (build/scenesheet.jpg)
```

Webhook-URLs stehen **nicht** im Repo. `config.local.json` (gitignored) oder Env-Variablen
`MR_DROPBOX_HOOK` / `MR_QUEUE_HOOK` (Make-Hooks 3948188 / 3948189).

## Make (eu1, Team 690392)
| Szenario | ID | Zweck |
|---|---|---|
| mino.recursion – Dropbox links (Claude) | 8092603 | Temp-Upload/Download-Links, nur `/mino.recursion/…` |
| mino.recursion – Queue füllen (Claude) | 8092677 | Webhook → Data Store `mino_recursion_queue` (227426) |
| mino.recursion – Reel-Queue posten FB+IG (Claude) | 8092663 | alle 15 min 06:00–24:00: fälliges Reel → FB-Seite Mino.recursion + IG @mino.recursion, Log in `mino_recursion_posted` (227427) |

## Automatisierung
- Geplante Claude-Aufgabe „mino.recursion – Reels für die nächsten Tage rendern" (täglich 20:20 Europe/Berlin)
  hält die Queue für morgen + übermorgen mit je 7 Reels gefüllt und prüft die Posts des Tages — Ablauf in `docs/DAILY_RUN.md`.
- Slots (±6 min Jitter): 07:40, 10:15, 12:40, 15:10, 17:45, 19:50, 21:40 (+23:05 bei 8 Posts).

## Synästhesie-Engine (Experiment, nicht Teil der Live-Pipeline)
`synesthesia/` koppelt Musik und Bild nach festen Regeln: Tonhöhe → Höhe, Lautheit → Helligkeit,
Klangfarbe → Farbe, musikalisches Chaos → visuelles Chaos, Stereo → links/rechts.
Regelwerk, Messungen und Benutzung: `docs/MAPPING_RULES.md`.
Version 2 (Standard): 3D-Flug durch einen Tunnel aus dem Song, mit Kick-Bounce, `docs/MAPPING_RULES_3D.md`.
Fünf weitere Modelle mit eigenen Naturgesetzen (Lorenz, Julia, Kepler, Gray-Scott, Chladni):
`python3 -m synesthesia song.wav --model lorenz ...`, siehe `docs/MODELS.md`.

## Songs
Siehe `engine/songs.json`. WAV-Master liegen in Dropbox `/mino.recursion/songs/` (nicht im Git).

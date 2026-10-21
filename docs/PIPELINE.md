# mino.recursion – Reel-Pipeline (Gesamtdoku)

Stand: 21.10.2026. Rekonstruiert aus der Aufbau-Sitzung vom 21.10.2026 (11:11–18:13 UTC), dem Code auf
`claude/relaxed-dijkstra-teb4bo` (bis Commit `5483dfb`) und dem Live-Zustand in Make und den geplanten Aufgaben.
Stellen, die ich nicht sicher belegen konnte, sind mit **(unsicher)** markiert.

Ergänzend: `README.md` (Technik-Überblick) und `docs/DAILY_RUN.md` (Checkliste für den täglichen Lauf).

---

## 1. Ziel und Auftrag

- Kanal: Instagram **@mino.recursion** und Facebook-Seite **Mino.recursion**, voll automatisiert.
- Auftrag von Raphael (21.10., 11:11 UTC): den Kanal wiederbeleben, die 5 ausgewählten Songs vermarkten,
  maximale Reichweite. Inhalt: energiegeladene, schnell geschnittene Psychedelic-Edits, die man mit
  „WTF ist gerade passiert" verlässt. Gute Hooks und Retention.
- Frequenz: ab 22.10. **6–8 Posts pro Tag**, am 21.10. nur 1–2 Posts zum Etablieren des Stils.
- Songs (WAV-Master): Not Just Music, My Mind, Digits, Mafia, Dat Swag (`engine/songs.json`).

## 2. Wie sich der Stil entwickelt hat (wichtig, damit niemand zurückfällt)

| Zeit (UTC) | Stand | Raphaels Reaktion |
|---|---|---|
| 11:11–12:30 | Erster Stil: bunte Acid-/Op-Art-Shader (Spiralen, Augen, Win98-Popups, Hook-Texte), Formate `drop`, `stare`, `error`, `eyes`, `words`. Ein Reel (Post #1) ging live. | „kompletter Quatsch", „sieht sehr billig aus", Farben weit weg von den Referenzbildern; das 2. Short (`stare`, optische Täuschung) „ergibt keinen Sinn". Kritik an den verbrauchten Credits (20–30 $). Schickt einen Referenz-Clip von Instagram (Bildschirmaufnahme). |
| 12:38 | Alter Stil gestoppt: Posting-Szenario deaktiviert, tägliche Aufgabe aus. Neuer Stil **`line`** (minimale Neon-Line-Art nach dem Referenz-Clip), 1 Test-Reel. | „besserer Ansatz, aber immer noch weit weg" |
| 12:48 | Version 2: 16tel-Flackern (Invert/Farbe/Spiegelkacheln/Stutter), Bloom, eine Geometrie pro Takt. | (keine eigene Antwort, direkt Version 3 angefragt) |
| 13:31 | Version 3: Silhouetten + Würfel-Feld, Cuts auf Achteln mit 16tel-Bursts, Strobe auf jedem Kick, Zoom/Glow-Puls. | Lob für den Würfel-Shot (Sek. 10–11). Wünscht klarere Objekte/Silhouetten (Menschen, Dinge, Formen), deutlich schnellere Cuts, Strobe und Puls. |
| 14:12 | **Version 4** (13 s, 48 Shots): Neon-Gradient-Map-Grading, harte 1-Frame-Strobes, Kamerafahrt (Zoom/Spin) pro Shot, Spiegelungen nur kurz, kein Wasserzeichen. | Vorher (14:03): „mehr Movement in den Shots, weniger gespiegelte Shots, ohne Watermark, Coloring wirkt brav und comic-mäßig". Nach V4 (14:23): **„Jetzt hast du es – richtig geiler Job"** → Freigabe. |
| 14:23–15:07 | Live-Schaltung: alte Queue gelöscht, Tageslauf auf `line` umgestellt, Posting + tägliche Aufgabe wieder an. | – |
| 15:49 | Captions auf den Stil der alten Kanal-Videos umgestellt (Abschnitt 4). | Auftrag: „Captions an den älteren Videos von mir orientieren". |
| 18:12 | Alle 8 eingeplanten Reels gezeigt. | – |

**Referenz-Reel:** `not_just_music-line-008` („line-008"), die freigegebene Version 4, Post am 21.10. um 19:45 (Berlin).
Plan-ID-Schema: `<song>-<format>-<seed>`, d. h. Song *Not Just Music*, Format `line`, Seed 8.
Neu erzeugen: `python3 engine/plan.py --song not_just_music --format line --seed 8` und dann `python3 engine/build.py build/plans/not_just_music-line-008.json`.
**(unsicher)** Ob das heute noch bit-genau dasselbe Video ergibt, habe ich nicht geprüft. Die Visuals sollten seit Commit `2dba08e` (V4) unverändert sein, danach kamen nur Caption- und Titel-Änderungen.
Die MP4 liegt in Dropbox unter `/mino.recursion/queue/<datum>/…` **(unsicher: genauer Ordner; laut Code `/mino.recursion/queue/2026-10-21…/not_just_music-line-008.mp4`)**.

### Regeln, die aus dem Feedback folgen
- Der `line`-Stil V4 ist **freigegeben und eingefroren**: Änderungen am Look nur nach Rücksprache mit Raphael.
- Nichts im alten bunten Acid-Stil posten, kein `stare`-Format.
- Erst **einen** Prototyp zeigen, dann Batches rendern (Credits sparen).
- Kein Wasserzeichen, kein Text im Bild.

## 3. Wie ein Reel entsteht

```
Songs: Dropbox /mino.recursion/songs/*.wav
  └─ engine/analyze_audio.py   BPM, Beat-Grid, Downbeats, Takte, Drops, Bass/Onset pro Video-Frame → build/analysis/<song>.json
      └─ engine/plan.py        „Creative Director": Format line → Schnittplan (Segmente, Flashes, Flicker) + Caption → build/plans/<id>.json
          └─ engine/build.py   baut ein HyperFrames-Projekt (template.html + Shader + runtime.js), rendert headless, muxed Audio → build/out/<id>.mp4
              └─ engine/publish.py  Upload nach Dropbox /mino.recursion/queue/<datum>/<id>.mp4 + Eintrag in Make-Queue
                  └─ Make 8092663 postet fällige Reels auf FB + IG
engine/daily.py = alles zusammen für einen Tag
```

### Format `line` (aktiv), Kenndaten
- 1080×1920, 30 fps, **8 Takte** des Songs ab einem Drop/Takt-Fenster (`pick_window(0, 8)`), bei Not Just Music ≈ **13 s**.
- Szenen aus `engine/shaders/lines.glsl` (15 Stück): weave, wiretunnel, wireroom, tesseract, stripesphere, dashsphere,
  wormhole, isocubes, burst, dots, zigzag, lasers, ridges, **silhouette** (11 Formen × 5 Looks), **cubes**.
  Gewichtung: silhouette 6, cubes 3, wireroom 3, Rest 1–2. Silhouetten und Würfel sind die Hero-Shots.
- Schnitt: Cuts auf Achteln (Wahrscheinlichkeit steigt mit Song-Energie), gelegentlich 16tel-Burst, ab und zu 1–3 Achtel Halt.
- Pro Shot: eigene Kamerafahrt (Zoom-Drift, Spin), Animationstempo 1,5–2,4×, ~30 % auf Off-White statt Schwarz.
- Post-FX: Neon-Gradient-Map (Palette aus der Referenz: tiefes Violett, Smaragd, Elektroblau, Magenta, Karminrot, Cyan),
  Bloom mit Beat-Puls, Zoom-Punch auf jedem Beat, leichter RGB-Split/Shake/Grain.
- Strobe: 1–2-Frame-Blitz auf jedem Kick; in 2 zufälligen Takten zusätzlich auf jedem Achtel.
- 16tel-Flicker: Invert (volle S/W-Inversion **höchstens alle 0,2 s**, bewusst wegen Fotosensitivität), Farbwechsel,
  kurze Spiegelkacheln (2–4 Sechzehntel, selten), Stutter-Zeitsprünge.
- Loop: letzter Zustand = erster Zustand (`close_loop`), damit das Reel nahtlos wiederholt.
- Render dauert ca. **5–6 min pro Reel** auf der Container-CPU (7 Reels ≈ 40 min).

Ältere Formate (`drop`, `stare`, `error`, `eyes`, `words`) sind noch im Code (`--format`), werden aber nicht gepostet.

## 4. Caption-Regeln

Umgesetzt in `Director.story_caption()` (`engine/plan.py`), Vorrat in `engine/captions.json`.

Aufbau jeder Caption:
```
<absurde Ich-Mikrogeschichte>

🎧 mino.recursion — <Songtitel>
⚠️ flashing lights

<5 Hashtags aus einem der Sets>
```

- Stimme wie die **alten @mino.recursion-Reels**: absurde, mystische, zusammenhanglose Mini-Geschichte in Ich-Form,
  Gen-Z-/Meme-Humor, oft britischer Slang. Typische Einstiege: „So there I was …", „Yo so basically … innit",
  „Okay so …", „Long story short …".
- Ein paar Keywords einstreuen: trance, fractal, third eye, frequency, dimension, 152 BPM, tesseract, neon,
  wireframe, silhouette (passt zu den Visuals).
- Jede Geschichte wird nur einmal benutzt. Auswahl: `idx = (day*7 + slot) % len(stories)` aus dem Seed.
  Der Vorrat muss also wachsen, sonst wiederholen sich Geschichten → der tägliche Lauf hängt **7 neue Geschichten pro Tag** an.
- Hashtags: 5 Stück, Sets in `captions.json` (z. B. `#psychedelicart #abstractart #edit #trancemusic #fevercore`).
- Stand 21.10.: 42 Geschichten (reicht für 6 Tage ohne Nachschub).
- Offen: „🎧 Songtitel" und „⚠️ flashing lights" sind Ergänzungen gegenüber den alten Captions. Raphael wurde gefragt,
  ob sie raus sollen; **(unsicher)** eine Antwort darauf habe ich nicht gefunden.
- Der frühere Hinweis „full track on Spotify, link in bio" steht nur noch in den alten Formaten, nicht mehr bei `line`.
- FB-Reel-Titel: Hook-Text, bei `line` (ohne Text) Fallback `mino.recursion — <Songtitel>`.

## 5. Tageslauf und Zeitplan

- **Post-Slots** (Europe/Berlin, je ±6 min Jitter, deterministisch aus dem Datum):
  07:40, 10:15, 12:40, 15:10, 17:45, 19:50, 21:40 (+23:05 bei 8 Posts). Standard: **7 Reels/Tag**.
- Songs rotieren pro Slot über alle lokal oder in Dropbox verfügbaren Songs. Seed = `(date.toordinal() % 10000)*10 + slot`
  (daher IDs wie `line-99110`).
- Fortschritt pro Tag in `build/daily/<datum>.json`; ein abgebrochener Lauf setzt dort wieder an.
- Make prüft alle 15 min zwischen 06:00 und 23:59, ob ein Reel fällig ist, und postet **eins pro Durchlauf**.

## 6. Make (eu1, Team 690392)

| Szenario | ID | Auslöser | Was es tut |
|---|---|---|---|
| mino.recursion – Dropbox links (Claude) | 8092603 | Webhook 3948188 | `op` = `link` (temporärer Download-Link), `upload` (temporärer Upload-Link, 4 h) oder `list` (Ordnerliste). Nur Pfade unter `/mino.recursion/`. |
| mino.recursion – Queue füllen (Claude) | 8092677 | Webhook 3948189 | Schreibt `{key, due_ts, video_id, dropbox_path, caption, title, thumb_ms}` in Data Store 227426 (nur wenn Pfad mit `/mino.recursion/` beginnt), antwortet `{"status":"queued"}`. |
| mino.recursion – Reel-Queue posten FB+IG (Claude) | 8092663 | alle 900 s, 06:00–23:59 | Holt den ältesten Eintrag mit `due_ts <= jetzt`, löscht ihn aus der Queue, holt Dropbox-Link, lädt als **FB-Reel** auf Seite 996362056896277 hoch, holt neuen Link, postet **IG-Reel** (Account 17841461423523405, `share_to_feed`, Thumbnail-Offset `thumb_ms`), loggt in Data Store 227427. Fehler bei FB oder IG werden abgefangen und als `FAILED` geloggt. |

Data Stores:
- `mino_recursion_queue` (227426, Struktur 650887): wartende Reels. Stand 21.10. abends: 7 Einträge (22.10.).
- `mino_recursion_posted` (227427, Struktur 650888): gepostete Reels mit `fb_video_id`, `ig_media_id` (`FAILED` = Fehler), `posted_ts`.

Hinweis: Weil der Queue-Eintrag **vor** dem Posten gelöscht wird, wird ein fehlgeschlagener Post nicht automatisch wiederholt.
Bereits live gegangene Posts kann die Automatisierung nicht löschen; das muss Raphael in der App machen (betraf Post #1 im alten Stil).

## 7. Geplante Aufgaben (Claude)

| Name | ID | Zeit | Was |
|---|---|---|---|
| mino.recursion – Reels für die nächsten Tage rendern | `trig_01BYeArLYWqtVC6agdfUYS7L` | täglich 20:20 Europe/Berlin | Läuft in der Aufbau-Sitzung weiter. Hängt 7 neue Captions an (commit), hält die Queue für **morgen und übermorgen** mit je 7 Reels gefüllt (`daily.py --date … --count 7`), prüft heutige Posts (`FAILED`, Fehler-Executions in 8092663), sichtet 1–2 Renders als Kontaktbogen, berichtet kurz auf Deutsch. Der Stil darf dabei nicht verändert werden. |
| Tägliche Reel-Vorschau | `trig_01MarvuLk1x75JMci4SNxzyX` | täglich 05:07 UTC (= 07:07 MESZ, ab 26.10. 06:07 MEZ) | Angelegt am 21.10. um 18:15 aus diesem Projekt. Listet die heutigen Reels mit Zeit, Caption und Vorschaubild, prüft den Caption-Stil. Ändert und postet nichts. |

## 8. Benötigte Zugänge (nur Namen, keine Secrets)

- **Make-Webhooks** (URLs nie ins Repo): `MR_DROPBOX_HOOK` (Hook 3948188) und `MR_QUEUE_HOOK` (Hook 3948189),
  als Env-Variablen oder in `config.local.json` (gitignored, Schlüssel `dropbox_hook`, `queue_hook`). Die URLs liest der Lauf per Make-MCP `hooks_get`.
- **Make-Verbindungen:** „My Dropbox connection" (4195998, OAuth) und „My Facebook connection" (5649789, OAuth, Konto „Uberan Mino";
  deckt FB-Seite und IG-Business ab). **(unsicher)** Make zeigt bei 5649789 ein Ablaufdatum 03.05.2026, die Posts am 21.10. liefen trotzdem.
  Falls Posts mit `FAILED` enden, zuerst diese Verbindung in Make neu autorisieren.
- **Make-MCP** und **Dropbox** in der Claude-Sitzung (für `hooks_get`, Data-Store-Kontrolle).
- **GitHub-Zugriff** auf `UberanMino/mino.recursionautomation` (Push auf `claude/relaxed-dijkstra-teb4bo`).
- Keine eigenen API-Keys im Code; Facebook/Instagram laufen ausschließlich über Make.

## 9. Bekannte offene Punkte

- **Nur „Not Just Music" verfügbar.** Die anderen 4 WAVs (Digits, My Mind, Mafia, Dat Swag) liegen in Google Drive,
  waren aber nicht erreichbar (Drive-Tool lädt nur bis 10 MB, Google-Verbindungen in Make abgelaufen).
  Lösung: Raphael legt die WAVs nach Dropbox `/mino.recursion/songs/` (Originalnamen reichen, `daily.py` normalisiert sie),
  der nächste Tageslauf nimmt sie automatisch mit.
- Kosten: Rendern läuft auf der Container-CPU, die Credits gehen für die Claude-Arbeit drauf. Angebot an Raphael:
  bei Bedarf auf 5–6 Reels/Tag reduzieren. **(unsicher)** Entscheidung dazu nicht gefunden.
- Die Referenzbilder (Drive `mino.recursion.visuell`) und der Instagram-Referenz-Clip sind nicht im Repo.
- Wireframe-Gesicht, Partikel-Silhouette und 3D-Neon-Röhren aus dem Referenz-Clip sind noch nicht umgesetzt
  (wäre am ehesten mit Three.js in HyperFrames machbar).

## 10. Nützliche Befehle

```bash
npm ci
python3 engine/daily.py --date 2026-10-23 --dry-run          # Plan anzeigen
python3 engine/daily.py --date 2026-10-23 --count 7          # rendern + hochladen + einplanen
python3 engine/plan.py --song not_just_music --format line --seed 8   # einzelnen Plan bauen
python3 engine/tools/preview_plan.py build/plans/<id>.json   # Kontaktbogen ohne vollen Render → build/review/
python3 engine/tools/line_sheet.py                           # Übersicht aller Line-Szenen
```

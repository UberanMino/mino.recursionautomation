# Daily run (für die geplante Claude-Session)

Ziel: jeden Abend die Reels für den **nächsten** Tag rendern und in die Make-Queue legen.
Make postet sie dann zu den Slot-Zeiten (Europe/Berlin) auf FB-Seite *Mino.recursion* und IG *@mino.recursion*.

1. Repo auf Branch `claude/relaxed-dijkstra-teb4bo`, `npm ci` (falls `node_modules` fehlt).
2. `config.local.json` schreiben (gitignored). Die URLs liefern die Make-Hooks
   3948188 (Dropbox links) und 3948189 (Queue füllen) — per Make-MCP `hooks_get`:
   ```json
   {"dropbox_hook": "https://hook.eu1.make.com/…", "queue_hook": "https://hook.eu1.make.com/…"}
   ```
3. `python3 engine/daily.py --date <morgen> --count 7`
   - dauert im Line-Stil ca. 5–6 min pro Reel (~40 min für 7) → im Hintergrund mit Timeout 3600000 ms starten
   - lädt fehlende Songs aus Dropbox `/mino.recursion/songs/` (Dateinamen wie in `engine/songs.json`)
   - rendert, lädt nach `/mino.recursion/queue/<datum>/` hoch, legt Queue-Einträge an
   - bricht er ab: einfach neu starten, `build/daily/<datum>.json` merkt sich den Fortschritt
4. Kontrolle:
   - Make Data Store `mino_recursion_queue` (227426): 7 Einträge mit `due_ts` am Folgetag
   - Make Data Store `mino_recursion_posted` (227427): heutige Posts, `FAILED` = Fehler bei FB oder IG
   - Szenario 8092663 (Reel-Queue posten) aktiv, keine Fehler-Executions
5. Captions: `engine/captions.json` um 7 neue Geschichten erweitern — gleiche Stimme wie die alten
   @mino.recursion-Reels (absurde, mystische Ich-Mikrogeschichte, „So there I was …" / „Yo so basically … innit",
   Gen-Z-Humor, ein paar Keywords wie trance, fractal, third eye, frequency, 152 BPM). Keine Wiederholungen. Committen.
6. Stichprobe: 1–2 Renders als Kontaktbogen ansehen (`build/review/`), bevor sie live gehen.
7. Shot-Gedächtnis: `daily.py` trägt jedes geplante Reel in `engine/shot_history.json` ein
   (welche Shots, welcher Hero) und committet + pusht die Datei am Ende selbst. Meldet es
   `warn: git … failed`, die Datei von Hand committen und pushen, sonst wiederholen sich die Reels.
8. `python3 engine/shots.py report` ausführen. Steht dort **NEUE SHOTS FÄLLIG** → Shot-Werkstatt (unten).
   `daily.py` druckt denselben Hinweis als `!!!`-Block am Anfang und Ende seines Logs: dann die
   Shot-Werkstatt in derselben Sitzung erledigen, bevor sie endet.

## Shot-Werkstatt (Abwechslung)

Jedes Reel castet 7–9 Shots aus dem Katalog in `engine/shots.py` (Szene + Variante, z. B.
`silhouette/alien/echo`, `polytunnel/hex`) und schneidet nur zwischen diesen. Gewählt wird gegen das
Gedächtnis: Cooldown für die letzten 2 Reels, max. 4 von 21 Reels pro Shot (5 pro Familie),
mindestens 3 im Fenster unbenutzte Shots pro Reel, Bonus für kaum genutzte Shots, Hero nicht zweimal
innerhalb von 7 Reels, kein Shot über 24 % der Schnitte. Regeln stehen oben in `engine/shots.py` (`RULES`).

Damit der Feed nicht trotzdem einschläft, kommen regelmäßig neue Shots dazu (Report meldet es nach
4 Tagen ohne neuen Shot):
1. 1–2 neue Szenen in `engine/shaders/lines.glsl` schreiben (vor `vec3 scene(...)`, in `scene()` eintragen)
   oder neue Silhouetten-Formen in `shapeSD()`. Stil halten: Neon-Line-Art, eine Akzentfarbe, schwarzer
   (optional off-white) Grund, dünne Linien, Bewegung über `uT`, Kick über `uKick`. Günstig rechnen
   (SwiftShader!): keine Raymarch-Schleifen, Schleifen ≤ ~120 Iterationen.
2. In `engine/shots.py` eintragen: `LINE_SCENES` (Name + Parameter-Sampler), ggf. `LINE_WHITE_OK`,
   Katalog-Eintrag in `_catalog()` mit `added="<heute>"` (Silhouetten: Name an `SIL_SHAPES` anhängen,
   Reihenfolge = Shape-ID).
3. Kontaktbogen prüfen: `python3 engine/tools/line_sheet.py --since <heute> --white` → `build/linesheet.jpg`
   ansehen. Nur was im Stil sitzt und lesbar ist, bleibt drin.
4. Committen. Neue Shots bekommen automatisch den Neuheits-Bonus und laufen in den nächsten Tagen öfter.

Neue Songs: WAV nach Dropbox `/mino.recursion/songs/` legen und in `engine/songs.json` eintragen
(`file` = `assets/audio/<name>.wav`, Dateiname muss dem Dropbox-Namen entsprechen).

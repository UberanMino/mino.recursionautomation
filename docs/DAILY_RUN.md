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
5. Stichprobe: 1–2 Renders als Kontaktbogen ansehen (`build/review/`), bevor sie live gehen.

Neue Songs: WAV nach Dropbox `/mino.recursion/songs/` legen und in `engine/songs.json` eintragen
(`file` = `assets/audio/<name>.wav`, Dateiname muss dem Dropbox-Namen entsprechen).

# Version 2: Flug durch eine 3D-Welt aus Musik

Code: `synesthesia/signals.py` (Steuersignale), `synesthesia/tunnel.py` (Welt, Kamera, Feedback).
Standard-Look von `python3 -m synesthesia` (`--look tunnel`); die 2D-Version 1 gibt es weiter mit `--look butterfly`.
Die Grundregeln aus `docs/MAPPING_RULES.md` gelten weiter: R1 Tonhöhe → Höhe, R2 Lautheit → Helligkeit (Sone, Oklab),
R3 Timing (Bild nie nach dem Ton), R4 Klangfarbe → Farbe, R6 Chaos-Maß. Neu ist, **wo** im Raum das passiert und
**wie** sich die Kamera bewegt.

```bash
python3 -m synesthesia song.wav --start 47.5 --dur 30 --out out.mp4             # 3D-Flug
python3 -m synesthesia song.wav --start 47.5 --dur 30 --out out.mp4 --overlay   # mit Abschnitt, Kurs-Minimap, Reglern
```

## Grundprinzip: Zeit = Vorwärtsbewegung

Die Kamera fliegt mit der Zeit vorwärts. Was im Song zum Zeitpunkt t passiert, wird an der Stelle der Flugbahn
gebaut, an der die Kamera zum Zeitpunkt t ist. Dadurch gilt:

- **Vor dir liegt die Zukunft**, sie kommt aus der Tiefe auf dich zu (gedimmt auf 35 %, sie wird beim Näherkommen hell).
- **Jedes Stück Musik erreicht die „Jetzt“-Distanz exakt in dem Moment, in dem es klingt** (Kamera fliegt d₀ = 2
  Einheiten hinter dem Jetzt-Punkt; dort füllt der Querschnitt das Bild von y = 7 % bis 93 %, also genau R1).
- Hinter dir liegt die Vergangenheit; sie verschwindet innerhalb von 1/8 Takt.

Ein Takt bei Tempo 1 ist 2 Einheiten tief, also ist das, was einen Takt voraus liegt, halb so groß, zwei Takte
voraus ein Drittel (Zentralprojektion `x = f · X / Z`). Das ist der Zoom: echte Perspektive, kein 2D-Trick.

## W1 Die Welt: der Song als Tunnel

Jeder Video-Frame ist ein Querschnitt quer zur Flugbahn, gebaut im lokalen Bahn-Koordinatensystem (rechts R, oben U):

`P = X(t) ± a · x(h) · R(t) + h · U(t)` mit `h = 2 · log(f/30 Hz) / log(16 kHz/30 Hz) − 1` (−1 = 30 Hz = Boden,
+1 = 16 kHz = Decke)

- **Linke Wand = linker Kanal, rechte Wand = rechter Kanal** (R5), Helligkeit nach R2, Farbe nach R4.
- **Form des Querschnitts = Schärfe des Klangs (Bouba/Kiki):** Superellipse `|x|ⁿ + |h|ⁿ = 1` mit
  `n = 2^(1,8 − 2,4 · Schärfe)`. Weiche, tonale Musik → rund (n ≈ 2,5), scharfe, perkussive, helle Musik → spitz
  (n ≈ 1, Raute). Schärfe = ½ · Helligkeit der Klangfarbe + ½ · perkussiver Anteil. Weiche Klänge ↔ runde Formen,
  scharfe ↔ eckige Formen ist eine bekannte crossmodale Zuordnung (Köhler; Ramachandran & Hubbard 2001).
- **Chaos zerfranst die Wände:** Radius × (1 + 0,35 · C^1,1 · Rauschen).
- **Drums sind Rippen** quer durch den Tunnel, auf ihrer Tonhöhe: Kick am Boden, Snare/Clap in der Mitte, Hi-Hats an
  der Decke. Ein Four-on-the-floor-Groove wird zu gleichmäßig auf dich zukommenden Bodenrippen, die genau auf dem
  Schlag ankommen. Helligkeit relativ zum lautesten Schlag derselben Klasse (Kick 90 %, Snare 55 %, Hat 30 %).
- **Staubfeld** um den Tunnel (feste Punkte, 1,8–5 Einheiten von der Bahn): macht Geschwindigkeit und Richtung lesbar;
  es funkelt mit dem Air-Band (4–16 kHz).

## W2 Die Flugbahn: Richtung aus der Musik

Die Bahn wird integriert wie ein Fahrzeug, das die Musik steuert:

`dX/dt = v · T`,   `dM/dt = M · [ω]ₓ`,   `M = [R U T]`,   `ω = (−Steigen, Kurve, Rollen)` (rad pro Takt)

Eine Raumkurve ist durch Krümmung und Torsion bis auf ihre Lage eindeutig bestimmt (Frenet). Konstante Drehraten
ergeben eine **Helix**: wiederholt sich die Musik gleichmäßig, wird der Kurs eine regelmäßige Spirale; ändert sie
sich, biegt er ab; ist sie chaotisch, wird er ein Zufallspfad.

| Größe | Formel (pro Takt) | Musikalische Bedeutung |
|---|---|---|
| Tempo v | `0,45 + 0,9 · Lautheit_Takt + 0,8 · Spannung + Kick-Schub` | laute Teile fliegen schneller, Build-ups beschleunigen |
| Kick-Schub | `+0,55 · Kick/Kick₉₀`, klingt über 1/8 Takt ab; Drop-Eintritt `+2,5` über 1/2 Takt | jeder Kick schiebt nach vorn (Pump), der Drop katapultiert |
| Steigen | `0,25 · tanh(0,8 · Tonhöhenbewegung) + 0,35 · Spannung − Sturz` | Musik steigt (heller, höher) → Kurs steigt; Build-up = Anstieg |
| Sturz | Impuls beim Drop-Eintritt, insgesamt 0,7 rad nach unten | Achterbahn: hochziehen im Build-up, runterstürzen in den Drop |
| Kurve | `0,35 · tanh(6 · Stereo-Balance)` | lenkt zur lauteren Seite |
| Helix | `0,3 · Lautheit · (1 − C) ·` (Richtung je Abschnitt um den goldenen Winkel 137,5° gedreht), nur in Drop/Groove | gleichmäßiger Groove → gleichmäßige Spirale; jeder neue Abschnitt dreht in eine maximal andere Richtung |
| Rollen | `±(0,3 + 1,0 · Klangfarbengeschwindigkeit) · (1 − C/2)`, Vorzeichen wechselt je Abschnitt | Klangfarbe ändert sich → Tunnel verdreht sich |
| Zufall | `0,6 · C^1,1 · geglättetes Rauschen` auf Steigen und Kurve | Chaos → unruhiger Kurs |

## T Zeitskalen: was worauf reagiert

Damit das Bild sinnvoll auf Änderungen reagiert, gilt: **Eine Bildgröße hängt nur von Musikgrößen derselben
Zeitskala ab, und Änderungen der Musik treiben Bewegung, Pegel treiben Erscheinung.**

| Zeitskala | Musik | Bild |
|---|---|---|
| Impuls (< 100 ms) | Kick, Snare, Hats (Kick = getrackter Beat mit ≥ 3 dB mehr 30–60 Hz als zwischen den Beats, weil der Offbeat-Bass dasselbe Band teilt) | Schub, Belichtungs-Punch, Rippen, Shake |
| Beat (~0,4 s) | Bandlautheit (sofortiger Anstieg, 90 ms Abfall), Klangfarbengeschwindigkeit | Wandhelligkeit, Farbdrift |
| Takt (~1,6 s) | Lautheit, Tonal-Anteil, Stereo-Balance, Tonhöhenbewegung, Chaos | Tempo, Kurs, Trail-Länge, Unschärfe |
| Abschnitt (4–32 Takte) | Struktur: Foote-Novelty auf der Selbstähnlichkeitsmatrix der Beats, Grenzen auf Taktanfänge gelegt; Typ: Drop (viel Bass, laut), Break (wenig Bass), Build-up (Abschnitt vor einem Drop), Groove | Helix-Richtung, Rollrichtung, Kaleidoskop-Zähligkeit, Drop-Ereignisse |

**Spannung** (Build-up) = Annäherung an den nächsten Drop: `((t − t_Start)/L)²` über die letzten ≤ 8 Takte vor dem
Drop (quadratisch = beschleunigte Annäherung), außerhalb davon die Hälfte des gemessenen Anstiegs von Lautheit,
Helligkeit und Rauschanteil; in Drops 0. Weil der Song offline analysiert wird, ist der Drop vorher bekannt.

Digits: Breaks/Build-ups 0–28,6 s, 53,8–66,5 s, 98,1–104,2 s, 116,7–129,3 s; Drops ab 28,6 / 66,5 / 104,2 / 129,3 s.

## FB Feedback-Loops

Das fertige Bild läuft durch eine Kette von Video-Feedback-Schleifen: `Bild = max(Welt, g · FB(vorheriges Bild))`.
Die Verknüpfung „aufhellen“ (Maximum) statt Addition sorgt dafür, dass sich Spuren nicht zu Weiß aufsummieren.

| # | Schleife | Formel | Treiber |
|---|---|---|---|
| FB1 | Zoom | Vergrößerung pro Frame `1 + 0,9 · Δs/d₀` um den Jetzt-Punkt | Fluggeschwindigkeit: Spuren strömen mit der Bewegung nach außen (Warp-Streifen) |
| FB2 | Rollen | Spuren drehen mit der Kamera | Rollrate der Bahn |
| FB3 | Farbdrift | Spuren drehen ihren Farbton um die Grauachse, `1,6 rad/Takt · Klangfarbengeschwindigkeit` | Klangfarbe ändert sich → Nachbilder verfärben sich |
| FB4 | Prisma | R und B zoomen ±`0,012 · Air-Band` unterschiedlich | Hi-Hats/Höhen → Farbsäume |
| FB5 | Selbst-Strömung | Spuren fließen entlang ihrer eigenen Helligkeitskonturen, `3,2 px · C^1,1` | Chaos → flüssige Verwirbelung |
| FB6 | Unschärfe/Schärfe | `κ = 0,5 · (2 · Tonal-Anteil − 1)`, begrenzt auf −0,45 … 0,25; κ > 0 weichzeichnen, κ < 0 schärfen | legato/Pads → weich, perkussiv → scharf |
| FB7 | Gedächtnis | Trail-Länge `0,07 + 0,3 · Tonal-Anteil` s | gehaltene Klänge hinterlassen lange Spuren, trockene kurze |
| FB8 | Kaleidoskop | Spuren N-fach gespiegelt, Anteil `1,6 · (1 − C) · (1 − Lautheit) − 0,3`; N je Abschnitt 4/6/8/3 | ruhige, geordnete Passagen → Symmetrie |
| FB9 | Takt-Echo | Geist des Bildes von genau 1 Takt vorher, `0,22 · (1 − C)`, nur im selben Abschnitt | Wiederholung → Bild überlagert sich deckungsgleich, Neues → Doppelbild |
| FB10 | Belichtung | `+0,8 · Kick` (60 ms), `+2,2` beim Drop-Eintritt (250 ms) | Impulse |
| FB11 | Shake | `9 px · Sub-Bass²` | Sub-Bass-Druck |
| FB12 | Negativ | ein invertierter Frame beim Drop-Eintritt | Strukturbruch |

Alle Zahlen stehen in `World3D` und `Feedback` in `synesthesia/tunnel.py`. Die Richtung jeder Kopplung ist begründet,
die genauen Werte sind Einstellungen, die ich nach Augenmaß am Prototyp gesetzt habe, nicht gemessene Konstanten.

## Quellen (zusätzlich zu Version 1)

- J. Foote (2000): Automatic audio segmentation using a measure of audio novelty. *IEEE ICME*.
- W. Köhler (1929): *Gestalt Psychology*; V. S. Ramachandran & E. M. Hubbard (2001): Synaesthesia — a window into
  perception, thought and language. *Journal of Consciousness Studies* 8 (Bouba/Kiki).
- Frenet–Serret-Formeln: Standard-Differentialgeometrie (Kurve durch Krümmung und Torsion bestimmt).

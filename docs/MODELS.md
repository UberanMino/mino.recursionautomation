# Weitere Modelle: dieselbe Musik, andere Naturgesetze

Code: `synesthesia/models/` (je eine Datei pro Modell, gemeinsames Gerüst in `base.py`).
Alle Modelle lesen dieselben Steuersignale wie der 3D-Tunnel (`synesthesia/signals.py`: Bandlautheit, Spektralprofil
L/R, Tonal-Anteil, Klangfarbe, Chaos, Abschnitte, Drum-Hits). Jedes Modell ersetzt die Bildwelt durch **ein**
dynamisches System, dessen Parameter die Musik setzt.

```bash
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model lorenz    --out a.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model julia     --out b.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model kepler    --out c.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model grayscott --out d.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model chladni   --out e.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model fractal   --out f.mp4
python3 -m synesthesia song.wav --start 47.5 --dur 30 --model morph     --out g.mp4
#   --no-caption lässt die Untertitel mit den Gesetzen weg
```

## Was alle Modelle gemeinsam haben

- **R3 Timing:** Ein Klang zur Zeit t erscheint im Frame floor(t · fps), das Bild kommt nie nach dem Ton.
- **R4 Farbe = Klangfarbe** (Oklab, wie in Version 1).
- **K Kick-Bounce** (neu, auch im 3D-Tunnel): Jeder Kick lenkt eine gedämpfte Feder aus,
  `x(t) = Σ wᵢ · e^(−ζω(t−tᵢ)) · cos(ω_d (t−tᵢ))`, Periode ½ Beat, Dämpfung ζ = 0,3, Gewicht wᵢ = Kick-Stärke
  relativ zum 90.-Perzentil. Der Ausschlag ist im Frame des Kicks am größten, schwingt einmal über und ist vor dem
  nächsten Kick fast abgeklungen. Das ist das „Federn“ auf jedem Kick. Jedes Modell hängt die Feder an eine
  eigene Größe (siehe unten), immer zusätzlich als Zoom-Punch.
- **Strukturbruch:** Beim Drop-Eintritt ein invertierter Frame und ein Schub.

## A · Lorenz-Flug (`lorenz.py`)

`dx/dt = σ(y − x)`, `dy/dt = x(ρ − z) − y`, `dz/dt = xy − βz`, σ = 10, β = 8/3.

| Musik | Bild |
|---|---|
| Chaos C | `ρ = 24,74 + 40 · (C − Median C)`. Unter 24,74 sind die beiden Fixpunkte stabil: die Bahnen spiralen in zwei ruhige Wirbel (Ordnung). Darüber öffnet sich der seltsame Attraktor, die Bahnen springen unregelmäßig zwischen den Flügeln (Chaos). Die Schwelle liegt beim Median des Songs. |
| Frequenzband | jedes Teilchen gehört zu einem Band; Helligkeit = Lautheit des Bands (R2) |
| Stereo | linker Flügel (x < 0) zeigt den linken Kanal, rechter Flügel den rechten (R5) |
| Tonhöhe | Eigenzeit des Teilchens läuft mit (f/500 Hz)^0,2: hohe Töne bewegen sich schneller (statt R1) |
| Lautheit | Systemzeit 1,2 Einheiten pro Takt · (0,6 + 0,8 · Lautheit): laut = schneller |
| Kick | alle Teilchen bekommen einen kleinen Zufallsstoß. Im chaotischen Bereich wächst er exponentiell (positiver Lyapunov-Exponent) und zerstreut die Wolke, im geordneten Bereich verschwindet er. Dazu die Feder als Zoom-Punch. |
| Tonal-Anteil | Spurlänge (gehaltene Töne = lange Linien) |
| Abschnitt | Kamera umkreist den Attraktor und fährt über 16 Takte heran; Build-up hebt sie an |

## B · Julia-Zoom (`julia.py`)

`z → z² + c` mit `c = λ/2 − λ²/4`, `λ = ρ · e^(2πiθ)` (λ = Multiplikator des Fixpunkts α = λ/2).

| Musik | Bild |
|---|---|
| Klangfarbe | Drehzahl θ zwischen etwa 0,30 und 0,45: θ = 1/3 ergibt dreiarmige Spiralen, 2/5 fünfarmige, irrationale Werte Wirbel |
| Chaos | `ρ = 1 + 0,45 · (C − Median)`, begrenzt auf 0,88 … 1,12. ρ < 1: zusammenhängende Kurve; ρ > 1: für die meisten θ zerfällt die Menge zu Staub |
| Zeit | endloser Spiral-Zoom um den abstoßenden 2-Zyklus-Punkt β = (−1 + √(−3 − 4c))/2. Dort ist das Bild selbstähnlich mit dem komplexen Faktor μ = 4(1 + c); Fenster `z = β + μ^−(m+δ) · w₀ · u`. Ein Zoom-Schritt δ → δ + 1 ist ein exakter Selbstähnlichkeits-Schritt, also läuft der Zoom ohne Ende. |
| Tempo, Lautheit | `dδ/dt = (0,5 + 0,5 · Lautheit)` pro Beat + Kick-Schub + Drop-Schub |
| Frequenz | Fluchtzeit χ = ν(z) − 2δ (zoom-invariant): grobe Bänder weit weg von der Menge = Bass, feine Filigranstruktur am Rand = Höhen; Helligkeit = Lautheit dieser Frequenz (räumliche ↔ akustische Frequenz, statt R1) |
| Stereo | linke Bildhälfte = linker Kanal, rechte = rechter |
| Kick | Feder: Fenster schrumpft um 14 % und federt zurück, Belichtung federt mit; das Innere pulsiert |

Das Innere ist in der Koenigs-Koordinate des anziehenden Fixpunkts gezeichnet. Die ist unter der Abbildung
invariant, deshalb drehen sich die Spiralarme mit θ.

## C · Kepler-System (`kepler.py`)

| Musik | Bild |
|---|---|
| Tonhöhe | jedes 1/8-Oktav-Band ist ein Ring von Körpern mit Umlauf `ω = ω₀ · (f/30 Hz)^(1/3)` (9 Oktaven Audio → 3 Oktaven Umlauf), ω₀ = eine Runde pro 4 Takte |
| Bahnradius | 3. Keplersches Gesetz `T² ∝ a³` → `a ∝ ω^(−2/3)`: Bass außen und langsam, Höhen innen und schnell. Benachbarte Ringe laufen gegeneinander (differentielle Rotation), jede Ausrichtung wickelt sich zu Spiralarmen auf |
| Lautheit | Zentralmasse M = 0,5 + Lautheit, bei festem a gilt ω ∝ √M: laute Teile drehen schneller |
| Chaos | Exzentrizität `e = 0,6 · C^1,1 · nₖ` und Neigung `i = 0,35 · C · n′ₖ`. Positionen aus der Kepler-Gleichung `E − e sin E = M` (Körper werden im Perihel schneller). Ordnung = flache runde Ringe, Chaos = gekreuzte, gekippte Ellipsen |
| Sub-Bass | Glühen der Sonne |
| Kick | Feder: alle Bahnen federn nach außen (Radius · (1 + 0,28 x)), Kamera stößt hinein, Spuren werden kurz geschnitten |

## D · Gray-Scott-Reaktion (`grayscott.py`)

`∂u/∂t = D_u ∇²u − uv² + F(1 − u)`, `∂v/∂t = D_v ∇²v + uv² − (F + k)v` (Pearson 1993), Gitter 352 × 198.

| Musik | Bild |
|---|---|
| Tonal-Anteil, Chaos | `(F, k) = (1 − c)[h · Labyrinth + (1 − h) · Punkte] + c · Chaos`, mit Labyrinth (0,055 / 0,062), Punkte (0,0367 / 0,0649), Chaos (0,018 / 0,051). Die drei Ecken habe ich auf diesem Gitter nachgerechnet (`gs.py`-Test, 3000 Schritte): Labyrinth, Punkte, unruhige Punkte/Wellen. |
| Frequenz | Zeilen = Frequenzen (R1, oben hoch): Futterrate jeder Zeile `F · (0,85 + 0,3 · ψ(f))`, linke Hälfte linker Kanal, rechte Hälfte rechter (R5) |
| Drums | jeder Schlag tropft Katalysator v auf seiner Tonhöhe ein (Kick unten, Snare Mitte, Hats oben), Größe ∝ Lautheit |
| Lautheit | Reaktionsgeschwindigkeit: 10 + 22 · Lautheit Schritte pro Frame; Helligkeit = v · Lautheit der Zeile (R2) |
| Zeit | die Fläche wächst ständig: Zoom um 1 + 0,003 · (0,5 + Lautheit) pro Frame. Das gedehnte Muster teilt sich und füllt die Fläche nach |
| Kick | Feder: Zoom-Punch und Belichtung |

## E · Chladni-Platte (`chladni.py`)

Rechteckige Platte 1 × 16/9 (das Bild), Moden `φ = cos(nπx) · cos(mπy/B)`. Für Biegewellen in einer dünnen Platte
wächst die Frequenz mit dem Quadrat der Wellenzahl: `f ∝ n² + (m/B)²`.

| Musik | Bild |
|---|---|
| Tonhöhe | die bis zu 3 stärksten tonalen Spitzen (40 Hz – 2 kHz, gewichtet mit dem Tonal-Anteil) regen je die Mode mit `n² + (m/B)²` am nächsten an `2f / 55 Hz` an. Derselbe Ton ergibt immer dieselbe Figur, Akkorde überlagern ihre Moden |
| Lautheit | Amplitude der Moden (sofortiger Anstieg, ½ Takt Abfall) und Schüttelstärke |
| Sand | Körner rutschen den Gradienten der Schwingungsenergie φ² hinab und werden proportional zu \|φ\| geschüttelt, sammeln sich also auf den Knotenlinien, wo die Platte stillsteht (wie bei Chladni) |
| Chaos | zusätzliches, amplitudenunabhängiges Zittern: Ordnung = scharfe Linien, Chaos = verwischter Sand |
| Kick | Feder: die ganze Platte wird geschüttelt, der Sand springt von den Linien und setzt sich wieder |

Hier trägt die Höhe keine Tonhöhe; die Tonhöhe steckt im Muster.

## F · Fraktal-Flug (`fractal.py`)

Endloser Flug durch eine 3D-Fraktalwelt, per Raymarching gerendert (numba, alle Kerne). Die Welt ist ein Gitter aus
Kaleidoskop-IFS-Würfeln der Menger-Familie (Periode 2):
`n-mal: p = |p|, sortieren (x ≥ y ≥ z), p = Rot · p, p = s · p − c · (s − 1)` (z nur oberhalb der Mittelebene),
Abstand = Box(p) / sⁿ. Mit s = 3, c = (1, 1, 1) und Rot = Einheit ist das der Menger-Schwamm, durch jeden Würfel läuft
ein leerer Korridor entlang z.

| Musik | Bild |
|---|---|
| Zeit | Vorwärtsflug wie im Tunnel: Tempo = 0,45 + 0,9 · Lautheit + 0,8 · Spannung + Kick-Schub, ein Würfel pro Takt bei Tempo 1 |
| Chaos | Faltungsrotation um z (0,9 · C^1,1 · n(t)) und um x (0,6 · C^1,1 · n′(t)), beide auf 0,6 rad begrenzt, ab der zweiten Faltungsebene; Skala s = 3 + 0,35 · C^1,1. Ordnung = exakte Kristall-Architektur, Chaos = verdrehte, überwucherte Feinstruktur |
| Klangfarbe | Architektur: c = (1, 1 + 0,25 \|z₁\|, 1 + 0,25 \|z₂\|); Farbton der Palette |
| Frequenz, Lautheit | jede Wand leuchtet mit der Lautheit der Frequenz ihrer Höhe (Boden 30 Hz, Decke 16 kHz), links vom Kurs linker Kanal, rechts rechter, und zwar aus dem Moment, in dem die Jetzt-Ebene diese Stelle erreicht. Die Zukunft liegt sichtbar vor dir |
| Kick | Lichtring in der Welt an der Stelle, die die Jetzt-Ebene beim Kick erreicht; dazu die Feder: Brennweiten-Punch (1 + 0,25 x), die Welt atmet (s · (1 + 0,025 x)), Belichtung · (1 + 0,6 x) |
| Abschnitt | Palette dreht um den goldenen Schnitt: jeder Abschnitt eine neue Farbwelt; Rollrichtung wechselt |

**Farbe (reicher als die anderen Modelle):** Orbit-Trap-Färbung mit einer Vollspektrum-Kosinus-Palette
`rgb = (0,5 + 0,5 · cos(2π(f · log trap + Farbton + 0,14 · Entfernung + (0, ⅓, ⅔))))^2,4`. Der Exponent schiebt zu
reinen Farbtönen, die Entfernung lässt den Korridor vor dir durch das Spektrum laufen, Chaos erhöht f (mehr
Farbbänder). Dunkle Schattierung in Spalten, damit Farben nicht ausbleichen.

**Korridor:** Die erste Faltungsebene wird nie gedreht und die Versätze c sind ≥ 1. Damit bleibt der große
Menger-Korridor entlang z erhalten, Chaos verdreht nur die feineren Ebenen. Geprüft auf ganz Digits (jeder 3. Frame):
Abstand von der Kamera und einem Ring mit Radius 0,06 um sie zum Fraktal immer ≥ 0,12. Das ist getestet, nicht
bewiesen. (In einer früheren Fassung, die alle Ebenen drehte, war der Korridor in 5 % der Frames zu.)

Braucht zusätzlich `pip install numba`.

## G · Gestaltwandler-Welt (`morph.py`)

Baut auf F auf (Flug, Spektrum in den Wänden, Kick-Ringe, Palette), aber das Fraktal selbst ist formbar: es wandelt
sich ohne Schnitt zwischen ganzen Fraktal-Familien, die Wände atmen und zerfließen, die Spuren sind Regenbogen-Tracer.

**Eine Formel für alle Formen.** Ebene 0 bleibt Menger (sortieren, s₀ = 3 + 0,2 C, c₀ wie in F) und hält die großen
Hallen offen. Ab Ebene 1 läuft pro Ebene:
`p = |p|`, sortieren, **Box-Faltung** (Mandelbox) `p = 2·clamp(p, −L, L) − p` mit `L = 1 + 10(1 − w_box)³`,
**Kugel-Faltung** `r² < m²: p/m²`, `r² < 1: p/r²` mit `m² = 1 − 0,75 w_inv`, `p = Rot · p`, `p = s · p − c(s − 1)`.
Abstand = `mix(Box(p), |p| − 1, w_rund) / dr` (dr sammelt s und die Faktoren der Kugel-Faltung).
Jeder Regler wird an einem Ende seines Bereichs zur Identität (w_box = 0: L = 11, keine Faltung; w_inv = 0: m² = 1,
keine Inversion). Darum hängen alle Formen stetig zusammen, und jedes Überblenden ist nahtlos. Faltungen und
Spiegelungen sind stückweise Isometrien, die Abstandsschätzung bleibt in jeder Zwischenform gültig.

Sechs Formen (Rotation x/z, w_box, w_inv, w_rund, s, c):

| Form | Werte | Wirkung |
|---|---|---|
| Menger | 0, 0, 0, 0, 0, 3,0, (1, 1, 1) | Kristall-Architektur wie F |
| Kristall | 0,35, 0,25, 0, 0, 0, 2,7, (1, 1,1, 0,9) | verdrehte Kristalle |
| Höhle | 0, 0, 0,5, 1, 0, 2,8, (1,2, 1,2, 1,2) | Hallen mit Kuppeln und Nischen |
| Blasen | 0, 0, 0, 0,8, 1, 2,7, (1, 1, 1) | runde, blasige Schwämme |
| Koralle | 0,2, −0,3, 0,4, 0,4, 0,4, 2,3, (1, 0,7, 1,2) | weiche, wuchernde Formen |
| Tempel | 0, 0, 0,6, 0, 0, 3,3, (1, 1,3, 1) | Gitter aus Kammern und Fenstern |

| Musik | Bild |
|---|---|
| Klangfarbe | wählt die Form: die sechs Formen sitzen auf festen Winkeln der Klangfarben-Ebene (taktgeglättete MFCC-PCA), Gewicht = `exp(−Abstand² / 0,35)`. Gleicher Klang, gleiche Welt |
| Abschnitt | jeder Abschnitt hat eine Heimat-Form (+1,2 Gewicht); die Anker drehen sich um eine Runde pro 8 Takte · (0,25 + Spannung), damit sich die Welt auch bei gleichbleibender Musik weiter verwandelt |
| Klangwechsel | Morph-Tempo: die Form folgt ihrem Ziel kritisch gedämpft mit τ = Takt · (1,2 − 0,9 · Klangfarben-Tempo), bei Abschnittseinsätzen ¼ Takt. Schneller Klangwechsel = schnelles Verwandeln, ein neuer Teil = sofort eine neue Welt |
| Tonal-Anteil, Spannung, Beat | atmende Wände: Raumverzerrung `p + A·sin(W·p_yzx + Phase)`, A = 0,012 + 0,035 · Tonal + 0,02 · Spannung, schwillt mit jedem Beat (· (1 + 0,35 sin(π · Beat))) und mit der Kick-Feder; die Phase fließt mit der Lautheit. Flächen-Sounds lassen die Welt zerfließen, trockene Drums halten sie scharf |
| Chaos | verdreht die Faltung der tieferen Ebenen (wie F) und erhöht die Skala |
| Hi-Hats | Tempo, mit dem die Farbstreifen über die Flächen kriechen |
| Frequenz, Lautheit, Kick, Abschnittsfarbe | wie F |

**Tracer:** Das vorige Bild wird um die Grauachse im Farbton gedreht (0,006 + 0,018 · Tonal Umdrehungen pro Frame),
mit dem Flug gezoomt, leicht gedreht und per Maximum überlagert: jede Kante zieht eine Regenbogenspur. Der Kick
schneidet die Spuren um 35 %.

**Flugkanal:** Anders als bei F garantiert die Geometrie allein keinen freien Weg: einige Formen und Mischungen wachsen
in den Korridor. Deshalb wird ein dünner Kanal (Radius 0,11) mit einem weichen Maximum in die Welt geschnitten.
Gemessen auf ganz Digits (jeder 3. Frame): in 53 % der Frames reicht die Geometrie näher als 0,11 an die Kamera, der
Kanal formt dann die Wände direkt um dich herum (sichtbar als Tor oder Röhre), in 7,8 % würde die Form die Kamera
sonst einschließen. Er sorgt dafür, dass der Flug nie in festem Material steckt; ganz unsichtbar ist er also nicht.

## Gemessen

Kick-Sync jedes Videos (Digits 47,5–77,5 s, 44 Kicks): mittlere Bildänderung zwischen zwei Frames, gemittelt über
alle Kicks, im Frame vor dem Kick und im Kick-Frame (Graustufen, 0–255, inklusive Untertitel):

| Video | Frame davor | Kick-Frame | Faktor |
|---|---|---|---|
| Tunnel ohne Feder (v2) | 9,6 | 22,8 | 2,4 |
| Tunnel mit Feder | 11,5 | 38,8 | 3,4 |
| A Lorenz | 2,2 | 8,9 | 4,0 |
| B Julia | 9,2 | 49,2 | 5,3 |
| C Kepler | 1,0 | 8,1 | 8,1 |
| D Gray-Scott | 5,2 | 21,4 | 4,1 |
| E Chladni | 3,4 | 19,3 | 5,7 |
| F Fraktal-Flug (ohne Untertitel) | 11,8 | 26,3 | 2,2 |
| G Gestaltwandler-Welt (ohne Untertitel) | 13,8 | 31,8 | 2,3 |

Bei allen liegt der Höhepunkt im Frame des Kicks, nicht danach (R3). Die absoluten Werte sind zwischen den Modellen
nicht vergleichbar (dunkle Bilder ändern sich weniger), der Faktor schon eher. Beim Fraktal-Flug ist der Faktor
kleiner, weil sich das Bild durch den schnellen Flug ohnehin in jedem Frame stark ändert; die Helligkeit springt im
Kick-Frame um +10,5 (Frame davor −0,6). Bei der Gestaltwandler-Welt ebenso: Helligkeit +12,1 im Kick-Frame
(Frame davor −2,4).

## Ehrlich eingeordnet

- Die Gleichungen (Lorenz, Julia/Koenigs, Kepler, Gray-Scott, Plattenmoden) sind Standard und korrekt übernommen.
  Die **Kopplungen** an die Musik (welche Musikgröße welchen Parameter treibt) sind meine Setzungen. Die Richtung ist
  jeweils begründet, die Zahlenwerte habe ich nach Augenmaß an Digits eingestellt; sie sind nicht gemessen.
- Gray-Scott-Regime: die Ecken habe ich auf dem verwendeten Gitter nachgerechnet; die Namen der Regime stammen aus
  Pearsons Klassifikation, die genaue Zuordnung zu seinen Buchstaben-Klassen habe ich nicht nachgeprüft.
- Chladni: echte Platten mit freiem Rand haben andere Eigenfunktionen als das Kosinus-Produkt; das Produkt ist die
  übliche vereinfachte Näherung (eingespannte/gestützte Platte), die Figuren sind daher Chladni-artig, nicht exakt.

## Quellen

- E. N. Lorenz (1963): Deterministic nonperiodic flow. *Journal of the Atmospheric Sciences* 20.
- J. E. Pearson (1993): Complex patterns in a simple system. *Science* 261.
- J. Milnor: *Dynamics in One Complex Variable* (Koenigs-Linearisierung, Multiplikatoren, Julia-Mengen).
- E. F. F. Chladni (1787): *Entdeckungen über die Theorie des Klanges*.
- J. Kepler (1619): *Harmonices Mundi* (drittes Gesetz).
- Mandelbox (Box- und Kugel-Faltung): Tom Lowe, 2010, im Forum fractalforums.com veröffentlicht. Den genauen
  Beitrag habe ich nicht nachgeschlagen.
- Kaleidoskop-IFS (abs/sortieren/skalieren, Grundlage von F und G): „Knighty“, fractalforums.com; ebenfalls nicht
  im Einzelnen nachgeschlagen.

# Musik → Bild: das Regelwerk der Synästhesie-Engine

Ordner `synesthesia/` — eigenständig, unabhängig von der Live-Pipeline (`engine/`, Reels für @mino.recursion).
Ziel: Musik und Bild nach **festen mathematischen Regeln** koppeln statt nach Gefühl. Jede Regel ist eine
kleine Formel; alle Konstanten stehen in `synesthesia/rules.py` (`Rules`) und lassen sich per JSON überschreiben.

## Bildaufbau („Spektral-Schmetterling“)

Die senkrechte Mittellinie ist **jetzt**. In jedem Frame wird der aktuelle Klang als senkrechtes Spektrum auf die
Mittellinie gemalt (unten tief, oben hoch), danach fließt das Bild nach außen. Jede Hälfte zeigt so den letzten
Takt Musik, wie eine Spur, die langsam verblasst. Gleichmäßige Kicks werden zu gleichmäßigen senkrechten Streifen,
Melodien zu Linien, Rauschen zu Schleiern. Ein geordneter Song bleibt spiegelsymmetrisch und ruhig, ein chaotischer
Moment wird turbulent, unsymmetrisch und reißt auf.

## Benutzen

```bash
pip install -r synesthesia/requirements.txt
python3 -m synesthesia song.wav --analyze-only                         # Songstruktur: Pegel, Chaos, Klangfarbe je 2 Takte
python3 -m synesthesia song.wav --start 18.7 --dur 22 --out out.mp4    # 1080×1920, 30 fps, mit Ton
python3 -m synesthesia song.wav --start 18.7 --dur 22 --out out.mp4 --overlay   # Erklär-Version mit Achsen + Chaos-Anzeige
python3 -m synesthesia song.wav --export score.json                    # alle Bildparameter pro Frame, für andere Renderer
python3 -m synesthesia.calibrate song.wav --start 31.2 --dur 4         # Chaos-Kalibrierung (siehe R6)
```

Die Analyse eines 3-Minuten-Songs dauert ca. 45 s und wird in `build/synesthesia/` zwischengespeichert;
das Rendern braucht ca. 0,2 s pro Frame (22 s Video ≈ 2 min).

## Analyse (synesthesia/features.py)

- Stereo, 44,1 kHz, ein Analyse-Frame alle **10 ms**, jeder Frame **zentriert** auf seinen Zeitpunkt.
- Spektrum auf einem log-Frequenz-Raster: 1/24 Oktave, 30 Hz – 16 kHz (218 Stufen).
  Drei Fensterlängen (93 / 46 / 23 ms für Bass / Mitten / Höhen, weich überblendet), damit der Bass sauber
  aufgelöst ist und die Höhen schnell bleiben.
- **Zeitschärfung**: Lange Fenster „sehen“ einen Kick schon bis zu 46 ms vor dem Ton. Pro Oktavband wird deshalb
  die Hüllkurve aus einem phasenneutralen Filter (10 ms) mit der Hüllkurve verglichen, die das lange Fenster sieht;
  das Verhältnis korrigiert das Spektrum zeitlich, die spektrale Form bleibt erhalten.
- Harmonisch/perkussiv-Trennung per Medianfilter (Fitzgerald 2010): pro Frequenz ein Anteil 0..1 „tonal“.
- Klangfarbe: MFCCs (Mel-Cepstrum, Koeffizienten 1–12) getrennt für die tonale und die perkussive Schicht.
- Tempo und Beats: Tracker aus `engine/analyze_audio.py` (Ellis 2007), wiederverwendet.

## Die Regeln

### R1 Tonhöhe → Höhe im Bild

`y = oben + (1 − log(f / 30 Hz) / log(16 kHz / 30 Hz)) · (unten − oben)`

Logarithmisch: **jede Oktave bekommt gleich viel Höhe** (≈ 180 px bei 1920 px), so wie das Gehör Tonhöhe
wahrnimmt. Tief = unten, hoch = oben. Hoher Ton ↔ oben ist eine der robustesten crossmodalen Zuordnungen
(Überblick: Spence 2011, *Crossmodal correspondences: A tutorial review*).
Innerhalb einer Rasterstufe wird zwischen den Stufen interpoliert, also bekommt jede Pixelzeile ihre eigene Frequenz.

### R2 Lautstärke → Stärke (Helligkeit)

1. Pegel pro Frequenz: Energie pro log-Frequenz-Einheit in dB, plus Gehörkurve (**B-Bewertung**, wählbar A/C/Z).
   Die B-Kurve gilt für mittlere bis laute Pegel, also für Musik, die laut gehört wird; sie schwächt Sub-Bass so ab,
   wie das Ohr ihn leiser empfindet.
2. Wahrgenommene Lautheit relativ zum lautesten Moment des Songs (99,5-Perzentil):
   `ψ = 2^((L − L_ref) / 10 dB)` — das Sone-Gesetz: **+10 dB klingen doppelt so laut** (Stevens).
   ψ = 1 → lautester Klang, 0,5 → 10 dB leiser, 0,25 → 20 dB leiser; unter −45 dB wird nichts gezeichnet.
3. Bild: Oklab-Helligkeit `L = 0,88 · ψ`. Oklab ist wahrnehmungsgleichmäßig, also gilt:
   **doppelt so laut empfunden = doppelt so hell empfunden.**

### R3 Timing (Synchronität)

- Anstieg sofort, Abfall mit Zeitkonstante 90 ms (kein Nachziehen beim Einsatz, kein Flackern danach).
- Ein Klang zum Zeitpunkt t erscheint in Frame `floor(t · 30)`: **das Bild darf bis zu einen Frame vor dem Ton
  kommen, nie danach.** Grund: Ton-vor-Bild fällt viel früher auf als Bild-vor-Ton (nach meinem Kenntnisstand
  nennt ITU-R BT.1359 als Erkennungsschwelle etwa 45 ms Ton-Vorlauf gegenüber etwa 125 ms Ton-Verzögerung).
- Gemessen am Prototyp (Kick-Anschläge aus der Wellenform gegen den ersten hellen Frame):
  vor der Zeitschärfung **40 ms** zu früh (bis 63 ms), danach **14 ms** zu früh im Median (10–90 %: −36 … +6 ms),
  also innerhalb eines Frames.

### R4 Klangfarbe → Farbe

Farbton und Sättigung kommen aus der Klangfarbe, die Helligkeit bleibt der Lautheit vorbehalten (R2).

1. **Klangfarben-Ebene des Songs**: Hauptkomponenten (PCA) der MFCCs, auf Varianz 1 normiert.
   Achse 1 ist so ausgerichtet, dass sie mit dem spektralen Schwerpunkt steigt (*hell klingend*),
   Achse 2 so, dass sie mit der spektralen Flachheit steigt (*rauschig*).
2. **Lineare, abstandstreue Abbildung** in die Farbebene (a, b) von Oklab:
   `ab = Anker + r · (z₁ · u₁ + z₂ · u₂)` mit weicher Begrenzung `|z| → tanh(|z|/2)`.
   Ähnliche Klangfarben bekommen ähnliche Farben, unterschiedliche Klangfarben verschiedene, und die Abstände
   bleiben proportional (Drehung + Skalierung, keine Verzerrung).
   - Anker = Durchschnittsklang des Songs: Magenta-Violett (Hue 325°, Chroma 0,14)
   - hell klingend → Richtung Blau/Cyan (Hue 215°), dunkel/warm → Pink/Rot
   - Achse 2 senkrecht dazu: rauschig ↔ tiefes Violett/Indigo bzw. Koralle
3. **Tonal vs. perkussiv**: Jede Frequenzzeile mischt die Farbe der tonalen Schicht mit einer blasseren Version
   der perkussiven (40 % Chroma), gewichtet mit ihrem tonalen Anteil h:
   `ab_Zeile = h · ab_tonal + (1 − h) · 0,4 · ab_perkussiv`. Reine Töne sind satt, Rauschen und Drums gehen
   Richtung Weiß („weißes Rauschen“).

Die Palette (Anker, Richtungen) ist eine **Designentscheidung** und frei einstellbar; die Regel selbst
(abstandstreue Abbildung Klangfarbe → Farbebene) bleibt.

### R5 Stereo → links/rechts

- Linker Kanal malt die linke Bildhälfte, rechter Kanal die rechte. Mono-Klänge sind exakt spiegelsymmetrisch,
  Panning wird zur Asymmetrie.
- Stereobreite (1 − Kohärenz von L und R pro Frequenz, über 200 ms): breite Klänge entstehen bis zu 5 % der
  Bildbreite neben der Mittellinie, Mono-Klänge direkt auf ihr. So entsteht die dunkle Mittelachse, wenn viel
  Breites spielt.

### R6 Musikalisches Chaos → visuelles Chaos

**Musik-Chaos C (0..1)**, drei Messgrößen, je auf den Song normiert (5-%-Perzentil → 0, 95 % → 1):

| Anteil | Messgröße | Idee |
|---|---|---|
| 55 % | **Nicht-Wiederholung**: mittlere dB-Abweichung der 1/3-Oktav-Bänder zum selben Moment 1 Beat, 2 Beats und 1 Takt vorher (die beste Übereinstimmung zählt) | Loops wiederholen sich = Ordnung; Fills, Übergänge, Neues = Chaos |
| 20 % | **Rauschanteil**: spektrale Flachheit 100 Hz–10 kHz | Rauschen ist Zufall |
| 25 % | **Off-Grid-Rhythmus**: Abstand der Onsets zum 16tel-Raster der Beats (0 = auf dem Raster, 1 = genau dazwischen), stärkegewichtet über 1 Takt | regelmäßige Hi-Hats sind Ordnung, stolpernde Schläge Chaos |

Gesamtwert auf 2–98 % gestreckt, Anstieg innerhalb 1/8 Takt, Abklingen über 1/2 Takt.
Digits: Drop-Passagen ≈ 0,2–0,35, Übergänge/Fills ≈ 0,7.

**Bild-Chaos = Musik-Chaos**, verteilt auf vier Freiheitsgrade:
- Turbulenz: wirbelfreie Strömung (Curl-Noise) verschiebt das Bild um bis zu `3,2 px · C^1,1` pro Frame;
  mit C wächst zusätzlich der Anteil kleiner Wirbel. Laminar ↔ turbulent.
- Symmetriebruch: das Strömungsfeld ist nicht spiegelsymmetrisch, also bricht die Symmetrie proportional zu C.
- Funken (R8): bei C = 0 fliegen sie als Spiegelpaare waagrecht, bei C = 1 in beliebige Richtungen.
- Ab C > 0,6 reißt das Bild in horizontale Streifen auf.

**Kalibrierung** (`synesthesia/calibrate.py`): dieselbe Passage wird mit erzwungenem C = 0, 0,1 … 1 gerendert und
die Bild-Unordnung gemessen (D = 1 − Korrelation des Bildes mit seinem Spiegelbild). Ergebnis Digits 31–35 s:

| C | 0 | 0,1 | 0,2 | 0,3 | 0,4 | 0,5 | 0,6 | 0,7 | 0,8 | 0,9 | 1,0 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D | 0,024 | 0,053 | 0,085 | 0,110 | 0,130 | 0,148 | 0,166 | 0,189 | 0,217 | 0,240 | 0,259 |

Damit D linear mit C wächst, braucht die Turbulenz den Exponenten 1,1 (Kleinste Quadrate in log-log) —
das ist `turb_gamma`. Visuelles Chaos ist also messbar proportional zum musikalischen.

### R7 Tempo → Bewegung

Ein Takt wandert eine halbe Bildbreite nach außen (`bar_width = 0,5`); die Bewegung ist an das BPM gekoppelt,
schnellere Songs fließen schneller. Bis zum Rand ist eine Spur auf 18 % verblasst.

### R8 Textur: tonal → Linien, perkussiv → Funken

Tonale Klänge sind Teil der fließenden Spur (Linien bei gehaltenen Tönen). Perkussive Onsets (pro Halboktave,
auf die steilste Stelle der Hüllkurve verfeinert) werfen zusätzlich Funken auf ihrer Tonhöhe: Anzahl und
Geschwindigkeit ∝ Lautheit ψ, Farbe = perkussive Klangfarbe, Lebensdauer ≈ 1/4 Takt.

## Was belegt ist und was Designentscheidung

Wahrnehmungspsychologisch gestützt (Richtung der Zuordnung): Tonhöhe ↔ Höhe, Lautheit ↔ Helligkeit/Größe,
Sone-Gesetz, Gehörkurven, Oklab als wahrnehmungsgleichmäßiger Farbraum, Asymmetrie der AV-Synchronität.
Eigene Designentscheidungen (begründet, aber nicht empirisch abgeleitet): die Farbpalette, die Gewichte der drei
Chaos-Messgrößen, die Spiegel-Ausfluss-Geometrie, Fadegeschwindigkeit, Funkenanzahl. Für Farbe ↔ Klangfarbe gibt
es meines Wissens keine so eindeutige allgemeine Zuordnung wie für Tonhöhe ↔ Höhe; deshalb ist hier die
*Abstandstreue* die Regel, nicht eine feste Farbe pro Instrument.

## Quellen

- C. Spence (2011): Crossmodal correspondences: A tutorial review. *Attention, Perception, & Psychophysics* 73.
- S. S. Stevens (1957): On the psychophysical law. *Psychological Review* 64.
- D. Fitzgerald (2010): Harmonic/percussive separation using median filtering. *DAFx-10*.
- D. P. W. Ellis (2007): Beat tracking by dynamic programming. *Journal of New Music Research* 36.
- S. McAdams et al. (1995): Perceptual scaling of synthesized musical timbres. *Psychological Research* 58
  (Klangfarbenräume: Helligkeit/spektraler Schwerpunkt als Hauptdimension).
- B. Ottosson (2020): A perceptual color space for image processing (Oklab), bottosson.github.io.
- IEC 61672-1 (A- und C-Bewertung); B-Kurve aus älteren Schallpegelmesser-Normen.
- ITU-R BT.1359 (Ton/Bild-Versatz im Rundfunk) — Zahlen oben aus dem Gedächtnis, nicht nachgeprüft.

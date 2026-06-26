# Prompt erstellt von
**Person die den Prompt erstellt hat:** Daniel 
# Prompt zu:
**Prompt wurde verwendet für:**
Verbesserung von Task_1 

# Benutztes KI-Tool
**Name:** Claude
**Version:** Opus 4.8

# Nutzungsprotokoll
## Verwendete Prompt:

Der Agent macht noch Fehler beim Pfad: Manchmal fehlt die letzte Bahn am Rand, oder er setzt Zwischenwerte statt 0.0 / Grenzwert auf der Querachse. Überarbeite bitte den System-Prompt so, dass er deterministischer ist:

Beschreib den Algorithmus in klaren nummerierten Schritten (Scanrichtung bestimmen → Positionen berechnen → Wegpunkte erzeugen).
Markier als KRITISCH, dass die letzte Position (= Grenzwert) Pflicht ist und mit beiden Endpunkten in der Liste stehen muss.
Schreib explizit rein, dass die Koordinate senkrecht zur Scanrichtung immer exakt 0.0 oder der Grenzwert ist, niemals ein Zwischenwert.
Füge zwei vollständige Beispiele hinzu (einmal Breite ≤ Höhe / vertikal, einmal Breite > Höhe / horizontal) mit kompletter Punktliste.



## Antwort der KI

## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?

Klar, ich habe den System-Prompt überarbeitet und deutlich strenger gemacht. Der Algorithmus ist jetzt in drei klar nummerierte Schritte gegliedert, die kritischen Regeln sind explizit hervorgehoben, und ich habe zwei vollständige Beispiele angehängt. Hier die neue Version:


# ROLLE
Du bist ein deterministischer Pfadplaner fuer einen autonomen Suchroboter.
Du berechnest einen vollstaendigen Abdeckungspfad fuer eine rechteckige
Flaeche und gibst ihn als geordnete Wegpunktliste aus.

# EINGABE
Du erhaeltst zwei positive Zahlen: die Breite (x) und die Hoehe (y) der
Flaeche in Metern. Die Flaeche reicht immer von (0,0) bis (Breite, Hoehe).

# ROBOTER
- Faehrt ausschliesslich gerade, achsenparallele Strecken
  (eine Bewegung aendert entweder x ODER y, niemals beides).
- Kamera blickt nach vorne und scannt einen 1.5 m breiten Streifen.
- Bahnabstand: 1.0 m (garantiert Ueberlappung, keine Luecken).

# ALGORITHMUS (Boustrophedon / Lawnmower)
## Schritt 1: Scanrichtung bestimmen
Vergleiche Breite und Hoehe:
- Breite <= Hoehe: scanne vertikal (Bahnen parallel zur y-Achse, entlang x)
- Breite > Hoehe:  scanne horizontal (Bahnen parallel zur x-Achse, entlang y)
Regel: Immer entlang der kuerzeren Dimension scannen -- das ergibt weniger Bahnen.

## Schritt 2: Positionen berechnen
Erzeuge Positionen entlang der Scanachse: 0.0, 1.0, 2.0, ... solange < Grenze.
Haenge den Grenzwert (Breite bzw. Hoehe) an falls noch nicht enthalten.
   Grenze=3: Positionen = [0.0, 1.0, 2.0, 3.0]
   Grenze=4: Positionen = [0.0, 1.0, 2.0, 3.0, 4.0]

## Schritt 3: Wegpunkte erzeugen
Pro Position genau 2 Punkte (Bahnanfang und Bahnende), abwechselnd Richtung:
Vertikal (Breite <= Hoehe): gerade Indizes (x, 0.0)->(x, Hoehe),
ungerade Indizes (x, Hoehe)->(x, 0.0).
Horizontal (Breite > Hoehe): gerade Indizes (0.0, y)->(Breite, y),
ungerade Indizes (Breite, y)->(0.0, y).

KRITISCH: Die letzte Position (= Grenzwert) ist PFLICHT und muss mit
BEIDEN Endpunkten in der Liste stehen.
Die Koordinate senkrecht zur Scanachse ist immer exakt 0.0 oder der
Grenzwert -- niemals ein Zwischenwert.

# AUSGABE
- Ausschliesslich gueltiges JSON passend zum Pydantic-Schema
  { "points": [ { "x": float, "y": float }, ... ] }.
- Keine Erklaerungen, kein Text, keine Codeblock-Markierungen.
- Alle Koordinaten als float mit einer Nachkommastelle.
- Reihenfolge der Punkte ist kritisch und muss exakt dem Fahrweg entsprechen.

# BEISPIEL A (Breite=3, Hoehe=5) -- Breite<=Hoehe -> vertikal -- 4 Positionen, 8 Punkte
{ "points": [ {0,0}, {0,5}, {1,5}, {1,0}, {2,0}, {2,5}, {3,5}, {3,0} ] }

# BEISPIEL B (Breite=5, Hoehe=3) -- Breite>Hoehe -> horizontal -- 4 Positionen, 8 Punkte
{ "points": [ {0,0}, {5,0}, {5,1}, {0,1}, {0,2}, {5,2}, {5,3}, {0,3} ] }
Was ich geändert habe:

Den Algorithmus in drei nummerierte Schritte aufgeteilt (Scanrichtung → Positionen → Wegpunkte), damit das Modell der Reihe nach vorgeht.
Einen mit KRITISCH markierten Block ergänzt, der erzwingt, dass die letzte Position (Grenzwert) mit beiden Endpunkten enthalten ist – das behebt die fehlende letzte Bahn am Rand.
Explizit festgelegt, dass die Querkoordinate immer exakt 0.0 oder der Grenzwert ist, niemals ein Zwischenwert – damit verschwinden die falschen Zwischenwerte.
Zwei vollständige Beispiele angehängt (vertikal und horizontal) mit kompletter Punktliste als Orientierung.
Damit sollte der Agent jetzt zuverlässig den Rand abdecken und keine Zwischenwerte mehr erzeugen

---


# Reflexion

## Evaluation der Antwort anhand von Bewertungskriterien

### Research

**Zeitaufwand (Prompt und Umsetzung der Antwort):**
- [] 1: Zeit gekostet, Frage an KI hat länger gedauert als es selber zu machen
- [] 2: Zeit gleich, Frage an KI hat ungefähr solange gedauert wie es selber zu tun
- [x] 3: Zeitgewinn, Frage an die KI war schneller als es selber zu machen

**Beachtung des Prompts von der KI (indirekt die Qualität des Promptes):**
- [] 1: Prompt wird praktisch nicht beachtet (weniger als 10% des Prompts)
- [] 2: Prompt wird nur in Ansätzen beachtet (mehr als 10% aber weniger als 90% des Prompts)
- [x] 3: Prompt wird fast vollständig beachtet (mehr als 90% des Prompts)

**Qualität der Quellen:**
- [] 1: Es werden Quellen wie Reddit oder graue Literaturen verwendet
- [x] 2: Es werden keine externen Quellen verwendet
- [] 3: Es werden wissenschaftliche Quellen oder Peer-Review-Journals verwendet

**Relevanz der Quellen:**
- [x] 1: Quellen sind nicht relevant für den Prompt
- [] 2: Quellen sind in teilen relevant für den Prompt
- [] 3: Quellen sind alle relevant für den Prompt

**Qualität der Antwort:**
- [] 1: Antwort wird verworfen
- [] 2: Antwort muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [x] 3: Antwort braucht kaum noch manuelle Nachbearbeitung

### Coding

**Zeitaufwand (Prompt und Umsetzung der Antwort):**
- [] 1: Zeit gekostet, Frage an KI hat länger gedauert als es selber zu machen
- [] 2: Zeit gleich, Frage an KI hat ungefähr solange gedauert wie es selber zu tun
- [x] 3: Zeitgewinn, Frage an die KI war schneller als es selber zu machen+

**Qualität vom Code:**
- [] 1: Code wird verworfen
- [x] 2: Code muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [x] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [] 2: Erklärungen helfen nur teilweise
- [] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion


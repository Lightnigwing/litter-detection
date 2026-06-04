# Prompt erstellt von
**Person die den Prompt erstellt hat:** 
Jonas Schweiss
# Prompt zu:
**Prompt wurde verwendet für:**
Research: []
Coding: [x]
Thema: Interference einbauen in task

# Benutztes KI-Tool
**Name:**  Claude
**Version:** Sonnet 4.6

# Nutzungsprotokoll
## Verwendete Prompt:

Dein Ziel ist es eine funktionierende Inference zu bauen.
Dabei gibt es ein paar Punkte zu beachten:
Hardware:
Momentan bist du auf einem Windows-PC, der Code soll jedoch später auf einem Jetson AGX Orin mit Linux laufen.

Aufgaben:
Umbau der Inference von ONNXRuntime zu PyTorch, sodass nur noch PyTorch verwendet wird (passe dabei auch das mögliche Training entsprechend an).
Korrekte Einbindung der Inference in Task2_2.
Aufräumen der pyproject.toml und Entfernen aller nicht genutzten Bibliotheken.

Erstelle dafür einen Plan. Falls du Fragen zur Software auf dem Jetson hast, stelle diese bitte bevor du den Plan finalisierst.

## Antwort der KI
Kompletette task2_2


## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?
Antwort wird für Prototype genutzt, es wurde vorallem der Plan überarbeitet und logisch einmal der code angeschaut, testen wie gut er funktioniert, auch in hinsicht Latenz passiert Vorort

# Reflexion

## Evaluation der Antwort anhand von Bewertungskriterien

### Research

**Zeitaufwand (Prompt und Umsetzung der Antwort):**
- [] 1: Zeit gekostet, Frage an KI hat länger gedauert als es selber zu machen
- [] 2: Zeit gleich, Frage an KI hat ungefähr solange gedauert wie es selber zu tun
- [] 3: Zeitgewinn, Frage an die KI war schneller als es selber zu machen

**Beachtung des Prompts von der KI (indirekt die Qualität des Promptes):**
- [] 1: Prompt wird praktisch nicht beachtet (weniger als 10% des Prompts)
- [] 2: Prompt wird nur in Ansätzen beachtet (mehr als 10% aber weniger als 90% des Prompts)
- [] 3: Prompt wird fast vollständig beachtet (mehr als 90% des Prompts)

**Qualität der Quellen:**
- [] 1: Es werden Quellen wie Reddit oder graue Literaturen verwendet
- [] 2: Es werden keine externen Quellen verwendet
- [] 3: Es werden wissenschaftliche Quellen oder Peer-Review-Journals verwendet

**Relevanz der Quellen:**
- [] 1: Quellen sind nicht relevant für den Prompt
- [] 2: Quellen sind in teilen relevant für den Prompt
- [] 3: Quellen sind alle relevant für den Prompt

**Qualität der Antwort:**
- [] 1: Antwort wird verworfen
- [] 2: Antwort muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [] 3: Antwort braucht kaum noch manuelle Nachbearbeitung

### Coding

**Zeitaufwand (Prompt und Umsetzung der Antwort):**
- [] 1: Zeit gekostet, Frage an KI hat länger gedauert als es selber zu machen
- [] 2: Zeit gleich, Frage an KI hat ungefähr solange gedauert wie es selber zu tun
- [x] 3: Zeitgewinn, Frage an die KI war schneller als es selber zu machen+

**Qualität vom Code:**
- [] 1: Code wird verworfen
- [] 2: Code muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [X] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [x] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [x] 2: Erklärungen helfen nur teilweise
- [] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion 
Erste mal Claude benutzt, deswegen noch nicht so vertraut damit. Denn Code denn er das erste mal gemacht hat war ganz gut, habe ihn aber noch mit ein paar promps nachgearbeitet, damit er verständlicher ist. usste auch einige Sachen nachfragen
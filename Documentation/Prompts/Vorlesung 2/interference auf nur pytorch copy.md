# Prompt erstellt von
**Person die den Prompt erstellt hat:** 
Jonas Schweiss
# Prompt zu:
**Prompt wurde verwendet für:**
Research: []
Coding: [x]
Thema: Model updaten

# Benutztes KI-Tool
**Name:**  Claude
**Version:** Fable-5

# Nutzungsprotokoll
## Verwendete Prompt:

Du bist ein CNN-Bauungsexperte der besonders gute Modele baut.

Dein Ziel ist es ein robustes Model zu bauen und dafür musst du folgende Dateien bearbeiten:
src/model/train.py: ist die trainingsdatei mit den momentanen bildern
src/model/prepare.py: vorverarbeitung der Bilder

Schau nur die beiden an und bearbeite nur die beiden.

Das neue Model soll:
- keine schwarzen ränder mehr haben in der prepare.py
- bessere Accuarcy am ende
- gut sein bei verschwommenen bildern, beim usecase ist die kamera auf einem bewegenden wackelnden objekt

Du kannst alles anpassen was du denkst hilft. Sei dir sicher, das deine Änderungen helfen

## Antwort der KI
Hat die alten onnxruntime sachen entfernt


## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?
Es ging darum die onnxruntime Sachen und ungenutzte librarys zu entfernen, bei den entfernten librarys wurde gegengescheckt ob es wirklich net mehr gebraucht wird
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
- [X] 2: Code muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [x] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [] 2: Erklärungen helfen nur teilweise
- [x] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion 
Es war einfacher das Claude einmal das Projekt durchschaut alls, es alles manuel zu machen
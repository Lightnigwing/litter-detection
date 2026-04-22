# Prompt erstellt von
**Person die den Prompt erstellt hat:** 
Jonas Schweiss
# Prompt zu:
**Prompt wurde verwendet für:**
Research: []
Coding: [x]
Thema: 
Struktur der prepare,.py erklären und verstehen, Verbesserungsvorschläge geben
# Benutztes KI-Tool
**Name:**  ChatGPT
**Version:** GPT-5.3

# Nutzungsprotokoll
## Verwendete Prompt:
Ich möchte eine Model tranieren das Müll erkennt. Ich nutze zum tranieren des models den Taco datensatz. ich habe eine datei bekommen die den entsprechenden Datensatz läd und in trainings/validations imgs splittet. Ich gebe dir im anschluss en Code und möchte das du mir zu den einzelnen funktionen eine beschreibung gibst ob die dahin sollten oder warum nicht und was sie bedeuten.
Coder der prepare.py

## Antwort der KI
Erklärung des Codes, aufgeteilt in einzelne Funktionen.
Verbesserungsvorschläge:

Was du wissen solltest
Der Code erstellt Segmentierungsdaten, keine Bounding Boxes.
RLE-Annotationen werden ignoriert.
Das Resize verzerrt Bilder leicht, weil das Seitenverhältnis nicht erhalten bleibt.


## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?
Die Antwort wurde genutzt um zum einen denn Aufbau und die einzelnen Schritte der prepare.py zu verstehen und mögliche Verbesserungen zu testen.
Zu den Verbesserungsvorschlägen:
RLE: wird weiterhin gleichbehandelt, nach kurzem loggen der betroffenen elemente, sind hier 0 RLE deswegen wird es nicht gesondert behandelt
Rsizing: Resizing durch resizing mit padding ersetzt, notwendig, da die Bilder in allen möglichen größen auftreten und wenn man sie nur auf 512 resizde, kommt es zu extremen Verzerungen

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
- [x] 2: Code muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [x] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [x] 2: Erklärungen helfen nur teilweise
- [] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion 
Das erklären der Datei und das manuelle nacharbeiten bzw nachfragen der Verbesserungsvorschläge hat geholfen die Datei besser zu verstehen und sinnvolle Verbesserungen zu finden
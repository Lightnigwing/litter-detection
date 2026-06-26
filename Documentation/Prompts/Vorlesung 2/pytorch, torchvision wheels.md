# Prompt erstellt von
**Person die den Prompt erstellt hat:** 
Jonas Schweiss
# Prompt zu:
**Prompt wurde verwendet für:**
Research: []
Coding: [x]
Thema: Wheels für pytorch und torchvision bauen

# Benutztes KI-Tool
**Name:**  Claude
**Version:** Sonnet 4.6

# Nutzungsprotokoll
## Verwendete Prompt:

Dein Ziel ist eine funktionierende Interference auf dem Jetson via pytorch
Du bist im Moment auf dem Windows entwicklungs pc.
Der Code aus dem Repo soll später auf einem Jetson AGX orin 64gb ausgeführt werden
Es hat python 3.11, dieses kann man auch nicht ändern.
Das Problem ist, das der Jetson mit Linux läuft und torch nicht einfach so laufen kann.
Sage mir welche befehle du brauchst um die richtigen wheels für torch zu bestimmen


## Antwort der KI
Die wheels für pytorch und torchvison bzw die Befehle bzw Anleitung was ich tun musste


## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?
Wurde genutzt um die wheels zu erstellen, es hat gedauert und der Prompt musste mit mehr informationen gefüttert werden

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
- [x] 2: Erklärungen helfen nur teilweise
- [] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion 
Claude war notwendig, da ich mich mit Linux wenig auskenne und nicht weis wie man die wheels custom baut. Es hat gedauert bis die wheels die richtigen waren, es musste immer wieder nachgeholfen werden, u.a. hat claude am Anfang Links geraten, was gedauert habe bis ich darauf gekommen bin
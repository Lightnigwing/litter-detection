# Prompt erstellt von
**Person die den Prompt erstellt hat:** 
Jonas Schweiss
# Prompt zu:
**Prompt wurde verwendet für:**
Research: []
Coding: [x]
Thema: 

# Benutztes KI-Tool
**Name:**  ChatGPT
**Version:** GPT-5.3

# Nutzungsprotokoll
## Verwendete Prompt:
Ich habe mehrere Tasks die entweder reiner Coder oder Coder und pydanticAI Agenten sind. Ich möchte es in einem sequentiellen Pattern ablaufen lassen, es gibt aber auch Tasks die parralel laufen. Gebe mir verschiedene Möglichkeiten wie ich es umsetzen kann, mit zb eine Datei die die Ordnung Vorgibt. Als Middleware wird zenoh verwendet. Es läuft in python.

## Antwort der KI
Verschiedene Vorschläge wie zb DAG oder eine Orchastrator Datei.


## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?
Ich habe mir die Vorschläge angeschaut und mich dann für eine Architecture mit Orchastrator Datei entschieden. Ich habe mir beispiele für die Orchastrator, die worker und eine beispiel Task geben lassen. Es wurde viel aus den Beispielen übernommen zb wie die Start/Done Thematik behandelt wird. Es wurde vorallem Anpassungen zum Thema wie die Tasks Informationen austauschen und das aussehen der Tasks verändert.

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
Es war hilfreich zu sehen wie ich meine Idee umsetzen kann. Der grobe Aufbau war hilfreich, es musste aber für das was ich brauchte relativ viel nachgearvbeitet werden. Es wurde unteranderem ein Zenoh storage von nöten, da der Aufbau der KI bzw das was ich bis dahin modefiziert hatte, nur funktioniert, wenn man die last message auf ein Topic haben kann und das geht bei zenoh mit rein pub/sub nicht, da dies nur für Live Daten ist.
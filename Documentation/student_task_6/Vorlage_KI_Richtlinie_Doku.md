# Prompt erstellt von
**Person die den Prompt erstellt hat:** Felix

# Prompt zu:
**Prompt wurde verwendet für:**
Erstellen von Task_3

# Benutztes KI-Tool
**Name:** Claude
**Version:** Opus 4.7

# Nutzungsprotokoll
## Verwendete Prompt:

Implementier mir bitte src/tasks/task6.py in unserem litter-detection Repo.

Was task6 macht: Wartet auf das Signal von task5 "ich bin an Punkt N angekommen", schickt dem Hund einen wiggle_hips Emote, und meldet zurück wenn fertig. Läuft parallel zu task5.

Konkret:
- Subscribe auf "pipeline/task5/arrived_at_point" (Live-Channel von task5, Payload ist Task5_Arrival mit point_key und is_last).
- Bei jedem Event:
  1. Publish ActionCommand(action=ActionType.wiggle_hips) auf "robodog/command/pose/action". Den Topic-String bitte aus interfaces/topics/topics.py (TOPICS.command.pose.action) holen.
  2. Sleep 3 Sekunden damit der Hund den Emote auch fertig macht (go2_bridge bestätigt nichts zurück).
  3. Publish Task6_EmoteDone(point_key=arrival.point_key) auf "pipeline/task6/emote_done" — das ist das Go-Signal für task5 zum nächsten Punkt.
  4. Wenn arrival.is_last == True: Loop verlassen.
- Am Schluss: return Task6(finished_emote=True).

Wichtig:
- ActionCommand, ActionType aus interfaces/motion.py.
- Task5_Arrival, Task6_EmoteDone aus topics_pydantic_models/pydantic_models.py.
- session.close() ans Ende, nicht in den Loop (war im Stub falsch).
- Der "data = False" Dummy im aktuellen Stub kann weg.
- Setz ne Timeout-Sicherung auf die Subscribe-Wait (~60s pro Punkt).



## Antwort der KI



## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?


---


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
- [x] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [x] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [] 2: Erklärungen helfen nur teilweise
- [x] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion 
Top
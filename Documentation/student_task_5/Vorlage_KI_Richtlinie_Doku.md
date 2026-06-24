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

Implementier mir bitte src/tasks/task5.py in unserem litter-detection Repo.

Was task5 macht: Der Hund fährt nacheinander zu allen Müllpunkten und sagt nach jeder Ankunft Task6 Bescheid, damit der einen Emote macht. Erst wenn Task6 mit dem Emote fertig ist, fährt task5 weiter zum nächsten Punkt.

Konkret:
- Litter-Punkte kommen aus pipeline/task4/done (per session.get), das ist ein Dict {"point1": {x, y}, "point2": {x, y}, ...}. Bitte sortier die Keys explizit damit die Reihenfolge stabil ist.
- Für jeden Punkt: bau einen NavigationRequest mit einem NavigationSegment auf Pose2D(x, y, theta=0.0) und publish auf "nav/request". Die NavManager (läuft als eigener Prozess) macht den Rest.
- Hör auf "nav/status" und warte bis NavigationState.ARRIVED_FINAL kommt.
- Dann publish Task5_Arrival(point_key=key, is_last=...) auf "pipeline/task5/arrived_at_point". is_last=True nur beim letzten Punkt.
- Warte auf Task6_EmoteDone vom Topic "pipeline/task6/emote_done" mit passendem point_key. Erst dann weiter zum nächsten.
- Am Schluss: return Task5(point_reached=True). Der Worker publisht das auf pipeline/task5/done.

Wichtig:
- session.close() gehört ans ENDE, nicht in den Loop (das war ein Bug im Stub).
- Models: Pose2D, NavigationRequest, NavigationSegment, NavigationState aus interfaces/navigation.py. Task5_Arrival/Task6_EmoteDone aus topics_pydantic_models/pydantic_models.py (die neuen Models füg ich noch hinzu).
- Topic-Strings bitte aus interfaces/topics/topics.py importieren, nicht hardcoden.
- Setz einen Timeout (~60s) auf die Wartephasen, sonst hängt die Pipeline still wenn was schiefgeht.



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
Die KI hat die Anforderungen des Prompts nahezu vollständig umgesetzt und funktionsfähigen Code erzeugt. Dadurch konnte die Implementierungszeit deutlich reduziert werden. Während der Integration zeigte sich jedoch ein kleiner Fehler: Task 6 wurde direkt nach der Ankunft ausgelöst, bevor der Hund vollständig zum Stillstand gekommen war, wodurch das Emote ignoriert wurde. Dieser Aspekt war im Prompt nicht explizit beschrieben und war mir zu diesem Zeitpunkt ebenfalls nicht bewusst. Daher musste zunächst eine Fehlersuche durchgeführt werden, um die Ursache zu identifizieren. Nachdem das Problem erkannt wurde, ließ es sich mit geringem Aufwand beheben. Insgesamt war die Antwort sehr hilfreich und erforderte nur wenig Nacharbeit.
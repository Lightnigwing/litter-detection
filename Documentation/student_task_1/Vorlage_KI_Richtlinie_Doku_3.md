# Prompt erstellt von
**Person die den Prompt erstellt hat:** Daniel 
# Prompt zu:
**Prompt wurde verwendet für:**
Erstellen von Task_1 

# Benutztes KI-Tool
**Name:** Claude
**Version:** Opus 4.8

# Nutzungsprotokoll
## Verwendete Prompt:

Erstell mir bitte Task 1 soll den Suchpfad für den Roboterhund planen: Sie kriegt die Breite (x) und Höhe (y) einer Fläche und soll daraus eine Liste von Wegpunkten machen, die der Hund abfährt, damit er die ganze Fläche absucht.

Die x und y kommen von Task 0 über Zenoh. Nutz einen pydantic-ai Agent mit dem lokalen Modell qwen2.5:7b über Ollama. Der Agent soll die Punkte als JSON zurückgeben. Halt dich an den Aufbau der anderen Tasks im Repo. Gib mir die fertige Datei.



## Antwort der KI

## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?

Ich habe src/tasks/task1.py erstellt. Die Datei öffnet eine Zenoh-Session, holt sich x und y von Task 0, lässt den Agenten den Pfad planen und gibt das Ergebnis als Task1_points zurück. Hier die Datei:


import json
from config import Settings
from topics_pydantic_models.pydantic_models import Task1_points, SearchPath
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


def run_task():
    settings = Settings()
    session = zenoh.open(settings.zenoh_config())

    replies = session.get("pipeline/task0/done")
    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    data = json.loads(data_reply["data"])
    print(f"[TASK1] Received data: {data}")

    provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    model = OpenAIChatModel("qwen2.5:7b", provider=provider)
    agent = Agent(
        model,
        output_type=SearchPath,
        system_prompt=(
            "Du bist ein Pfadplaner fuer einen Suchroboter. "
            "Du bekommst die Breite und Hoehe einer Flaeche und planst einen "
            "Pfad, der die ganze Flaeche abdeckt. Fahre Bahn fuer Bahn hin und "
            "her. Gib die Wegpunkte als Liste von x/y-Punkten zurueck."
        ),
    )

    user_prompt = f"Breite={data['x']}, Hoehe={data['y']}. Plane den Suchpfad."
    result_agent = agent.run_sync(user_prompt)
    search_path = result_agent.output

    result = Task1_points(
        points={f"point{i}": p for i, p in enumerate(search_path.points)}
    )
    print(f"[TASK1] {len(search_path.points)} Punkte: {search_path.points}")

    session.close()
    return result
Was ich gemacht habe:

Zenoh-Session geöffnet und x/y aus pipeline/task0/done ausgelesen.
Einen pydantic-ai Agenten mit qwen2.5:7b über Ollama aufgesetzt, der eine SearchPath-Punktliste zurückgibt.
Dem Agenten per System-Prompt die Aufgabe (Bahn für Bahn, Fläche abdecken) erklärt.
Das Ergebnis zu Task1_points durchnummeriert und zurückgegeben.
Hinweis: Das ist eine erste, einfache Version. Sie hat noch ein paar Schwachstellen, die wir bei Bedarf angehen sollten:

Der System-Prompt ist noch sehr vage – das kleine Modell wird damit unzuverlässige Pfade liefern (fehlende Randbahnen, Zwischenwerte).
Es gibt keine Wiederholung und keinen Timeout – wenn der Agent einmal Mist baut oder hängt, schlägt die Task fehl.
Die Positionsberechnung überlässt sie komplett dem Modell, statt sie im Code vorzubereiten.
Kein MLflow-Logging.

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
- [] 2: Es werden keine externen Quellen verwendet
- [x] 3: Es werden wissenschaftliche Quellen oder Peer-Review-Journals verwendet

**Relevanz der Quellen:**
- [] 1: Quellen sind nicht relevant für den Prompt
- [x] 2: Quellen sind in teilen relevant für den Prompt
- [] 3: Quellen sind alle relevant für den Prompt

**Qualität der Antwort:**
- [] 1: Antwort wird verworfen
- [x] 2: Antwort muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
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
- [] 2: Erklärungen helfen nur teilweise
- [x] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion


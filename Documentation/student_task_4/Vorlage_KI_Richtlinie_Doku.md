# Prompt erstellt von
**Person die den Prompt erstellt hat:** Daniel 
# Prompt zu:
**Prompt wurde verwendet für:**
Erstellen von Task 4

# Benutztes KI-Tool
**Name:** Claude
**Version:** Opus 4.8

# Nutzungsprotokoll
## Verwendete Prompt:


Task 1 läuft jetzt sauber, danke. Erstell mir bitte als Nächstes task 4

Task 4 ist im Prinzip ähnlich wie Task 1 (Zenoh-Session, pydantic-ai Agent mit qwen2.5:7b über Ollama, Ergebnis als durchnummerierte Punkte), aber mit ein paar Unterschieden:

Task 4 plant keinen neuen Pfad, sondern bekommt schon fertige Müllpunkte und soll sie nur in die kürzeste Reihenfolge sortieren (kürzeste Gesamtstrecke, klassisches Travelling-Salesman-Problem).
Die Müllpunkte kommen von Task 2_2 über Zenoh.
Zusätzlich braucht der Agent die aktuelle Position des Hundes als Startpunkt. Die steht nicht in einer fertigen Antwort, sondern wird laufend übers Odometry-Topic gesendet.
Der Agent soll als Output die Punkte in optimierter Reihenfolge geben, und am Ende soll das Ergebnis neu von point1 an durchnummeriert als Task4 rauskommen.
Halt dich sonst an den Aufbau der anderen Tasks. Gib mir die fertige Datei und erklär kurz, was sie macht.

## Antwort der KI

## Wofür wurde die Antwort genutzt und inwiefern wurde sie überarbeitet ?

ch habe src/tasks/task4.py erstellt. Sie holt sich die Müllpunkte von Task 2_2 und die aktuelle Position vom Odometry-Topic, lässt den Agenten die kürzeste Reihenfolge planen und gibt das Ergebnis als Task4 zurück. Hier die Datei:


import json
import threading
from config import Settings
from topics_pydantic_models.pydantic_models import Task4, OrderedPoints
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from interfaces.topics import TOPICS


def run_task():
    settings = Settings()
    session = zenoh.open(settings.zenoh_config())

    # Müllpunkte von Task 2_2 holen
    replies = session.get("pipeline/task2_2/done")
    data_reply = None
    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())
    if data_reply is None:
        session.close()
        raise RuntimeError("task4: kein task2_2/done Reply erhalten")

    data = json.loads(data_reply["data"])
    litter_points = data.get("litter_points", {})

    # Aktuelle Position einmalig aus dem ersten Odometry-Sample lesen
    pose_holder = {"pose": None}
    pose_event = threading.Event()

    def od_save(sample: zenoh.Sample) -> None:
        try:
            od = json.loads(sample.payload.to_bytes())
            if "x" in od and "y" in od:
                pose_holder["pose"] = {"x": float(od["x"]), "y": float(od["y"])}
                pose_event.set()
        except Exception:
            pass

    sub_od = session.declare_subscriber(TOPICS.system_state.odometry, od_save)
    pose_event.wait(timeout=5.0)
    sub_od.undeclare()
    current_pose = pose_holder["pose"]
    if current_pose is None:
        session.close()
        raise RuntimeError("task4: Position konnte nicht gelesen werden")

    result = None
    while result is None:
        try:
            provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
            model = OpenAIChatModel("qwen2.5:7b", provider=provider)
            route_planner_agent = Agent(
                model,
                output_type=OrderedPoints,
                retries=3,
                system_prompt=(
                    "Du bist ein intelligenter Router für einen Hund-Roboter. "
                    "Der Roboter startet bei seiner aktuellen Position und muss alle Müllpunkte besuchen. "
                    "Optimiere die Reihenfolge der Punkte, um die Gesamtfahrstrecke zu minimieren. "
                    "Der Hund läuft nur in geraden Linien zwischen den Punkten. "
                    "Gib nur die Punkte in optimierter Reihenfolge aus, als keys point1, point2, ... mit je x/y. "
                    "Keine anderen Keys verwenden."
                ),
            )

            user_prompt = (
                f"Aktuelle Position: x={current_pose['x']}, y={current_pose['y']}. "
                f"Müllpunkte: {json.dumps(litter_points)}. "
                "Plane die kürzeste Route und gib die Punkte in optimierter Reihenfolge als JSON zurück."
            )

            result_agent = route_planner_agent.run_sync(user_prompt)
            ordered: OrderedPoints = result_agent.output

            points_dict = {}
            for i, point in enumerate(ordered.points.values(), 1):
                points_dict[f"point{i}"] = point

            result = Task4(litter_points=points_dict)
            return result
        finally:
            session.close()
Was ich gemacht habe:

Zenoh-Session geöffnet und die Müllpunkte aus pipeline/task2_2/done ausgelesen.
Die aktuelle Position nicht per session.get, sondern über einen Odometry-Subscriber geholt: Ich warte mit einem threading.Event auf das erste gültige Sample (max. 5 Sekunden) und melde den Subscriber danach wieder ab.
Einen Routenplaner-Agenten (qwen2.5:7b über Ollama) aufgesetzt, der die Punkte in optimierter Reihenfolge als OrderedPoints zurückgibt – mit retries=3, falls das Format mal nicht passt.
Dem Agenten im User-Prompt die Startposition und alle Müllpunkte mitgegeben und ihn die kürzeste Route planen lassen (Travelling-Salesman-Logik).
Das Ergebnis neu von point1 an durchnummeriert und als Task4 zurückgegeben. Das Ganze läuft in einer Schleife, bis ein gültiges Ergebnis vorliegt.
Der wichtigste Unterschied zu Task 1: Task 1 erzeugt einen Pfad von Grund auf, Task 4 sortiert bereits gefundene Punkte nur clever um.

---


# Reflexion

## Evaluation der Antwort anhand von Bewertungskriterien

### Research

**Zeitaufwand (Prompt und Umsetzung der Antwort):**
- [] 1: Zeit gekostet, Frage an KI hat länger gedauert als es selber zu machen
- [] 2: Zeit gleich, Frage an KI hat ungefähr solange gedauert wie es selber zu tun
- [X] 3: Zeitgewinn, Frage an die KI war schneller als es selber zu machen

**Beachtung des Prompts von der KI (indirekt die Qualität des Promptes):**
- [] 1: Prompt wird praktisch nicht beachtet (weniger als 10% des Prompts)
- [] 2: Prompt wird nur in Ansätzen beachtet (mehr als 10% aber weniger als 90% des Prompts)
- [X] 3: Prompt wird fast vollständig beachtet (mehr als 90% des Prompts)

**Qualität der Quellen:**
- [x] 1: Es werden Quellen wie Reddit oder graue Literaturen verwendet
- [] 2: Es werden keine externen Quellen verwendet
- [] 3: Es werden wissenschaftliche Quellen oder Peer-Review-Journals verwendet

**Relevanz der Quellen:**
- [] 1: Quellen sind nicht relevant für den Prompt
- [x] 2: Quellen sind in teilen relevant für den Prompt
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
- [] 2: Code muss in großen Teilen überarbeitet werden (ggf. Prompt überarbeiten)
- [x] 3: Code braucht kaum noch manuelle Nachbearbeitung

**Verständlichkeit des Codes (Struktur, verwendete Tools):**
- [] 1: Code nicht einfach verständlich, nur mit erneutem Nachfragen ansatzweise verständlich
- [] 2: Code kann mit dem richtigen Hintergrundwissen und einiger Zeit verstanden werden
- [x] 3: Code ist einem klar nach kurzer Zeit und ohne großes Vorwissen verständlich

**Erklärungen des Codes (wenn gewünscht im Prompt):**
- [] 1: Erklärungen komplett nutzlos
- [] 2: Erklärungen helfen nur teilweise
- [x] 3: Erklärungen erklären alles


## Kurze persönliche Reflexion

Bei ählichen aufgaben bzw änderungen ist KI perfekt dafür geeignet und mann muss selber kaum mehr was anpassen.
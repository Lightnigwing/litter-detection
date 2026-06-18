import json
import threading
import time
from config import Settings
from topics_pydantic_models.pydantic_models import Point, Task4, OrderedPoints
import zenoh
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from interfaces.topics import TOPICS


def run_task():

    # Initialisiert Zenoh-Session
    settings = Settings()
    session = zenoh.open(settings.zenoh_config())

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies = session.get("pipeline/task2_2/done")
    data_reply = None
    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    if data_reply is None:
        session.close()
        raise RuntimeError("task4: kein task2_2/done Reply erhalten")

    data = json.loads(data_reply["data"])
    litter_points = data.get("litter_points", {})
    # Aktuelle Position genau einmal aus dem ersten gültigen Odometry-Sample setzen.
    # Odometry wird kontinuierlich publiziert -> Subscriber + Event statt session.get.
    pose_holder: dict = {"pose": None}
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
    pose_event.wait(timeout=5.0)  # warte auf erstes Odometry-Sample
    sub_od.undeclare()
    current_pose = pose_holder["pose"]
    if current_pose is not None:
        print(f"[TASK4] Current pose: {current_pose}")

    if current_pose is None:
        print("[TASK4] ERROR: Konnte aktuelle Position vom Odometry-Topic nicht lesen!")
        session.close()
        raise RuntimeError("task4: Position konnte nicht gelesen werden")

    """""
    litter_points = {
        "point1": {"x": 5.0, "y": 3.0},
        "point2": {"x": 7.0, "y": 1.0},
        "point3": {"x": 5.0, "y": 8.0},
        "point4": {"x": 1.0, "y": 6.0},
        "point5": {"x": 2.0, "y": 4.0},
    }
    current_pose = {"x": 7.0, "y": 8.0}
    """""

    result = None
    # Main loop der Task-Logik
    while result is None:
        try:
            print(f"[TASK4] Received litter points: {litter_points}")
            print(f"[TASK4] Current pose: {current_pose}")

            # Pydantic-AI Agent für intelligente Routenplanung
            provider = OpenAIProvider(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            model = OpenAIChatModel("qwen2.5:7b", provider=provider)

            route_planner_agent = Agent(
                model,
                output_type=OrderedPoints,
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

            print(f"[TASK4] Agent geplant: {len(ordered.points)} Punkte in optimierter Reihenfolge")

            # Durchnumeriere die Punkte von 1 an
            points_dict = {}
            for i, point in enumerate(ordered.points.values(), 1):
                points_dict[f"point{i}"] = point

            result = Task4(litter_points=points_dict)

            return result
        finally:
            session.close()

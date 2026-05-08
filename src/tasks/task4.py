import json
import time
from config import Settings
from topics_json.Task_json import Point, Task4
import zenoh

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from interfaces.topics import TOPICS


class OrderedPoints(BaseModel):
    """Die optimierte Reihenfolge der Müllpunkte."""
    points: dict[str, Point]


def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

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

    # Lese aktuelle Position mit Wiederholungen
    current_pose = None
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            odom_replies = session.get(TOPICS.system_state.odometry)
            for r in odom_replies:
                try:
                    od = json.loads(r.ok.payload.to_bytes())
                    if "x" in od and "y" in od:
                        current_pose = {"x": float(od["x"]), "y": float(od["y"])}
                        break
                except Exception:
                    continue
            if current_pose is not None:
                break
        except Exception:
            pass
        
        if attempt < max_attempts - 1:
            time.sleep(0.5)
    
    if current_pose is None:
        print("[TASK4] ERROR: Konnte aktuelle Position vom Odometry-Topic nicht lesen!")
        session.close()
        raise RuntimeError("task4: Position konnte nicht gelesen werden")

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
            model = OpenAIChatModel("gemma4:e4b", provider=provider)

            route_planner_agent = Agent(
                model,
                result_type=OrderedPoints,
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
            ordered: OrderedPoints = result_agent.data

            print(f"[TASK4] Agent geplant: {len(ordered.points)} Punkte in optimierter Reihenfolge")

            # Durchnumeriere die Punkte von 1 an (wie in task1)
            points_dict = {}
            for i, point in enumerate(ordered.points.values(), 1):
                points_dict[f"point{i}"] = point

            result = Task4(litter_points=points_dict)

            return result
        finally:
            session.close()


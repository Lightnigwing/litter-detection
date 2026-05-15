import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from config import Settings
from topics_json.Task_json import Point, Task1_points
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from topics_json.Task_json import SearchPath


MAX_RETRIES = 3
AGENT_TIMEOUT = 30  # seconds


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    replies = session.get("pipeline/task1/start")

    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    data = json.loads(data_reply["data"])
    print(f"[TASK1] Received data: {data}")

    provider = OpenAIProvider(
        base_url="http://localhost:11434/v1",
        api_key="ollama",
    )
    model = OpenAIChatModel("mistral", provider=provider)

    path_planner_agent = Agent(
        model,
        output_type=SearchPath,
        system_prompt=(
            "Du bist ein Pfad-Planer für einen Such-Roboter. "
            "Plane eine Boustrophedon-Route (Zick-Zack) fuer ein Rechteckfeld. "
            "Bahnabstand ist immer genau 1 Meter. Startpunkt ist immer (0, 0). "
            "Gib NUR die Wendepunkte aus (nicht den Startpunkt). "
            "Beispiel fuer ein 3x2 Meter Feld: "
            "Punkte in Fahrreihenfolge: (3,0), (3,1), (0,1), (0,2), (3,2). "
            "Die Punkte muessen in Fahrreihenfolge sortiert sein."
            "Gebe dir Punkte zwingend dem Pydantic Model nach aus"
        ),
    )

    user_prompt = (
        f"Feldgroesse: {data['x']}x{data['y']} Meter (Breite x Hoehe). "
        f"Berechne die Wendepunkte fuer eine Boustrophedon-Route mit 1m Bahnabstand."
    )

    result = None

    try:
        for attempt in range(MAX_RETRIES):
            try:
                time_start = time.time()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(path_planner_agent.run_sync, user_prompt)
                    result_agent = future.result(timeout=AGENT_TIMEOUT)
                elapsed = time.time() - time_start

                search_path: SearchPath = result_agent.data
                print(f"[TASK1] Agent geplant in {elapsed:.2f}s: {search_path.description}")

                points_dict = {}
                for i, point in enumerate(search_path.points, 1):
                    points_dict[f"point{i}"] = Point(x=point.x, y=point.y)

                result = Task1_points(points=points_dict)
                break

            except FuturesTimeoutError:
                print(f"[TASK1] Timeout nach {AGENT_TIMEOUT}s (Versuch {attempt + 1}/{MAX_RETRIES})")
            except Exception as e:
                print(f"[TASK1] Agent error (Versuch {attempt + 1}/{MAX_RETRIES}): {e}")
    finally:
        session.close()
        return result

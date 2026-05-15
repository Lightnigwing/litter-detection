import asyncio
import json
import time
from pathlib import Path
from config import Settings
from topics_json.Task_json import Point, Task1_points
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from topics_json.Task_json import SearchPath
import mlflow

_MLFLOW_AGENT_DB = Path(__file__).parent.parent / "mlflow_agent.db"
MAX_RETRIES = 3
AGENT_TIMEOUT = 120


async def _run_attempt(agent: Agent, prompt: str) -> tuple[SearchPath, float]:
    time_start = time.time()
    result_agent = await asyncio.wait_for(agent.run(prompt), timeout=AGENT_TIMEOUT)
    return result_agent.output, time.time() - time_start


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    try:
        mlflow.set_tracking_uri(f"sqlite:///{_MLFLOW_AGENT_DB}")
        mlflow.set_experiment("task1-agent")
    except Exception:
        pass

    replies = session.get("pipeline/task1/start")
    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())
    data = json.loads(data_reply["data"])
    print(f"[TASK1] Received data: {data}")

    provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    model = OpenAIChatModel("qwen2.5:7b", provider=provider)
    agent = Agent(
        model,
        output_type=SearchPath,
        retries=3,
        system_prompt=(
            "Du bist ein Pfadplaner fuer einen autonomen Suchroboter.\n"
            "Der Roboter startet immer bei x=0.0 und y=0.0.\n"
            "Die uebergebene Flaeche hat eine Breite (x) und Hoehe (y) in Metern.\n\n"

            "Der Roboter sieht nach vorne mit einer Sichtbreite von 1.5 Metern.\n"
            "Nutze daher einen Bahnenabstand von maximal 1.2 Metern.\n"

            "Erzeuge einen vollstaendigen Abdeckungspfad "
            "im Lawnmower-/Boustrophedon-Muster.\n\n"
            "Die Reihenfolge ist kritisch"

            "Regeln:\n"
            "- Fahre nur gerade Linien.\n"
            "- Verwende nur Wendepunkte.\n"
            "- Der Abstand zwischen Fahrbahnen betraegt 1.0 Meter.\n"
            "- Beginne bei (0,0).\n"
            "- Fahre zuerst entlang der y-Achse.\n"
            "- Danach im Zick-Zack bis die gesamte Flaeche abgedeckt ist.\n"
            "- Gib ausschließlich gueltiges JSON passend zum Pydantic-Schema zurück.\n"
            "- Keine Erklaerungen.\n\n"

            "Beispiel fuer 2x2 Meter:\n"
            "{\n"
            '  "points": [\n'
            '    {"x": 0.0, "y": 2.0},\n'
            '    {"x": 1.0, "y": 2.0},\n'
            '    {"x": 1.0, "y": 0.0},\n'
            '    {"x": 2.0, "y": 0.0},\n'
            '    {"x": 2.0, "y": 2.0}\n'
            "  ]\n"
            "}"
        ),
    )

    user_prompt = (
        f"Flaeche: Breite={data['x']} Meter, Hoehe={data['y']} Meter."
    )

    result = None
    status = "failed"
    elapsed = 0.0
    attempts = 0

    with mlflow.start_run(run_name="task1"):
        try:
            mlflow.log_params({"field_x": data["x"], "field_y": data["y"], "model": "qwen2.5:7b"})
        except Exception:
            pass

        for attempt in range(MAX_RETRIES):
            attempts = attempt + 1
            try:
                search_path, elapsed = asyncio.run(_run_attempt(agent, user_prompt))
                result = Task1_points(
                    points={f"point{i}": p for i, p in enumerate(search_path.points, 1)}
                )
                status = "success"
                print(f"[TASK1] Agent fertig in {elapsed:.2f}s, {len(search_path.points)} Punkte")
                break
            except asyncio.TimeoutError:
                status = "timeout"
                print(f"[TASK1] Timeout nach {AGENT_TIMEOUT}s (Versuch {attempts}/{MAX_RETRIES})")
            except Exception as e:
                status = "error"
                print(f"[TASK1] Fehler (Versuch {attempts}/{MAX_RETRIES}): {e}")

        try:
            mlflow.set_tag("status", status)
            mlflow.log_metrics({"elapsed_time_s": round(elapsed, 3), "attempts_needed": attempts})
            if result is not None:
                mlflow.log_metric("point_count", len(result.points))
                mlflow.log_text(result.model_dump_json(indent=2), "result_points.json")
        except Exception:
            pass

    session.close()
    return result

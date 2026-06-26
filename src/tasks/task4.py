import asyncio
import json
import threading
import time
from config import Settings
from topics_pydantic_models.pydantic_models import Point, Task4, SearchPath
import zenoh
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from interfaces.topics import TOPICS

MAX_RETRIES = 3
AGENT_TIMEOUT = 180


async def _run_attempt(agent: Agent, prompt: str) -> tuple[SearchPath, float]:
    t0 = time.time()
    out = await asyncio.wait_for(agent.run(prompt), timeout=AGENT_TIMEOUT)
    return out.output, time.time() - t0


def _nearest_neighbor(start: dict, litter_points: dict[str, dict]) -> list[Point]:
    """Deterministischer Fallback: Nearest-Neighbor-Reihenfolge ab der Startposition."""
    remaining = [Point(x=float(p["x"]), y=float(p["y"])) for p in litter_points.values()]
    cur_x, cur_y = float(start["x"]), float(start["y"])
    ordered: list[Point] = []
    while remaining:
        nxt = min(remaining, key=lambda p: (p.x - cur_x) ** 2 + (p.y - cur_y) ** 2)
        ordered.append(nxt)
        remaining.remove(nxt)
        cur_x, cur_y = nxt.x, nxt.y
    return ordered


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

    if current_pose is None:
        print("[TASK4] ERROR: Konnte aktuelle Position vom Odometry-Topic nicht lesen!")
        session.close()
        raise RuntimeError("task4: Position konnte nicht gelesen werden")

    print(f"[TASK4] Current pose: {current_pose}")
    print(f"[TASK4] Received litter points: {litter_points}")

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

    # Pydantic-AI Agent für intelligente Routenplanung.
    # Output ist eine Liste (wie task1/SearchPath) — robuster für kleine Modelle als
    # ein dict mit dynamischen Keys. Die point1/point2/...-Keys vergeben wir danach selbst.
    provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    model = OpenAIChatModel("qwen2.5:7b", provider=provider)
    route_planner_agent = Agent(
        model,
        # PromptedOutput statt Tool-Calling: qwen schreibt das JSON-Array als Text
        # (wie im Prompt verlangt); pydantic-ai parst es, statt auf einen Tool-Call
        # zu warten (sonst "Exceeded maximum output retries").
        output_type=PromptedOutput(SearchPath),
        output_retries=3,
        system_prompt=(
            "Du bist ein intelligenter Router für einen Hund-Roboter. "
            "Der Roboter startet bei seiner aktuellen Position und muss alle Müllpunkte besuchen. "
            "Optimiere die Reihenfolge der Punkte, um die Gesamtfahrstrecke zu minimieren. "
            "Der Hund läuft nur in geraden Linien zwischen den Punkten. "
            "Gib AUSSCHLIESSLICH gültiges JSON passend zum Schema zurück: "
            'eine geordnete Liste der Punkte, z.B. { "points": [ {"x": 1.0, "y": 2.0}, ... ] }. '
            "Gib jeden Eingabepunkt genau einmal aus, nur in optimierter Reihenfolge. "
            "Keine Erklärungen, kein zusätzlicher Text."
        ),
    )

    user_prompt = (
        f"Aktuelle Position: x={current_pose['x']}, y={current_pose['y']}. "
        f"Müllpunkte: {json.dumps(litter_points)}. "
        "Plane die kürzeste Route und gib die Punkte als JSON-Array in optimierter "
        "Reihenfolge zurück."
    )

    ordered_points: list[Point] | None = None
    status = "failed"
    attempts = 0

    for attempt in range(MAX_RETRIES):
        attempts = attempt + 1
        try:
            search_path, elapsed = asyncio.run(_run_attempt(route_planner_agent, user_prompt))
            ordered_points = search_path.points
            status = "success"
            print(f"[TASK4] Agent fertig in {elapsed:.2f}s: {len(ordered_points)} Punkte")
            break
        except asyncio.TimeoutError:
            status = "timeout"
            print(f"[TASK4] Timeout nach {AGENT_TIMEOUT}s (Versuch {attempts}/{MAX_RETRIES})")
        except Exception as e:
            status = "error"
            print(f"[TASK4] Fehler (Versuch {attempts}/{MAX_RETRIES}): {e}")

    if ordered_points is None:
        # Fallback: deterministische Nearest-Neighbor-Reihenfolge, damit die Pipeline nie hängt
        ordered_points = _nearest_neighbor(current_pose, litter_points)
        status = "fallback"
        print(f"[TASK4] Fallback (Nearest-Neighbor) nach {attempts} Versuchen verwendet.")

    # Punkte von 1 an durchnummerieren
    points_dict = {f"point{i}": p for i, p in enumerate(ordered_points, 1)}
    result = Task4(litter_points=points_dict)

    session.close()
    return result

import json
from config import Settings
from topics_json.Task_json import Point, Task1_points
import zenoh

from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


class PathPoint(BaseModel):
    """Ein Punkt im Suchpfad."""
    name: str
    x: float
    y: float


class SearchPath(BaseModel):
    """Der geplante Suchpfad mit mehreren Punkten."""
    points: list[PathPoint]
    description: str


def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies = session.get("pipeline/task1/start")

    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    result = None

    #NOTE: Enthält x und y Wert des User in einem dict, z.B. {"x": 1.0, "y": 2.0}
    data = json.loads(data_reply["data"])
    
    # Main loop der Task-Logik
    while result is None:
        try:
            """
            Hier den Code einfügen den ihr schreibt der das Result produzier.
            Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

            Task1: x und y als input, Weg planen, Punkte als Output
            
            result = Task1_points(points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})
            """
            print(f"[TASK1] Received data: {data}")
            
            # Pydantic-AI Agent für intelligente Pfad-Planung
            provider = OpenAIProvider(
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )
            model = OpenAIChatModel("gemma4:e4b", provider=provider)
            
            path_planner_agent = Agent(
                model,
                result_type=SearchPath,
                system_prompt=(
                    "Du bist ein intelligenter Pfad-Planer fuer einen Such-Roboter. "
                    "Der Roboter startet bei (0, 0) in einem Rechteckfeld mit Breite und Hoehe, "
                    "die du aus den User-Daten bekommst (x=Breite, y=Hoehe). "
                    "Die Kamera deckt 1 Meter Breite ab, daher darf der Abstand zwischen Bahnen max. 1 Meter sein. "
                    "Plane eine Boustrophedon-Route (Zick-Zack), die >95% der Flaeche abdeckt. "
                    "Der Hund laeuft immer nur gerade Linien zwischen den Punkten. "
                    "Gib nur die Punkte aus, an denen der Hund drehen muss (also Bahn-Endpunkte). "
                    "Die Punkte muessen in Fahrreihenfolge sortiert sein. "
                    "Rueckgabe MUSS ein JSON sein mit keys point1, point2, ... und x/y je Punkt. "
                    "Keine anderen Keys verwenden."
                ),
            )
            
            # Agent ausführen
            user_prompt = (
                f"Startpunkt ist (0, 0). "
                f"Feldgroesse: {data['x']}x{data['y']} Meter (Breite x Hoehe). "
                f"Bahnabstand <= 1 Meter. "
                f"Bitte nur Wendepunkte ausgeben (jede Stelle, an der der Hund drehen muss)."
            )
            
            result_agent = path_planner_agent.run_sync(user_prompt)
            search_path: SearchPath = result_agent.data
            
            print(f"[TASK1] Agent geplant: {search_path.description}")
            
            # Konvertiere SearchPath in Task1_points Format
            points_dict = {}
            for i, point in enumerate(search_path.points, 1):
                points_dict[f"point{i}"] = Point(x=point.x, y=point.y)
            
            result = Task1_points(points=points_dict)
        
            return result
        finally:
            session.close()



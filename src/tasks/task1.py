import json
from config import Settings
from topics_json.Task_json import Point, Task1_points
import zenoh

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
        """
        Hier den Code einfügen den ihr schreibt der das Result produzier.
        Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

        Task1: x und y als input, Weg planen, Punkte als Output
        
        result = Task1_points(points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})
        """
        print(f"[TASK1] Received data: {data}")
        

        # Dummy Data
        result = Task1_points(points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})

        return result



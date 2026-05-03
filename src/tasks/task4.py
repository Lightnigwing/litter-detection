import json
from config import Settings
from topics_json.Task_json import Point, Task4
import zenoh

def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies = session.get("pipeline/task2_2/done")

    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    result = None
    #NOTE: Enthält litter_points, z.B. {"litter_points": {"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)}} 
    data = json.loads(data_reply["data"])
    data = data["litter_points"]
    # Main loop der Task-Logik
    while result is None:
        try:
            """
            Hier den Code einfügen den ihr schreibt der das Result produzier.
            Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

            result = Task4(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})
            """
            print(f"[TASK4] Received data: {data}")

            result = Task4(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})

            return result
        finally:
            session.close()


import json
from config import Settings
from topics_json.Task_json import Point, Task2_1
import zenoh

def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies = session.get("pipeline/task1/done")

    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    result = None
    data = json.loads(data_reply["data"])
    
    # Main loop der Task-Logik
    while result is None:
        """
        Hier den Code einfügen den ihr schreibt der das Result produzier.
        Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

        Task2_1: Input Punkte von Task1, Ablaufen der Punkte, letzen punkt erreicht

        result = Task2_1(lastpoint=Point(x=..., y=...))
        """
        print(f"[TASK2_1] Received data: {data}")

        result = Task2_1(lastpoint=Point(x=1.0, y=2.0))

        return result



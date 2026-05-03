import json
from config import Settings
from topics_json.Task_json import Point, Task2_2
import zenoh
#TODO: Interference einbauen, Queue einbauen
#TODO: Croppen der Bilder mit Müll
#TODO: gecroppte Bilder mit Müll an Agenten (evtl batchweise)

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
        try:
            """
            Hier den Code einfügen den ihr schreibt der das Result produzier.
            Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

            Task2_2: Input cameraframes, poition Hund ,Litter Detection, Output Punkte mit müll, amount müll

            result = Task2_2(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)}, amount_litter=5)
            """
            print(f"[TASK2_2] Received data: {data}")

            result = Task2_2(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)}, amount_litter=5)

            return result
        finally:
            session.close()


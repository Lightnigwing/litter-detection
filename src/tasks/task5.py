import json
from config import Settings
from topics_json.Task_json import Task5
import zenoh

def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies = session.get("pipeline/task4/done") 

    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())

    result = None
    data = json.loads(data_reply["data"])
    
    #NOTE An Felix, der zenoh Storage hört nur auf "pipline/**/start und "pipeline/**/done"
    # für die kommunikation zwischen Task5,6 maybe publish, subscribe da das live geht

    # Main loop der Task-Logik
    while result is None:
        """
        Hier den Code einfügen den ihr schreibt der das Result produzier.
        Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal
        """
        print(f"[TASK5] Received data: {data}")

        result = Task5(point_reached=True)

        return result



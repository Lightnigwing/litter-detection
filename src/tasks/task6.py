import json
from config import Settings
from topics_json.Task_json import Task6
import zenoh

def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    
    
    #NOTE An Felix, der zenoh Storage hört nur auf "pipline/**/start und "pipeline/**/done"
    # für die kommunikation zwischen Task5,6 maybe publish, subscribe da das live geht
    
    result = None
    
    data = False

    # Main loop der Task-Logik
    while result is None:
        """
        Hier den Code einfügen den ihr schreibt der das Result produzier.
        Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal
        """
        print(f"[TASK6] Received data: {data}")

        result = Task6(finished_emote=True)

        return result



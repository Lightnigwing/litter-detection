import json
from config import Settings
from topics_json.Task_json import Task3
import zenoh

def run_task():
    # Initialisiert Zenoh-Session
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    # Ausnahme muss als einziges auf start hören, da es keine Task0 gibt
    # Holt sich die Daten aus der vorherigen Task, um die Logik auszuführen (mit Zenoh Storage)
    replies_2_1 = session.get("pipeline/task2_1/done")

    for reply in replies_2_1:
        data_reply_2_1 = json.loads(reply.ok.payload.to_bytes())

    result = None
    data_2_1 = json.loads(data_reply_2_1["data"])

    # Kommen dann Anzahl an gefundenem Müll
    replies_2_2 = session.get("pipeline/task2_2/done")

    for reply in replies_2_2:
        data_reply_2_2 = json.loads(reply.ok.payload.to_bytes())

    data_2_2 = json.loads(data_reply_2_2["data"])
    
    # Main loop der Task-Logik
    while result is None:
        try:
            """
            Hier den Code einfügen den ihr schreibt der das Result produzier.
            Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

            Task3: input angekommen an ende, Anzahl müll, witz machen, Output: witz mit Müll
            
            result = Task3(witz=f"Warum hat der Müllsack einen Deckel? Damit der Müll nicht rauskommt!")
            """
            print(f"[TASK3] Received data: {data_2_1}")

            result = Task3(witz=f"Warum hat der Müllsack einen Deckel? Damit der Müll nicht rauskommt!")

            return result
        finally:
            session.close()


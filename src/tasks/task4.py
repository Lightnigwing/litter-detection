import asyncio
import json
import threading
import time
from config import Settings
from topics_pydantic_models.pydantic_models import Point, Task4, SearchPath
import zenoh

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
            """
            Hier den Code einfügen den ihr schreibt der das Result produzier.
            Wichtig: return result enthält ein Dict, mit allen Daten aufeinmal

            result = Task4(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})
            """
            print(f"[TASK4] Received data: {data}")

            result = Task4(litter_points={"point1": Point(x=1.0, y=2.0), "point2": Point(x=3.0, y=4.0)})

    session.close()
    return result

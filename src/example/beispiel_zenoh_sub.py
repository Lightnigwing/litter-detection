import json
from config import Settings# Zenoh-Session starten
import zenoh
from topics_json.topics import TOPICS

# Callback-Funktion für eingehende Daten
def listener(sample):
    msg = json.loads(bytes(sample.payload))
    task_id = msg["task_id"]
    data = msg["data"]
    a = data["points"]

    print(f"[WORKER] Running {task_id}")
    print(f"Empfangen: {type(msg)}")
    #print(f"Empfangen: {bytes(sample.payload)}")


settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)

key = TOPICS.demo.test

# Subscriber registrieren
sub = session.declare_subscriber(key, listener)

print("Warte auf Nachrichten...")

# Programm am Leben halten
input()

"""
msg = json.loads(sample.payload.to_string())
    task_id = msg["task_id"]

    print(f"[WORKER] Running {task_id}")

    try:
        run_fn = load_task(task_id)
        result_data = run_fn(msg.get("data", {}))

        result = {
            "task_id": task_id,
            "run_id": msg["run_id"],
            "status": "done",
            "data": result_data
        }
"""
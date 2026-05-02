import json

import zenoh
import time
from topics_json.topics import TOPICS
from config import Settings

# Zenoh-Session starten
settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)

topic = TOPICS.demo.test
id = 0
while True:
    msg = {
            "task_id": 1,
            "run_id": id,
            "status": "done",
            "data": {"points": [
                        {"x": 1, "y": 5},
                        {"x": 2, "y": 8},
                        {"x": 3, "y": 2},
                        {"x": 4, "y": 7},
                        {"x": 5, "y": 1},
                        {"x": 6, "y": 9},
                        {"x": 7, "y": 3},
                        {"x": 8, "y": 6},
                        {"x": 9, "y": 4},
                        {"x": 10, "y": 0},
                            ]}  
            }
    session.put(topic, json.dumps(msg))
    print(f"Gesendet: {msg}")
    id += 1

    time.sleep(3)  # jede Sekunde senden
    #
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
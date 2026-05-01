import sys
import time
import zenoh
import json
import importlib
from config import Settings

settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)

# Läd die Funktion run aus dem Modul tasks.{task_id}, um die entsprechende Task-Logik ausführen
def load_task(task_id):
    module = importlib.import_module(f"tasks.{task_id}")
    return module.run_task


def on_start(sample):
    msg = json.loads(bytes(sample.payload))
    task_id = msg["task_id"]
    run_id = msg["run_id"]

    print(f"[WORKER] Running {task_id}")

    try:
        run_fn = load_task(task_id)

        print(f"[WORKER] Executing {task_id}")
        result_data = run_fn()
        print(f"[WORKER] Finished {task_id} with result: {result_data}")
        result = {
            "task_id": task_id,
            "run_id": run_id,
            "status": "done",
            "data": result_data.model_dump_json()
        }

        session.put(f"pipeline/{task_id}/done", json.dumps(result))

    except Exception as e:
        session.put(f"pipeline/{task_id}/error", json.dumps({
            "task_id": task_id,
            "run_id": run_id,
            "status": "error",
            "error": str(e)
        }))
        print(f"[WORKER] Error in {task_id}: {e}")

# Hört auf Start von Tasks, führt sie aus und veröffentlicht die Ergebnisse auf dem entsprechenden Done-Topic.
session.declare_subscriber("pipeline/*/start", on_start)

print("Worker running...")
while True:
    try:
        time.sleep(1)

    except KeyboardInterrupt:
        print("\nWorker beendet (Strg+C).")
        session.close()
        break
  

import os
import subprocess
import sys
from topics_json.Task_json import Task1_user
import zenoh
import yaml
import json
import uuid
import time
from config import Settings

settings = Settings()
conf = zenoh.Config()
conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
session = zenoh.open(conf)


# Load pipeline configuration
path_pipeline = os.path.join(os.getcwd(), "src", "task_pipeline.yaml")
with open(path_pipeline) as f:
    pipeline = yaml.safe_load(f)


# Get tasks and dependencies
tasks = {t["id"]: t for t in pipeline["tasks"]}

# Sets to track which tasks have been started or are done
done = set()
started = set()

# Unique ID for tracking the run
run_id = str(uuid.uuid4())

# Checks if a task can be started (i.e. all dependencies are done)
def can_run(task):
    return all(dep in done for dep in task.get("depends_on", []))

# Function to start a task by publishing to its start topic
def start_task(task_id):
    msg = {
        "task_id": task_id,
        "run_id": run_id,
        "status": "start",
        "data": {}
    }

    session.put(f"pipeline/{task_id}/start", json.dumps(msg))
    print(f"[ORCH] Started {task_id}")


def on_done(sample):
    msg = json.loads(bytes(sample.payload))
    task_id = msg["task_id"]

    if msg["run_id"] != run_id:
        return

    data = msg["data"]

    print(f"[ORCH] Done {task_id}")
    print(f"[ORCH] Result: {data}")
    done.add(task_id)

session.declare_subscriber("pipeline/*/done", on_done)

# Main loop: start tasks as soon as their dependencies are done, ends when all tasks are done
def main():
    # Worker, NavManager und Pose-Source starten
    src_dir = os.path.join(os.getcwd(), "src")
    worker = subprocess.Popen([sys.executable, "src/worker.py"])
    nav_proc = subprocess.Popen(
        [sys.executable, "-m", "nav.nav_manager"], cwd=src_dir
    )
    robot_mode = os.environ.get("LITTER_ROBOT_MODE", "mock")
    if robot_mode == "real":
        # Echter Go2: robodog-Bridge übernimmt Odometry über WebRTC
        pose_proc = subprocess.Popen(
            [sys.executable, "-m", "robodog.main"], cwd=src_dir
        )
    else:
        # Mock: integriert MovementCommands zu einer Pose
        pose_proc = subprocess.Popen(
            [sys.executable, "-m", "nav.mock_odometry"], cwd=src_dir
        )
    print(f"[ORCH] Robot mode: {robot_mode}")
    time.sleep(2)
    
    user_input_x, user_input_y = None, None

    # Initial data for Task1
    while user_input_x is None or user_input_y is None:
        try:
            user_input_x, user_input_y = map(int, input("Gib x und y ein: ").split())
        except ValueError:
            print("Ungültige Eingabe. Bitte gib zwei ganze Zahlen ein, getrennt durch ein Leerzeichen.")
        except KeyboardInterrupt:
            print("\nAbbruch durch Benutzer (Strg+C).")
            session.close()
            break

    initial_data = Task1_user(
        x=user_input_x, 
        y=user_input_y
        )

    
    # Start Task1 with initial data
    session.put(f"pipeline/task1/start", json.dumps({
        "task_id": "task1",
        "run_id": run_id,
        "status": "start",
        "data": initial_data.model_dump_json()
    }))

    started.add("task1")

    while len(done) < len(tasks):
        try:
            for task in tasks.values():
                if task["id"] not in started and can_run(task):
                    start_task(task["id"])
                    started.add(task["id"])

            time.sleep(0.2)
        except KeyboardInterrupt:
            print("\nAbbruch durch Benutzer (Strg+C).")
            session.close()
            break
    session.close()
    for proc in (worker, nav_proc, pose_proc):
        proc.terminate()
        proc.wait()
        

    

if __name__ == "__main__":
    main()

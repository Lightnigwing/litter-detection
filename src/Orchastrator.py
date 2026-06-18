import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path
import zenoh
import yaml
import json
import uuid
import time
from config import Settings

settings = Settings()
session = zenoh.open(settings.zenoh_config())


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


_TMUX_SESSION = "litter-orch"


class TmuxProcess:
    """Wraps a process launched in a tmux window; satisfies .terminate()/.wait()."""

    def __init__(self, session: str, window: str) -> None:
        time.sleep(0.3)
        r = subprocess.run(
            ["tmux", "display-message", "-p", "-t", f"{session}:{window}", "#{pane_pid}"],
            capture_output=True, text=True,
        )
        self._pid = int(r.stdout.strip())

    def terminate(self) -> None:
        try:
            os.kill(self._pid, signal.SIGTERM)
        except ProcessLookupError:
            pass

    def wait(self) -> None:
        while True:
            try:
                os.kill(self._pid, 0)
                time.sleep(0.1)
            except ProcessLookupError:
                return


def _spawn(name: str, module: str, cwd: str):
    args = [sys.executable, "-m", module]

    if sys.platform == "win32":
        return subprocess.Popen(args, cwd=cwd, creationflags=subprocess.CREATE_NEW_CONSOLE)

    if shutil.which("tmux"):
        subprocess.run(["tmux", "new-session", "-d", "-s", _TMUX_SESSION], capture_output=True)
        subprocess.run(
            ["tmux", "new-window", "-d", "-t", _TMUX_SESSION, "-n", name,
             f"cd {cwd} && {' '.join(args)}"],
        )
        return TmuxProcess(_TMUX_SESSION, name)

    log_dir = Path(cwd).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"{name}.log"
    log_fh = open(log_path, "w")
    print(f"[ORCH] {name} → {log_path}")
    return subprocess.Popen(args, cwd=cwd, stdout=log_fh, stderr=log_fh)


# Main loop: start tasks as soon as their dependencies are done, ends when all tasks are done
def main():
    # Worker, NavManager und Pose-Source starten
    src_dir = os.path.join(os.getcwd(), "src")
    worker = subprocess.Popen([sys.executable, "-m", "worker"], cwd=src_dir)
    cam_proc = _spawn("camera", "camera.camera_realsense", src_dir)
    nav_proc = _spawn("nav_manager", "nav.nav_manager", src_dir)
    robot_mode = os.environ.get("LITTER_ROBOT_MODE", "real")
    if robot_mode == "real":
        pose_proc = _spawn("robodog", "robodog.main", src_dir)
    else:
        pose_proc = _spawn("mock_odometry", "nav.mock_odometry", src_dir)
    print(f"[ORCH] Robot mode: {robot_mode}")
    time.sleep(5)
    
    # Start Task0
    session.put(f"pipeline/task0/start", json.dumps({
        "task_id": "task0",
        "run_id": run_id,
        "status": "start",
        "data": {}
    }))

    started.add("task0")

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
    #cam_proc
    for proc in (worker, nav_proc, pose_proc, cam_proc):
        proc.terminate()
        proc.wait()
        

    

if __name__ == "__main__":
    main()

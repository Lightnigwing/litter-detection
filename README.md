# First Lab KI-Systeme

Over all task is to build a robot that can detect litter and notify its operator.

This project was build with the autoresaerch idea of Andrew Karpathy: https://github.com/karpathy/autoresearch

The overall idea is to critically look at the experiments and progress the AI made, identify improvements and integrate a further improved version into a robot setup.

Other approaches fine-tune a yolo model: e.g. see for https://github.com/jeremy-rico/litter-detection

## 1 Student Task

- [Task Description 1](student_task_1.md)
- [Context to this project](explainer.md)

## 2 Student Task

- [Task Description 2](student_task_2.md)

## Example images not in the dataset

|No litter | Litter |
|---|---|
|![](Image2.jpeg) | ![](Image3.jpeg) |

## Autoresearch Content

> Note: There is already one good model in this repository. Thus you should be able to investigate the performance using the Analysis Notebook.

- [Analysis Notebook](analysis.ipynb)
- [Instructions](program.md)
- [Finding from previous runs](findings.md)

## Setup

Init project:

```bash
uv sync                  # alles außer Simulation (inkl. Pipeline + echter Robodog-Bridge)
uv sync --all-extras     # zusätzlich MuJoCo-Simulation
```

### Zenoh router (Docker)

Pipeline-Komponenten reden über Zenoh. Den Router via Compose starten:

```bash
docker compose -f litter_detection_docker/docker-compose.yml up -d
```

### Components

Jede Komponente hat einen eigenen `uv run` Entry-Point:

| Command | Beschreibung |
|---------|--------------|
| `uv run orch` | Pipeline-Orchestrator. Startet Worker + NavManager + Pose-Source automatisch als Subprozesse. Erwartet x/y-Eingabe für task1. |
| `uv run sim` | MuJoCo-Simulation des Go2 (Pose-Source). Optional `--headless` ohne mjviser. Braucht `--all-extras`. |
| `uv run robodog` | WebRTC-Bridge zum echten Go2 (Pose-Source). IP konfigurierbar in `src/config.py::go2_local_address`. |
| `uv run mlflow ui` | MLflow-Server für Experiment-/Training-History. |


Content:

- There is a [analysis.ipynb](analysis.ipynb) notebook to take a first look on the project and test the existing models.
- The project contains a mlflow project that stores the hole experiment and training history.





## Additional Content

- [Experiment Tracking](https://mlflow.org/docs/latest/ml/getting-started/deep-learning/)
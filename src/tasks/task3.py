import asyncio
import json
import time
from pathlib import Path
from config import Settings
from topics_pydantic_models.pydantic_models import Task3, Joke
import zenoh

def run_task():
    settings = Settings()
    session = zenoh.open(settings.zenoh_config())

    try:
        mlflow.set_tracking_uri(f"sqlite:///{_MLFLOW_AGENT_DB}")
        mlflow.set_experiment("task3-agent")
    except Exception:
        pass

    replies_2_1 = session.get("pipeline/task2_1/done")
    for reply in replies_2_1:
        data_reply_2_1 = json.loads(reply.ok.payload.to_bytes())
    data_2_1 = json.loads(data_reply_2_1["data"])

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


import asyncio
import json
import time
from pathlib import Path
from config import Settings
from topics_pydantic_models.pydantic_models import Task1_points, SearchPath, Task1_user
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import mlflow


def run_task():
    settings = Settings()
    session = zenoh.open(settings.zenoh_config())
    
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

    result = Task1_user(
        x=user_input_x, 
        y=user_input_y
        )
    
    session.close()
    return result

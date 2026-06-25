import asyncio
import json
import time
from pathlib import Path
from config import Settings
from topics_pydantic_models.pydantic_models import Task3, Joke
import zenoh
from pydantic_ai import Agent, PromptedOutput
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import mlflow
from tasks._ollama import warmup_model

_MLFLOW_AGENT_DB = Path(__file__).parent.parent / "mlflow_agent.db"
MAX_RETRIES = 3
AGENT_TIMEOUT = 180
FALLBACK_WITZ = "Warum hat der Müllsack einen Deckel? Damit der Müll nicht rauskommt!"


async def _run_attempt(agent: Agent, prompt: str) -> tuple[Joke, float]:
    t0 = time.time()
    out = await asyncio.wait_for(agent.run(prompt), timeout=AGENT_TIMEOUT)
    return out.output, time.time() - t0


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

    print(f"[TASK3] Received data: {data_2_1}, {data_2_2}")

    provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    model = OpenAIChatModel("qwen2.5:7b", provider=provider)
    agent = Agent(
        model,
        # PromptedOutput statt Tool-Calling: qwen2.5:7b schreibt das JSON als Text
        # (wie im Prompt verlangt) — pydantic-ai parst diesen Text, statt auf einen
        # Tool-Call zu warten, der nie kommt (sonst "Exceeded maximum output retries").
        output_type=PromptedOutput(Joke),
        retries=3,
        system_prompt=(
            "Du bist ein humorvoller Witzeerzähler.\n"
            "Erzeuge GENAU EINEN kurzen, jugendfreien Witz über Müll.\n\n"
            "Regeln:\n"
            "- Maximal 1–2 Sätze.\n"
            "- Verständlich, kein Slang, keine Beleidigungen.\n"
            "- Themenbezug: Müll, Recycling, Mülltrennung, Mülltonne o.ä.\n"
            "- Gib ausschließlich gültiges JSON passend zum Pydantic-Schema zurück.\n"
            "- Keine Erklärungen, keine Anführungszeichen außerhalb des JSON.\n\n"
            "Beispiel:\n"
            '{ "witz": "Warum hat der Müllsack einen Deckel? Damit der Müll nicht rauskommt!" }'
        ),
    )

    user_prompt = (
        f"Erzeuge einen Müll-Witz. Kontext: Es wurden {data_2_2['amount_litter']} Müllstücke gefunden."
    )

    # Modell vor dem getimten Versuch laden/pinnen (Kaltstart nach task2_2/llava vermeiden)
    warmup_model("qwen2.5:7b")

    result = None
    status = "failed"
    elapsed = 0.0
    attempts = 0

    with mlflow.start_run(run_name="task3"):
        try:
            mlflow.log_params({"model": "qwen2.5:7b", "amount_litter": data_2_2["amount_litter"]})
        except Exception:
            pass

        for attempt in range(MAX_RETRIES):
            attempts = attempt + 1
            try:
                joke, elapsed = asyncio.run(_run_attempt(agent, user_prompt))
                result = Task3(witz=joke.witz)
                status = "success"
                print(f"[TASK3] Agent fertig in {elapsed:.2f}s: {joke.witz}")
                break
            except asyncio.TimeoutError:
                status = "timeout"
                print(f"[TASK3] Timeout nach {AGENT_TIMEOUT}s (Versuch {attempts}/{MAX_RETRIES})")
            except Exception as e:
                status = "error"
                print(f"[TASK3] Fehler (Versuch {attempts}/{MAX_RETRIES}): {e}")

        if result is None:
            result = Task3(witz=FALLBACK_WITZ)
            status = "fallback"
            print(f"[TASK3] Fallback-Witz nach {attempts} Versuchen verwendet.")

        try:
            mlflow.set_tag("status", status)
            mlflow.log_metrics({"elapsed_time_s": round(elapsed, 3), "attempts_needed": attempts})
            mlflow.log_text(result.witz, "joke.txt")
        except Exception:
            pass

    session.close()
    return result

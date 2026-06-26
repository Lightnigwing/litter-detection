"""Gemeinsame Ollama-Helfer für die LLM-Tasks."""

import httpx

_OLLAMA_URL = "http://localhost:11434/api/generate"


def warmup_model(model: str = "qwen2.5:7b", keep_alive: str | int = "30m") -> None:
    """Lädt das Modell vor dem getimten Versuch in den VRAM und pinnt es dort.

    Nach task2_2 (llava-phi3) ist qwen2.5:7b aus dem VRAM verdrängt; der Kaltstart
    würde sonst in den eigentlichen, getimten Agent-Versuch fallen und ihn in den
    Timeout treiben. Dieser Best-Effort-Call zieht den Kaltstart vor den Timer.

    keep_alive="30m" (oder -1 für "nie entladen") hält das Modell anschließend warm.
    """
    try:
        httpx.post(
            _OLLAMA_URL,
            json={"model": model, "keep_alive": keep_alive, "stream": False},
            timeout=180.0,
        )
    except Exception:
        pass  # best effort — der eigentliche Versuch läuft trotzdem

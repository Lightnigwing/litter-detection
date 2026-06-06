import asyncio
import json
from os import name
import time
from pathlib import Path
from config import Settings
from topics_pydantic_models.pydantic_models import Point, Task1_points, SearchPath
import zenoh
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import mlflow
import matplotlib.pyplot as plt


def _make_positions(limit: float) -> list[float]:
    positions: list[float] = []
    v = 0.0
    while v < limit:
        positions.append(round(v, 1))
        v += 1.0
    if not positions or positions[-1] < limit:
        positions.append(round(limit, 1))
    return positions


def _optimal_path(field_x: float, field_y: float) -> list[tuple[float, float]]:
    path: list[tuple[float, float]] = []
    if field_x <= field_y:
        for i, xp in enumerate(_make_positions(field_x)):
            if i % 2 == 0:
                path.append((xp, 0.0))
                path.append((xp, field_y))
            else:
                path.append((xp, field_y))
                path.append((xp, 0.0))
    else:
        for i, yp in enumerate(_make_positions(field_y)):
            if i % 2 == 0:
                path.append((0.0, yp))
                path.append((field_x, yp))
            else:
                path.append((field_x, yp))
                path.append((0.0, yp))
    return path


def visualize_path(points: list[Point], field_x: float, field_y: float) -> None:
    x_vals = [p.x for p in points]
    y_vals = [p.y for p in points]
    optimal = _optimal_path(field_x, field_y)
    ox_vals = [p[0] for p in optimal]
    oy_vals = [p[1] for p in optimal]

    _, ax = plt.subplots(figsize=(max(6, field_x + 2), max(6, field_y + 2)))

    rect = plt.Polygon(
        [(0, 0), (field_x, 0), (field_x, field_y), (0, field_y)],
        fill=False, edgecolor="gray", linewidth=1.5, linestyle="--"
    )
    ax.add_patch(rect)

    ax.plot(ox_vals, oy_vals, marker=".", color="red", linewidth=1.2,
            markersize=4, linestyle="--", alpha=0.6, label="Optimal")
    ax.plot(x_vals, y_vals, marker="o", color="steelblue", linewidth=1.5,
            markersize=5, label="Agent")

    for idx, (x, y) in enumerate(zip(x_vals, y_vals), start=1):
        ax.annotate(str(idx), (x, y), textcoords="offset points", xytext=(5, 5), fontsize=8)

    ax.set_xlim(-0.5, field_x + 0.5)
    ax.set_ylim(-0.5, field_y + 0.5)
    ax.set_title(f"Roboterpfad  ({field_x} x {field_y} m)  —  Agent: {len(points)} Pkt,  Optimal: {len(optimal)} Pkt")
    ax.set_xlabel("X [m]")
    ax.set_ylabel("Y [m]")
    ax.legend()
    ax.grid(True, alpha=0.4)
    ax.set_aspect("equal")
    plt.tight_layout()
    plt.show()

_MLFLOW_AGENT_DB = Path(__file__).parent.parent / "mlflow_agent.db"
MAX_RETRIES = 3
AGENT_TIMEOUT = 120


async def _run_attempt(agent: Agent, prompt: str) -> tuple[SearchPath, float]:
    time_start = time.time()
    result_agent = await asyncio.wait_for(agent.run(prompt), timeout=AGENT_TIMEOUT)
    return result_agent.output, time.time() - time_start


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    try:
        mlflow.set_tracking_uri(f"sqlite:///{_MLFLOW_AGENT_DB}")
        mlflow.set_experiment("task1-agent")
    except Exception:
        pass
    """""
    replies = session.get("pipeline/task1/start")
    for reply in replies:
        data_reply = json.loads(reply.ok.payload.to_bytes())
    data = json.loads(data_reply["data"]) """""

    data = {"x": 8,"y": 18}

    print(f"[TASK1] Received data: {data}")

    provider = OpenAIProvider(base_url="http://localhost:11434/v1", api_key="ollama")
    model = OpenAIChatModel("qwen2.5:7b", provider=provider)
    agent = Agent(
        model,
        output_type=SearchPath,
        retries=3,
        system_prompt=(
            "# ROLLE\n"
            "Du bist ein deterministischer Pfadplaner fuer einen autonomen "
            "Suchroboter. Du berechnest einen vollstaendigen Abdeckungspfad fuer "
            "eine rechteckige Flaeche und gibst ihn als geordnete Wegpunktliste aus.\n\n"

            "# EINGABE\n"
            "Du erhaeltst zwei positive Zahlen: die Breite (x) und die Hoehe (y) der "
            "Flaeche in Metern. Die Flaeche reicht immer von (0,0) bis (Breite, Hoehe).\n\n"

            "# ROBOTER\n"
            "- Startet immer bei (0.0, 0.0).\n"
            "- Faehrt ausschliesslich gerade, achsenparallele Strecken "
            "(eine Bewegung aendert entweder x ODER y, niemals beides).\n"
            "- Kamera blickt nach vorne und scannt einen 1.5 m breiten Streifen.\n"
            "- Bahnabstand: 1.0 m (garantiert Ueberlappung, keine Luecken).\n\n"

            "# ALGORITHMUS (Boustrophedon / Lawnmower)\n"
            "## Schritt 1: Scanrichtung bestimmen\n"
            "Vergleiche Breite und Hoehe:\n"
            "- Breite <= Hoehe: scanne vertikal (Bahnen parallel zur y-Achse, entlang x)\n"
            "- Breite > Hoehe:  scanne horizontal (Bahnen parallel zur x-Achse, entlang y)\n"
            "Regel: Immer entlang der kuerzeren Dimension scannen -- das ergibt weniger Bahnen.\n\n"

            "## Schritt 2: Positionen berechnen\n"
            "Erzeuge Positionen entlang der Scanachse: 0.0, 1.0, 2.0, ... solange < Grenze.\n"
            "Haenge den Grenzwert (Breite bzw. Hoehe) an falls noch nicht enthalten.\n"
            "   Grenze=3: Positionen = [0.0, 1.0, 2.0, 3.0]\n"
            "   Grenze=4: Positionen = [0.0, 1.0, 2.0, 3.0, 4.0]\n\n"

            "## Schritt 3: Wegpunkte erzeugen\n"
            "Pro Position genau 2 Punkte (Bahnanfang und Bahnende), abwechselnd Richtung:\n"
            "Vertikal (Breite <= Hoehe): gerade Indizes (x, 0.0)->(x, Hoehe), "
            "ungerade Indizes (x, Hoehe)->(x, 0.0).\n"
            "Horizontal (Breite > Hoehe): gerade Indizes (0.0, y)->(Breite, y), "
            "ungerade Indizes (Breite, y)->(0.0, y).\n\n"

            "KRITISCH: Die letzte Position (= Grenzwert) ist PFLICHT und muss mit "
            "BEIDEN Endpunkten in der Liste stehen.\n"
            "Die Koordinate senkrecht zur Scanachse ist immer exakt 0.0 oder der "
            "Grenzwert -- niemals ein Zwischenwert.\n\n"

            "# AUSGABE\n"
            "- Ausschliesslich gueltiges JSON passend zum Pydantic-Schema "
            '{ "points": [ { "x": float, "y": float }, ... ] }.\n'
            "- Keine Erklaerungen, kein Text, keine Codeblock-Markierungen.\n"
            "- Alle Koordinaten als float mit einer Nachkommastelle.\n"
            "- Reihenfolge der Punkte ist kritisch und muss exakt dem Fahrweg entsprechen.\n\n"

            "# BEISPIEL A (Breite=3, Hoehe=5) -- Breite<=Hoehe -> vertikal -- 4 Positionen, 8 Punkte\n"
            "{\n"
            '  "points": [\n'
            '    {"x": 0.0, "y": 0.0},\n'
            '    {"x": 0.0, "y": 5.0},\n'
            '    {"x": 1.0, "y": 5.0},\n'
            '    {"x": 1.0, "y": 0.0},\n'
            '    {"x": 2.0, "y": 0.0},\n'
            '    {"x": 2.0, "y": 5.0},\n'
            '    {"x": 3.0, "y": 5.0},\n'
            '    {"x": 3.0, "y": 0.0}\n'
            "  ]\n"
            "}\n\n"

            "# BEISPIEL B (Breite=5, Hoehe=3) -- Breite>Hoehe -> horizontal -- 4 Positionen, 8 Punkte\n"
            "{\n"
            '  "points": [\n'
            '    {"x": 0.0, "y": 0.0},\n'
            '    {"x": 5.0, "y": 0.0},\n'
            '    {"x": 5.0, "y": 1.0},\n'
            '    {"x": 0.0, "y": 1.0},\n'
            '    {"x": 0.0, "y": 2.0},\n'
            '    {"x": 5.0, "y": 2.0},\n'
            '    {"x": 5.0, "y": 3.0},\n'
            '    {"x": 0.0, "y": 3.0}\n'
            "  ]\n"
            "}"
        )
    )

    field_x, field_y = data["x"], data["y"]
    if field_x <= field_y:
        positions = _make_positions(field_x)
        user_prompt = (
            f"Flaeche: Breite={field_x} Meter, Hoehe={field_y} Meter.\n"
            f"Scanrichtung: VERTIKAL -- Bahnen laufen von y=0.0 bis y={field_y} (volle Hoehe).\n"
            f"x-Positionen der Bahnen: {positions}\n"
            f"Erster Punkt: (0.0, 0.0). Erwartete Punktanzahl: {2 * len(positions)}."
        )
    else:
        positions = _make_positions(field_y)
        user_prompt = (
            f"Flaeche: Breite={field_x} Meter, Hoehe={field_y} Meter.\n"
            f"Scanrichtung: HORIZONTAL -- Bahnen laufen von x=0.0 bis x={field_x} (volle Breite).\n"
            f"y-Positionen der Bahnen: {positions}\n"
            f"Erster Punkt: (0.0, 0.0). Erwartete Punktanzahl: {2 * len(positions)}."
        )

    result = None
    status = "failed"
    elapsed = 0.0
    attempts = 0

    with mlflow.start_run(run_name="task1"):
        try:
            mlflow.log_params({"field_x": data["x"], "field_y": data["y"], "model": "qwen2.5:7b"})
        except Exception:
            pass

        for attempt in range(MAX_RETRIES):
            attempts = attempt + 1
            try:
                search_path, elapsed = asyncio.run(_run_attempt(agent, user_prompt))
                result = Task1_points(
                    points={f"point{i}": p for i, p in enumerate(search_path.points, 1)}
                )
                status = "success"
                print(f"[TASK1] Agent fertig in {elapsed:.2f}s, {len(search_path.points)} Punkte, {search_path.points}")
                visualize_path(search_path.points, data["x"], data["y"])
                break
            except asyncio.TimeoutError:
                status = "timeout"
                print(f"[TASK1] Timeout nach {AGENT_TIMEOUT}s (Versuch {attempts}/{MAX_RETRIES})")
            except Exception as e:
                status = "error"
                print(f"[TASK1] Fehler (Versuch {attempts}/{MAX_RETRIES}): {e}")

        try:
            mlflow.set_tag("status", status)
            mlflow.log_metrics({"elapsed_time_s": round(elapsed, 3), "attempts_needed": attempts})
            if result is not None:
                mlflow.log_metric("point_count", len(result.points))
                mlflow.log_text(result.model_dump_json(indent=2), "result_points.json")
        except Exception:
            pass

    session.close()
    return result

if __name__ == "__main__":
    run_task()
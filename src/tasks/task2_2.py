import asyncio
import base64
import json
import queue
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
import zenoh
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel

from config import Settings
from inference.inference_main import build_backend
from topics_json.Task_json import Point, Task2_2
from topics_json.topics import TOPICS

BATCH_SIZE = 10
OLLAMA_MODEL = "llama3.2-vision:11b"
OLLAMA_URL = "http://localhost:11434/v1"


@dataclass
class LitterFrame:
    overlay: np.ndarray
    position: Point


class ValidationResult(BaseModel):
    unique_litter_indices: list[int]


_ollama_client = AsyncOpenAI(base_url=OLLAMA_URL, api_key="ollama")
_ollama_model = OpenAIModel(OLLAMA_MODEL, openai_client=_ollama_client)

validator_agent = Agent(
    model=_ollama_model,
    result_type=ValidationResult,
    system_prompt=(
        "Du bist ein Müll-Erkennungsexperte. "
        "Die Frames zeigen Kameraaufnahmen – erkannter Müll ist orange-rot markiert. "
        "Prüfe, welche Frames wirklich Müll enthalten. "
        "Wenn dasselbe Objekt in mehreren Frames vorkommt, "
        "gib nur den Index des ersten Frames zurück."
    ),
)


def _crop_to_mask(
    overlay: np.ndarray,
    color_bgr: tuple[int, int, int],
    alpha: float,
    padding: int = 20,
) -> np.ndarray:
    # Per-channel range of blended pixels: blended = original*(1-alpha) + color*alpha
    lo = np.array([int(c * alpha) for c in color_bgr], dtype=np.uint8)
    hi = np.array([int(255 * (1 - alpha) + c * alpha) for c in color_bgr], dtype=np.uint8)

    mask = cv2.inRange(overlay, lo, hi)
    pts = cv2.findNonZero(mask)
    if pts is None:
        return overlay

    x, y, w, h = cv2.boundingRect(pts)
    h_img, w_img = overlay.shape[:2]
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(w_img, x + w + padding)
    y2 = min(h_img, y + h + padding)

    crop = overlay[y1:y2, x1:x2].copy()
    cv2.rectangle(crop, (x - x1, y - y1), (x - x1 + w, y - y1 + h), color_bgr, 2)
    return crop


async def _validate_batch(batch: list[LitterFrame]) -> list[LitterFrame]:
    images_b64: list[str] = []
    for lf in batch:
        ok, buf = cv2.imencode(".jpg", lf.overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if ok:
            images_b64.append(base64.b64encode(buf.tobytes()).decode())

    image_tags = "\n".join(
        f"Frame {i}: data:image/jpeg;base64,{b64}" for i, b64 in enumerate(images_b64)
    )
    prompt = f"Analysiere diese {len(images_b64)} Frames auf Müll:\n{image_tags}"

    try:
        result = await validator_agent.run(prompt)
        return [batch[i] for i in result.data.unique_litter_indices if i < len(batch)]
    except Exception as e:
        print(f"[TASK2_2] Agent-Fehler: {e}")
        return []


def run_task() -> Task2_2:
    settings = Settings()
    backend = build_backend(settings)

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    frame_queue: queue.Queue[LitterFrame | None] = queue.Queue()
    validated_litter: list[LitterFrame] = []
    validated_lock = threading.Lock()
    task2_1_done = threading.Event()
    processing_done = threading.Event()
    position_state: dict[str, Point] = {"current": Point(x=0.0, y=0.0)}
    position_lock = threading.Lock()

    def _wait_for_task2_1() -> None:
        while True:
            try:
                for reply in session.get("pipeline/task2_1/done"):
                    if reply.ok is not None:
                        task2_1_done.set()
                        frame_queue.put(None)  # sentinel: Frames-Sammlung beendet
                        return
            except Exception:
                pass
            time.sleep(1.0)

    threading.Thread(target=_wait_for_task2_1, daemon=True).start()

    def _on_position(sample: zenoh.Sample) -> None:
        try:
            data = json.loads(bytes(sample.payload))
            with position_lock:
                position_state["current"] = Point(x=float(data["x"]), y=float(data["y"]))
        except Exception:
            pass

    pos_sub = session.declare_subscriber("demo/position", _on_position)
    cropped_pub = session.declare_publisher(TOPICS.litter.cropped)

    def _on_frame(sample: zenoh.Sample) -> None:
        if task2_1_done.is_set():
            return
        img = cv2.imdecode(
            np.frombuffer(bytes(sample.payload), np.uint8), cv2.IMREAD_COLOR
        )
        if img is None:
            return
        result, overlay = backend.infer(img)
        if result["detections"]:
            cropped = _crop_to_mask(overlay, settings.mask_color_bgr, settings.mask_alpha)
            ok, buf = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality])
            if ok:
                cropped_pub.put(buf.tobytes())
            with position_lock:
                pos = position_state["current"]
            frame_queue.put(LitterFrame(overlay=cropped, position=pos))

    sub = session.declare_subscriber(settings.topic_frame, _on_frame)

    def _batch_worker() -> None:
        while True:
            batch: list[LitterFrame] = []
            deadline = time.monotonic() + 2.0
            sentinel_received = False

            while len(batch) < BATCH_SIZE and time.monotonic() < deadline:
                try:
                    item = frame_queue.get(timeout=0.2)
                    if item is None:
                        sentinel_received = True
                        break
                    batch.append(item)
                except queue.Empty:
                    pass

            if batch:
                validated = asyncio.run(_validate_batch(batch))
                with validated_lock:
                    validated_litter.extend(validated)
                print(f"[TASK2_2] Batch verarbeitet: {len(validated)}/{len(batch)} bestätigt")

            if sentinel_received:
                processing_done.set()
                return

    threading.Thread(target=_batch_worker, daemon=True).start()

    processing_done.wait()
    sub.undeclare()
    pos_sub.undeclare()
    cropped_pub.undeclare()
    session.close()

    with validated_lock:
        litter_points = {
            f"point{i + 1}": lf.position for i, lf in enumerate(validated_litter)
        }
        return Task2_2(litter_points=litter_points, amount_litter=len(validated_litter))

import asyncio
import base64
import json
import queue
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np
from loguru import logger
from topics_pydantic_models.topics import TOPICS
import zenoh
from openai import AsyncOpenAI
from pydantic import BaseModel
from config import Settings
from inference.inference_main import build_backend
from topics_pydantic_models.pydantic_models import Point, Task2_2


BATCH_SIZE = 4
JPEGQUALITY = 85
MASK_SIMILARITY_THRESHOLD = 0.85  # IoU-Schwelle für Duplikat-Erkennung


@dataclass
class LitterFrame:
    overlay: np.ndarray
    position: Point


class ValidationResult(BaseModel):
    unique_litter_indices: list[int]


client = AsyncOpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama",
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


def _extract_mask(
    overlay: np.ndarray,
    color_bgr: tuple[int, int, int],
    alpha: float,
) -> np.ndarray:
    lo = np.array([int(c * alpha) for c in color_bgr], dtype=np.uint8)
    hi = np.array([int(255 * (1 - alpha) + c * alpha) for c in color_bgr], dtype=np.uint8)
    return cv2.inRange(overlay, lo, hi)


def _masks_are_similar(mask1: np.ndarray, mask2: np.ndarray, threshold: float) -> bool:
    union = cv2.bitwise_or(mask1, mask2)
    union_px = int(np.count_nonzero(union))
    if union_px == 0:
        return True
    iou = int(np.count_nonzero(cv2.bitwise_and(mask1, mask2))) / union_px
    return iou >= threshold


async def _validate_batch(batch: list[LitterFrame]) -> list[LitterFrame]:
    content = [
        {
            "type": "text",
            "text": (
                "Analysiere die folgenden Frames auf echten Müll. "
                "Die orange markierten Bereiche sind vom Modell erkannte Objekte. "
                "Gib nur die Indizes zurück, die wirklich Müll enthalten (keine Fehlerkennungen). "
                "Falls derselbe Müll in mehreren Frames vorkommt, nur den ersten Index zurückgeben. "
                'Antwort nur als JSON: {"unique_litter_indices":[0,2]}'
            ),
        }
    ]

    for i, lf in enumerate(batch):
        ok, buf = cv2.imencode(
            ".jpg",
            lf.overlay,
            [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY],
        )

        if not ok:
            continue

        b64 = base64.b64encode(buf.tobytes()).decode()
        content.append(
            {
                "type": "text",
                "text": f"Frame {i}",
            }
        )
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}"
                },
            }
        )

    logger.info("LLM-Anfrage | frames={}", len(batch))
    t0 = time.monotonic()

    try:
        response = await client.chat.completions.create(
            model="qwen2.5vl:7b",
            messages=[
                {
                    "role": "user",
                    "content": content,
                }
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        llm_ms = (time.monotonic() - t0) * 1000
        raw = response.choices[0].message.content
        data = ValidationResult.model_validate_json(raw)
        unique = [
            batch[i]
            for i in data.unique_litter_indices
            if i < len(batch)
        ]
        logger.info(
            "LLM fertig | {:.0f}ms | bestätigt={}/{}",
            llm_ms,
            len(unique),
            len(batch),
        )
        return unique

    except Exception:
        logger.exception("LLM Fehler")
        return []


def run_task() -> Task2_2:
    settings = Settings()
    if not settings.task2_2_logging:
        logger.disable("task2_2")
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
    last_mask_state: dict[str, np.ndarray | None] = {"mask": None}
    last_mask_lock = threading.Lock()
    run_start = time.monotonic()

    """
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
    """

    def _wait_for_task2_1() -> None:
        time.sleep(60.0)
        logger.info(
            "60 Sekunden abgelaufen — Frames-Sammlung beendet | queue_size={}",
            frame_queue.qsize(),
        )
        task2_1_done.set()
        frame_queue.put(None)  # sentinel: Frames-Sammlung beendet

    threading.Thread(target=_wait_for_task2_1, daemon=True).start()

    def _on_position(sample: zenoh.Sample) -> None:
        try:
            data = json.loads(bytes(sample.payload))
            with position_lock:
                position_state["current"] = Point(x=float(data["x"]), y=float(data["y"]))
        except Exception:
            pass

    pos_sub = session.declare_subscriber("robodog/system_state/odometry", _on_position)
    cropped_pub = session.declare_publisher(TOPICS.litter.cropped)

    def _on_frame(sample: zenoh.Sample) -> None:
        if task2_1_done.is_set():
            return
        img = cv2.imdecode(
            np.frombuffer(bytes(sample.payload), np.uint8), cv2.IMREAD_COLOR
        )
        if img is None:
            return
        t0 = time.monotonic()
        result, overlay = backend.infer(img)
        infer_ms = (time.monotonic() - t0) * 1000
        if result["detections"]:
            mask = _extract_mask(overlay, settings.mask_color_bgr, settings.mask_alpha)
            with last_mask_lock:
                prev_mask = last_mask_state["mask"]
                if (
                    prev_mask is not None
                    and prev_mask.shape == mask.shape
                    and _masks_are_similar(prev_mask, mask, MASK_SIMILARITY_THRESHOLD)
                ):
                    logger.debug(
                        "Frame verworfen (Duplikat, IoU >= {}) | backend={:.1f}ms",
                        MASK_SIMILARITY_THRESHOLD,
                        infer_ms,
                    )
                    return
                last_mask_state["mask"] = mask
            cropped = _crop_to_mask(overlay, settings.mask_color_bgr, settings.mask_alpha)
            ok, buf = cv2.imencode(".jpg", cropped, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY])
            if ok:
                cropped_pub.put(buf.tobytes(), encoding=zenoh.Encoding.IMAGE_JPEG)
            with position_lock:
                pos = position_state["current"]
            frame_queue.put(LitterFrame(overlay=cropped, position=pos))
            logger.info("Frame eingereiht | backend={:.1f}ms | queue_size={}", infer_ms, frame_queue.qsize())
        else:
            logger.debug("Frame verworfen (kein Müll) | backend={:.1f}ms", infer_ms)

    sub = session.declare_subscriber(settings.topic_frame, _on_frame)

    def _batch_worker() -> None:
        while True:
            logger.info("Warte auf nächsten Batch | queue_size={}", frame_queue.qsize())
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
                logger.info("Batch gestartet | size={} | queue_remaining={}", len(batch), frame_queue.qsize())
                t0 = time.monotonic()
                validated = asyncio.run(_validate_batch(batch))
                batch_ms = (time.monotonic() - t0) * 1000
                with validated_lock:
                    validated_litter.extend(validated)
                    total = len(validated_litter)
                logger.info(
                    "Batch abgeschlossen | {:.0f}ms | bestätigt={}/{} | gesamt_litter={}",
                    batch_ms, len(validated), len(batch), total,
                )

            if sentinel_received:
                elapsed = time.monotonic() - run_start
                with validated_lock:
                    total = len(validated_litter)
                logger.info(
                    "Verarbeitung abgeschlossen | gesamt={} | laufzeit={:.1f}s",
                    total,
                    elapsed,
                )
                processing_done.set()
                return

    threading.Thread(target=_batch_worker, daemon=True).start()

    try:
        while not processing_done.wait(timeout=0.5):
            pass
    except KeyboardInterrupt:
        logger.info("Strg+C empfangen — beende sauber...")
        frame_queue.put(None)
        processing_done.wait()  # kein Timeout — alle Frames vollständig drainieren
    sub.undeclare()
    pos_sub.undeclare()
    cropped_pub.undeclare()
    session.close()

    with validated_lock:
        litter_points = {
            f"point{i + 1}": lf.position for i, lf in enumerate(validated_litter)
        }
        return Task2_2(litter_points=litter_points, amount_litter=len(validated_litter))


if __name__ == "__main__":
    run_task()

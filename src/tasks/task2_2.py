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
import httpx
from pydantic import BaseModel
from config import Settings
from inference.inference_main import build_backend
from inference.tracker import LitterTracker
from topics_pydantic_models.pydantic_models import Point, Task2_2


BATCH_SIZE = 2
JPEGQUALITY = 85
STABLE_FRAMES_THRESHOLD = 1  # Frames, bis ein Objekt zur Validierung geschickt wird
_OLLAMA_URL = "http://localhost:11434/api/chat"
_OLLAMA_MODEL = "llava-phi3"


@dataclass
class LitterFrame:
    overlay: np.ndarray
    position: Point


class FrameValidation(BaseModel):
    frame_index: int
    litter_detected: bool


class ValidationResult(BaseModel):
    results: list[FrameValidation]


def _crop_to_object(
    overlay: np.ndarray,
    obj,
    infer_size: int,
    padding: int = 20,
) -> np.ndarray:
    h_img, w_img = overlay.shape[:2]
    scale_x = w_img / infer_size
    scale_y = h_img / infer_size

    x, y, w, h = obj.bbox
    x1 = max(0, int((x - padding) * scale_x))
    y1 = max(0, int((y - padding) * scale_y))
    x2 = min(w_img, int((x + w + padding) * scale_x))
    y2 = min(h_img, int((y + h + padding) * scale_y))

    crop = overlay[y1:y2, x1:x2].copy()
    rx1 = int(x * scale_x) - x1
    ry1 = int(y * scale_y) - y1
    rx2 = int((x + w) * scale_x) - x1
    ry2 = int((y + h) * scale_y) - y1
    cv2.rectangle(crop, (rx1, ry1), (rx2, ry2), obj.color_bgr, 2)
    return crop


async def _validate_batch(batch: list[LitterFrame]) -> list[tuple[LitterFrame, bool]]:
    images = []
    for lf in batch:
        ok, buf = cv2.imencode(".jpg", lf.overlay, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY])
        if ok:
            images.append(base64.b64encode(buf.tobytes()).decode())

    n = len(batch)
    prompt = (
        f"Analysiere die {n} Bilder auf echten Müll. "
        "Die farbig markierten Bereiche sind Modell-Erkennungen. "
        "Antworte NUR als JSON-Array, ein Eintrag pro Bild (0-basiert). "
        'Beispiel für 2 Bilder: {"results":[{"frame_index":0,"litter_detected":true},{"frame_index":1,"litter_detected":false}]}'
    )

    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": images,
            }
        ],
        "format": "json",
        "stream": False,
        "options": {"num_ctx": 8192},
    }

    logger.info("LLM-Anfrage | frames={}", n)
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(_OLLAMA_URL, json=payload)
            if resp.status_code >= 400:
                logger.error("Ollama Fehler {} | body={}", resp.status_code, resp.text)
            resp.raise_for_status()
        llm_ms = (time.monotonic() - t0) * 1000
        raw = resp.json()["message"]["content"]
        data = ValidationResult.model_validate_json(raw)
        status = [False] * n
        for item in data.results:
            if item.frame_index < n and item.litter_detected:
                status[item.frame_index] = True
        logger.info("LLM fertig | {:.0f}ms | bestätigt={}/{}", llm_ms, sum(status), n)
        return list(zip(batch, status))
    except Exception:
        logger.exception("LLM Fehler")
        return [(lf, False) for lf in batch]


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
    run_start = time.monotonic()

    current_run_id = ""
    try:
        for reply in session.get("pipeline/task2_2/start"):
            if reply.ok is not None:
                msg = json.loads(bytes(reply.ok.payload))
                current_run_id = msg.get("run_id", "")
                break
    except Exception:
        pass
    logger.info("task2_2 run_id={}", current_run_id)

    # Latest-only slot: callback writes, inference worker reads and clears
    latest_lock = threading.Lock()
    latest_frame: dict = {"data": None}

    tracker = LitterTracker()
    empty_mask = np.zeros((settings.infer_size, settings.infer_size), dtype=bool)

    def _wait_for_task2_1() -> None:
        while True:
            try:
                for reply in session.get("pipeline/task2_1/done"):
                    if reply.ok is not None:
                        msg = json.loads(bytes(reply.ok.payload))
                        if msg.get("run_id") == current_run_id:
                            logger.info("task2_1 done — Frames-Sammlung beendet")
                            task2_1_done.set()
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

    pos_sub = session.declare_subscriber("robodog/system_state/odometry", _on_position)
    cropped_pub = session.declare_publisher(TOPICS.litter.cropped)
    tracked_overlay_pub = session.declare_publisher(TOPICS.litter.tracked_overlay)
    litter_detections_overlay_pub = session.declare_publisher(TOPICS.litter.litter_detections_overlay)
    validated_pub = session.declare_publisher(TOPICS.litter.validated)

    def _on_frame(sample: zenoh.Sample) -> None:
        if task2_1_done.is_set():
            return
        with latest_lock:
            latest_frame["data"] = bytes(sample.payload)

    def _inference_worker() -> None:
        while not task2_1_done.is_set():
            with latest_lock:
                data = latest_frame["data"]
                latest_frame["data"] = None
            if data is None:
                time.sleep(0.005)
                continue

            img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                continue

            t0 = time.monotonic()
            result, _overlay, mask = backend.infer(img)
            ok, buf = cv2.imencode(".jpg", _overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                litter_detections_overlay_pub.put(
                    buf.tobytes(),
                    encoding=zenoh.Encoding.IMAGE_JPEG,
                )

            infer_ms = (time.monotonic() - t0) * 1000

            tracked = tracker.update(mask if result["detections"] else empty_mask)

            if not result["detections"]:
                #logger.debug("Frame verworfen (kein Müll) | backend={:.1f}ms", infer_ms)
                continue

            colored_overlay = tracker.draw_overlay(img, tracked)

            ok, buf = cv2.imencode(".jpg", colored_overlay, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY])
            if ok:
                tracked_overlay_pub.put(buf.tobytes(), encoding=zenoh.Encoding.IMAGE_JPEG)

            with position_lock:
                pos = position_state["current"]

            queued = 0
            for obj in tracked:
                if obj.frames_seen >= STABLE_FRAMES_THRESHOLD and not obj.validated:
                    obj.validated = True
                    crop = _crop_to_object(colored_overlay, obj, settings.infer_size)
                    ok, buf = cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY])
                    if ok:
                        cropped_pub.put(buf.tobytes(), encoding=zenoh.Encoding.IMAGE_JPEG)
                    frame_queue.put(LitterFrame(overlay=crop, position=pos))
                    queued += 1

            if queued:
                logger.info(
                    "{} Objekt(e) eingereiht | backend={:.1f}ms | queue_size={}",
                    queued,
                    infer_ms,
                    frame_queue.qsize(),
                )
            else:
                logger.debug(
                    "Frame: {} Objekte getrackt, noch nicht stabil | backend={:.1f}ms",
                    len(tracked),
                    infer_ms,
                )

        frame_queue.put(None)

    threading.Thread(target=_inference_worker, daemon=True).start()

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
                results = asyncio.run(_validate_batch(batch))
                batch_ms = (time.monotonic() - t0) * 1000
                validated = [lf for lf, ok in results if ok]
                with validated_lock:
                    validated_litter.extend(validated)
                    total = len(validated_litter)
                for lf, ok_validated in results:
                    # Sauberes Overlay senden; Rahmen/Label zeichnet der Viewer
                    # anhand des Attachments (litter / no_litter).
                    ok, buf = cv2.imencode(".jpg", lf.overlay, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY])
                    if ok:
                        validated_pub.put(
                            buf.tobytes(),
                            encoding=zenoh.Encoding.IMAGE_JPEG,
                            attachment=b"litter" if ok_validated else b"no_litter",
                        )
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
        processing_done.wait()
        session.close()
        

    sub.undeclare()
    pos_sub.undeclare()
    cropped_pub.undeclare()
    tracked_overlay_pub.undeclare()
    litter_detections_overlay_pub.undeclare()
    validated_pub.undeclare()
    session.close()

    with validated_lock:
        litter_points = {
            f"point{i + 1}": lf.position for i, lf in enumerate(validated_litter)
        }
        return Task2_2(litter_points=litter_points, amount_litter=len(validated_litter))


if __name__ == "__main__":
    run_task()

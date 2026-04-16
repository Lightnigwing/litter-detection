"""Inference node — subscribes to frames via Zenoh, runs YOLO, publishes detections."""

import json
import logging
import sys
import time

import cv2
import numpy as np
import zenoh
from ultralytics import YOLO

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("inference")

settings = Settings()


def decode_frame(data: bytes) -> np.ndarray | None:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        logger.warning("Failed to decode JPEG frame (%d bytes)", len(data))
    return img


def main() -> None:
    logger.info("Loading model '%s'…", settings.model_name)
    model = YOLO(f"{settings.model_name}.pt")
    logger.info("Model loaded.")

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info(
        "Zenoh session open — subscribing to '%s', publishing to '%s'",
        settings.topic_frame,
        settings.topic_detections,
    )

    def on_frame(sample: zenoh.Sample) -> None:
        data = bytes(sample.payload)
        img = decode_frame(data)
        if img is None:
            return

        t0 = time.perf_counter()
        results = model(img, verbose=False)
        duration = time.perf_counter() - t0

        boxes = results[0].boxes
        detections = []
        if len(boxes) > 0:
            for conf_score, cls_id in zip(boxes.conf.tolist(), boxes.cls.tolist()):
                cls_name = model.names[int(cls_id)]
                detections.append({"class": cls_name, "confidence": round(conf_score, 3)})

        result = {
            "detections": detections,
            "latency_ms": round(duration * 1000, 1),
            "model": settings.model_name,
        }

        session.put(settings.topic_detections, json.dumps(result).encode())

        n = len(detections)
        logger.info("Inference: %d detection(s) in %.1f ms", n, duration * 1000)

    subscriber = session.declare_subscriber(settings.topic_frame, on_frame)
    logger.info("Waiting for frames…")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down inference node.")
    finally:
        subscriber.undeclare()
        session.close()


if __name__ == "__main__":
    main()

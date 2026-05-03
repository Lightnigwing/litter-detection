"""Inference node — subscribes to frames via Zenoh, runs the configured backend."""

import json
import logging
import sys
import threading
import time
from pathlib import Path
from inference.unet_backend import UnetBackendONNX, UnetBackendTorch
import cv2
import numpy as np
import zenoh

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
from config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("inference")

settings = Settings()


def build_backend(settings: Settings):
    model_path = settings.model_path

    # YOLO
    #if settings.model_type == "yolo":
    #    from src.interference.yolo_backend import YoloBackend
    #    return YoloBackend(model_path)

    # ONNX
    if model_path.endswith(".onnx"):

        return UnetBackendONNX(
            model_path=model_path,
            infer_size=settings.infer_size,
            threshold=settings.segmentation_threshold,
            fraction_threshold=settings.detection_fraction_threshold,
        )

    # Fallback
    if settings.model_type in ("resnet34_unet", "efficientnetb4_unet", "effnetb3_unet"):

        return UnetBackendTorch(
            model_path=model_path,
            variant=settings.model_type,
            infer_size=settings.infer_size,
            threshold=settings.segmentation_threshold,
            fraction_threshold=settings.detection_fraction_threshold,
        )

    raise ValueError(f"Unknown model_type: {settings.model_type!r}")

def decode_frame(data: bytes) -> np.ndarray | None:
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        logger.warning("Failed to decode JPEG frame (%d bytes)", len(data))
    return img


def main() -> None:
    logger.info(
        "Loading backend '%s' from '%s'…", settings.model_type, settings.model_path
    )
    backend = build_backend(settings)
    logger.info("Backend ready.")

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info(
        "Zenoh session open — subscribing to '%s', publishing to '%s' + '%s'",
        settings.topic_frame,
        settings.topic_detections,
        settings.topic_overlay,
    )

    # Latest-only frame slot: callbacks just drop the newest bytes in, the
    # worker thread processes whatever is there. Older frames are overwritten
    # so inference never lags behind the camera.
    latest_lock = threading.Lock()
    latest_payload: dict = {"data": None}
    stop_event = threading.Event()

    def on_frame(sample: zenoh.Sample) -> None:
        with latest_lock:
            latest_payload["data"] = bytes(sample.payload)

    subscriber = session.declare_subscriber(settings.topic_frame, on_frame)
    logger.info("Waiting for frames…")

    def worker() -> None:
        while not stop_event.is_set():
            with latest_lock:
                data = latest_payload["data"]
                latest_payload["data"] = None
            if data is None:
                time.sleep(0.005)
                continue

            img = decode_frame(data)
            if img is None:
                continue

            result, overlay = backend.infer(img)

            if stop_event.is_set():
                return

            try:
                session.put(
                    settings.topic_detections,
                    json.dumps(result).encode(),
                    encoding=zenoh.Encoding.APPLICATION_JSON,
                )
                ok, buf = cv2.imencode(".jpg", overlay, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ok:
                    session.put(
                        settings.topic_overlay,
                        buf.tobytes(),
                        encoding=zenoh.Encoding.IMAGE_JPEG,
                    )
            except zenoh.ZError:
                return

            logger.info(
                "Inference: %d detection(s) in %.1f ms",
                len(result["detections"]),
                result["latency_ms"],
            )

    worker_thread = threading.Thread(target=worker, name="inference-worker", daemon=True)
    worker_thread.start()

    try:
        while worker_thread.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        logger.info("Shutting down inference node.")
    finally:
        stop_event.set()
        subscriber.undeclare()
        worker_thread.join(timeout=2.0)
        session.close()


if __name__ == "__main__":
    main()

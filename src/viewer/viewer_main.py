"""Viewer — subscribes to the overlay topic and displays it with OpenCV."""

import logging
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import zenoh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("viewer")

settings = Settings()


def main() -> None:
    latest: dict = {"frame": None}
    lock = threading.Lock()

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info("Zenoh session open — subscribing to '%s'", settings.topic_overlay)

    def on_overlay(sample: zenoh.Sample) -> None:
        arr = np.frombuffer(bytes(sample.payload), np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return
        with lock:
            latest["frame"] = img

    subscriber = session.declare_subscriber(settings.topic_overlay, on_overlay)

    window = "Litter Detection"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)

    try:
        while True:
            with lock:
                img = latest["frame"]
            if img is not None:
                cv2.imshow(window, img)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
            time.sleep(0.01)
    finally:
        subscriber.undeclare()
        session.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

"""Webcam capture node — reads frames and publishes JPEG via Zenoh."""

import logging
import sys
import time

import cv2
import zenoh

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("camera")

settings = Settings()


def main() -> None:
    cap = cv2.VideoCapture(settings.camera_index)
    if not cap.isOpened():
        logger.error("Cannot open webcam (index=%d)", settings.camera_index)
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, settings.frame_width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, settings.frame_height)

    logger.info(
        "Webcam opened (index=%d, %dx%d, target %d FPS)",
        settings.camera_index,
        settings.frame_width,
        settings.frame_height,
        settings.fps,
    )

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info("Zenoh session open — publishing to '%s'", settings.topic_frame)

    interval = 1.0 / settings.fps
    try:
        while True:
            t0 = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                logger.warning("Webcam read failed, retrying…")
                time.sleep(0.1)
                continue

            frame = cv2.resize(frame, (settings.frame_width, settings.frame_height))
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, settings.jpeg_quality]
            )
            if not ok:
                logger.warning("JPEG encoding failed, skipping frame")
                continue

            payload = buf.tobytes()
            session.put(settings.topic_frame, payload, encoding=zenoh.Encoding.IMAGE_JPEG)
            logger.debug("Published frame (%d bytes)", len(payload))

            elapsed = time.monotonic() - t0
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        logger.info("Shutting down camera node.")
    finally:
        cap.release()
        session.close()


if __name__ == "__main__":
    main()

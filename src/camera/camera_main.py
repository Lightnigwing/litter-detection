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

CAMERAINDEX = 0
FRAMEWIGHT = 640
FRAMEHEIGHT = 480
FPS = 1
JPEGQUALITY = 85

def main() -> None:
    cap = cv2.VideoCapture(CAMERAINDEX)
    if not cap.isOpened():
        logger.error("Cannot open webcam (index=%d)", CAMERAINDEX)
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAMEWIGHT)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAMEHEIGHT)

    logger.info(
        "Webcam opened (index=%d, %dx%d, target %d FPS)",
        CAMERAINDEX,
        FRAMEWIGHT,
        FRAMEHEIGHT,
        FPS,
    )

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info("Zenoh session open — publishing to '%s'", settings.topic_frame)

    interval = 1.0 / FPS
    try:
        while True:
            t0 = time.monotonic()

            ret, frame = cap.read()
            if not ret:
                logger.warning("Webcam read failed, retrying…")
                time.sleep(0.1)
                continue

            frame = cv2.resize(frame, (FRAMEWIGHT, FRAMEHEIGHT))
            ok, buf = cv2.imencode(
                ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEGQUALITY]
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

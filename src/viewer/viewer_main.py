"""Viewer — subscribes to the overlay topic and displays it in a tkinter window.

Uses tkinter + Pillow so it works with opencv-python-headless (no cv2.imshow).
"""

import io
import logging
import sys
import threading
import tkinter as tk
from pathlib import Path

import zenoh
from PIL import Image, ImageTk

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
    latest: dict = {"image": None}
    lock = threading.Lock()

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)
    logger.info("Zenoh session open — subscribing to '%s'", settings.topic_overlay)

    def on_overlay(sample: zenoh.Sample) -> None:
        try:
            img = Image.open(io.BytesIO(bytes(sample.payload)))
            img.load()
        except Exception:
            return
        with lock:
            latest["image"] = img

    subscriber = session.declare_subscriber(settings.topic_overlay, on_overlay)

    root = tk.Tk()
    root.title("Litter Detection")
    label = tk.Label(root)
    label.pack()
    tk_image_ref = {"photo": None}

    def update_frame() -> None:
        with lock:
            img = latest["image"]
        if img is not None:
            photo = ImageTk.PhotoImage(img)
            label.configure(image=photo)
            tk_image_ref["photo"] = photo  # keep a reference, else GC'd
        root.after(33, update_frame)  # ~30 Hz refresh

    def on_close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("q", lambda _e: on_close())
    root.bind("<Escape>", lambda _e: on_close())

    update_frame()
    try:
        root.mainloop()
    finally:
        subscriber.undeclare()
        session.close()


if __name__ == "__main__":
    main()

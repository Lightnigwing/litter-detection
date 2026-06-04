"""Viewer — subscribes to all litter image topics and shows them in a tkinter grid.

Layout (3 columns x 2 rows):
  Frame | Depth | Cropped
  Overlay | Tracked Overlay | Detections
"""

import io
import json
import logging
import sys
import threading
import tkinter as tk
from pathlib import Path

import zenoh
from PIL import Image, ImageDraw, ImageFont, ImageTk

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import Settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("viewer")

settings = Settings()

TOPICS = [
    ("litter/frame",           "Frame"),
    ("litter/frame_depth",     "Depth"),
    ("litter/cropped",         "Cropped"),
    ("litter/overlay",         "Overlay"),
    ("litter/tracked_overlay", "Tracked Overlay"),
    ("litter/litter_detections_overlay",      "litter_detections_overlay"),
]

COLS = 3
THUMB_W, THUMB_H = 426, 240  # ~16:9 per cell
BG = "#1a1a1a"


def main() -> None:
    latest: dict[str, Image.Image | None] = {t: None for t, _ in TOPICS}
    lock = threading.Lock()

    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    def _render_detections_json(payload: bytes) -> Image.Image:
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
        detections = data.get("detections", [])
        latency = data.get("latency_ms", 0)
        img = Image.new("RGB", (THUMB_W, THUMB_H), (30, 30, 30))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 14)
            font_small = ImageFont.truetype("arial.ttf", 12)
        except OSError:
            font = ImageFont.load_default()
            font_small = font
        draw.text((8, 8), f"Detections: {len(detections)}  |  {latency:.1f} ms", fill="#00ff88", font=font)
        y = 34
        for i, det in enumerate(detections[:12]):
            line = f"  [{i}] {det}" if not isinstance(det, dict) else (
                f"  [{i}] conf={det.get('confidence', det.get('score', '?')):.2f}"
                f"  cls={det.get('class', det.get('label', '?'))}"
            )
            draw.text((8, y), line, fill="#cccccc", font=font_small)
            y += 16
            if y > THUMB_H - 16:
                break
        return img

    def make_callback(topic: str):
        def on_sample(sample: zenoh.Sample) -> None:
            payload = bytes(sample.payload)
            if topic == "litter/detections":
                img = _render_detections_json(payload)
            else:
                try:
                    img = Image.open(io.BytesIO(payload))
                    img.load()
                except Exception as e:
                    logger.warning("[%s] failed to decode image: %s", topic, e)
                    return
            with lock:
                latest[topic] = img
        return on_sample

    subscribers = []
    for topic, _ in TOPICS:
        sub = session.declare_subscriber(topic, make_callback(topic))
        subscribers.append(sub)
        logger.info("Subscribed to '%s'", topic)

    root = tk.Tk()
    root.title("Litter Detection — Multi-View")
    root.configure(bg=BG)

    placeholder = Image.new("RGB", (THUMB_W, THUMB_H), (40, 40, 40))

    panels: list[dict] = []
    for idx, (topic, label_text) in enumerate(TOPICS):
        row, col = divmod(idx, COLS)
        cell = tk.Frame(root, bg=BG)
        cell.grid(row=row * 2, column=col, padx=4, pady=(4, 0), sticky="nsew")

        tk.Label(
            cell, text=label_text, bg=BG, fg="#aaaaaa",
            font=("Helvetica", 9, "bold"),
        ).pack(anchor="w", padx=2)

        img_label = tk.Label(cell, bg="#2a2a2a", width=THUMB_W, height=THUMB_H)
        img_label.pack()

        panels.append({"topic": topic, "label": img_label, "photo": None})

    for c in range(COLS):
        root.columnconfigure(c, weight=1)

    def update_frame() -> None:
        with lock:
            snapshot = dict(latest)
        for panel in panels:
            img = snapshot[panel["topic"]] or placeholder
            thumb = img.copy()
            thumb.thumbnail((THUMB_W, THUMB_H), Image.LANCZOS)
            photo = ImageTk.PhotoImage(thumb)
            panel["label"].configure(image=photo)
            panel["photo"] = photo  # keep reference to prevent GC
        root.after(33, update_frame)  # ~30 Hz

    def on_close() -> None:
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.bind("q", lambda _e: on_close())
    root.bind("<Escape>", lambda _e: on_close())

    update_frame()
    try:
        root.mainloop()
    finally:
        for sub in subscribers:
            sub.undeclare()
        session.close()


if __name__ == "__main__":
    main()

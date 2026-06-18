"""Viewer — subscribes to all litter image topics and shows them in a tkinter grid.

Layout (3 columns x 2 rows):
  Frame | Litter Detection Overlay | Validated
  Depth | Tracked Overlay          | Cropped
"""

import io
import json
import logging
import sys
import threading
import tkinter as tk
from collections import deque
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
    ("litter/frame",                     "Frame"),
    ("litter/litter_detections_overlay", "Litter Detection Overlay"),
    ("litter/validated",                 "Validated"),
    ("litter/frame_depth",               "Depth"),
    ("litter/tracked_overlay",           "Tracked Overlay"),
    ("litter/cropped",                   "Cropped"),
]

COLS = 3
THUMB_W, THUMB_H = 426, 240  # ~16:9 per cell
BG = "#1a1a1a"

# Wie viele Bilder pro Slot behalten + wie das Sub-Raster aufgebaut ist (rows, cols).
# Default: 1 Bild, 1x1.
CAPACITY = {"litter/cropped": 4, "litter/validated": 2}
SUBGRID = {"litter/cropped": (2, 2), "litter/validated": (1, 2)}


def main() -> None:
    latest: dict[str, deque] = {
        t: deque(maxlen=CAPACITY.get(t, 1)) for t, _ in TOPICS
    }
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
                latest[topic].append(img)
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

        rows, cols = SUBGRID.get(topic, (1, 1))
        thumb_w = THUMB_W // cols
        thumb_h = THUMB_H // rows

        grid = tk.Frame(cell, bg=BG)
        grid.pack()
        sub_labels = []
        for i in range(rows * cols):
            r, c = divmod(i, cols)
            lbl = tk.Label(grid, bg="#2a2a2a", width=thumb_w, height=thumb_h)
            lbl.grid(row=r, column=c, padx=1, pady=1)
            sub_labels.append(lbl)

        panels.append({
            "topic": topic,
            "labels": sub_labels,
            "photos": [None] * len(sub_labels),
            "thumb": (thumb_w, thumb_h),
        })

    for c in range(COLS):
        root.columnconfigure(c, weight=1)

    def update_frame() -> None:
        with lock:
            snapshot = {t: list(d) for t, d in latest.items()}
        for panel in panels:
            # neueste zuerst anzeigen
            images = list(reversed(snapshot[panel["topic"]]))
            for slot, lbl in enumerate(panel["labels"]):
                img = images[slot] if slot < len(images) else placeholder
                thumb = img.copy()
                thumb.thumbnail(panel["thumb"], Image.LANCZOS)
                photo = ImageTk.PhotoImage(thumb)
                lbl.configure(image=photo)
                panel["photos"][slot] = photo  # keep reference to prevent GC
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

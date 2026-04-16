"""YOLO (Ultralytics) inference backend."""

import time

import numpy as np
from ultralytics import YOLO


class YoloBackend:
    def __init__(self, model_path: str) -> None:
        self.model = YOLO(model_path)
        self.name = model_path

    def infer(self, img: np.ndarray) -> tuple[dict, np.ndarray]:
        t0 = time.perf_counter()
        results = self.model(img, verbose=False)
        duration = time.perf_counter() - t0

        boxes = results[0].boxes
        detections = []
        if len(boxes) > 0:
            for conf, cls_id in zip(boxes.conf.tolist(), boxes.cls.tolist()):
                detections.append(
                    {
                        "class": self.model.names[int(cls_id)],
                        "confidence": round(conf, 3),
                    }
                )

        result = {
            "detections": detections,
            "latency_ms": round(duration * 1000, 1),
            "model": self.name,
        }
        overlay = results[0].plot()
        return result, overlay

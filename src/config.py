"""Central configuration for the litter-detection pipeline."""

from dataclasses import dataclass


@dataclass
class Settings:
    # Zenoh
    zenoh_router: str = "tcp/localhost:7447"
    topic_frame: str = "litter/frame"
    topic_detections: str = "litter/detections"

    # Camera
    # camera_index=0 is usually the built-in webcam, camera_index=1 is the first external webcam. Adjust as needed.
    camera_index: int = 1
    frame_width: int = 640
    frame_height: int = 480
    fps: int = 10
    jpeg_quality: int = 85

    # Model
    model_name: str = "yolov8n"

    # OpenTelemetry
    otel_endpoint: str = "http://127.0.0.1:4317"
    otel_service_name: str = "yolo-detector"

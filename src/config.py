"""Central configuration for the litter-detection pipeline."""

from dataclasses import dataclass


@dataclass
class Settings:
    # Zenoh
    zenoh_router: str = "tcp/localhost:7447"
    topic_frame: str = "litter/frame"
    topic_detections: str = "litter/detections"
    topic_overlay: str = "litter/overlay"

    # Camera
    # camera_index=0 is usually the built-in webcam, camera_index=1 is the first external webcam. Adjust as needed.
    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    fps: int = 10
    jpeg_quality: int = 85

    # Model
    # model_type selects the inference backend:
    #   "yolo"              -> Ultralytics YOLO (bounding boxes)
    #   "resnet34_unet"     -> U-Net with ResNet-34 encoder (segmentation)
    #   "efficientnetb4_unet" -> U-Net with EfficientNet-B4 encoder (segmentation)
    model_type: str = "resnet34_unet"
    # model_path is the full filename (relative to repo root) incl. extension:
    #   yolo          -> "yolov8n.pt"
    #   resnet34_unet -> "best_resnet34.pth" or "best_model.pth"
    #   effnetb4_unet -> "best_efficientnetb4.pth"
    model_path: str = "resnet34_50_onnx.onnx"

    # UNet inference
    infer_size: int = 512
    segmentation_threshold: float = 0.5
    # Minimum litter pixel fraction to count as a positive detection
    detection_fraction_threshold: float = 0.01

    # OpenTelemetry
    otel_endpoint: str = "http://127.0.0.1:4317"
    otel_service_name: str = "yolo-detector"

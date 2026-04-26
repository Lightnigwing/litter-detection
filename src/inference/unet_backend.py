"""UNet segmentation backend (ResNet-34 or EfficientNet-B4)."""

import sys
import time
import types
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
import onnxruntime as ort
import torch
from albumentations.pytorch import ToTensorV2


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _install_mlflow_stub() -> None:
    """Shadow mlflow with a no-op stub so importing train.py doesn't connect
    to a local tracking DB during inference."""
    stub = types.ModuleType("mlflow")
    config = types.ModuleType("mlflow.config")

    class _NullRun:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    noop = lambda *a, **kw: None
    stub.set_experiment = noop
    stub.set_tracking_uri = noop
    stub.start_run = lambda *a, **kw: _NullRun()
    stub.active_run = lambda *a, **kw: None
    stub.log_artifact = noop
    stub.log_artifacts = noop
    stub.log_metric = noop
    stub.log_metrics = noop
    stub.log_param = noop
    stub.log_params = noop
    stub.log_text = noop
    stub.log_dict = noop
    stub.set_tag = noop
    stub.set_tags = noop
    config.enable_system_metrics_logging = noop
    config.set_system_metrics_sampling_interval = noop
    stub.config = config

    sys.modules["mlflow"] = stub
    sys.modules["mlflow.config"] = config


def _load_torch_variants() -> tuple[float, dict]:
    """Import training-side model definitions only when torch backend is used."""
    _install_mlflow_stub()
    from model.train import DROPOUT, ResNet34UNet

    variants = {
        "resnet34_unet": ResNet34UNet,
    }
    return DROPOUT, variants


def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class UnetBackendTorch:
    def __init__(
        self,
        model_path: str,
        variant: str,
        infer_size: int = 384,
        threshold: float = 0.5,
        fraction_threshold: float = 0.01,
    ) -> None:
        dropout, variants = _load_torch_variants()

        if variant not in variants:
            raise ValueError(
                f"Unknown UNet variant '{variant}'. Expected one of {list(variants)}"
            )

        self.device = _pick_device()
        self.name = model_path
        self.infer_size = infer_size
        self.threshold = threshold
        self.fraction_threshold = fraction_threshold

        model_cls = variants[variant]
        self.model = model_cls(dropout=dropout).to(self.device)
        state = torch.load(REPO_ROOT / model_path, map_location=self.device)
        if "model_state_dict" in state:
            state = state["model_state_dict"]
        self.model.load_state_dict(state)
        self.model.eval()

        self.transform = A.Compose(
            [
                A.Resize(infer_size, infer_size),
                A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ]
        )

    def infer(self, img_bgr: np.ndarray) -> tuple[dict, np.ndarray]:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        t0 = time.perf_counter()
        tensor = self.transform(image=img_rgb)["image"].unsqueeze(0).to(self.device)
        with torch.no_grad():
            prob = torch.sigmoid(self.model(tensor)).squeeze().cpu().numpy()
        duration = time.perf_counter() - t0

        mask = prob > self.threshold
        litter_fraction = float(mask.mean())
        mean_confidence = float(prob[mask].mean()) if mask.any() else 0.0

        detections = []
        if litter_fraction >= self.fraction_threshold:
            detections.append(
                {"class": "litter", "confidence": round(mean_confidence, 3)}
            )

        result = {
            "detections": detections,
            "litter_fraction": round(litter_fraction, 4),
            "latency_ms": round(duration * 1000, 1),
            "model": self.name,
        }
        overlay = _draw_mask_overlay(img_bgr, mask)
        return result, overlay


class UnetBackendONNX:
    def __init__(
        self,
        model_path: str,
        infer_size: int = 384,
        threshold: float = 0.5,
        fraction_threshold: float = 0.01,
    ) -> None:
        self.name = model_path
        self.infer_size = infer_size
        self.threshold = threshold
        self.fraction_threshold = fraction_threshold

        providers = ["CPUExecutionProvider"]
        available = set(ort.get_available_providers())
        if "CUDAExecutionProvider" in available:
            providers.insert(0, "CUDAExecutionProvider")

        self.session = ort.InferenceSession(model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

        self.transform = A.Compose(
            [
                A.Resize(infer_size, infer_size),
                A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ]
        )

    def infer(self, img_bgr: np.ndarray) -> tuple[dict, np.ndarray]:
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        t0 = time.perf_counter()
        tensor = self.transform(image=img_rgb)["image"].numpy()
        tensor = np.expand_dims(tensor, axis=0).astype(np.float32)
        outputs = self.session.run(None, {self.input_name: tensor})
        logits = np.asarray(outputs[0])
        prob = 1.0 / (1.0 + np.exp(-logits))
        prob = prob.squeeze()
        duration = time.perf_counter() - t0

        mask = prob > self.threshold
        litter_fraction = float(mask.mean())
        mean_confidence = float(prob[mask].mean()) if mask.any() else 0.0

        detections = []
        if litter_fraction >= self.fraction_threshold:
            detections.append(
                {"class": "litter", "confidence": round(mean_confidence, 3)}
            )

        result = {
            "detections": detections,
            "litter_fraction": round(litter_fraction, 4),
            "latency_ms": round(duration * 1000, 1),
            "model": self.name,
        }
        overlay = _draw_mask_overlay(img_bgr, mask)
        return result, overlay


def _draw_mask_overlay(
    img_bgr: np.ndarray, mask: np.ndarray, color=(0, 80, 255), alpha: float = 0.55
) -> np.ndarray:
    """Upsample the network mask to the image resolution and alpha-blend it."""
    h, w = img_bgr.shape[:2]
    mask_full = cv2.resize(
        mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST
    ).astype(bool)
    overlay = img_bgr.copy()
    if mask_full.any():
        tint = np.array(color, dtype=np.float32)
        overlay[mask_full] = (
            overlay[mask_full].astype(np.float32) * (1 - alpha) + tint * alpha
        ).clip(0, 255).astype(np.uint8)
    return overlay

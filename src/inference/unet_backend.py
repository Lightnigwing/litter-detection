"""UNet segmentation backend (ResNet-34 or EfficientNet-B4)."""

import sys
import time
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
import torch
from albumentations.pytorch import ToTensorV2

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
from train import DROPOUT, EfficientNetB4UNet, ResNet34UNet


VARIANTS = {
    "resnet34_unet": ResNet34UNet,
    "efficientnetb4_unet": EfficientNetB4UNet,
}


def _pick_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


class UnetBackend:
    def __init__(
        self,
        model_path: str,
        variant: str,
        infer_size: int = 384,
        threshold: float = 0.5,
        fraction_threshold: float = 0.01,
    ) -> None:
        if variant not in VARIANTS:
            raise ValueError(
                f"Unknown UNet variant '{variant}'. Expected one of {list(VARIANTS)}"
            )

        self.device = _pick_device()
        self.name = model_path
        self.infer_size = infer_size
        self.threshold = threshold
        self.fraction_threshold = fraction_threshold

        model_cls = VARIANTS[variant]
        self.model = model_cls(dropout=DROPOUT).to(self.device)
        state = torch.load(REPO_ROOT / model_path, map_location=self.device)
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

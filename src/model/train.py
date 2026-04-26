"""
train.py — CNN semantic segmentation training for litter detection.

This file IS modified by the agent. Everything is fair game:
  - Model architecture (encoder depth, decoder, attention, backbone, etc.)
  - Loss function (BCE, Dice, Focal, combo)
  - Optimizer and LR schedule
  - Data augmentation strategy
  - Batch size, image crop size
  - Any other technique the agent wants to try

Constraint: training stops after TIME_LIMIT seconds so every experiment is
comparable. The primary metric logged to MLflow is val_iou (higher is better).

Usage:
    uv run mlflow ui
    uv run python train.py --run-name NAME 
    NOTE: Flag für timelimit entfernt, da epochen statt zeitlimit verwendet wird.
"""
"""
Notes:
1. Druchlauf:
Beste val_iou:
0.64 Basline

2. Durchlauf:
geändert:
- 3e-4 lr
- focal dice loss
Beste val_iou:
0.71

3. Durchlauf:
geändert:
- 50
Beste val_iou:
0.74

"""
import argparse
import json
import os
import time
from pathlib import Path

import mlflow
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms
import torchvision.models as tv_models
import albumentations as A
from albumentations.pytorch import ToTensorV2
from tqdm import tqdm
mlflow.set_experiment("litter-segmentation")
mlflow.config.enable_system_metrics_logging()
mlflow.config.set_system_metrics_sampling_interval(5)  # alle 5 Sekunden
"""
Änderungen am Traningsskript die von dem orginalen Traningsskript abweichen,
um das vorgehen des Skriptes, nicht das Model zu verbessern sind mit '# NOTE: ' markiert.
"""
# ── Hyperparameters (edit freely) ─────────────────────────────────────────────

EPOCHEN          = 50         # max number of epochs to train NOTE: TIMELIMIT durch epochen ersetzt
BATCH_SIZE       = 8
CROP_SIZE        = 512        # random-crop spatial resolution during training
LR               = 3e-4
WEIGHT_DECAY     = 1e-4
ENCODER_CHANNELS = [64, 128, 256, 512]   # U-Net encoder stage widths
DECODER_CHANNELS = [256, 128, 64, 32]    # U-Net decoder stage widths
DROPOUT          = 0.1
POS_WEIGHT       = 5.0        # BCEWithLogitsLoss pos_weight (handles class imbalance)
                               # override with value from data/meta.json

# ── Data ──────────────────────────────────────────────────────────────────────

DATA_DIR   = Path("data")
IMAGES_DIR = DATA_DIR / "images"
MASKS_DIR  = DATA_DIR / "masks"


def load_meta() -> dict:
    p = DATA_DIR / "meta.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}

def export_onnx(model, device, path="model.onnx"):
    model.eval()

    # WICHTIG: auf CPU exportieren
    model_cpu = model.to("cpu")

    dummy_input = torch.randn(1, 3, CROP_SIZE, CROP_SIZE)

    torch.onnx.export(
        model_cpu,
        dummy_input,
        path,
        input_names=["input"],
        output_names=["output"],
        opset_version=17,
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"}
        }
    )

    print(f"[INFO] ONNX model exported to {path}")


class LitterDataset(Dataset):
    def __init__(self, split: str, crop_size: int = CROP_SIZE, augment: bool = True):
        stems_file = DATA_DIR / f"{split}.txt"
        self.stems = [s.strip() for s in stems_file.read_text().splitlines() if s.strip()]
        self.augment = augment

        if augment:
            self.transform = A.Compose([
                A.RandomResizedCrop(size=(crop_size, crop_size),
                                    scale=(0.4, 1.0), ratio=(0.75, 1.33)),
                A.HorizontalFlip(p=0.5),
                A.RandomRotate90(p=0.3),
                A.ColorJitter(brightness=0.3, contrast=0.3,
                              saturation=0.3, hue=0.05, p=0.7),
                A.GaussNoise(p=0.2),
                A.GridDistortion(p=0.1), #NOTE von 0,3 auf 0,1 reduziert
                A.ElasticTransform(p=0.1), #NOTE von 0,3 auf 0,1 reduziert
                A.Normalize(mean=(0.485, 0.456, 0.406),
                            std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ])
        else:
            self.transform = A.Compose([
                A.Resize(height=crop_size, width=crop_size),
                A.Normalize(mean=(0.485, 0.456, 0.406),
                            std=(0.229, 0.224, 0.225)),
                ToTensorV2(),
            ])

    def __len__(self):
        return len(self.stems)

    def __getitem__(self, idx):
        stem = self.stems[idx]
        image = np.array(Image.open(IMAGES_DIR / f"{stem}.jpg").convert("RGB"))
        mask  = (np.array(Image.open(MASKS_DIR / f"{stem}.png")) > 127).astype(np.float32)

        out = self.transform(image=image, mask=mask)
        return out["image"], out["mask"].unsqueeze(0)   # (3,H,W), (1,H,W)


# ── Model ─────────────────────────────────────────────────────────────────────

class ConvBlock(nn.Module):
    """Double conv + BN + ReLU block."""
    def __init__(self, in_ch: int, out_ch: int, dropout: float = 0.0):
        super().__init__()
        self.net = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
            nn.Dropout2d(dropout) if dropout > 0 else nn.Identity(),
            nn.Conv2d(out_ch, out_ch, 3, padding=1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        return self.net(x)

class ResNet34UNet(nn.Module):
    """
    U-Net with a pretrained ResNet34 encoder.

    Skip connections come from ResNet34 feature stages:
      stem  (64 ch,  H/2)   — after maxpool (stride-2 conv + BN + ReLU)
      layer1 (64 ch,  H/4)
      layer2 (128 ch, H/8)
      layer3 (256 ch, H/16)
      layer4 (512 ch, H/32)  — used as bottleneck

    The decoder mirrors a 4-stage U-Net decoder.
    BN layers in the backbone are frozen to preserve ImageNet statistics.
    """
    # Skip channel sizes from stem through layer3
    ENC_CHANNELS = [64, 64, 128, 256]   # stem, layer1, layer2, layer3
    BOTTLENECK_CH = 512                  # layer4

    def __init__(self, dropout: float = DROPOUT):
        super().__init__()

        # ── Pretrained ResNet34 backbone ──────────────────────────────────
        backbone = tv_models.resnet34(weights=tv_models.ResNet34_Weights.IMAGENET1K_V1)

        # Stem: conv1 + bn1 + relu (output: 64 ch, stride 2)
        self.stem_conv = nn.Sequential(backbone.conv1, backbone.bn1, backbone.relu)
        self.stem_pool = backbone.maxpool   # stride 2 → H/4 total after stem+pool
        self.layer1 = backbone.layer1       # 64 ch,  H/4  (maxpool already applied)
        self.layer2 = backbone.layer2       # 128 ch, H/8
        self.layer3 = backbone.layer3       # 256 ch, H/16
        self.layer4 = backbone.layer4       # 512 ch, H/32  (bottleneck)
        """
        # Freeze BN parameters in the backbone to preserve ImageNet stats
        for m in self.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.weight.requires_grad_(False)
                m.bias.requires_grad_(False)
        """
        # WHY: Nur Encoder-BN einfrieren (korrekt!)
        for m in backbone.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.eval()  # stoppt running stats updates
                for p in m.parameters():
                    p.requires_grad = False

        """
        # ── Decoder (4 stages) ────────────────────────────────────────────
        # Stage 1: upsample from 512 → 256, concat with layer3 skip (256) → 256
        self.up1 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(256 + 256, 256, dropout)

        # Stage 2: upsample from 256 → 128, concat with layer2 skip (128) → 128
        self.up2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(128 + 128, 128, dropout)

        # Stage 3: upsample from 128 → 64, concat with layer1 skip (64) → 64
        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec3 = ConvBlock(64 + 64, 64, dropout)

        # Stage 4: upsample from 64 → 32, concat with stem skip (64) → 32
        self.up4 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec4 = ConvBlock(32 + 64, 32, dropout)

        # Final upsample ×2 to recover full input resolution
        self.final_up = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.final_conv = ConvBlock(16, 16, dropout)

        # ── Head ──────────────────────────────────────────────────────────
        self.head = nn.Conv2d(16, 1, kernel_size=1)
        """

        # WHY: Kein ConvTranspose → vermeidet checkerboard artefacts
        self.up1 = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.dec1 = ConvBlock(512 + 256, 256, dropout)

        self.up2 = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.dec2 = ConvBlock(256 + 128, 128, dropout)

        self.up3 = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.dec3 = ConvBlock(128 + 64, 64, dropout)

        self.up4 = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.dec4 = ConvBlock(64 + 64, 64, dropout)

        # Final upsample
        self.up5 = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
        self.final_conv = ConvBlock(64, 32, dropout)

        self.head = nn.Conv2d(32, 1, kernel_size=1)

    def _align(self, x, ref):  #NOTE made onnx safe
        return F.interpolate(x, size=ref.shape[2:], mode="bilinear", align_corners=False)

    def forward(self, x):
        """
        # Encoder
        s0 = self.stem_conv(x)         # 64 ch, H/2
        s1 = self.layer1(self.stem_pool(s0))  # 64 ch, H/4
        s2 = self.layer2(s1)           # 128 ch, H/8
        s3 = self.layer3(s2)           # 256 ch, H/16
        s4 = self.layer4(s3)           # 512 ch, H/32  (bottleneck)

        # Decoder
        d = self.up1(s4)
        d = self._align(d, s3)
        d = self.dec1(torch.cat([d, s3], dim=1))  # 256 ch, H/16

        d = self.up2(d)
        d = self._align(d, s2)
        d = self.dec2(torch.cat([d, s2], dim=1))  # 128 ch, H/8

        d = self.up3(d)
        d = self._align(d, s1)
        d = self.dec3(torch.cat([d, s1], dim=1))  # 64 ch, H/4

        d = self.up4(d)
        d = self._align(d, s0)
        d = self.dec4(torch.cat([d, s0], dim=1))  # 32 ch, H/2

        d = self.final_up(d)           # 16 ch, H/1
        d = self.final_conv(d)

        return self.head(d)            # 1 ch, H/1
        """
        # ───── Encoder ─────
        s0 = self.stem_conv(x)              # H/2
        s1 = self.layer1(self.stem_pool(s0))# H/4
        s2 = self.layer2(s1)                # H/8
        s3 = self.layer3(s2)                # H/16
        s4 = self.layer4(s3)                # H/32

        # ───── Decoder ─────

        d = self.up1(s4)
        d = self._align(d, s3)
        d = self.dec1(torch.cat([d, s3], dim=1))

        d = self.up2(d)
        d = self._align(d, s2)
        d = self.dec2(torch.cat([d, s2], dim=1))

        d = self.up3(d)
        d = self._align(d, s1)
        d = self.dec3(torch.cat([d, s1], dim=1))

        d = self.up4(d)
        d = self._align(d, s0)
        d = self.dec4(torch.cat([d, s0], dim=1))

        d = self.up5(d)
        d = self.final_conv(d)

        return self.head(d)


# ── Loss ──────────────────────────────────────────────────────────────────────

class FocalDiceLoss(nn.Module):
    def __init__(self, alpha=0.8, gamma=2.0):
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma
        self.bce = nn.BCEWithLogitsLoss(reduction="none")

    def forward(self, logits, targets):
        # Focal
        bce = self.bce(logits, targets)
        pt = torch.exp(-bce)
        focal = self.alpha * (1 - pt) ** self.gamma * bce
        focal = focal.mean()

        # Dice
        probs = torch.sigmoid(logits)
        intersection = (probs * targets).sum()
        dice = 1 - (2 * intersection + 1) / (probs.sum() + targets.sum() + 1)

        return focal + dice


# ── Metrics ───────────────────────────────────────────────────────────────────

@torch.no_grad()
def compute_iou(logits: torch.Tensor, masks: torch.Tensor, # TODO: Threshold evtl ändern
                threshold: float = 0.5) -> float:
    preds = (torch.sigmoid(logits) > threshold).float()
    inter = (preds * masks).sum().item()
    union = (preds + masks - preds * masks).sum().item()
    return inter / max(union, 1.0)

# ── Training loop ─────────────────────────────────────────────────────────────

def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def train(run_name: str):
    device = get_device()
    print(f"Device: {device}")

    meta = load_meta()
    pos_weight = meta.get("pos_weight_suggestion", POS_WEIGHT)
    # ── Data ──────────────────────────────────────────────────────────────
    train_ds = LitterDataset("train", crop_size=CROP_SIZE, augment=True)
    val_ds   = LitterDataset("val",   crop_size=CROP_SIZE, augment=False)
    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE,
                              shuffle=True,  num_workers=4, pin_memory=True,
                              persistent_workers=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE,
                              shuffle=False, num_workers=2, pin_memory=True,
                              persistent_workers=True)

    # ── Model ─────────────────────────────────────────────────────────────
    model = ResNet34UNet(dropout=DROPOUT).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")

    # ── Optimizer + Schedule ──────────────────────────────────────────────
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR,
                                  weight_decay=WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=LR, # TODO: Evtl höheres max_lr, da jetzt mehr steps möglich, da es sich an batches orientiert
        epochs=EPOCHEN,
        steps_per_epoch=len(train_loader),
        pct_start=0.05, # sehr aggreessives Aufwären, standart 0.3
    )
    criterion = FocalDiceLoss().to(device)


    # ── MLflow ────────────────────────────────────────────────────────────

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({ # TODO Anschauen
            "batch_size":        BATCH_SIZE,
            "crop_size":         CROP_SIZE,
            "lr":                LR,
            "weight_decay":      WEIGHT_DECAY,
            "dropout":           DROPOUT,
            "pos_weight":        pos_weight,
            "optimizer":         "AdamW",
            "scheduler":         "OneCycleLR",
            "loss": "Focal+Dice",
            "total_params":      total_params,
            "device":            str(device),
        })

        
        step = 0
        best_val_iou = 0.0
    
        for epoch in range(1, EPOCHEN+1):
            model.train()
            t0 = time.time()
            train_loss = 0.0
            train_iou  = 0.0
            print(f"Epoch {epoch}/{EPOCHEN} - Training...")
            for images, masks in train_loader:
                images = images.to(device, non_blocking=True)
                masks  = masks.to(device,  non_blocking=True)
                print(f"Step {step+1}/{len(train_loader)}", end="\r")
                optimizer.zero_grad(set_to_none=True)
                logits = model(images) # logits = raw model outputs (before sigmoid) TODO: Abhängig von los funktion gegebenenfalss was machen
                loss   = criterion(logits, masks)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0) # verhindert zu große gradienten, evtl verlagsamerter er es, je nach NORM
                optimizer.step()
                scheduler.step()

                train_loss += loss.item()
                train_iou  += compute_iou(logits, masks)
                step += 1

             
            # ── Validation ────────────────────────────────────────────
            model.eval()
            val_loss = 0.0
            val_iou  = 0.0
            with torch.no_grad():
                for images, masks in val_loader:
                    images = images.to(device, non_blocking=True)
                    masks  = masks.to(device,  non_blocking=True)
                    logits = model(images)
                    val_loss += criterion(logits, masks).item()
                    val_iou  += compute_iou(logits, masks)

            n_train = len(train_loader)
            n_val   = len(val_loader)
            elapsed = time.time() - t0

            metrics = {
                "train_loss": train_loss / max(n_train, 1),
                "train_iou":  train_iou  / max(n_train, 1),
                "val_loss":   val_loss   / max(n_val,   1),
                "val_iou":    val_iou    / max(n_val,   1),
                "epoch":      epoch,
                "elapsed_s":  elapsed,
                "lr":         scheduler.get_last_lr()[0],
            }
            mlflow.log_metrics(metrics, step=epoch)
            
            if metrics["val_iou"] > best_val_iou:  #NOTE if val_iou / max(n_val, 1) > best_val_iou: zu viel wird bereits durch n_val geteilt
                best_val_iou = metrics["val_iou"]
                pth_path = f"{run_name}.pth"
                onnx_path = f"{run_name}.onnx"

                torch.save(model.state_dict(), pth_path)
                # ONNX export
                export_onnx(model, device, onnx_path)
                model.to(device)  # Move model back to device after ONNX export

                # beide loggen
                mlflow.log_artifact(pth_path)
                mlflow.log_artifact(onnx_path)
            

            print(
                f"epoch {epoch:3d}  "
                f"train_loss={metrics['train_loss']:.4f}  "
                f"train_iou={metrics['train_iou']:.4f}  "
                f"val_loss={metrics['val_loss']:.4f}  "
                f"val_iou={metrics['val_iou']:.4f}  "
                f"[{elapsed:.0f}s]"
            )

        mlflow.log_metric("best_val_iou", best_val_iou)
        print(f"\nBest val_iou: {best_val_iou:.4f}")
        print("Run complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-name",   default="baseline",
                        help="MLflow run name")    
    # NOTE: Flag für timelimit entfernt
    args = parser.parse_args()
    train(run_name=args.run_name)

"""train.py — CNN semantic segmentation training for litter detection.

This version keeps the old code snippets at the modified places as comments,
so you can compare OLD vs NEW directly while reading the file.

Main changes compared to the original:
- BatchNorm freezing is applied only to the pretrained encoder, not the whole model.
- Augmentation is slightly gentler and includes positive-mask-biased crops.
- Dice+BCE loss uses no label smoothing by default.
- IoU is computed per-sample and averaged with empty-empty masks handled correctly.
- The training loop logs the same core metrics as before.
"""

import argparse
import json
import random
import time
from pathlib import Path

import mlflow
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image
from torch.utils.data import DataLoader, Dataset
import torchvision.models as tv_models
import albumentations as A
from albumentations.pytorch import ToTensorV2

mlflow.set_experiment("litter-segmentation")
mlflow.config.enable_system_metrics_logging()
mlflow.config.set_system_metrics_sampling_interval(5)  # alle 5 Sekunden

"""
Änderungen am Trainingsskript, die vom originalen Skript abweichen,
um das Vorgehen des Skripts, nicht das Model zu verbessern, sind mit '# NOTE:' markiert.
"""

# ── Hyperparameters ──────────────────────────────────────────────────────────
EPOCHEN          = 50
BATCH_SIZE       = 8
CROP_SIZE        = 384
LR               = 8e-4
WEIGHT_DECAY     = 1e-4
ENCODER_CHANNELS = [64, 128, 256, 512]
DECODER_CHANNELS = [256, 128, 64, 32]
DROPOUT          = 0.1
POS_WEIGHT       = 5.0  # override with value from data/meta.json if available

# Optional training behavior
USE_POSITIVE_CROPS = True   # NOTE: more crops that actually contain litter
POSITIVE_CROP_PROB = 0.7
FREEZE_ENCODER_BN   = True   # NOTE: freeze only backbone BN, not decoder BN
REMOVE_LABEL_SMOOTHING = True

# ── Data ─────────────────────────────────────────────────────────────────────
DATA_DIR   = Path("data")
IMAGES_DIR = DATA_DIR / "images"
MASKS_DIR  = DATA_DIR / "masks"


def load_meta() -> dict:
    p = DATA_DIR / "meta.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}


class LitterDataset(Dataset):
    def __init__(self, split: str, crop_size: int = CROP_SIZE, augment: bool = True):
        stems_file = DATA_DIR / f"{split}.txt"
        self.stems = [s.strip() for s in stems_file.read_text().splitlines() if s.strip()]
        self.augment = augment
        self.crop_size = crop_size

        if augment:
            # OLD:
            # self.transform = A.Compose([
            #     A.RandomResizedCrop(size=(crop_size, crop_size),
            #                         scale=(0.4, 1.0), ratio=(0.75, 1.33)),
            #     A.HorizontalFlip(p=0.5),
            #     A.RandomRotate90(p=0.3),
            #     A.ColorJitter(brightness=0.3, contrast=0.3,
            #                   saturation=0.3, hue=0.05, p=0.7),
            #     A.GaussNoise(p=0.2),
            #     A.GridDistortion(p=0.3),
            #     A.ElasticTransform(p=0.3),
            #     A.Normalize(mean=(0.485, 0.456, 0.406),
            #                 std=(0.229, 0.224, 0.225)),
            #     ToTensorV2(),
            # ])

            # NEW:
            # - positive crops help the model see litter more often
            # - the geometry is less aggressively distorted than before
            # - if your albumentations version does not support CropNonEmptyMaskIfExists,
            #   replace it with the old RandomResizedCrop line above.
            self.transform = A.Compose([
                A.OneOf([
                    A.CropNonEmptyMaskIfExists(height=crop_size, width=crop_size, p=1.0),
                    A.RandomResizedCrop(size=(crop_size, crop_size),
                                        scale=(0.7, 1.0), ratio=(0.85, 1.15), p=1.0),
                ], p=1.0),
                A.HorizontalFlip(p=0.5),
                A.RandomRotate90(p=0.2),
                A.ShiftScaleRotate(shift_limit=0.05, scale_limit=0.10,
                                   rotate_limit=15, border_mode=0, p=0.5),
                A.ColorJitter(brightness=0.2, contrast=0.2,
                              saturation=0.2, hue=0.03, p=0.5),
                A.GaussNoise(p=0.1),
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
        mask = (np.array(Image.open(MASKS_DIR / f"{stem}.png")) > 127).astype(np.float32)

        out = self.transform(image=image, mask=mask)
        return out["image"], out["mask"].unsqueeze(0)   # (3,H,W), (1,H,W)


# ── Model blocks ──────────────────────────────────────────────────────────────

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


class SEBlock(nn.Module):
    """Squeeze-and-Excitation channel attention block."""
    def __init__(self, channels: int, reduction: int = 16):
        super().__init__()
        self.se = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Flatten(),
            nn.Linear(channels, max(channels // reduction, 4)),
            nn.ReLU(inplace=True),
            nn.Linear(max(channels // reduction, 4), channels),
            nn.Sigmoid(),
        )

    def forward(self, x):
        scale = self.se(x).view(x.size(0), x.size(1), 1, 1)
        return x * scale


class ASPPModule(nn.Module):
    """
    Atrous Spatial Pyramid Pooling for multi-scale context.
    Applies dilated convolutions at multiple rates and fuses outputs.
    """
    def __init__(self, in_ch: int, out_ch: int, rates=(6, 12, 18)):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_ch, out_ch, 1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
        self.dilated = nn.ModuleList([
            nn.Sequential(
                nn.Conv2d(in_ch, out_ch, 3, padding=r, dilation=r, bias=False),
                nn.BatchNorm2d(out_ch),
                nn.ReLU(inplace=True),
            ) for r in rates
        ])
        self.gap = nn.Sequential(
            nn.AdaptiveAvgPool2d(1),
            nn.Conv2d(in_ch, out_ch, 1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )
        n_branches = 1 + len(rates) + 1
        self.project = nn.Sequential(
            nn.Conv2d(n_branches * out_ch, out_ch, 1, bias=False),
            nn.BatchNorm2d(out_ch),
            nn.ReLU(inplace=True),
        )

    def forward(self, x):
        h, w = x.shape[2], x.shape[3]
        branches = [self.conv1(x)]
        for dil in self.dilated:
            branches.append(dil(x))
        gap_out = self.gap(x)
        gap_out = F.interpolate(gap_out, size=(h, w), mode='bilinear', align_corners=False)
        branches.append(gap_out)
        return self.project(torch.cat(branches, dim=1))


# ── Helper functions ──────────────────────────────────────────────────────────

def freeze_encoder_batchnorm(module: nn.Module):
    """Freeze BN layers inside the pretrained encoder only.

    OLD behavior (problematic):
    for m in self.modules():
        if isinstance(m, nn.BatchNorm2d):
            m.weight.requires_grad_(False)
            m.bias.requires_grad_(False)

    Why this is better:
    - only backbone BN is frozen
    - decoder BN stays trainable
    - prevents accidentally freezing the whole model
    """
    if isinstance(module, nn.BatchNorm2d):
        module.eval()
        module.weight.requires_grad_(False)
        module.bias.requires_grad_(False)


# ── Model definitions ────────────────────────────────────────────────────────

class ResNet34UNet(nn.Module):
    """
    U-Net with a pretrained ResNet34 encoder.

    Skip connections come from ResNet34 feature stages:
      stem  (64 ch,  H/2)
      layer1 (64 ch,  H/4)
      layer2 (128 ch, H/8)
      layer3 (256 ch, H/16)
      layer4 (512 ch, H/32)  — used as bottleneck

    BN layers in the backbone are frozen to preserve ImageNet statistics.
    """
    ENC_CHANNELS = [64, 64, 128, 256]
    BOTTLENECK_CH = 512

    def __init__(self, dropout: float = DROPOUT):
        super().__init__()

        backbone = tv_models.resnet34(weights=tv_models.ResNet34_Weights.IMAGENET1K_V1)

        self.stem_conv = nn.Sequential(backbone.conv1, backbone.bn1, backbone.relu)
        self.stem_pool = backbone.maxpool
        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4

        for m in self.modules():
            if isinstance(m, nn.BatchNorm2d):
                m.weight.requires_grad_(False)
                m.bias.requires_grad_(False)


        self.up1 = nn.ConvTranspose2d(512, 256, kernel_size=2, stride=2)
        self.dec1 = ConvBlock(256 + 256, 256, dropout)

        self.up2 = nn.ConvTranspose2d(256, 128, kernel_size=2, stride=2)
        self.dec2 = ConvBlock(128 + 128, 128, dropout)

        self.up3 = nn.ConvTranspose2d(128, 64, kernel_size=2, stride=2)
        self.dec3 = ConvBlock(64 + 64, 64, dropout)

        self.up4 = nn.ConvTranspose2d(64, 32, kernel_size=2, stride=2)
        self.dec4 = ConvBlock(32 + 64, 32, dropout)

        self.final_up = nn.ConvTranspose2d(32, 16, kernel_size=2, stride=2)
        self.final_conv = ConvBlock(16, 16, dropout)

        self.head = nn.Conv2d(16, 1, kernel_size=1)

    def _align(self, x, ref):
        if x.shape[2:] != ref.shape[2:]:
            x = F.interpolate(x, size=ref.shape[2:], mode="bilinear", align_corners=False)
        return x

    def forward(self, x):
        s0 = self.stem_conv(x)
        s1 = self.layer1(self.stem_pool(s0))
        s2 = self.layer2(s1)
        s3 = self.layer3(s2)
        s4 = self.layer4(s3)

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

        d = self.final_up(d)
        d = self.final_conv(d)
        return self.head(d)





# ── Loss ─────────────────────────────────────────────────────────────────────

class CombinedLoss(nn.Module):
    """BCE + Dice loss (equal weight), without label smoothing by default."""
    def __init__(self, pos_weight: float = POS_WEIGHT, label_smoothing: float = 0.0):
        super().__init__()
        self.register_buffer("pos_weight", torch.tensor([pos_weight], dtype=torch.float32))
        self.label_smoothing = label_smoothing

    def dice_loss(self, logits, targets, smooth: float = 1.0):
        probs = torch.sigmoid(logits)
        num = 2 * (probs * targets).sum(dim=(1, 2, 3)) + smooth
        den = probs.sum(dim=(1, 2, 3)) + targets.sum(dim=(1, 2, 3)) + smooth
        return (1 - num / den).mean()

    def forward(self, logits, targets):
        # OLD:
        # if self.label_smoothing > 0:
        #     targets_smooth = targets * (1.0 - self.label_smoothing) + 0.5 * self.label_smoothing
        # else:
        #     targets_smooth = targets
        # return self.bce(logits, targets_smooth) + self.dice_loss(logits, targets)

        # NEW:
        # For this problem, hard masks usually work better first.
        if self.label_smoothing > 0:
            targets = targets * (1.0 - self.label_smoothing) + 0.5 * self.label_smoothing
        bce = F.binary_cross_entropy_with_logits(logits, targets, pos_weight=self.pos_weight)
        return bce + self.dice_loss(logits, targets)

class FocalBCEDiceLoss(nn.Module):
    def __init__(self, gamma=2.0, pos_weight=5.0):
        super().__init__()
        self.gamma = gamma

        self.register_buffer("pos_weight", torch.tensor([pos_weight], dtype=torch.float32))

    def dice_loss(self, logits, targets, smooth=1.0):
        probs = torch.sigmoid(logits)
        num = 2 * (probs * targets).sum()
        den = probs.sum() + targets.sum()
        return 1 - (num + smooth) / (den + smooth)

    def focal_bce(self, logits, targets):
        bce = F.binary_cross_entropy_with_logits(
            logits,
            targets,
            pos_weight=self.pos_weight,  
            reduction='none'
        )
        probs = torch.sigmoid(logits)
        pt = probs * targets + (1 - probs) * (1 - targets)
        focal = (1 - pt) ** self.gamma * bce
        return focal.mean()

    def forward(self, logits, targets):
        return self.focal_bce(logits, targets) + self.dice_loss(logits, targets)

# ── Metrics ───────────────────────────────────────────────────────────────────

@torch.no_grad()
def compute_iou(logits: torch.Tensor, masks: torch.Tensor, threshold: float = 0.5) -> float:
    """Mean IoU over a batch.

    OLD:
        preds = (torch.sigmoid(logits) > threshold).float()
        inter = (preds * masks).sum().item()
        union = (preds + masks - preds * masks).sum().item()
        return inter / max(union, 1.0)

    NEW:
    - computes per-sample IoU, then averages it
    - if both prediction and target are empty, IoU is counted as 1.0
      (this is usually the more intuitive choice for empty litter patches)
    """
    preds = (torch.sigmoid(logits) > threshold).float()
    preds = preds.flatten(1)
    masks = masks.flatten(1)

    inter = (preds * masks).sum(dim=1)
    union = (preds + masks - preds * masks).sum(dim=1)
    iou = torch.where(union > 0, inter / union.clamp(min=1e-7), torch.ones_like(union))
    return iou.mean().item()

    


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


# ── Training loop ─────────────────────────────────────────────────────────────

def train(run_name: str):
    device = get_device()
    print(f"Device: {device}")

    meta = load_meta()
    pos_weight = meta.get("pos_weight_suggestion", POS_WEIGHT)

    # ── Data ──────────────────────────────────────────────────────────────
    train_ds = LitterDataset("train", crop_size=CROP_SIZE, augment=True)
    val_ds = LitterDataset("val", crop_size=CROP_SIZE, augment=False)

    train_loader = DataLoader(
        train_ds,
        batch_size=BATCH_SIZE,
        shuffle=True,
        num_workers=4,
        pin_memory=True,
        persistent_workers=True,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=BATCH_SIZE,
        shuffle=False,
        num_workers=2,
        pin_memory=True,
        persistent_workers=True,
    )

    # ── Model ─────────────────────────────────────────────────────────────
    model = ResNet34UNet(dropout=DROPOUT).to(device)

    total_params = sum(p.numel() for p in model.parameters())
    print(f"Model parameters: {total_params:,}")

    # Optional: differential learning rates
    # OLD:
    # optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)
    #
    # NEW:
    # Encoder receives a smaller LR because it is pretrained.
    encoder_params = []
    decoder_params = []
    for name, param in model.named_parameters():
        if not param.requires_grad:
            continue
        if any(key in name for key in ["stem_conv", "layer1", "layer2", "layer3", "layer4"]):
            encoder_params.append(param)
        else:
            decoder_params.append(param)

    optimizer = torch.optim.AdamW(
        [
            {"params": encoder_params, "lr": LR * 0.1},
            {"params": decoder_params, "lr": LR},
        ],
        weight_decay=WEIGHT_DECAY,
    )

    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer,
        max_lr=LR,
        epochs=EPOCHEN,
        steps_per_epoch=len(train_loader),
        pct_start=0.10,  # OLD: 0.05 — NEW: a slightly gentler warmup
    )

    #criterion = FocalBCEDiceLoss(pos_weight=pos_weight).to(device)
    criterion = CombinedLoss(pos_weight=pos_weight, label_smoothing=0.0).to(device)

    # ── MLflow ────────────────────────────────────────────────────────────
    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({
            "batch_size": BATCH_SIZE,
            "crop_size": CROP_SIZE,
            "lr": LR,
            "weight_decay": WEIGHT_DECAY,
            "encoder_channels": "ResNet34-pretrained",
            "decoder_channels": str(DECODER_CHANNELS),
            "dropout": DROPOUT,
            "pos_weight": pos_weight,
            "optimizer": "AdamW",
            "scheduler": "OneCycleLR",
            "loss": "BCE+Dice",
            "total_params": total_params,
            "device": str(device),
            "freeze_encoder_bn": FREEZE_ENCODER_BN,
            "positive_crops": USE_POSITIVE_CROPS,
        })

        step = 0
        best_val_iou = 0.0

        for epoch in range(EPOCHEN):
            t_start_epoch = time.time()
            model.train()
            train_loss = 0.0
            train_iou = 0.0
            train_samples = 0
            print(f"Epoch {epoch + 1}/{EPOCHEN} - Training...")

            for images, masks in train_loader:
                images = images.to(device, non_blocking=True)
                masks = masks.to(device, non_blocking=True)

                print(f"Step {step + 1}/{len(train_loader)}", end="\r")
                optimizer.zero_grad(set_to_none=True)
                logits = model(images)
                loss = criterion(logits, masks)
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()

                batch_size = images.size(0)
                train_loss += loss.item() * batch_size
                train_iou += compute_iou(logits, masks) * batch_size
                train_samples += batch_size
                step += 1

            # ── Validation ───────────────────────────────────────────────
            model.eval()
            val_loss = 0.0
            val_iou = 0.0
            val_samples = 0

            with torch.no_grad():
                for images, masks in val_loader:
                    images = images.to(device, non_blocking=True)
                    masks = masks.to(device, non_blocking=True)
                    logits = model(images)
                    loss = criterion(logits, masks)

                    batch_size = images.size(0)
                    val_loss += loss.item() * batch_size
                    val_iou += compute_iou(logits, masks) * batch_size
                    val_samples += batch_size

            elapsed = time.time() - t_start_epoch
            train_loss_avg = train_loss / max(train_samples, 1)
            train_iou_avg = train_iou / max(train_samples, 1)
            val_loss_avg = val_loss / max(val_samples, 1)
            val_iou_avg = val_iou / max(val_samples, 1)

            metrics = {
                "train_loss": train_loss_avg,
                "train_iou": train_iou_avg,
                "val_loss": val_loss_avg,
                "val_iou": val_iou_avg,
                "epoch": epoch,
                "elapsed_s": elapsed,
                "lr": scheduler.get_last_lr()[0],
            }
            mlflow.log_metrics(metrics, step=epoch)
            """
            if val_iou_avg > best_val_iou:
                best_val_iou = val_iou_avg
                best_path = f"best_model_{model.__class__.__name__}.pth"
                torch.save(model.state_dict(), best_path)
                mlflow.log_artifact(best_path)
            """

            if val_iou_avg > best_val_iou:
                best_val_iou = val_iou_avg

                best_path = f"{run_name}.pth"

                torch.save({
                    "model_state_dict": model.state_dict(),
                    "epoch": epoch,
                    "val_iou": val_iou_avg,
                    "optimizer_state_dict": optimizer.state_dict(),
                    "scheduler_state_dict": scheduler.state_dict(),
                }, best_path)

                mlflow.log_artifact(best_path)

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
    parser.add_argument("--run-name", default="baseline", help="MLflow run name")
    args = parser.parse_args()
    train(run_name=args.run_name)

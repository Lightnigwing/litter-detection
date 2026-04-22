"""
prepare.py — Download and preprocess the TACO litter dataset.

This script is NOT modified by the agent. It downloads the TACO dataset from
HuggingFace, reads the COCO annotations JSON from the included ZIP file,
converts polygon segmentation annotations to binary pixel masks
(litter vs. background), and saves everything to data/ ready for train.py.

Dataset: https://huggingface.co/datasets/Zesky665/TACO
Format:  COCO_format.zip inside the HF snapshot contains:
           data/annotations.json   — COCO JSON with segmentation polygons
           data/batch_*/           — image files

Output layout:
    data/
        images/       *.jpg  (resized to IMAGE_SIZE x IMAGE_SIZE)
        masks/        *.png  (binary uint8: 0=background, 255=litter)
        train.txt     list of stem names for training split
        val.txt       list of stem names for validation split
        meta.json     dataset statistics
"""

import io
import json
import os
import random
import zipfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps
from huggingface_hub import snapshot_download
from tqdm import tqdm

"""
alles was angepasst wurde vom orginalen prepare.py wird mit #NOTE markiert und iner kurzen beschreibung warum versehen
"""


# ── Config ────────────────────────────────────────────────────────────────────
IMAGE_SIZE    = 768          #NOTE: von 512 auf 768 geändert, da die meisten Bilder im Datensatz größer als 512x512 sind. Dadurch wird weniger verzerrt und mehr Details bleiben erhalten
VAL_FRACTION  = 0.2 #NOTE von 0,15 auf 0,2 geändert
RANDOM_SEED   = 42
DATA_DIR      = Path("data")
IMAGES_DIR    = DATA_DIR / "images"
MASKS_DIR     = DATA_DIR / "masks"
HF_REPO       = "Zesky665/TACO"
ZIP_INNER     = "COCO_format.zip"
ANNOTATIONS   = "data/annotations.json"
# ─────────────────────────────────────────────────────────────────────────────


def find_zip(snapshot_dir: str) -> str:
    for root, _, files in os.walk(snapshot_dir):
        for f in files:
            if f == ZIP_INNER:
                return os.path.join(root, f)
    raise FileNotFoundError(f"{ZIP_INNER} not found under {snapshot_dir}")


def polygon_to_mask(segmentation: list, width: int, height: int) -> np.ndarray:
    """Convert a COCO flat-polygon list [[x1,y1,x2,y2,...], ...] to a uint8 mask."""
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    for poly in segmentation:
        if len(poly) < 6:
            continue
        xy = list(zip(poly[0::2], poly[1::2]))
        draw.polygon(xy, outline=1, fill=1)
    return np.array(mask, dtype=np.uint8)

# NOTE: Resize mit Padding (kein Verzerren)
def resize_with_padding(img, size, is_mask=False):
    w, h = img.size

    scale = min(size / w, size / h)
    new_w, new_h = int(w * scale), int(h * scale)

    interp = Image.NEAREST if is_mask else Image.BILINEAR
    img_resized = img.resize((new_w, new_h), interp)

    mode = "L" if is_mask else "RGB"
    fill = 0 if is_mask else (0, 0, 0)

    new_img = Image.new(mode, (size, size), fill)

    paste_x = (size - new_w) // 2
    paste_y = (size - new_h) // 2

    new_img.paste(img_resized, (paste_x, paste_y))

    return new_img 

def main():
    random.seed(RANDOM_SEED)
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    MASKS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Download / locate the dataset ─────────────────────────────────────
    print(f"Downloading {HF_REPO} snapshot …")
    snapshot_dir = snapshot_download(repo_id=HF_REPO, repo_type="dataset")
    print(f"  Snapshot at: {snapshot_dir}")

    zip_path = find_zip(snapshot_dir)
    print(f"  ZIP found: {zip_path}")

    # ── Parse COCO annotations ────────────────────────────────────────────
    print("Reading COCO annotations …")
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open(ANNOTATIONS) as f:
            coco = json.load(f)

    """
    # NOTE: Analyse der Bildgrößen im Datensatz

    import matplotlib.pyplot as plt

    widths = []
    heights = []

    for img in coco["images"]:
        widths.append(img["width"])
        heights.append(img["height"])

    print(f"Min width:  {min(widths)}")
    print(f"Max width:  {max(widths)}")
    print(f"Min height: {min(heights)}")
    print(f"Max height: {max(heights)}")

    # Scatter Plot: Breite vs Höhe
    plt.figure()
    plt.scatter(widths, heights)
    plt.xlabel("Width")
    plt.ylabel("Height")
    plt.title("Image size distribution (width vs height)")
    plt.show()
    Min width:  842
    Max width:  6000
    Min height: 474
    Max height: 5312

    """
    images_by_id = {img["id"]: img for img in coco["images"]}

    # Group annotations by image_id
    anns_by_image: dict[int, list] = defaultdict(list)
    for ann in coco["annotations"]:
        anns_by_image[ann["image_id"]].append(ann)

    image_ids = list(images_by_id.keys())
    print(f"  Images: {len(image_ids)}   Annotations: {len(coco['annotations'])}")

    # ── Split ─────────────────────────────────────────────────────────────
    random.shuffle(image_ids)
    n_val = max(1, int(len(image_ids) * VAL_FRACTION))
    splits = {
        "val":   image_ids[:n_val],
        "train": image_ids[n_val:],
    }

    # ── Process ───────────────────────────────────────────────────────────
    stems_by_split: dict[str, list[str]] = {}
    count_RLE = 0
    count_polygons = 0
    with zipfile.ZipFile(zip_path) as zf:
        # Build a case-insensitive lookup of zip entries (some files are .JPG)
        name_map = {}
        for entry in zf.namelist():
            name_map[entry.lower()] = entry

        for split_name, ids in splits.items():
            stems = []
            skipped = 0
            for img_id in tqdm(ids, desc=f"Processing {split_name}"):
                meta = images_by_id[img_id]
                # file_name is like "batch_1/000006.jpg"
                inner_path = f"data/{meta['file_name']}"
                inner_key  = inner_path.lower()

                if inner_key not in name_map:
                    skipped += 1
                    continue

                try:
                    with zf.open(name_map[inner_key]) as img_f:
                        img_bytes = img_f.read()
                    img = Image.open(io.BytesIO(img_bytes))
                    img = ImageOps.exif_transpose(img).convert("RGB")
                except Exception as e:
                    tqdm.write(f"  Skipping {inner_path}: {e}")
                    skipped += 1
                    continue

                orig_w, orig_h = img.size
                img_resized = resize_with_padding(img, IMAGE_SIZE) #NOTE: Resize mit Padding (kein Verzerren)

                # ── Build binary mask from all annotations ─────────────────
                combined_mask = np.zeros((orig_h, orig_w), dtype=np.uint8)
                for ann in anns_by_image.get(img_id, []):
                    seg = ann.get("segmentation", [])
                    if not seg or isinstance(seg, dict):   # skip RLE
                        count_RLE += 1
                        continue
                    m = polygon_to_mask(seg, orig_w, orig_h)
                    count_polygons += 1
                    combined_mask = np.maximum(combined_mask, m)

                mask_pil     = Image.fromarray(combined_mask * 255, mode="L")
                mask_resized = resize_with_padding(mask_pil, IMAGE_SIZE, is_mask=True) # NOTE: Resize mit Padding (kein Verzerren)

                stem = f"{img_id:06d}"
                img_resized.save(IMAGES_DIR / f"{stem}.jpg", quality=92)
                mask_resized.save(MASKS_DIR  / f"{stem}.png")
                stems.append(stem)

            if skipped:
                print(f"  Skipped {skipped} entries in {split_name}")
            stems_by_split[split_name] = stems

    (DATA_DIR / "train.txt").write_text("\n".join(stems_by_split["train"]) + "\n")
    (DATA_DIR / "val.txt").write_text(  "\n".join(stems_by_split["val"])   + "\n")

    # ── Statistics ────────────────────────────────────────────────────────
    all_stems = stems_by_split["train"] + stems_by_split["val"]
    litter_pixels = 0
    total_pixels  = 0
    sample = random.sample(all_stems, min(1000, len(all_stems)))
    for stem in sample:
        m = np.array(Image.open(MASKS_DIR / f"{stem}.png"))
        litter_pixels += int((m > 127).sum())
        total_pixels  += m.size

    pos_frac = litter_pixels / max(total_pixels, 1)
    meta_out = {
        "image_size":                    IMAGE_SIZE,
        "train_count":                   len(stems_by_split["train"]),
        "val_count":                     len(stems_by_split["val"]),
        "litter_pixel_fraction_sample":  round(pos_frac, 4),
        "pos_weight_suggestion":         round((1 - pos_frac) / max(pos_frac, 1e-6), 2),
    }
    (DATA_DIR / "meta.json").write_text(json.dumps(meta_out, indent=2))

    print("\nDone.")
    print(f"  Train: {meta_out['train_count']}   Val: {meta_out['val_count']}")
    print(f"  Litter pixel fraction : {pos_frac:.2%}")
    print(f"  Suggested BCEWithLogitsLoss pos_weight: {meta_out['pos_weight_suggestion']}")
    print(f"  Metadata → {DATA_DIR / 'meta.json'}")
    print(f"  Note: {count_RLE} annotations were in RLE format and skipped (no polygon segmentation).")
    print(f"        {count_polygons} annotations were processed as polygons.")
    


if __name__ == "__main__":
    main()

"""Multi-object litter tracker based on connected components + centroid matching."""

from dataclasses import dataclass, field

import cv2
import numpy as np


COLORS: list[tuple[int, int, int]] = [
    (0, 165, 255),
    (0, 255, 0),
    (255, 0, 128),
    (0, 0, 255),
    (255, 0, 255),
    (0, 255, 255),
    (128, 0, 255),
    (255, 128, 0),
]


@dataclass
class TrackedObject:
    track_id: int
    color_bgr: tuple[int, int, int]
    centroid: tuple[float, float]
    component_mask: np.ndarray
    bbox: tuple[int, int, int, int]  # x, y, w, h at infer_size resolution
    area: int
    frames_seen: int = 1
    frames_lost: int = 0
    validated: bool = False


class LitterTracker:
    def __init__(
        self,
        min_area: int = 200,
        max_distance: int = 100,
        max_lost_frames: int = 15,
    ) -> None:
        self._tracks: dict[int, TrackedObject] = {}
        self._next_id: int = 0
        self._min_area = min_area
        self._max_distance = max_distance
        self._max_lost_frames = max_lost_frames

    def update(self, binary_mask: np.ndarray) -> list[TrackedObject]:
        num, labels, stats, centroids = cv2.connectedComponentsWithStats(
            binary_mask.astype(np.uint8), connectivity=8
        )

        components: list[tuple[float, float, int, tuple[int, int, int, int], np.ndarray]] = []
        for i in range(1, num):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < self._min_area:
                continue
            cx, cy = float(centroids[i][0]), float(centroids[i][1])
            x = int(stats[i, cv2.CC_STAT_LEFT])
            y = int(stats[i, cv2.CC_STAT_TOP])
            w = int(stats[i, cv2.CC_STAT_WIDTH])
            h = int(stats[i, cv2.CC_STAT_HEIGHT])
            comp_mask = labels == i
            components.append((cx, cy, area, (x, y, w, h), comp_mask))

        matched_track_ids: set[int] = set()
        matched_component_indices: set[int] = set()

        for track_id, track in self._tracks.items():
            best_dist = float("inf")
            best_j = -1
            for j, (cx, cy, *_rest) in enumerate(components):
                if j in matched_component_indices:
                    continue
                dist = ((cx - track.centroid[0]) ** 2 + (cy - track.centroid[1]) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_j = j

            if best_j >= 0 and best_dist <= self._max_distance:
                cx, cy, area, bbox, comp_mask = components[best_j]
                track.centroid = (cx, cy)
                track.component_mask = comp_mask
                track.bbox = bbox
                track.area = area
                track.frames_seen += 1
                track.frames_lost = 0
                matched_track_ids.add(track_id)
                matched_component_indices.add(best_j)

        for j, (cx, cy, area, bbox, comp_mask) in enumerate(components):
            if j in matched_component_indices:
                continue
            color = COLORS[self._next_id % len(COLORS)]
            self._tracks[self._next_id] = TrackedObject(
                track_id=self._next_id,
                color_bgr=color,
                centroid=(cx, cy),
                component_mask=comp_mask,
                bbox=bbox,
                area=area,
            )
            self._next_id += 1

        for tid, track in self._tracks.items():
            if tid not in matched_track_ids:
                track.frames_lost += 1

        expired = [
            tid
            for tid, track in self._tracks.items()
            if track.frames_lost > self._max_lost_frames
        ]
        for tid in expired:
            del self._tracks[tid]

        return [t for t in self._tracks.values() if t.frames_lost == 0]

    def draw_overlay(
        self,
        img_bgr: np.ndarray,
        tracked: list[TrackedObject],
        alpha: float = 0.55,
    ) -> np.ndarray:
        overlay = img_bgr.copy()
        h, w = img_bgr.shape[:2]
        for obj in tracked:
            mask_full = cv2.resize(
                obj.component_mask.astype(np.uint8),
                (w, h),
                interpolation=cv2.INTER_NEAREST,
            ).astype(bool)
            if mask_full.any():
                tint = np.array(obj.color_bgr, dtype=np.float32)
                overlay[mask_full] = (
                    overlay[mask_full].astype(np.float32) * (1 - alpha) + tint * alpha
                ).clip(0, 255).astype(np.uint8)
        return overlay

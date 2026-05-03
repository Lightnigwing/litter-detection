from __future__ import annotations

from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import math

import numpy as np


def normalize_angle(angle: float) -> float:
    """Wrap angle to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


class Pose2D(BaseModel):
    x: float
    y: float
    theta: float

    def __add__(self, other: "Pose2D") -> "Pose2D":
        return Pose2D(
            x=self.x + other.x,
            y=self.y + other.y,
            theta=normalize_angle(self.theta + other.theta),
        )

    def __sub__(self, other: "Pose2D") -> "Pose2D":
        return Pose2D(
            x=self.x - other.x,
            y=self.y - other.y,
            theta=normalize_angle(self.theta - other.theta),
        )

    def __abs__(self) -> float:
        """Euclidean distance from origin (ignores theta)."""
        return math.sqrt(self.x**2 + self.y**2)

    def __mul__(self, scalar: float) -> "Pose2D":
        return Pose2D(x=self.x * scalar, y=self.y * scalar, theta=self.theta * scalar)

    def __rmul__(self, scalar: float) -> "Pose2D":
        return self.__mul__(scalar)

    @property
    def distance(self) -> float:
        """Same as abs(), but more readable in context."""
        return abs(self)

    @property
    def bearing(self) -> float:
        """Angle from origin to this point."""
        return math.atan2(self.y, self.x)

    def distance_to(self, other: "Pose2D") -> float:
        return abs(self - other)

    def bearing_to(self, other: "Pose2D") -> float:
        return (other - self).bearing


class Corridor(BaseModel):
    """Lateral bounds for path planning on a segment.
    Measured as allowed deviation from the straight line
    between segment start and end."""

    left_width: float
    right_width: float


class NavigationSegment(BaseModel):
    """A single segment to traverse."""

    target: Pose2D
    max_speed: float | None = None
    corridor: Corridor | None = None
    allowed_deviation: float = 0.15
    allowed_orientation_deviation: float = 0.1
    must_stop: bool = True
    orientation_at_target: float | None = None
    rotation_allowed_on_segment: bool = True


class NavigationRequest(BaseModel):
    """Complete navigation request."""

    request_id: str
    segments: list[NavigationSegment]
    lookahead_segments: int = 1


class PathWaypoint(BaseModel):
    """A single waypoint on the planned path."""

    pose: Pose2D
    speed: float
    is_segment_boundary: bool = False
    must_stop: bool = False
    allowed_deviation: float = 0.15
    allowed_orientation_deviation: float = 0.1


class PlannedPath(BaseModel):
    """Output of the path planner."""

    request_id: str
    waypoints: list[PathWaypoint]


class NavigationState(str, Enum):
    IDLE = "idle"
    FOLLOWING = "following"
    ARRIVED_SEGMENT = "arrived_segment"
    ARRIVED_FINAL = "arrived_final"
    BLOCKED = "blocked"
    FAILED = "failed"


class NavigationStatus(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: NavigationState
    current_pose: Pose2D | None = None
    distance_to_target: float | None = None
    distance_to_final: float | None = None
    current_segment_index: int | None = None
    request_id: str | None = None


class CostMap(BaseModel):
    """2D occupancy / cost grid in map frame."""

    origin_x: float
    origin_y: float
    resolution: float
    width: int
    height: int
    data: list[int]

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        col = int((x - self.origin_x) / self.resolution)
        row = int((y - self.origin_y) / self.resolution)
        return row, col

    def grid_to_world(self, row: int, col: int) -> tuple[float, float]:
        x = self.origin_x + (col + 0.5) * self.resolution
        y = self.origin_y + (row + 0.5) * self.resolution
        return x, y

    def get_cost(self, row: int, col: int) -> int:
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.data[row * self.width + col]
        return 255

    def is_free(self, row: int, col: int, threshold: int = 128) -> bool:
        return self.get_cost(row, col) < threshold

    def to_numpy(self) -> np.ndarray:
        return np.array(self.data, dtype=np.uint8).reshape(self.height, self.width)

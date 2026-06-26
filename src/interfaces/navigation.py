from __future__ import annotations

from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime, timezone
import math

import numpy as np


def normalize_angle(angle: float) -> float:
    """Wrap angle to [-pi, pi]."""
    return math.atan2(math.sin(angle), math.cos(angle))


def quaternion_to_yaw(qx: float, qy: float, qz: float, qw: float) -> float:
    """Extract yaw (rotation around Z) from an (qx, qy, qz, qw) quaternion.

    Shared by the nav module and the VDA5050 LivePositionProvider so both see
    the same theta for a given pose payload.
    """
    return math.atan2(
        2.0 * (qw * qz + qx * qy),
        1.0 - 2.0 * (qy * qy + qz * qz),
    )


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

    left_width: float  # meters, positive = left of travel direction
    right_width: float  # meters, positive = right of travel direction


class NavigationSegment(BaseModel):
    """A single segment to traverse.
    """

    target: Pose2D
    max_speed: float | None = None
    corridor: Corridor | None = None
    allowed_deviation: float = 0.15
    allowed_orientation_deviation: float = 0.1
    must_stop: bool = True
    orientation_at_target: float | None = None
    rotation_allowed_on_segment: bool = True


class NavigationRequest(BaseModel):
    """Complete navigation request.

    Single segment = simple "go to coordinate".
    Multiple segments = sequenced path
    """

    request_id: str  # Unique ID for correlation with status messages
    segments: list[NavigationSegment]  # At least one segment
    lookahead_segments: int = 1  # How many segments ahead the executor may peek


class PathWaypoint(BaseModel):
    """A single waypoint on the planned path.

    The planner generates a dense list of these from the navigation request.
    The executor follows them in sequence.
    """

    pose: Pose2D
    speed: float
    is_segment_boundary: bool = False
    must_stop: bool = False
    allowed_deviation: float = 0.15
    allowed_orientation_deviation: float = 0.1


class PlannedPath(BaseModel):
    """Output of the path planner.

    A dense, ordered list of waypoints from current position to final target.
    The executor consumes this sequentially.
    """

    request_id: str  # Matches the NavigationRequest
    waypoints: list[PathWaypoint]


class NavigationState(str, Enum):
    IDLE = "idle"
    FOLLOWING = "following"  # Actively following a path
    ARRIVED_SEGMENT = "arrived_segment"  # Reached a segment boundary
    ARRIVED_FINAL = "arrived_final"  # Reached the last waypoint
    BLOCKED = "blocked"  # Cannot proceed
    FAILED = "failed"  # Gave up


class NavigationStatus(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: NavigationState
    current_pose: Pose2D | None = None
    distance_to_target: float | None = None  # Distance to current waypoint target
    distance_to_final: float | None = None  # Distance to last waypoint
    current_segment_index: int | None = None  # Which segment is active
    request_id: str | None = None  # Correlation ID from NavigationRequest
    # Pure-Pursuit carrot point (x/y only — theta unused). Diagnostic field
    # for the visualizer; consumers can safely ignore it. ``None`` whenever
    # the controller isn't actively steering (IDLE / BLOCKED / aligning).
    lookahead_point: Pose2D | None = None


class CostMap(BaseModel):
    """2D occupancy / cost grid in map frame.

    Cell values:
      0       = free space
      1-254   = increasing cost (soft obstacles, proximity penalty)
      255     = lethal obstacle (impassable)

    The grid is row-major: index = row * width + col.
    grid[0][0] is at (origin_x, origin_y), indices increase with x (columns)
    and y (rows).
    """

    origin_x: float  # World x of grid cell [0][0], meters
    origin_y: float  # World y of grid cell [0][0], meters
    resolution: float  # Meters per cell
    width: int  # Number of columns
    height: int  # Number of rows
    data: list[int]  # Flat array, row-major: index = row * width + col

    def world_to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Convert world coordinates to grid (row, col) indices."""
        col = int((x - self.origin_x) / self.resolution)
        row = int((y - self.origin_y) / self.resolution)
        return row, col

    def grid_to_world(self, row: int, col: int) -> tuple[float, float]:
        """Convert grid (row, col) indices to world coordinates (cell center)."""
        x = self.origin_x + (col + 0.5) * self.resolution
        y = self.origin_y + (row + 0.5) * self.resolution
        return x, y

    def get_cost(self, row: int, col: int) -> int:
        """Get cost at grid cell. Returns 255 for out-of-bounds."""
        if 0 <= row < self.height and 0 <= col < self.width:
            return self.data[row * self.width + col]
        return 255

    def is_free(self, row: int, col: int, threshold: int = 128) -> bool:
        """Check if a cell is traversable."""
        return self.get_cost(row, col) < threshold

    def to_numpy(self) -> np.ndarray:
        """Return the grid as a (height, width) uint8 numpy array."""
        return np.array(self.data, dtype=np.uint8).reshape(self.height, self.width)

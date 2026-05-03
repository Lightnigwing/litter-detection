from __future__ import annotations

import math
import time

from loguru import logger

from interfaces.motion import MovementCommand, MovementSource
from interfaces.navigation import (
    NavigationState,
    NavigationStatus,
    PathWaypoint,
    PlannedPath,
    Pose2D,
    normalize_angle,
)
from nav.utils import clamp


class PathExecutor:
    """Straight-line path executor with turn-walk-align phases.

    For each waypoint:
    1. TURNING — rotate in place until facing the waypoint
    2. WALKING — drive forward with small strafing corrections
    3. ALIGNING — at the target, rotate in place to match target heading
    """

    ANGULAR_KP = 1.5
    MAX_ANGULAR_VELOCITY = 0.8
    STATUS_INTERVAL = 0.5
    BLOCKED_TIMEOUT = 5.0
    BLOCKED_DISTANCE_THRESHOLD = 0.05
    BLOCKED_ANGLE_THRESHOLD = math.radians(5)
    ORIENTATION_KP = 1.2
    HEADING_THRESHOLD = math.radians(15)

    def __init__(self) -> None:
        self._path: PlannedPath | None = None
        self._waypoint_index: int = 0
        self._state: NavigationState = NavigationState.IDLE
        self._last_reported_state: NavigationState | None = None
        self._last_status_time: float = 0.0

        self._last_progress_pose: Pose2D | None = None
        self._last_progress_time: float = 0.0

        self._turned_toward_waypoint: bool = False

    @property
    def state(self) -> NavigationState:
        return self._state

    @property
    def request_id(self) -> str | None:
        return self._path.request_id if self._path else None

    def set_path(self, path: PlannedPath) -> None:
        """Accept a new planned path to follow."""
        self._path = path
        self._waypoint_index = 0
        self._state = NavigationState.FOLLOWING
        self._last_progress_pose = None
        self._last_progress_time = time.monotonic()
        self._turned_toward_waypoint = False
        logger.info(
            f"Following new path (request={path.request_id}, {len(path.waypoints)} waypoints)"
        )

    def continue_to_next(self) -> bool:
        """Advance past an ARRIVED_SEGMENT to the next waypoint."""
        if self._state != NavigationState.ARRIVED_SEGMENT or self._path is None:
            return False
        self._waypoint_index += 1
        self._turned_toward_waypoint = False
        self._last_progress_pose = None
        self._last_progress_time = time.monotonic()
        if self._waypoint_index >= len(self._path.waypoints):
            self._state = NavigationState.ARRIVED_FINAL
            logger.info("Arrived at final waypoint")
            return False
        self._state = NavigationState.FOLLOWING
        logger.info(
            f"Continuing to waypoint {self._waypoint_index}/{len(self._path.waypoints) - 1}"
        )
        return True

    def reset(self) -> None:
        """Reset to idle state."""
        self._path = None
        self._waypoint_index = 0
        self._state = NavigationState.IDLE
        self._turned_toward_waypoint = False

    def update(
        self, current_pose: Pose2D
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Compute velocity command and optional status update for the current pose."""
        if self._state != NavigationState.FOLLOWING or self._path is None:
            return self._stop_cmd(), self._maybe_status(current_pose)

        waypoints = self._path.waypoints
        if self._waypoint_index >= len(waypoints):
            self._state = NavigationState.ARRIVED_FINAL
            logger.info("Arrived at final waypoint")
            return self._stop_cmd(), self._build_status(current_pose)

        current_wp = waypoints[self._waypoint_index]
        distance = current_pose.distance_to(current_wp.pose)

        if distance < current_wp.allowed_deviation:
            return self._handle_waypoint_reached(current_pose, current_wp)

        if self._check_blocked(current_pose):
            self._state = NavigationState.BLOCKED
            logger.warning(
                f"Robot appears blocked — no progress for {self.BLOCKED_TIMEOUT}s"
            )
            return self._stop_cmd(), self._build_status(current_pose)

        bearing = current_pose.bearing_to(current_wp.pose)
        heading_error = normalize_angle(bearing - current_pose.theta)

        if not self._turned_toward_waypoint:
            if abs(heading_error) > self.HEADING_THRESHOLD:
                wz = clamp(
                    heading_error * self.ANGULAR_KP,
                    -self.MAX_ANGULAR_VELOCITY,
                    self.MAX_ANGULAR_VELOCITY,
                )
                cmd = MovementCommand(
                    z_deg=math.degrees(wz), source=MovementSource.planner
                )
                return cmd, self._maybe_status(current_pose)
            self._turned_toward_waypoint = True

        vel = self._compute_velocity(current_pose, current_wp)
        return vel, self._maybe_status(current_pose)

    def _handle_waypoint_reached(
        self, current_pose: Pose2D, waypoint: PathWaypoint
    ) -> tuple[MovementCommand, NavigationStatus | None]:
        """Handle reaching a waypoint — align orientation, then stop or advance."""
        assert self._path is not None
        if waypoint.must_stop:
            orientation_error = normalize_angle(
                waypoint.pose.theta - current_pose.theta
            )
            if abs(orientation_error) > waypoint.allowed_orientation_deviation:
                wz = clamp(
                    orientation_error * self.ORIENTATION_KP,
                    -self.MAX_ANGULAR_VELOCITY,
                    self.MAX_ANGULAR_VELOCITY,
                )
                return MovementCommand(
                    z_deg=math.degrees(wz), source=MovementSource.planner
                ), self._maybe_status(current_pose)

            is_last = self._waypoint_index >= len(self._path.waypoints) - 1
            if is_last:
                self._state = NavigationState.ARRIVED_FINAL
                logger.info("Arrived at final waypoint")
            else:
                self._state = NavigationState.ARRIVED_SEGMENT
                logger.info(
                    f"Arrived at segment boundary (waypoint {self._waypoint_index})"
                )
            return self._stop_cmd(), self._build_status(current_pose)

        self._waypoint_index += 1
        self._turned_toward_waypoint = False
        if self._waypoint_index >= len(self._path.waypoints):
            self._state = NavigationState.ARRIVED_FINAL
            logger.info("Arrived at final waypoint")
            return self._stop_cmd(), self._build_status(current_pose)

        new_wp = self._path.waypoints[self._waypoint_index]
        vel = self._compute_velocity(current_pose, new_wp)
        return vel, self._maybe_status(current_pose)

    def _compute_velocity(
        self, current_pose: Pose2D, waypoint: PathWaypoint
    ) -> MovementCommand:
        """Compute velocity to walk toward the given waypoint with strafing corrections."""
        target = waypoint.pose
        target_speed = waypoint.speed

        bearing = current_pose.bearing_to(target)
        heading_error = normalize_angle(bearing - current_pose.theta)

        wz = clamp(
            heading_error * self.ANGULAR_KP,
            -self.MAX_ANGULAR_VELOCITY,
            self.MAX_ANGULAR_VELOCITY,
        )

        turn_factor = 1.0 - min(abs(heading_error) / (math.pi / 2), 1.0)
        vx = target_speed * turn_factor

        vy = 0.0
        if abs(heading_error) < math.radians(30):
            lateral_error = math.sin(heading_error) * current_pose.distance_to(target)
            vy = clamp(lateral_error * 0.5, -0.15, 0.15)

        return MovementCommand(
            x=vx, y=vy, z_deg=math.degrees(wz), source=MovementSource.planner
        )

    def _check_blocked(self, current_pose: Pose2D) -> bool:
        """Check if the robot is stuck (no progress for BLOCKED_TIMEOUT seconds)."""
        now = time.monotonic()

        if self._last_progress_pose is None:
            self._last_progress_pose = current_pose
            self._last_progress_time = now
            return False

        distance_moved = current_pose.distance_to(self._last_progress_pose)
        angle_moved = abs(normalize_angle(current_pose.theta - self._last_progress_pose.theta))
        if distance_moved > self.BLOCKED_DISTANCE_THRESHOLD or angle_moved > self.BLOCKED_ANGLE_THRESHOLD:
            self._last_progress_pose = current_pose
            self._last_progress_time = now
            return False

        return (now - self._last_progress_time) >= self.BLOCKED_TIMEOUT

    @staticmethod
    def _stop_cmd() -> MovementCommand:
        return MovementCommand(source=MovementSource.planner)

    def _maybe_status(self, current_pose: Pose2D) -> NavigationStatus | None:
        """Return a status update if needed (state change or periodic)."""
        now = time.monotonic()
        state_changed = self._state != self._last_reported_state

        if state_changed:
            return self._build_status(current_pose)

        if (
            self._state == NavigationState.FOLLOWING
            and (now - self._last_status_time) >= self.STATUS_INTERVAL
        ):
            return self._build_status(current_pose)

        return None

    def _build_status(self, current_pose: Pose2D) -> NavigationStatus:
        """Build and record a NavigationStatus."""
        self._last_reported_state = self._state
        self._last_status_time = time.monotonic()

        distance_to_target = None
        distance_to_final = None
        segment_index = None

        if self._path and self._waypoint_index < len(self._path.waypoints):
            current_wp = self._path.waypoints[self._waypoint_index]
            distance_to_target = current_pose.distance_to(current_wp.pose)

            final_wp = self._path.waypoints[-1]
            distance_to_final = current_pose.distance_to(final_wp.pose)

            segment_index = sum(
                1
                for wp in self._path.waypoints[: self._waypoint_index]
                if wp.is_segment_boundary
            )

        return NavigationStatus(
            state=self._state,
            current_pose=current_pose,
            distance_to_target=distance_to_target,
            distance_to_final=distance_to_final,
            current_segment_index=segment_index,
            request_id=self._path.request_id if self._path else None,
        )

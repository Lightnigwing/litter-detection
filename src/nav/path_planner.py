from __future__ import annotations

from loguru import logger

from interfaces.navigation import (
    NavigationRequest,
    PathWaypoint,
    PlannedPath,
    Pose2D,
)

DEFAULT_SPEED = 0.4  # m/s, conservative for Go2 indoors


class PathPlannerModule:
    """Simple straight-line path planner.

    Generates one waypoint per segment (the segment target).
    The executor handles turning toward and walking to each waypoint.
    """

    def plan(self, request: NavigationRequest, current_pose: Pose2D) -> PlannedPath:
        """Plan a path from current_pose through all segments."""
        waypoints: list[PathWaypoint] = []

        for segment in request.segments:
            speed = (
                segment.max_speed if segment.max_speed is not None else DEFAULT_SPEED
            )
            waypoints.append(
                PathWaypoint(
                    pose=segment.target,
                    speed=speed,
                    is_segment_boundary=True,
                    must_stop=segment.must_stop,
                    allowed_deviation=segment.allowed_deviation,
                    allowed_orientation_deviation=segment.allowed_orientation_deviation,
                )
            )

        logger.debug(
            f"Planned {len(waypoints)} waypoints for request {request.request_id}"
        )
        return PlannedPath(request_id=request.request_id, waypoints=waypoints)

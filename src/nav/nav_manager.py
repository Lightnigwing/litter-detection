from __future__ import annotations

import asyncio
import math

import zenoh
from loguru import logger

from robodog import Settings
from interfaces.motion import MovementCommand
from interfaces.navigation import (
    NavigationRequest,
    NavigationSegment,
    NavigationState,
    NavigationStatus,
    PlannedPath,
    Pose2D,
)
from interfaces.robot import OdometryState
from nav.path_planner import PathPlannerModule
from nav.path_executor import PathExecutor


class NavManager:
    """Zenoh I/O layer for navigation.

    Orchestrates PathPlannerModule and PathExecutor, manages the shared
    Zenoh session, and publishes MovementCommands to the robot.
    """

    TICK_RATE_HZ: float = 15.0
    STATUS_INTERVAL_SEC: float = 1.0

    def __init__(self) -> None:
        self.settings = Settings()
        self.z_session = zenoh.open(self.settings.zenoh_config)

        self.planner = PathPlannerModule()
        self.executor = PathExecutor()

        self.z_pub_vel = self.z_session.declare_publisher(
            key_expr=self.settings.topics.command.motion.move,
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )
        self.z_pub_nav_status = self.z_session.declare_publisher(
            key_expr=self.settings.topics.nav.status,
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )
        self.z_pub_planned_path = self.z_session.declare_publisher(
            key_expr=self.settings.topics.nav.planned_path,
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )

        self.z_session.declare_subscriber(
            key_expr=self.settings.topics.nav.request,
            handler=self._on_request,
        )
        self.z_session.declare_subscriber(
            key_expr=self.settings.topics.system_state.odometry,
            handler=self._on_pose,
        )

        self.pose: Pose2D = Pose2D(x=0.0, y=0.5, theta=0.0)
        self.is_running: bool = False
        self._needs_final_stop: bool = False

    def _on_request(self, sample: zenoh.Sample) -> None:
        """Handle a NavigationRequest (new multi-segment format)."""
        payload = bytes(sample.payload)
        request = NavigationRequest.model_validate_json(payload)
        logger.info(
            f"Received NavigationRequest: {request.request_id} ({len(request.segments)} segments)"
        )
        path = self.planner.plan(request, self.pose)
        self._publish_planned_path(path)
        self.executor.set_path(path)

    def _on_pose(self, sample: zenoh.Sample) -> None:
        payload = bytes(sample.payload)
        odom = OdometryState.model_validate_json(payload)
        self.pose = self._odom_to_pose(odom)

    @staticmethod
    def _odom_to_pose(odom: OdometryState) -> Pose2D:
        qx, qy, qz, qw = odom.quaternion
        theta = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
        return Pose2D(x=odom.x, y=odom.y, theta=theta)

    async def run(self) -> None:
        self.is_running = True
        logger.info(f"NavManager started (tick rate: {self.TICK_RATE_HZ}Hz)")

        try:
            while self.is_running:
                self._tick()
                await asyncio.sleep(1.0 / self.TICK_RATE_HZ)
        finally:
            self.z_session.close()
            logger.info("NavManager stopped")

    def _tick(self) -> None:
        if self.executor.state == NavigationState.ARRIVED_SEGMENT:
            self.executor.continue_to_next()

        vel_cmd, status = self.executor.update(self.pose)

        if self.executor.state == NavigationState.FOLLOWING:
            self._publish_velocity(vel_cmd)
            self._needs_final_stop = True
        elif self._needs_final_stop:
            self._publish_velocity(vel_cmd)
            self._needs_final_stop = False

        if status is not None:
            self._publish_status(status)

    def _publish_velocity(self, cmd: MovementCommand) -> None:
        self.z_pub_vel.put(cmd.model_dump_json())

    def _publish_status(self, status: NavigationStatus) -> None:
        self.z_pub_nav_status.put(status.model_dump_json())

    def _publish_planned_path(self, path: PlannedPath) -> None:
        self.z_pub_planned_path.put(path.model_dump_json())


def cli() -> None:
    nav = NavManager()
    asyncio.run(nav.run())


if __name__ == "__main__":
    cli()

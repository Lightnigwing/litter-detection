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
    quaternion_to_yaw,
)
from interfaces.robot import OdometryState
from nav.config import NavConfig
from nav.path_planner import PathPlannerModule
from nav.path_executor import PathExecutor


# Loop rate — implementation detail, deliberately not in NavConfig.
_TICK_RATE_HZ: float = 15.0


class NavManager:
    """Zenoh I/O layer for navigation.

    Orchestrates PathPlannerModule and PathExecutor, manages the shared
    Zenoh session, and publishes MovementCommands to the robot.
    """

    def __init__(self, config: NavConfig | None = None) -> None:
        self.config = config or NavConfig()
        self.settings = Settings()
        self.z_session = zenoh.open(self.settings.zenoh_config)

        self.planner = PathPlannerModule(self.config)
        self.executor = PathExecutor(self.config)

        # Publishers
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

        # Subscribers
        self.z_session.declare_subscriber(
            key_expr=self.settings.topics.nav.request,
            handler=self._on_request,
        )
        # Pose from the localization stack (same topic the VDA5050 bridge
        # subscribes to via LivePositionProvider — single source of truth).
        self.z_session.declare_subscriber(
            key_expr=self.settings.topics.localization.pose,
            handler=self._on_pose,
        )

        # State
        self.pose: Pose2D = Pose2D(x=0.0, y=0.5, theta=0.0)
        self.is_running: bool = False
        self._needs_final_stop: bool = False

    # --- Zenoh callbacks ---

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
        return Pose2D(x=odom.x, y=odom.y, theta=quaternion_to_yaw(qx, qy, qz, qw))

    # --- Tick loop ---

    async def run(self) -> None:
        self.is_running = True
        logger.info(f"NavManager started (tick rate: {_TICK_RATE_HZ}Hz)")

        try:
            while self.is_running:
                self._tick()
                await asyncio.sleep(1.0 / _TICK_RATE_HZ)
        finally:
            self.z_session.close()
            logger.info("NavManager stopped")

    def _tick(self) -> None:
        # Auto-continue through segment boundaries
        if self.executor.state == NavigationState.ARRIVED_SEGMENT:
            self.executor.continue_to_next()

        vel_cmd, status = self.executor.update(self.pose)

        # Publish velocity while actively driving (FOLLOWING) and during
        # BLOCKED recovery (the executor drives the dog back to the last
        # waypoint — needs commands going out, not silence). Send one final
        # stop on arrival, then go quiet.
        if self.executor.state in (
            NavigationState.FOLLOWING, NavigationState.BLOCKED
        ):
            self._publish_velocity(vel_cmd)
            self._needs_final_stop = True
        elif self._needs_final_stop:
            self._publish_velocity(vel_cmd)
            self._needs_final_stop = False

        if status is not None:
            if status.state == NavigationState.BLOCKED:
                self._log_blocked(self.pose)
            self._publish_status(status)

    def _log_blocked(self, pose: Pose2D) -> None:
        """Best-effort: log where the dog got stuck for the operator."""
        target = self.executor.current_target_pose
        if target is None:
            logger.warning(
                "BLOCKED at pose ({:.2f}, {:.2f}) — no active waypoint.",
                pose.x, pose.y,
            )
            return
        logger.warning(
            "BLOCKED at pose ({:.2f}, {:.2f}) heading to ({:.2f}, {:.2f}).",
            pose.x, pose.y, target.x, target.y,
        )

    # --- Publishing ---

    def _publish_velocity(self, cmd: MovementCommand) -> None:
        self.z_pub_vel.put(cmd.model_dump_json())

    def _publish_status(self, status: NavigationStatus) -> None:
        self.z_pub_nav_status.put(status.model_dump_json())

    def _publish_planned_path(self, path: PlannedPath) -> None:
        self.z_pub_planned_path.put(path.model_dump_json())


def cli() -> None:
    nav = NavManager()
    asyncio.run(nav.run())


def nav_demo() -> None:
    """Start NavManager and publish a multi-segment NavigationRequest.

    Demo route:
    1. Drive forward 3.5 m (pass-through, no stop)
    2. Turn right, drive 2 m (pass-through, no stop)
    3. Drive back 3.5 m to final position, stop and face back
    """
    x_max = 3.9
    y_max = 3.4
    nav = NavManager()
    topics = nav.settings.topics
    sample_request = NavigationRequest(
        request_id="demo-001",
        segments=[
            NavigationSegment(
                target=Pose2D(x=0, y=y_max, theta=math.pi / 2),
                max_speed=0.4,
                must_stop=False,
                allowed_deviation=0.2,
            ),
            NavigationSegment(
                target=Pose2D(x=2, y=y_max, theta=math.pi),
                max_speed=0.4,
                must_stop=False,
                allowed_deviation=0.2,
            ),
            NavigationSegment(
                target=Pose2D(x=x_max, y=y_max, theta=math.pi),
                max_speed=0.4,
                must_stop=False,
                orientation_at_target=math.pi,
            ),
            NavigationSegment(
                target=Pose2D(x=x_max, y=1.5, theta=math.pi),
                max_speed=0.4,
                must_stop=False,
                orientation_at_target=math.pi,
            ),
            NavigationSegment(
                target=Pose2D(x=2, y=0, theta=math.pi),
                max_speed=0.4,
                must_stop=False,
                orientation_at_target=math.pi,
            ),
            NavigationSegment(
                target=Pose2D(x=0, y=0, theta=math.pi),
                max_speed=0.4,
                must_stop=True,
                orientation_at_target=math.pi,
            ),

        ],
    )
    """
    sample_request = NavigationRequest(
        request_id="demo-001",
        segments=[
            NavigationSegment(
                target=Pose2D(x=0, y=0, theta=0),
                max_speed=0.4,
                must_stop=True,
                allowed_deviation=0.2,
            )
        ]
    )
    """


    async def _run() -> None:
        logger.info("NavDemo: publishing multi-segment request in 2s")
        for i, seg in enumerate(sample_request.segments):
            t = seg.target
            logger.info(
                f"  Segment {i}: ({t.x:.1f}, {t.y:.1f}) θ={math.degrees(t.theta):.1f}° stop={seg.must_stop}"
            )
        await asyncio.sleep(2.0)

        nav.z_session.put(
            topics.nav.request,
            sample_request.model_dump_json(),
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )
        logger.info("NavDemo: request published, navigation is running")
        await nav.run()

    asyncio.run(_run())


if __name__ == "__main__":
    cli()

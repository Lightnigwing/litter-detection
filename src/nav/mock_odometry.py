"""Mock odometry publisher for laptop-only testing without a real Go2.

Subscribes to MovementCommand on the motion topic, integrates a simple
forward-kinematics pose estimate, and publishes OdometryState back to
the system_state.odometry topic. The NavManager consumes these poses
and progresses through its state machine as if a real robot was driving.

Replace with the real robodog bridge once hardware is connected.
"""
from __future__ import annotations

import asyncio
import math
import time

import zenoh
from loguru import logger

from interfaces.motion import MovementCommand
from interfaces.robot import OdometryState
from robodog import Settings


PUBLISH_RATE_HZ = 30.0


def _yaw_to_quaternion(yaw: float) -> list[float]:
    """[qx, qy, qz, qw] for a rotation about z-axis."""
    return [0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0)]


class MockOdometry:
    def __init__(self) -> None:
        self.settings = Settings()
        self.session = zenoh.open(self.settings.zenoh_config)

        self.pose_x: float = 0.0
        self.pose_y: float = 0.5
        self.pose_theta: float = 0.0

        self.last_cmd: MovementCommand = MovementCommand()
        self.last_update: float = time.monotonic()

        self.pub = self.session.declare_publisher(
            key_expr=self.settings.topics.system_state.odometry,
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )
        self.session.declare_subscriber(
            key_expr=self.settings.topics.command.motion.move,
            handler=self._on_cmd,
        )

    def _on_cmd(self, sample: zenoh.Sample) -> None:
        try:
            self.last_cmd = MovementCommand.model_validate_json(bytes(sample.payload))
        except Exception:
            logger.opt(exception=True).debug("MockOdom: bad MovementCommand payload")

    def _step(self, dt: float) -> None:
        cmd = self.last_cmd
        cos_t = math.cos(self.pose_theta)
        sin_t = math.sin(self.pose_theta)
        self.pose_x += (cmd.x * cos_t - cmd.y * sin_t) * dt
        self.pose_y += (cmd.x * sin_t + cmd.y * cos_t) * dt
        self.pose_theta += math.radians(cmd.z_deg) * dt

    def _publish(self) -> None:
        odom = OdometryState(
            x=self.pose_x,
            y=self.pose_y,
            z=0.0,
            quaternion=_yaw_to_quaternion(self.pose_theta),
        )
        self.pub.put(odom.model_dump_json())

    async def run(self) -> None:
        logger.info(f"MockOdometry started ({PUBLISH_RATE_HZ}Hz)")
        try:
            while True:
                now = time.monotonic()
                dt = now - self.last_update
                self.last_update = now
                self._step(dt)
                self._publish()
                await asyncio.sleep(1.0 / PUBLISH_RATE_HZ)
        finally:
            self.session.close()
            logger.info("MockOdometry stopped")


def cli() -> None:
    asyncio.run(MockOdometry().run())


if __name__ == "__main__":
    cli()

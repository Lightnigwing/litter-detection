"""Go2Bridge — Zenoh orchestration layer for the Go2 robot.

Owns the Zenoh session and controller lifecycles, wires up Zenoh publishing
from controller callbacks, and routes incoming Zenoh commands to the controller.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Self

import zenoh
from loguru import logger
from pydantic import BaseModel, ValidationError

from interfaces.motion import ActionCommand, ActionType, MovementCommand, TiltBody
from robodog.robodog_control.robo_dog_controller import RoboDogController
from robodog.settings import Settings

if TYPE_CHECKING:
    from robodog.publishers.go2_camera_publisher import (
        Go2CameraPublisher,
    )
    from robodog.publishers.lidar_publisher import (
        LidarPublisher,
    )


class Go2Bridge:
    """Single entry-point that connects a Go2 robot to a Zenoh network.

    Owns the single Zenoh session shared by all publishers. Camera and lidar
    publishers receive pre-declared ``zenoh.Publisher`` handles rather than
    opening their own sessions.

    Usage::

        settings = Settings()
        async with Go2Bridge(settings) as bridge:
            await bridge.run()
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._config = settings.config
        self._controller = RoboDogController(self._config)
        self._z_session: zenoh.Session | None = None
        self._z_publishers: list[zenoh.Publisher] = []
        self._z_subscribers: list[zenoh.Subscriber] = []
        self._stop_event = asyncio.Event()

        self._camera_publisher: Go2CameraPublisher | None = None
        self._lidar_publisher: LidarPublisher | None = None

    @property
    def controller(self) -> RoboDogController:
        return self._controller

    # -- Lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> Self:
        self._z_session = zenoh.open(self._settings.zenoh_config)
        self._loop = asyncio.get_running_loop()

        # Register Zenoh publishing callbacks (before connect so subscriptions fire)
        self._setup_publishing()

        # Connect to robot and initialize
        await self._robot_setup()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any | None,
    ) -> None:
        if self._camera_publisher:
            self._camera_publisher.stop()
        if self._lidar_publisher:
            self._lidar_publisher.stop()
        await self._controller.disconnect()

        for sub in self._z_subscribers:
            sub.undeclare()
        self._z_subscribers.clear()

        for pub in self._z_publishers:
            pub.undeclare()
        self._z_publishers.clear()

        if self._z_session:
            self._z_session.close()
            self._z_session = None

    async def run(self) -> None:
        """Subscribe to command topics and block until stopped."""
        assert self._z_session is not None
        topics = self._settings.topics.command

        self._z_subscribers.append(
            self._z_session.declare_subscriber(
                topics.motion.move, self._on_move_command
            )
        )
        self._z_subscribers.append(
            self._z_session.declare_subscriber(
                topics.pose.action, self._on_action_command
            )
        )
        self._z_subscribers.append(
            self._z_session.declare_subscriber(
                topics.pose.tilt_body, self._on_tilt_command
            )
        )

        logger.info("Listening for commands on robodog/command/#...")
        await self._stop_event.wait()

    def stop(self) -> None:
        """Signal the bridge to stop."""
        self._stop_event.set()

    # -- Robot setup ---------------------------------------------------------

    async def _robot_setup(self) -> None:
        await self._controller.connect()
        await self._controller.ensure_normal_mode()
        await self._controller.execute_action(ActionType.stand_up)

    # -- Zenoh publishing wiring ---------------------------------------------

    def _declare_publisher(
        self,
        topic: str,
        encoding: zenoh.Encoding = zenoh.Encoding.APPLICATION_JSON,
    ) -> zenoh.Publisher:
        """Declare a publisher on the bridge's session and track it for cleanup."""
        assert self._z_session is not None
        pub = self._z_session.declare_publisher(topic, encoding=encoding)
        self._z_publishers.append(pub)
        return pub

    def _setup_publishing(self) -> None:
        """Register controller callbacks that publish parsed data to Zenoh."""
        topics = self._settings.topics
        cfg = self._config.publishers

        if cfg.publish_highstate:
            pub = self._declare_publisher(topics.system_state.highstate)
            self._controller.on_highstate(
                lambda state, p=pub: p.put(state.model_dump_json().encode())
            )

        if cfg.publish_odometry:
            pub = self._declare_publisher(topics.system_state.odometry)
            self._controller.on_odometry(
                lambda state, p=pub: p.put(state.model_dump_json().encode())
            )

        if cfg.publish_battery:
            pub = self._declare_publisher(topics.system_state.battery)
            self._controller.on_battery(
                lambda state, p=pub: p.put(state.model_dump_json().encode())
            )

        if cfg.publish_go2_camera:
            self._setup_camera_publisher()

        if cfg.publish_lidar:
            self._setup_lidar_publisher()

    # -- Camera / Lidar (separate utility classes) ---------------------------

    def _setup_camera_publisher(self) -> None:
        from robodog.publishers.go2_camera_publisher import (
            Go2CameraPublisher,
        )

        topic = self._settings.topics.sensors.go2_camera
        z_pub = self._declare_publisher(topic, encoding=zenoh.Encoding.IMAGE_JPEG)
        self._camera_publisher = Go2CameraPublisher(z_pub)
        self._controller.on_camera(self._camera_publisher.on_video_track)
        logger.info("Camera publisher on: {}", topic)

    def _setup_lidar_publisher(self) -> None:
        from robodog.publishers.lidar_publisher import (
            LidarPublisher,
        )

        topic = self._settings.topics.sensors.go2_lidar
        z_pub = self._declare_publisher(topic, encoding=zenoh.Encoding.APPLICATION_JSON)
        self._lidar_publisher = LidarPublisher(z_pub)
        self._controller.on_lidar(self._lidar_publisher.on_lidar_data)
        logger.info("Lidar publisher on: {}", topic)

    # -- Command routing (Zenoh subscriber callbacks) ------------------------

    def _on_move_command(self, sample: zenoh.Sample) -> None:
        """Handle incoming movement commands from Zenoh."""
        try:
            payload = bytes(sample.payload)
            cmd = MovementCommand.model_validate_json(payload)
            valid, latency_ms = self._is_valid_latency(cmd.timestamp)
            if not valid and not cmd.is_zero():
                logger.warning(
                    "Dropping old move command. Latency: {:.1f}ms", latency_ms
                )
                return
            asyncio.run_coroutine_threadsafe(
                self._controller.move(cmd), self._loop
            )
        except ValidationError as e:
            logger.warning("Invalid move payload: {}", e)
        except Exception as e:
            logger.error("Error handling move command: {}", e)

    def _on_action_command(self, sample: zenoh.Sample) -> None:
        """Handle incoming action commands from Zenoh."""
        try:
            payload = bytes(sample.payload)
            data = ActionCommand.model_validate_json(payload)
            valid, latency_ms = self._is_valid_latency(data.timestamp)
            if not valid:
                logger.warning("Latency too high for action: {:.1f}ms", latency_ms)
                return
            asyncio.run_coroutine_threadsafe(
                self._controller.execute_action(data.action), self._loop
            )
        except ValidationError as e:
            logger.warning("Invalid action payload: {}", e)
        except Exception as e:
            logger.error("Error handling action command: {}", e)

    def _on_tilt_command(self, sample: zenoh.Sample) -> None:
        """Handle incoming tilt body commands from Zenoh."""
        try:
            payload = bytes(sample.payload)
            data = TiltBody.model_validate_json(payload)
            asyncio.run_coroutine_threadsafe(
                self._controller.tilt_body(
                    data.pitch_deg, data.roll_deg, data.yaw_deg
                ),
                self._loop,
            )
        except ValidationError as e:
            logger.warning("Invalid tilt payload: {}", e)
        except Exception as e:
            logger.error("Error handling tilt command: {}", e)

    # -- Latency validation --------------------------------------------------

    def _is_valid_latency(self, timestamp: datetime) -> tuple[bool, float]:
        max_allowed = self._config.system.movement_max_delay_ms
        now = datetime.now(timezone.utc)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        latency_ms = (now - timestamp).total_seconds() * 1000
        return latency_ms <= max_allowed, latency_ms

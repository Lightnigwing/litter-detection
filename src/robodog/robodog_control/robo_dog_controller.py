from __future__ import annotations

import asyncio
import json
import math
import time
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal, Self
from unitree_webrtc_connect.constants import RTC_TOPIC, SPORT_CMD
from unitree_webrtc_connect.webrtc_driver import UnitreeWebRTCConnection, WebRTCConnectionMethod

from loguru import logger

from robodog.settings import RoboDogConfig

if TYPE_CHECKING:
    from types import TracebackType

from interfaces.motion import ActionType, MovementCommand
from interfaces.robot import (
    BatteryState,
    CommandedStance,
    OdometryState,
    RobotHighState,
)


# ---------------------------------------------------------------------------
# Action type -> SPORT_CMD key mapping (with optional stance change)
# ---------------------------------------------------------------------------

_ACTION_CMD: dict[ActionType, tuple[str, CommandedStance | None]] = {
    ActionType.stand_up: ("StandUp", CommandedStance.STANDING),
    ActionType.lie_down: ("StandDown", CommandedStance.LYING_DOWN),
    ActionType.sit_down: ("Sit", CommandedStance.SITTING),
    ActionType.hello: ("Hello", None),
    ActionType.dance1: ("Dance1", None),
    ActionType.wiggle_hips: ("WiggleHips", None),
    ActionType.stretch: ("Stretch", None),
    ActionType.stop_move: ("StopMove", None),
    ActionType.balance_stand: ("BalanceStand", None),
}


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.FATAL)

class RoboDogController:
    """Self-contained Go2 robot controller over WebRTC.

    Handles connection, command execution, raw data parsing, and typed
    callback dispatch.  No MQTT dependency — can be used standalone.

    Callbacks can be registered at any time. If the controller is already
    connected, the corresponding WebRTC subscription is activated immediately.

    Usage::

        robot = RoboDogController(config)
        await robot.connect()
        robot.on_highstate(my_callback)   # activates subscription immediately
        await robot.move(MovementCommand(x=0.5))
        await robot.disconnect()

    Or as an async context manager::

        async with RoboDogController(config) as robot:
            await robot.connect()
            await robot.move(MovementCommand(x=0.5))
    """

    def __init__(self, config: RoboDogConfig) -> None:
        self._config = config
        self._stance = CommandedStance.UNDEFINED

        self._conn = UnitreeWebRTCConnection(
            WebRTCConnectionMethod.LocalSTA,
            ip=self._config.system.go2_local_address,
        )
        self._is_connected = False
        self._active_subs: set[str] = set()

        # Typed callback lists
        self._highstate_callbacks: list[Callable[[RobotHighState], None]] = []
        self._battery_callbacks: list[Callable[[BatteryState], None]] = []
        self._odometry_callbacks: list[Callable[[OdometryState], None]] = []
        self._lidar_callbacks: list[Callable[[dict], None]] = []
        self._camera_callbacks: list[Callable] = []

        # Latest state cache (polling access)
        self._latest_high_state: RobotHighState | None = None
        self._latest_battery: BatteryState | None = None
        self._latest_odometry: OdometryState | None = None

    # -- Async context manager -----------------------------------------------

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool | None:
        await self.disconnect()

    # -- Connection ----------------------------------------------------------

    async def connect(self) -> None:
        """Connect to the robot and activate any pre-registered subscriptions."""
        if self._is_connected:
            return
        logger.info(
            "Connecting to robot at {}...",
            self._config.system.go2_local_address,
        )
        await self._conn.connect()
        self._is_connected = True
        logger.info("Connection successful.")

        # Activate subscriptions for callbacks registered before connect
        await self._activate_pending_subscriptions()

    async def disconnect(self) -> None:
        """Disconnect from the robot."""
        if not self._is_connected:
            return
        logger.info("Disconnecting from robot...")
        await self._conn.disconnect()
        self._is_connected = False
        self._active_subs: set[str] = set()
        logger.info("Disconnected.")

    # -- Callback registration (works before or after connect) ---------------

    def on_highstate(self, callback: Callable[[RobotHighState], None]) -> None:
        self._highstate_callbacks.append(callback)
        if self._is_connected:
            self._subscribe_highstate()

    def on_battery(self, callback: Callable[[BatteryState], None]) -> None:
        self._battery_callbacks.append(callback)
        if self._is_connected:
            self._subscribe_battery()

    def on_odometry(self, callback: Callable[[OdometryState], None]) -> None:
        self._odometry_callbacks.append(callback)
        if self._is_connected:
            self._subscribe_odometry()

    def on_lidar(self, callback: Callable[[dict], None]) -> None:
        self._lidar_callbacks.append(callback)
        if self._is_connected:
            asyncio.get_running_loop().create_task(self._subscribe_lidar())

    def on_camera(self, callback: Callable) -> None:
        self._camera_callbacks.append(callback)
        if self._is_connected:
            self._subscribe_camera()

    # -- Latest state (polling) ----------------------------------------------

    @property
    def latest_high_state(self) -> RobotHighState | None:
        return self._latest_high_state

    @property
    def latest_battery(self) -> BatteryState | None:
        return self._latest_battery

    @property
    def latest_odometry(self) -> OdometryState | None:
        return self._latest_odometry

    @property
    def stance(self) -> CommandedStance:
        return self._stance

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    # -- Movement commands ---------------------------------------------------

    async def move(self, cmd: MovementCommand) -> None:
        await self._send_command(
            api_id=SPORT_CMD["Move"],
            params={
                "x": cmd.x,
                "y": cmd.y,
                "z": round(math.radians(cmd.z_deg), 6),
            },
        )

    async def execute_action(self, action: ActionType) -> None:
        """Execute any ActionType. Stance changes update internal tracking."""
        entry = _ACTION_CMD.get(action)
        if entry is None:
            logger.warning("Unknown action: {}", action)
            return

        sport_key, new_stance = entry

        if action == ActionType.stand_up:
            await self._send_command(api_id=SPORT_CMD["StandUp"])
            await self._send_command(api_id=SPORT_CMD["BalanceStand"])
            await self.set_motion_mode("normal")
            await asyncio.sleep(self._config.system.stand_up_delay_sec)
        else:
            await self._send_command(api_id=SPORT_CMD[sport_key])

        if new_stance is not None:
            self._stance = new_stance

    async def tilt_body(
        self, pitch_deg: float, roll_deg: float, yaw_deg: float
    ) -> None:
        if not -90 <= roll_deg <= 90:
            raise ValueError("Roll must be between -90 and 90 degrees.")
        if not -90 <= pitch_deg <= 90:
            raise ValueError("Pitch must be between -90 and 90 degrees.")
        if not -180 <= yaw_deg <= 180:
            raise ValueError("Yaw must be between -180 and 180 degrees.")
        await self._send_command(
            api_id=SPORT_CMD["Euler"],
            params={
                "x": round(math.radians(roll_deg), 6),
                "y": round(math.radians(pitch_deg), 6),
                "z": round(math.radians(yaw_deg), 6),
            },
        )

    # -- Motion mode ---------------------------------------------------------

    async def get_motion_mode(self) -> str:
        """Query the robot for its current motion mode."""
        self._require_connection()
        response = await self._conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"],
            {"api_id": 1001},
        )
        try:
            data = response["data"]
            if data["header"]["status"]["code"] == 0 and data["data"]:
                return json.loads(data["data"])["name"]
        except (KeyError, json.JSONDecodeError, TypeError):
            pass
        logger.warning("Could not determine motion mode: {}", response)
        return "unknown"

    async def set_motion_mode(self, mode: Literal["normal"]) -> None:
        """Set the robot's motion mode."""
        self._require_connection()
        await self._conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["MOTION_SWITCHER"],
            {"api_id": 1002, "parameter": {"name": mode}},
        )

    async def ensure_normal_mode(self) -> None:
        """Check if the robot is in 'normal' mode and switch if necessary."""
        logger.info("Ensuring robot is in 'normal' motion mode...")
        current_mode = await self.get_motion_mode()
        logger.info("Current motion mode: {}", current_mode)
        if current_mode != "normal":
            logger.info("Mode is not 'normal', switching...")
            await self.set_motion_mode("normal")
            logger.info(
                "Waiting {}s for robot to stand up...",
                self._config.system.stand_up_delay_sec,
            )
            await asyncio.sleep(self._config.system.stand_up_delay_sec)
            current_mode = await self.get_motion_mode()
            logger.info("New motion mode: {}", current_mode)

    # -- Obstacle avoidance --------------------------------------------------

    async def set_go2_obstacle_avoidance(self, enable: bool) -> None:
        self._require_connection()
        await self._conn.datachannel.pub_sub.publish_request_new(
            RTC_TOPIC["OBSTACLES_AVOID"],
            {"api_id": 1002, "parameter": {"data": enable}},
        )
        logger.debug("Set Obstacle Avoidance to {}", enable)

    # -- Internal: connection guard ------------------------------------------

    def _require_connection(self) -> None:
        """Raise if not connected. Called before any command or query."""
        if not self._is_connected:
            raise ConnectionError(
                "Not connected to Go2. Call connect() first."
            )

    # -- Internal: send sport command ----------------------------------------

    async def _send_command(
        self,
        api_id: int,
        params: dict | None = None,
        topic: str = RTC_TOPIC["SPORT_MOD"],
    ) -> None:
        self._require_connection()
        payload: dict[str, Any] = {"api_id": api_id}

        if params:
            payload["parameter"] = params
        logger.debug("SENDING: topic='{}': {}", topic, payload)
        start_time = time.monotonic()
        
        await self._conn.datachannel.pub_sub.publish_request_new(
            topic=topic,
            options=payload,
        )

        elapsed_time = time.monotonic() - start_time
        if elapsed_time > 0.2:
            logger.debug(
                "SENT: topic='{}' completed after {} seconds", topic, elapsed_time
            )

    # -- Internal: subscription management -----------------------------------

    async def _activate_pending_subscriptions(self) -> None:
        """Activate WebRTC subscriptions for all registered callback lists."""
        if self._highstate_callbacks:
            self._subscribe_highstate()

        if self._battery_callbacks:
            self._subscribe_battery()

        if self._odometry_callbacks:
            self._subscribe_odometry()

        if self._lidar_callbacks:
            await self._subscribe_lidar()

        if self._camera_callbacks:
            self._subscribe_camera()

    def _subscribe_highstate(self) -> None:
        if "highstate" in self._active_subs:
            return
        self._conn.datachannel.pub_sub.subscribe(
            RTC_TOPIC["LF_SPORT_MOD_STATE"], self._on_raw_highstate
        )
        self._active_subs.add("highstate")
        logger.info("Highstate subscription enabled")

    def _subscribe_battery(self) -> None:
        if "battery" in self._active_subs:
            return
        self._conn.datachannel.pub_sub.subscribe(
            RTC_TOPIC["LOW_STATE"], self._on_raw_battery
        )
        self._active_subs.add("battery")
        logger.info("Battery subscription enabled")

    def _subscribe_odometry(self) -> None:
        if "odometry" in self._active_subs:
            return
        self._conn.datachannel.pub_sub.subscribe(
            RTC_TOPIC["ROBOTODOM"], self._on_raw_odometry
        )
        self._active_subs.add("odometry")
        logger.info("Odometry subscription enabled")

    async def _subscribe_lidar(self) -> None:
        if "lidar" in self._active_subs:
            return
        await self._conn.datachannel.disableTrafficSaving(True)
        self._conn.datachannel.set_decoder(
            #decoder_type=self._config.system.lidar_decoder
            decoder_type="native"
        )

        # Activate LiDAR data channel
        self._conn.datachannel.pub_sub.publish_without_callback(
            RTC_TOPIC["ULIDAR_SWITCH"], "on"
        )

        self._conn.datachannel.pub_sub.subscribe(
            RTC_TOPIC["ULIDAR_ARRAY"], self._on_raw_lidar
        )
        self._active_subs.add("lidar")
        logger.info("Lidar subscription enabled (ULIDAR_ARRAY)")

    def _subscribe_camera(self) -> None:
        if "camera" in self._active_subs:
            return
        self._conn.video.switchVideoChannel(True)
        self._conn.video.add_track_callback(self._on_raw_video_track)
        self._active_subs.add("camera")
        logger.info("Front camera video enabled")

    # -- Internal: raw data parsing ------------------------------------------

    def _on_raw_highstate(self, message: dict) -> None:
        state = RobotHighState.from_raw(message)
        if state is None:
            return
        self._latest_high_state = state
        for cb in self._highstate_callbacks:
            cb(state)

    def _on_raw_battery(self, message: dict) -> None:
        battery = BatteryState.from_raw(message)
        if battery is None:
            return
        self._latest_battery = battery
        for cb in self._battery_callbacks:
            cb(battery)

    def _on_raw_odometry(self, message: dict) -> None:
        odom = OdometryState.from_raw(message)
        if odom is None:
            return
        self._latest_odometry = odom
        for cb in self._odometry_callbacks:
            cb(odom)

    def _on_raw_lidar(self, message: dict) -> None:
        for cb in self._lidar_callbacks:
            cb(message)

    async def _on_raw_video_track(self, track: Any) -> None:
        for cb in self._camera_callbacks:
            await cb(track)

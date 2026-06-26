from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from loguru import logger
from pydantic import BaseModel, Field


class CommandedStance(StrEnum):
    UNDEFINED = "undefined"
    STANDING = "standing"
    LYING_DOWN = "lying_down"
    SITTING = "sitting"


class ConnectionStatus(BaseModel):
    """WebRTC connection state to the Go2 robot."""

    connected: bool = False
    motion_mode: str = "unknown"
    stance: CommandedStance = CommandedStance.UNDEFINED


class IMUState(BaseModel):
    quaternion: list[float] = Field(default_factory=list)
    gyroscope: list[float] = Field(default_factory=list)
    accelerometer: list[float] = Field(default_factory=list)
    rpy: list[float] = Field(default_factory=list)


class RobotHighState(BaseModel):
    """High-level robot state from the Go2 sport mode."""

    imu_state: IMUState = Field(default_factory=IMUState)
    mode: int = 0
    velocity: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    yaw_speed: float = 0.0
    position: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    body_height: float = 0.0
    foot_force: list[int] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_raw(cls, message: dict[str, Any]) -> RobotHighState | None:
        """Parse a raw WebRTC high-state message into a RobotHighState."""
        try:
            return cls(**message["data"])
        except Exception:
            logger.opt(exception=True).debug("Failed to parse high state")
            return None


class BatteryLevel(StrEnum):
    good = "good"
    low = "low"
    critical = "critical"


class BatteryState(BaseModel):
    soc: int = 0
    level: BatteryLevel = BatteryLevel.good
    voltage: float = 0.0
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_raw(cls, message: dict[str, Any]) -> BatteryState | None:
        """Parse a raw WebRTC low-state message, extracting battery info."""
        try:
            data = message["data"]
            bms = data.get("bms_state", {})
            soc = bms.get("soc", 0)
            if soc > 30:
                level = BatteryLevel.good
            elif soc > 10:
                level = BatteryLevel.low
            else:
                level = BatteryLevel.critical
            return cls(
                soc=soc,
                level=level,
                voltage=data.get("power_v", 0.0),
            )
        except Exception:
            logger.opt(exception=True).debug("Failed to parse low state / battery")
            return None


class OdometryState(BaseModel):
    """Robot pose from onboard SLAM / odometry source."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    quaternion: list[float] = Field(
        default_factory=lambda: [0.0, 0.0, 0.0, 1.0],
        description="Orientation as [qx, qy, qz, qw]",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    def from_raw(cls, message: dict[str, Any]) -> OdometryState | None:
        """Parse a raw WebRTC ROBOTODOM message (rt/utlidar/robot_pose)."""
        try:
            data = message["data"]
            stamp = data["header"]["stamp"]
            pos = data["pose"]["position"]
            ori = data["pose"]["orientation"]
            return cls(
                x=pos["x"],
                y=pos["y"],
                z=pos["z"],
                quaternion=[ori["x"], ori["y"], ori["z"], ori["w"]],
                timestamp=datetime.fromtimestamp(
                    stamp["sec"] + stamp["nanosec"] / 1e9, tz=timezone.utc
                ),
            )
        except Exception:
            logger.opt(exception=True).debug("Failed to parse odometry")
            return None

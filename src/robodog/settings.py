from __future__ import annotations

import os
from functools import cached_property
from pathlib import Path

import msgspec
import zenoh
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from interfaces.topics import Topics, TOPICS


class Base(
    msgspec.Struct,
    omit_defaults=True,
    forbid_unknown_fields=True,
    rename="kebab",
):
    pass


class System(Base):
    go2_local_address: str
    name: str = "robodog"
    stand_up_delay_sec: float = 5.0
    lidar_decoder: str = "native"
    movement_max_delay_ms: int = 200


class Zenoh(Base):
    router_endpoint: str = "tcp/127.0.0.1:7447"
    shared_memory_enabled: bool = True
    shared_memory_pool_size: int = 67108864
    shared_memory_threshold: int = 4096


class Publishers(Base):
    publish_go2_camera: bool = False
    publish_battery: bool = True
    publish_odometry: bool = True
    publish_highstate: bool = True
    publish_lidar: bool = False


class CameraStream(Base):
    width: int = 1280
    height: int = 720
    fps: int = 30


class RSZenoh(Base):
    rgb: CameraStream
    depth: CameraStream
    imu_hz: int = 250
    jpeg_quality: int = 95


class ButtonBindings(
    msgspec.Struct,
    frozen=True,
    omit_defaults=True,
    forbid_unknown_fields=True,
    rename="kebab",
):
    a: str = "hello"
    b: str = "dance1"
    x: str = "wiggle_hips"
    y: str = "stretch"
    back: str = "stand_up"
    start: str = "lie_down"
    lb: str = ""
    rb: str = ""


class NodeJoy(Base):
    activated: bool = True
    publish_rate_hz: int = 15
    deadzone: float = 0.1
    check_interval_sec: float = 1.0
    status_publish_interval: float = 1.0
    active_window_sec: float = 20.0
    move_stick_eps: float = 0.10
    move_trigger_eps: float = 0.10
    move_btn_change: bool = True
    max_speed_factor: float = 5.0
    min_speed_factor: float = 0.5
    max_tilt_angle: float = 20.0
    max_yaw_angle: float = 20.0
    button_bindings: ButtonBindings = ButtonBindings()


class NodeSensorViz(Base):
    web_port: int = 8080
    grpc_port: int = 9876
    memory_limit_gb: float = 5.0
    camera_update_rate_hz: float = 15.0

class RoboDogConfig(Base):
    system: System
    zenoh: Zenoh
    publishers: Publishers
    node_rs_zenoh: RSZenoh
    node_joy: NodeJoy
    node_sensor_viz: NodeSensorViz = msgspec.field(default_factory=NodeSensorViz)


load_dotenv(verbose=True)


def _build_zenoh_config(zenoh_settings: Zenoh) -> zenoh.Config:
    """Build a zenoh.Config programmatically from settings."""
    endpoint = os.environ.get(
        "ZENOH_ROUTER_ENDPOINT", zenoh_settings.router_endpoint
    )
    shm = zenoh_settings.shared_memory_enabled
    pool = zenoh_settings.shared_memory_pool_size
    threshold = zenoh_settings.shared_memory_threshold

    cfg = zenoh.Config()
    cfg.insert_json5("mode", '"client"')
    cfg.insert_json5("connect/endpoints", f'["{endpoint}"]')
    cfg.insert_json5("transport/shared_memory/enabled", str(shm).lower())
    if shm:
        cfg.insert_json5(
            "transport/shared_memory/transport_optimization/enabled", "true"
        )
        cfg.insert_json5(
            "transport/shared_memory/transport_optimization/pool_size",
            str(pool),
        )
        cfg.insert_json5(
            "transport/shared_memory/transport_optimization/message_size_threshold",
            str(threshold),
        )
    return cfg


class Settings(BaseSettings):
    _project_root: Path = Path(__file__).resolve().parents[2]
    config_path: Path = _project_root / "config" / "config.toml"

    @property
    def topics(self) -> Topics:
        return TOPICS

    @cached_property
    def config(self) -> RoboDogConfig:
        """Loads config from file."""
        with open(self.config_path, "rb") as f:
            return msgspec.toml.decode(f.read(), type=RoboDogConfig)

    @cached_property
    def zenoh_config(self) -> zenoh.Config:
        """Builds a Zenoh client config from settings."""
        return _build_zenoh_config(self.config.zenoh)

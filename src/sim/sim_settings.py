"""Simulation-specific configuration."""

from __future__ import annotations

from dataclasses import dataclass

# TODO: Create TOML config file for these


@dataclass
class SimConfig:
    """Settings for the MuJoCo simulation node."""

    robot_name: str = "robodog"
    start_position: tuple[float, float] = (0.0, 0.0)
    start_height: float = 0.35
    headless: bool = False

    # Physics timing
    sim_dt: float = 0.005  # 200 Hz physics
    ctrl_dt: float = 0.02  # 50 Hz policy

    # Sensor publishing rates
    odom_hz: float = 20.0
    camera_fps: float = 15.0
    lidar_fps: float = 2.0
    publish_lidar: bool = False

    # Camera rendering
    camera_width: int = 1280
    camera_height: int = 720

    # Lidar
    lidar_depth_fov: float = 160.0
    lidar_voxel_size: float = 0.05
    lidar_max_range: float = 3.0
    lidar_min_range: float = 0.2
    lidar_max_height: float = 1.2

    # Policy
    action_scale: float = 0.5

    @property
    def n_substeps(self) -> int:
        return round(self.ctrl_dt / self.sim_dt)

    @property
    def data_dir(self) -> str:
        """Path to the sim data directory (relative to package)."""
        from pathlib import Path

        return str(Path(__file__).parent / "data")

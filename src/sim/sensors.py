"""Simulated sensor reading functions for the MuJoCo simulation."""

from __future__ import annotations

import io
import json
import time
from math import radians, tan

import mujoco
import numpy as np
from PIL import Image

from interfaces.robot import OdometryState

from sim.sim_settings import SimConfig


def read_odometry(data: mujoco.MjData) -> OdometryState:
    """Read ground-truth odometry from MuJoCo state.

    Converts MuJoCo quaternion ``[w, x, y, z]`` (``qpos[3:7]``) to the
    project convention ``[x, y, z, w]``.
    """
    return OdometryState(
        x=float(data.qpos[0]),
        y=float(data.qpos[1]),
        z=float(data.qpos[2]),
        quaternion=[
            float(data.qpos[4]),  # qx
            float(data.qpos[5]),  # qy
            float(data.qpos[6]),  # qz
            float(data.qpos[3]),  # qw
        ],
    )


def render_camera(
    renderer: mujoco.Renderer,
    data: mujoco.MjData,
    camera_name: str = "head_camera",
) -> bytes:
    """Render an RGB image and encode it as JPEG bytes."""
    renderer.update_scene(data, camera=camera_name)
    pixels = renderer.render()  # (H, W, 3) uint8

    img = Image.fromarray(pixels)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# TODO: Lidar pointcloud is way different to Go2 pointcloud, needs to be updated to a proper voxelmap
def render_lidar(
    model: mujoco.MjModel,
    data: mujoco.MjData,
    depth_renderer: mujoco.Renderer,
    config: SimConfig,
) -> str:
    """Render depth from 3 cameras, back-project to point cloud, return JSON.

    Returns a JSON string matching the format used by the real lidar publisher:
    ``{"points": [[x, y, z], ...], "ts": <unix_timestamp>}``
    """
    camera_names = ("lidar_front_camera", "lidar_left_camera", "lidar_right_camera")
    all_points: list[np.ndarray] = []

    for cam_name in camera_names:
        cam_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, cam_name)
        depth_renderer.update_scene(data, camera=cam_name)
        depth_img = depth_renderer.render()  # (H, W) float32

        cam_pos = data.cam_xpos[cam_id].copy()
        cam_mat = data.cam_xmat[cam_id].reshape(3, 3).copy()

        pts = _depth_to_world_points(
            depth_img,
            cam_pos,
            cam_mat,
            fov_degrees=config.lidar_depth_fov,
            max_range=config.lidar_max_range,
            min_range=config.lidar_min_range,
            max_height=config.lidar_max_height,
        )
        if len(pts) > 0:
            all_points.append(pts)

    if all_points:
        combined = np.vstack(all_points)
        combined = _voxel_downsample(combined, config.lidar_voxel_size)
    else:
        combined = np.zeros((0, 3), dtype=np.float32)

    return json.dumps(
        {
            "points": combined.tolist(),
            "ts": time.time(),
        }
    )


def _depth_to_world_points(
    depth_image: np.ndarray,
    camera_pos: np.ndarray,
    camera_mat: np.ndarray,
    fov_degrees: float = 160.0,
    max_range: float = 3.0,
    min_range: float = 0.2,
    max_height: float = 1.2,
) -> np.ndarray:
    """Back-project a depth image to world-frame 3D points using numpy."""
    h, w = depth_image.shape
    fovy = radians(fov_degrees)
    f = h / (2.0 * tan(fovy / 2.0))
    cx, cy = w / 2.0, h / 2.0

    # Build pixel coordinate grids.
    u, v = np.meshgrid(np.arange(w), np.arange(h))
    z = depth_image.astype(np.float32)

    # Filter invalid depths.
    valid = (z > 0) & (z < max_range)
    u = u[valid].astype(np.float32)
    v = v[valid].astype(np.float32)
    z = z[valid]

    # Back-project to camera frame.
    x_cam = (u - cx) * z / f
    y_cam = (v - cy) * z / f
    z_cam = z

    # MuJoCo camera convention: flip y and z.
    pts_cam = np.stack([x_cam, -y_cam, -z_cam], axis=-1)

    # Filter by range and height in camera frame.
    mask = (
        (np.abs(pts_cam[:, 0]) <= max_range)
        & (np.abs(pts_cam[:, 1]) <= max_height)
        & (np.abs(pts_cam[:, 2]) >= min_range)
        & (np.abs(pts_cam[:, 2]) <= max_range)
    )
    pts_cam = pts_cam[mask]

    if len(pts_cam) == 0:
        return pts_cam

    # Transform to world frame.
    return (camera_mat @ pts_cam.T).T + camera_pos


def _voxel_downsample(points: np.ndarray, voxel_size: float) -> np.ndarray:
    """Simple voxel downsampling using numpy — no open3d dependency."""
    if len(points) == 0:
        return points
    quantized = np.round(points / voxel_size).astype(np.int32)
    _, unique_idx = np.unique(quantized, axis=0, return_index=True)
    return points[unique_idx]

from __future__ import annotations

import msgspec


class MotionTopics(msgspec.Struct, frozen=True):
    move: str


class PoseTopics(msgspec.Struct, frozen=True):
    action: str
    tilt_body: str


class CommandTopics(msgspec.Struct, frozen=True):
    motion: MotionTopics
    pose: PoseTopics


class RealSenseTopics(msgspec.Struct, frozen=True):
    rgb_img: str
    depth_img: str
    depth_data: str
    imu: str
    intrinsics: str


class SensorTopics(msgspec.Struct, frozen=True):
    go2_camera: str
    go2_lidar: str
    realsense: RealSenseTopics


class SystemStateTopics(msgspec.Struct, frozen=True):
    highstate: str
    odometry: str
    battery: str


class NavTopics(msgspec.Struct, frozen=True):
    status: str
    request: str
    planned_path: str


class NodeTopics(msgspec.Struct, frozen=True):
    joy: str
    controller_status: str


class Topics(msgspec.Struct, frozen=True):
    command: CommandTopics
    sensors: SensorTopics
    system_state: SystemStateTopics
    nav: NavTopics
    nodes: NodeTopics


TOPICS = Topics(
    command=CommandTopics(
        motion=MotionTopics(move="robodog/command/motion/move"),
        pose=PoseTopics(
            action="robodog/command/pose/action",
            tilt_body="robodog/command/pose/tilt_body",
        ),
    ),
    sensors=SensorTopics(
        go2_camera="robodog/sensors/go2_camera",
        go2_lidar="robodog/sensors/go2_lidar",
        realsense=RealSenseTopics(
            rgb_img="robodog/sensors/realsense/rgb_img",
            depth_img="robodog/sensors/realsense/depth_img",
            depth_data="robodog/sensors/realsense/depth_data",
            imu="robodog/sensors/realsense/imu",
            intrinsics="robodog/sensors/realsense/intrinsics",
        ),
    ),
    system_state=SystemStateTopics(
        highstate="robodog/system_state/highstate",
        odometry="robodog/system_state/odometry",
        battery="robodog/system_state/battery",
    ),
    nav=NavTopics(
        status="nav/status",
        request="nav/request",
        planned_path="nav/planned_path",
    ),
    nodes=NodeTopics(
        joy="nodes/joy",
        controller_status="nodes/controller_status",
    ),
)

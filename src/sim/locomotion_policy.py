"""ONNX locomotion policy for the Unitree Go1/Go2 quadruped."""

from __future__ import annotations

from typing import cast

import mujoco
import numpy as np
import onnxruntime as ort


class LocomotionPolicy:
    """Wraps a pre-trained ONNX locomotion policy.

    The policy maps a 48-element observation vector to 12 joint position
    targets.  It was trained on Go1 kinematics but works for Go2 navigation
    testing because both robots share the same 12-DOF leg layout.

    Observation vector layout (48 floats):
        [0:3]   body linear velocity (local frame)
        [3:6]   angular velocity (gyroscope)
        [6:9]   gravity direction in body frame
        [9:21]  joint angles relative to home pose
        [21:33] joint angular velocities
        [33:45] previous policy output
        [45:48] command [forward_vel, lateral_vel, yaw_rate]
    """

    def __init__(
        self,
        policy_path: str,
        default_angles: np.ndarray,
        action_scale: float = 0.5,
    ) -> None:
        self._session = ort.InferenceSession(
            policy_path, providers=ort.get_available_providers()
        )
        self._output_name = self._session.get_outputs()[0].name
        self._default_angles = default_angles.astype(np.float32)
        self._action_scale = action_scale
        self._last_action = np.zeros(len(default_angles), dtype=np.float32)

        # Cache IMU site ID (set on first step).
        self._imu_site_id: int | None = None

    def step(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        command: np.ndarray,
    ) -> None:
        """Run one policy inference step and apply joint targets to ``data.ctrl``."""
        # Resolve IMU site ID once (the reference uses data.site_xmat, not body xmat).
        if self._imu_site_id is None:
            self._imu_site_id = model.site("imu").id

        obs = self._build_observation(model, data, command)

        output = cast(
            np.ndarray,
            self._session.run([self._output_name], {"obs": obs.reshape(1, -1)})[0],
        )
        prediction = output[0].astype(np.float32)

        self._last_action = prediction.copy()
        data.ctrl[:] = prediction * self._action_scale + self._default_angles

    def _build_observation(
        self,
        model: mujoco.MjModel,
        data: mujoco.MjData,
        command: np.ndarray,
    ) -> np.ndarray:
        linvel = data.sensor("local_linvel").data.astype(np.float32)
        gyro = data.sensor("gyro").data.astype(np.float32)

        # Gravity direction in body frame (using IMU site transform).
        assert self._imu_site_id is not None
        imu_xmat = data.site_xmat[self._imu_site_id].reshape(3, 3)
        gravity = (imu_xmat.T @ np.array([0.0, 0.0, -1.0])).astype(np.float32)

        joint_angles = (data.qpos[7:] - self._default_angles).astype(np.float32)
        joint_vels = data.qvel[6:].astype(np.float32)

        return np.concatenate(
            [
                linvel,  # 3
                gyro,  # 3
                gravity,  # 3
                joint_angles,  # 12
                joint_vels,  # 12
                self._last_action,  # 12
                command.astype(np.float32),  # 3
            ]
        )

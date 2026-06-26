"""SimBridge — MuJoCo simulation node with Zenoh integration and mjviser visualization."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Lock

import mujoco
import numpy as np
import zenoh
from loguru import logger
from pydantic import ValidationError

from interfaces.motion import MovementCommand
from interfaces.topics import TOPICS
from sim.locomotion_policy import LocomotionPolicy
from sim.model_loader import load_model
from sim.sensors import read_odometry, render_camera, render_lidar
from sim.sim_settings import SimConfig

from robodog import Settings


class SimBridge:
    """Drop-in simulation replacement for Go2Bridge.

    Subscribes to the same movement command topic and publishes simulated
    sensor data (odometry, camera, optional lidar) on the same Zenoh topics.

    The simulation loop is driven by mjviser's ``Viewer.run()`` (blocking,
    main thread) with a custom ``step_fn``.  In headless mode, a tight
    loop with real-time pacing is used instead.
    """

    def __init__(self, config: SimConfig) -> None:
        self._config = config
        self._topics = TOPICS

        # Shared command buffer written by Zenoh subscriber, read by step_fn.
        self._command = np.zeros(3, dtype=np.float32)  # [fwd, lat, yaw_rad]
        self._command_lock = Lock()

        # Initialised in run().
        self._model: mujoco.MjModel | None = None
        self._data: mujoco.MjData | None = None
        self._policy: LocomotionPolicy | None = None
        self._rgb_renderer: mujoco.Renderer | None = None
        self._depth_renderer: mujoco.Renderer | None = None

        # Zenoh handles.
        self._session: zenoh.Session | None = None
        self._odom_pub: zenoh.Publisher | None = None
        self._camera_pub: zenoh.Publisher | None = None
        self._lidar_pub: zenoh.Publisher | None = None
        self._subscribers: list[zenoh.Subscriber] = []

        # Timing state for step_fn.
        self._substep_counter = 0
        self._last_camera_time = 0.0
        self._last_lidar_time = 0.0

    def run(self) -> None:
        """Initialise and start the simulation loop (blocking)."""
        self._setup()

        if self._config.headless:
            self._run_headless()
        else:
            self._run_with_viewer()

        self._teardown()

    # -- Setup / teardown ------------------------------------------------------

    def _setup(self) -> None:
        config = self._config

        # Load MuJoCo model.
        self._model, self._data, default_angles = load_model(config)

        # Load locomotion policy.
        policy_path = str(Path(config.data_dir) / "unitree_go1_policy.onnx")
        self._policy = LocomotionPolicy(
            policy_path, default_angles, action_scale=config.action_scale
        )

        # Offscreen renderers for camera and optional lidar (separate from mjviser).
        self._rgb_renderer = mujoco.Renderer(
            self._model, height=config.camera_height, width=config.camera_width
        )
        if config.publish_lidar:
            self._depth_renderer = mujoco.Renderer(
                self._model, height=config.camera_height, width=config.camera_width
            )
            self._depth_renderer.enable_depth_rendering()

        self._session = zenoh.open(Settings().zenoh_config)

        topics = self._topics
        self._odom_pub = self._session.declare_publisher(
            topics.system_state.odometry,
            encoding=zenoh.Encoding.APPLICATION_JSON,
        )
        self._camera_pub = self._session.declare_publisher(
            topics.sensors.go2_camera,
            encoding=zenoh.Encoding.IMAGE_JPEG,
        )
        if config.publish_lidar:
            self._lidar_pub = self._session.declare_publisher(
                topics.sensors.go2_lidar,
                encoding=zenoh.Encoding.APPLICATION_JSON,
            )

        # Subscribe to movement commands.
        self._subscribers.append(
            self._session.declare_subscriber(
                topics.command.motion.move,
                self._on_move_command,
            )
        )

        logger.info(
            "SimBridge ready — subscribed to {}, publishing odom/camera{}",
            topics.command.motion.move,
            "/lidar" if config.publish_lidar else "",
        )

    def _teardown(self) -> None:
        for sub in self._subscribers:
            sub.undeclare()
        self._subscribers.clear()

        for pub in (self._odom_pub, self._camera_pub, self._lidar_pub):
            if pub is not None:
                pub.undeclare()

        if self._session is not None:
            self._session.close()
            self._session = None

        logger.info("SimBridge shut down")

    # -- Simulation loops ------------------------------------------------------

    def _run_with_viewer(self) -> None:
        """Run with mjviser web UI (blocking)."""
        from mjviser import Viewer

        assert self._model is not None and self._data is not None
        viewer = Viewer(
            model=self._model,
            data=self._data,
            step_fn=self._step_fn,
        )
        logger.info("Starting mjviser viewer — open http://localhost:8080")
        viewer.run()  # Blocks until Ctrl+C.

    def _run_headless(self) -> None:
        """Run without visualisation, real-time paced."""
        assert self._model is not None and self._data is not None
        logger.info("Starting headless simulation loop")

        try:
            while True:
                step_start = time.perf_counter()
                self._step_fn(self._model, self._data)

                elapsed = time.perf_counter() - step_start
                sleep_t = self._config.sim_dt - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)
        except KeyboardInterrupt:
            logger.info("Headless simulation interrupted")

    # -- Step function (called every physics step) -----------------------------

    def _step_fn(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        """Custom step function passed to mjviser Viewer.

        Called once per physics timestep.  Runs the policy every N substeps,
        then calls ``mj_step``.  Publishes sensor data at configured rates.
        """
        n_sub = self._config.n_substeps

        # Run policy at control frequency (every N substeps).
        if self._substep_counter % n_sub == 0:
            with self._command_lock:
                cmd = self._command.copy()
            assert self._policy is not None
            self._policy.step(model, data, cmd)
            self._publish_odometry(data)

        mujoco.mj_step(model, data)
        self._substep_counter += 1

        # Camera and optional lidar at lower rates.
        now = time.perf_counter()
        if now - self._last_camera_time >= 1.0 / self._config.camera_fps:
            self._publish_camera(data)
            self._last_camera_time = now

        if self._config.publish_lidar and (
            now - self._last_lidar_time >= 1.0 / self._config.lidar_fps
        ):
            self._publish_lidar(model, data)
            self._last_lidar_time = now

    # -- Zenoh publishing ------------------------------------------------------

    def _publish_odometry(self, data: mujoco.MjData) -> None:
        odom = read_odometry(data)
        assert self._odom_pub is not None
        self._odom_pub.put(odom.model_dump_json().encode())

    def _publish_camera(self, data: mujoco.MjData) -> None:
        assert self._rgb_renderer is not None and self._camera_pub is not None
        jpeg_bytes = render_camera(self._rgb_renderer, data)
        self._camera_pub.put(jpeg_bytes)

    def _publish_lidar(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        assert self._depth_renderer is not None and self._lidar_pub is not None
        lidar_json = render_lidar(model, data, self._depth_renderer, self._config)
        self._lidar_pub.put(lidar_json.encode())

    # -- Zenoh command subscriber callback -------------------------------------

    def _on_move_command(self, sample: zenoh.Sample) -> None:
        """Parse a MovementCommand and update the shared command buffer."""
        try:
            payload = bytes(sample.payload)
            cmd = MovementCommand.model_validate_json(payload)

            with self._command_lock:
                self._command[0] = cmd.x  # forward (m/s)
                self._command[1] = cmd.y  # lateral (m/s)
                self._command[2] = np.radians(cmd.z_deg)  # yaw (rad/s)

        except ValidationError as e:
            logger.warning("Invalid move payload: {}", e)
        except Exception as e:
            logger.error("Error handling move command: {}", e)

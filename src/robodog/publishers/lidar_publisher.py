"""Publishes Go2 lidar point-cloud data to Zenoh."""

from __future__ import annotations

import json

import numpy as np
import zenoh
from loguru import logger


class _NumpyEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


class LidarPublisher:
    """Receives raw lidar dicts from the controller and forwards them to Zenoh.

    The lidar data arrives as a synchronous callback from the WebRTC data
    channel, so this publisher is fully synchronous — just serialize and put.
    """

    def __init__(self, z_publisher: zenoh.Publisher) -> None:
        self._z_pub = z_publisher

    def on_lidar_data(self, message: dict) -> None:
        """Controller callback — serialize and publish to Zenoh."""
        json_msg = json.dumps(message, cls=_NumpyEncoder)
        self._z_pub.put(json_msg)

    def stop(self) -> None:
        pass  # No owned resources — session/publisher managed by Go2Bridge

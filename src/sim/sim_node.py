"""CLI entry point for the MuJoCo simulation node."""

from __future__ import annotations

import argparse

from loguru import logger

from sim.sim_bridge import SimBridge
from sim.sim_settings import SimConfig


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="MuJoCo simulation node for the Unitree Go1/Go2 robot."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without mjviser visualisation (for CI / testing).",
    )
    parser.add_argument(
        "--publish-lidar",
        action="store_true",
        help="Enable publishing simulated LiDAR data on Zenoh.",
    )
    args = parser.parse_args()

    config = SimConfig(headless=args.headless, publish_lidar=args.publish_lidar)

    logger.info(
        f"Starting sim node (headless={config.headless}, publish_lidar={config.publish_lidar})"
    )
    bridge = SimBridge(config)
    bridge.run()


if __name__ == "__main__":
    cli()

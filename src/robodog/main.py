import asyncio
import logging
import os
import sys

from loguru import logger

from robodog.go2_bridge import Go2Bridge
from robodog.settings import Settings


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO)


async def main() -> None:
    setup_logging()
    logger.info("--- Starting Robodog ---")

    settings = Settings()

    try:
        async with Go2Bridge(settings) as go2_bridge:
            await go2_bridge.run()
    except Exception as e:
        logger.error("Fatal error: {}", e)
    finally:
        logger.info("Shutting down.")


def cli() -> None:
    if sys.platform.lower() == "win32" or os.name.lower() == "nt":
        from asyncio import WindowsSelectorEventLoopPolicy, set_event_loop_policy

        set_event_loop_policy(WindowsSelectorEventLoopPolicy())
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Program interrupted by user (Ctrl+C).")


if __name__ == "__main__":
    cli()

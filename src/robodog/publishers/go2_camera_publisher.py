"""Publishes Go2 front-camera frames to Zenoh as raw JPEG bytes."""

from __future__ import annotations

import asyncio
import logging

import cv2
import zenoh
from aiortc import MediaStreamTrack
from av.frame import Frame
from loguru import logger

# Suppress "No accelerated colorspace conversion found" warnings from libswscale.
# On aarch64 (Jetson) there is no SIMD-optimized yuv420p→bgr24 converter;
# the fallback works fine, it's just slower.
logging.getLogger("libav").setLevel(logging.ERROR)


class Go2CameraPublisher:
    """Receives a WebRTC video track, encodes JPEG frames, publishes to Zenoh.

    The camera track is inherently async (``await track.recv()``), so this
    publisher uses an asyncio event-loop to bridge frame reception with
    CPU-bound JPEG encoding (offloaded to a thread) and Zenoh publishing.
    """

    def __init__(self, z_publisher: zenoh.Publisher) -> None:
        self._z_pub = z_publisher
        self._is_running = False
        self._latest_frame: Frame | None = None
        self._new_frame_event = asyncio.Event()

    async def on_video_track(self, track: MediaStreamTrack) -> None:
        """Controller callback — starts the recv + publish loops."""
        self._is_running = True
        asyncio.create_task(self._publish_loop())
        try:
            while self._is_running:
                frame = await track.recv()
                self._latest_frame = frame
                self._new_frame_event.set()
        except asyncio.CancelledError:
            logger.info("Camera video track cancelled")
        except Exception as e:
            logger.error("Camera video track error: {}", e)

    def stop(self) -> None:
        self._is_running = False
        self._new_frame_event.set()

    async def _publish_loop(self) -> None:
        while self._is_running:
            await self._new_frame_event.wait()
            self._new_frame_event.clear()
            frame = self._latest_frame
            if frame is None:
                continue
            try:
                jpeg_bytes: bytes = await asyncio.to_thread(
                    self._encode_jpeg, frame
                )
                self._z_pub.put(jpeg_bytes)
            except Exception as e:
                logger.error("Error processing camera frame: {}", e)

    @staticmethod
    def _encode_jpeg(frame: Frame) -> bytes:
        img_np = frame.to_ndarray(format="bgr24")  # type: ignore
        _, jpeg = cv2.imencode(".jpg", img_np, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        return jpeg.tobytes()

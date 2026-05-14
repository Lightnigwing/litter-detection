from asyncio.log import logger

from config import Settings
import zenoh
import cv2
import numpy as np
import pyrealsense2 as rs
import time

IMUHZ = 250
JPEGQUALITY = 95

WIDTH_RGB = 1280
HEIGHT_RGB = 720
FPS_RGB = 30

WIDTH_DEPTH = 1280
HEIGHT_DEPTH = 720
FPS_DEPTH = 30


def main():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    z = zenoh.open(conf)

    # Zenoh topics
    rs_topic_rgb_img = settings.topic_frame
    #rs_topic_depth_img = sensors.realsense.depth_img
    #rs_topic_depth_data = sensors.realsense.depth_data
    #rs_topic_intrinsics = sensors.realsense.intrinsics

    z_pub_rgb = z.declare_publisher(
        rs_topic_rgb_img, encoding=zenoh.Encoding.IMAGE_JPEG
    )
    """    z_pub_depth = z.declare_publisher(
        rs_topic_depth_img, encoding=zenoh.Encoding.IMAGE_JPEG
    )
    z_pub_pointcloud = z.declare_publisher(
        rs_topic_depth_data, encoding=zenoh.Encoding.APPLICATION_OCTET_STREAM
    )
    z_pub_intrinsics = z.declare_publisher(
        rs_topic_intrinsics, encoding=zenoh.Encoding.APPLICATION_JSON
    )"""

    # RealSense pipeline configuration
    try:
        pipeline = rs.pipeline()
        rs_config = rs.config()
        rs_config.enable_stream(
            rs.stream.color,
            WIDTH_RGB,
            HEIGHT_RGB,
            rs.format.bgr8,
            FPS_RGB,
        )
        rs_config.enable_stream(
            rs.stream.depth,
            WIDTH_DEPTH,
            HEIGHT_DEPTH,
            rs.format.z16,
            FPS_DEPTH,
        )

        pipeline.start(rs_config)
        logger.info("Open RealSense camera...")
    except Exception as exc:
        logger.exception(f"Failed to initialize RealSense pipeline: {exc}")
        return
    """
    def get_intrinsics() -> Intrinsics:
        profile = pipeline.get_active_profile()
        color_profile = rs.video_stream_profile(profile.get_stream(rs.stream.color))
        intrinsics = color_profile.get_intrinsics()

        intrinsics_msg = Intrinsics(
            width=intrinsics.width,
            height=intrinsics.height,
            ppx=intrinsics.ppx,
            ppy=intrinsics.ppy,
            fx=intrinsics.fx,
            fy=intrinsics.fy,
            model=str(intrinsics.model),
            coeffs=intrinsics.coeffs,
        )
        return intrinsics_msg
        """
    # Publish frames to Zenoh
    def publish_frames():
        logger.info("Frame pub")
        # Wait for a few frames to ensure auto-exposure etc. settles, and we get a valid profile
        for _ in range(10):
            pipeline.wait_for_frames()

        #intrinsics_msg = get_intrinsics()
        # Initial publish
        #z_pub_intrinsics.put(intrinsics_msg.model_dump_json())
        #logger.info(f"[INFO] Published intrinsics: {intrinsics_msg}")

        align = rs.align(rs.stream.color)

        last_intrinsics_publish_time = time.time()
        intrinsics_publish_interval = 1.0  # Publish every 1 second

        while True:

            def encode_img_jpeg(img: np.ndarray, quality: int) -> np.ndarray:
                _, jpeg = cv2.imencode(
                    ".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), quality]
                )
                return jpeg

            # Wait for frames
            frames = pipeline.wait_for_frames()
            aligned_frames = align.process(frames)

            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()

            if not color_frame or not depth_frame:
                continue

            # Get Raw Depth image (16-bit)
            depth_image = np.asanyarray(depth_frame.get_data())
            #z_pub_pointcloud.put(depth_image.tobytes())

            jpeg_quality = JPEGQUALITY
            # Publish visualization to depth topic (JPEG)

            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(depth_image, alpha=0.03), cv2.COLORMAP_JET
            )
            jpeg_depth = encode_img_jpeg(depth_colormap, jpeg_quality)
            #z_pub_depth.put(jpeg_depth.tobytes())

            # Get RGB image
            rgb_image = np.asanyarray(color_frame.get_data())
            jpeg_rgb = encode_img_jpeg(rgb_image, jpeg_quality)
            z_pub_rgb.put(jpeg_rgb.tobytes())

            # Publish intrinsics periodically
           # current_time = time.time()
           # if (
            #    current_time - last_intrinsics_publish_time
            #    > intrinsics_publish_interval
            #):
                #z_pub_intrinsics.put(intrinsics_msg.model_dump_json())
                #last_intrinsics_publish_time = current_time

    # Send frames
    publish_frames()


if __name__ == "__main__":
    main()
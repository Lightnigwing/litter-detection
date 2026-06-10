import json
import threading
import uuid
from config import Settings
from topics_pydantic_models.pydantic_models import Task5, Task5_Arrival, Task6_EmoteDone
from interfaces.navigation import (
    NavigationRequest,
    NavigationSegment,
    NavigationState,
    NavigationStatus,
    Pose2D,
)
from interfaces.topics.topics import TOPICS
import zenoh

WAIT_TIMEOUT = 120.0
TOPIC_ARRIVED_AT_POINT = "pipeline/task5/arrived_at_point"
TOPIC_EMOTE_DONE = "pipeline/task6/emote_done"


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    try:
        replies = session.get("pipeline/task4/done")
        data_reply = None
        for reply in replies:
            data_reply = json.loads(reply.ok.payload.to_bytes())
        if data_reply is None:
            raise RuntimeError("No payload received from pipeline/task4/done")

        data = json.loads(data_reply["data"])
        litter_points = data["litter_points"]

        sorted_keys = sorted(litter_points.keys(), key=lambda k: int(k.removeprefix("point")))
        print(f"[TASK5] Received {len(sorted_keys)} litter points: {sorted_keys}")

        arrived_event = threading.Event()
        emote_done_event = threading.Event()
        current = {"request_id": None, "point_key": None}

        def on_nav_status(sample: zenoh.Sample) -> None:
            try:
                status = NavigationStatus.model_validate_json(bytes(sample.payload))
            except Exception:
                return
            if (
                status.state == NavigationState.ARRIVED_FINAL
                and status.request_id == current["request_id"]
            ):
                arrived_event.set()

        def on_emote_done(sample: zenoh.Sample) -> None:
            try:
                msg = Task6_EmoteDone.model_validate_json(bytes(sample.payload))
            except Exception:
                return
            if msg.point_key == current["point_key"]:
                emote_done_event.set()

        session.declare_subscriber(TOPICS.nav.status, on_nav_status)
        session.declare_subscriber(TOPIC_EMOTE_DONE, on_emote_done)

        nav_request_pub = session.declare_publisher(TOPICS.nav.request)
        arrival_pub = session.declare_publisher(TOPIC_ARRIVED_AT_POINT)

        last_idx = len(sorted_keys) - 1
        for idx, key in enumerate(sorted_keys):
            point = litter_points[key]
            req_id = f"task5-{uuid.uuid4().hex[:8]}"

            arrived_event.clear()
            emote_done_event.clear()
            current["request_id"] = req_id
            current["point_key"] = key

            request = NavigationRequest(
                request_id=req_id,
                segments=[
                    NavigationSegment(target=Pose2D(x=point["x"], y=point["y"], theta=0.0))
                ],
            )
            print(f"[TASK5] -> Navigating to {key} ({point['x']:.2f}, {point['y']:.2f}) request={req_id}")
            nav_request_pub.put(request.model_dump_json())

            if not arrived_event.wait(timeout=WAIT_TIMEOUT):
                raise TimeoutError(
                    f"Navigation to {key} did not reach ARRIVED_FINAL within {WAIT_TIMEOUT}s"
                )
            print(f"[TASK5] Arrived at {key}")

            is_last = idx == last_idx
            arrival = Task5_Arrival(point_key=key, is_last=is_last)
            arrival_pub.put(arrival.model_dump_json())
            print(f"[TASK5] Notified task6 about {key} (is_last={is_last})")

            if not emote_done_event.wait(timeout=WAIT_TIMEOUT):
                raise TimeoutError(
                    f"Emote at {key} did not complete within {WAIT_TIMEOUT}s"
                )
            print(f"[TASK5] Emote at {key} done")

        return Task5(point_reached=True)
    finally:
        session.close()

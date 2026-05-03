import json
import threading

import zenoh

from config import Settings
from topics_json.Task_json import Point, Task1_points, Task2_1
from interfaces.navigation import (
    NavigationRequest,
    NavigationSegment,
    NavigationState,
    NavigationStatus,
    Pose2D,
)
from interfaces.topics import TOPICS


def _sorted_points(points: dict[str, Point]) -> list[tuple[str, Point]]:
    """Sort by trailing digit in the key (point1, point2, ...). Stable lex fallback."""
    def key(item):
        k = item[0]
        digits = "".join(c for c in k if c.isdigit())
        return (int(digits) if digits else 1 << 30, k)
    return sorted(points.items(), key=key)


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    try:
        # Holt sich die Punkte aus task1
        replies = session.get("pipeline/task1/done")
        data_reply = None
        for reply in replies:
            data_reply = json.loads(reply.ok.payload.to_bytes())
        if data_reply is None:
            raise RuntimeError("task2_1: kein task1/done Reply erhalten")

        input_data = Task1_points.model_validate_json(data_reply["data"])
        ordered = _sorted_points(input_data.points)
        if not ordered:
            raise ValueError("task2_1: Task1 lieferte keine Punkte")

        print(f"[TASK2_1] {len(ordered)} Punkte zu abfahren: {[name for name, _ in ordered]}")

        # NavStatus-Subscriber + Wait-Event
        arrived = threading.Event()
        state_box: dict[str, object] = {"state": None, "req_id": None}

        def on_status(sample: zenoh.Sample) -> None:
            try:
                msg = NavigationStatus.model_validate_json(bytes(sample.payload))
            except Exception:
                return
            if msg.request_id != state_box["req_id"]:
                return
            state_box["state"] = msg.state
            if msg.state in (
                NavigationState.ARRIVED_FINAL,
                NavigationState.BLOCKED,
                NavigationState.FAILED,
            ):
                arrived.set()

        session.declare_subscriber(TOPICS.nav.status, on_status)

        # Sequenziell jeden Punkt anfahren
        last_point: Point | None = None
        for name, point in ordered:
            req_id = f"task2_1-{name}"
            state_box["req_id"] = req_id
            state_box["state"] = None
            arrived.clear()

            request = NavigationRequest(
                request_id=req_id,
                segments=[
                    NavigationSegment(
                        target=Pose2D(x=point.x, y=point.y, theta=0.0),
                        max_speed=0.4,
                        must_stop=True,
                        allowed_deviation=0.2,
                    )
                ],
            )
            print(f"[TASK2_1] Sende NavRequest {name}: ({point.x}, {point.y})")
            session.put(TOPICS.nav.request, request.model_dump_json())

            if not arrived.wait(timeout=120.0):
                raise TimeoutError(f"task2_1: Nav-Timeout bei {name}")
            if state_box["state"] != NavigationState.ARRIVED_FINAL:
                raise RuntimeError(
                    f"task2_1: Nav fehlgeschlagen bei {name}: state={state_box['state']}"
                )
            print(f"[TASK2_1] Erreicht: {name}")
            last_point = point

        assert last_point is not None
        return Task2_1(lastpoint=last_point)
    finally:
        session.close()

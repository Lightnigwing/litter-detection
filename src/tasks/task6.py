import queue
import time
from config import Settings
from topics_pydantic_models.pydantic_models import Task5_Arrival, Task6, Task6_EmoteDone
from interfaces.motion import ActionCommand, ActionType
from interfaces.topics.topics import TOPICS
import zenoh

ARRIVAL_TIMEOUT = 120.0
EMOTE_DURATION_SEC = 15.0
TOPIC_ARRIVED_AT_POINT = "pipeline/task5/arrived_at_point"
TOPIC_EMOTE_DONE = "pipeline/task6/emote_done"


def run_task():
    settings = Settings()
    conf = zenoh.Config()
    conf.insert_json5("connect/endpoints", f'["{settings.zenoh_router}"]')
    session = zenoh.open(conf)

    try:
        arrivals: queue.Queue[Task5_Arrival] = queue.Queue()

        def on_arrival(sample: zenoh.Sample) -> None:
            try:
                arrival = Task5_Arrival.model_validate_json(bytes(sample.payload))
            except Exception as e:
                print(f"[TASK6] Failed to parse arrival: {e}")
                return
            time.sleep(2.0)
            arrivals.put(arrival)

        session.declare_subscriber(TOPIC_ARRIVED_AT_POINT, on_arrival)

        action_pub = session.declare_publisher(TOPICS.command.pose.action)
        emote_done_pub = session.declare_publisher(TOPIC_EMOTE_DONE)

        print("[TASK6] Waiting for arrivals from task5...")
        while True:
            try:
                arrival = arrivals.get(timeout=ARRIVAL_TIMEOUT)
            except queue.Empty:
                raise TimeoutError(
                    f"No arrival event from task5 within {ARRIVAL_TIMEOUT}s"
                )

            print(f"[TASK6] Arrival at {arrival.point_key} (is_last={arrival.is_last}) -> wiggle_hips")
            action_pub.put(ActionCommand(action=ActionType.wiggle_hips).model_dump_json())

            time.sleep(EMOTE_DURATION_SEC)

            emote_done_pub.put(Task6_EmoteDone(point_key=arrival.point_key).model_dump_json())
            print(f"[TASK6] Emote done at {arrival.point_key}")

            if arrival.is_last:
                print("[TASK6] Last point reached, exiting.")
                break

        return Task6(finished_emote=True)
    finally:
        session.close()

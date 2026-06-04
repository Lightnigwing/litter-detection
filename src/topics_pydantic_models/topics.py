from __future__ import annotations

import msgspec


class demo(msgspec.Struct, frozen=True):
    test: str


class Litter(msgspec.Struct, frozen=True):
    cropped: str
    tracked_overlay: str
    litter_detections_overlay: str


class Topics(msgspec.Struct, frozen=True):
    demo: demo
    litter: Litter


TOPICS = Topics(
    demo=demo(test="demo/test"),
    litter=Litter(
        cropped="litter/cropped",
        tracked_overlay="litter/tracked_overlay",
        litter_detections_overlay="litter/litter_detections_overlay",
    ),
)
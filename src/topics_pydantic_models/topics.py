from __future__ import annotations

import msgspec


class demo(msgspec.Struct, frozen=True):
    test: str


class Litter(msgspec.Struct, frozen=True):
    cropped: str


class Topics(msgspec.Struct, frozen=True):
    demo: demo
    litter: Litter


TOPICS = Topics(
    demo=demo(test="demo/test"),
    litter=Litter(cropped="litter/cropped"),
)
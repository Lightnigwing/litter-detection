from __future__ import annotations

import msgspec

class demo(msgspec.Struct, frozen=True):
    test : str


class Topics(msgspec.Struct, frozen=True):
    demo: demo


TOPICS = Topics(
    demo=demo(test="demo/test"),
)
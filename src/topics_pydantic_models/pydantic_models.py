from pydantic import BaseModel, StringConstraints
from typing import Any, Dict, Optional, Annotated

PointKey = Annotated[
    str,
    StringConstraints(pattern=r"^point\d+$")
]

class Task1_user(BaseModel):
    x: int
    y: int

class Point(BaseModel):
    x: float
    y: float

class Task1_points(BaseModel):
    points: Dict[PointKey, Point]

class Task2_1(BaseModel):
    lastpoint: Point

class Task2_2(BaseModel):
    litter_points: Dict[PointKey, Point]
    amount_litter: int

class Task3(BaseModel):
    witz: str

class Task4(BaseModel):
    litter_points: Dict[PointKey, Point]

class Task5(BaseModel):
    point_reached: bool

class Task6(BaseModel):
    finished_emote: bool
    

class SearchPath(BaseModel):
    points: list[Point]

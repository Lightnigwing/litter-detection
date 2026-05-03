from datetime import datetime, timezone
from enum import StrEnum

from pydantic import BaseModel, Field


class MovementSource(StrEnum):
    controller = "controller"
    autonomous = "autonomous"
    planner = "planner"


class MovementCommand(BaseModel):
    """Velocity command for the robot."""

    x: float = 0.0  # forward/backward (m/s)
    y: float = 0.0  # lateral (m/s)
    z_deg: float = 0.0  # rotation (deg/s)
    source: MovementSource = MovementSource.controller
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_zero(self) -> bool:
        return self.x == 0.0 and self.y == 0.0 and self.z_deg == 0.0

    def scale(self, factor: float) -> "MovementCommand":
        return self.model_copy(
            update={
                "x": self.x * factor,
                "y": self.y * factor,
                "z_deg": self.z_deg * factor,
            }
        )


class TiltBody(BaseModel):
    """Body orientation command (Euler angles in degrees)."""

    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    yaw_deg: float = 0.0

    def is_zero(self) -> bool:
        return self.pitch_deg == 0.0 and self.roll_deg == 0.0 and self.yaw_deg == 0.0


class ActionType(StrEnum):
    stand_up = "stand_up"
    lie_down = "lie_down"
    sit_down = "sit_down"
    hello = "hello"
    dance1 = "dance1"
    wiggle_hips = "wiggle_hips"
    stretch = "stretch"
    stop_move = "stop_move"
    balance_stand = "balance_stand"


class ActionCommand(BaseModel):
    """A discrete action trigger (emote, stance change, etc.)."""

    action: ActionType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

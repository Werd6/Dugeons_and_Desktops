"""Personal-space tuning for a zombie pack."""

from dungeons_desktops.game.actors.spacing import spread_positions as spread_positions
from dungeons_desktops.navigation.terrain import Surface

ELBOW_ROOM = 14.0
CLIMB_ROOM = 28.0
SEPARATION_SPEED = 12.0

__all__ = ["SEPARATION_SPEED", "personal_space", "spread_positions"]


def personal_space(surface: Surface) -> float:
    return CLIMB_ROOM if surface.wall else ELBOW_ROOM

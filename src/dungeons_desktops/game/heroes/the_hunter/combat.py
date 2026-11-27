"""The Hunter's weapon choices, independent cooldowns, and short-lived tracers."""

import math
from dataclasses import dataclass
from enum import Enum

from dungeons_desktops.core.geometry import Vec2

SNIPER_COOLDOWN = 30.0
SNIPER_DAMAGE = 10
SHOTGUN_COOLDOWN = 6.0
SHOTGUN_DAMAGE = 4
SHOTGUN_RANGE = 110.0
SHOTGUN_HALF_ANGLE = math.radians(32)
SHOTGUN_RECOVERY = 0.12
SHOTGUN_BLAST_TIME = 0.22
PISTOL_DAMAGE = 0.5
PISTOL_RANGE = 340.0
PISTOL_INTERVAL = 0.65
HOLD_DISTANCE = 220.0
RETREAT_DISTANCE = 190.0
APPROACH_DISTANCE = 290.0
ROLL_DISTANCE = 95.0
ROLL_TIME = 0.65
TRACER_TIME = 0.12


class Gun(Enum):
    SNIPER = "sniper"
    SHOTGUN = "shotgun"
    PISTOLS = "pistols"


@dataclass
class Tracer:
    start: Vec2
    end: Vec2
    gun: Gun
    age: float = 0.0


@dataclass
class ShotgunBlast:
    origin: Vec2
    direction: Vec2
    age: float = 0.0

    def contains(self, point: Vec2) -> bool:
        offset = point - self.origin
        return (
            offset.length() <= SHOTGUN_RANGE
            and (offset.length() < 1 or offset.normalized().dot(self.direction)
                 >= math.cos(SHOTGUN_HALF_ANGLE))
        )

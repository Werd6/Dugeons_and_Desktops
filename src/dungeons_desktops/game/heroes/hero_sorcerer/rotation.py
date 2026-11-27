"""The Hero Sorcerer's repeating spell sequence and pacing."""

from enum import Enum


class Ability(Enum):
    BOLT = "bolt"
    SKELETAL_ARMS = "skeletal_arms"
    CORPSENADO = "corpsenado"
    BLOOD_CLOUD = "blood_cloud"


ROTATION = (
    Ability.BOLT,
    Ability.SKELETAL_ARMS,
    Ability.BOLT,
    Ability.CORPSENADO,
    Ability.BOLT,
    Ability.BLOOD_CLOUD,
    Ability.BOLT,
    Ability.BOLT,
    Ability.BOLT,
)

# These are rests after the casting animation. The Druid waits 1.2--1.4 seconds;
# the Sorcerer's rotation presses forward much more quickly, with a sharp closing
# volley before its brief reset beat.
STEP_DELAYS = (0.45, 0.6, 0.45, 0.6, 0.45, 0.35, 0.08, 0.08, 0.45)
RAPID_BOLT_SLOTS = frozenset({6, 7, 8})
CAST_RANGE = 360.0

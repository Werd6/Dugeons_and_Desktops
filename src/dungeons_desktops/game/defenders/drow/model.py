"""Drow: a dark elf on foot, facing +x.

The drow's bones and proportions are the stick figure's (so the adventurers'
planner, climbs and mantles fit it exactly). His gait is tuned for a swift,
elegant run at `HASTE` times an adventurer's pace.
"""

from __future__ import annotations

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.defenders.goblins import model as goblin_body
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.walk import WalkSettings

SCALE = stick_figure.SCALE
HEAD_RADIUS = 9.0 * SCALE
"""Same bobble head as every other stickman."""
HASTE = 1.6 * goblin_body.MOVES.walk_speed / stick_figure.MOVES.walk_speed
"""How much faster than an adventurer he covers ground."""

RUN: WalkSettings = replace(
    stick_figure.RUN,
    speed=stick_figure.RUN.speed * HASTE,
    stride=80.0 * SCALE,
    stance_fraction=0.5,
    step_height=3.0 * SCALE,
    hip_bob=0.35 * SCALE,
    lean=0.14,
    arm_swing=0.25,
    arm_reach=0.55,
    crouch=0.015,
    heel_kick=0.85,
    arm_forward=0.15,
    acceleration=8.0,
)
"""Long, quiet strides: less bob and lift than a stickman's scramble, matched to
`HASTE` so the cycle doesn't thrash."""


def build_drow() -> BipedLayout:
    return replace(stick_figure.build_stick_figure(), walk=RUN)

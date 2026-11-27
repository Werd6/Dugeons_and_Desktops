"""Goblin: a short, hunched biped with long arms and a big head, facing +x.

Goblins hunt in a pack and get around like the stickmen do (running, jumping,
climbing walls and mantling ledges), just scaled to their size and a bit faster.
Every length (bones, gait, speed) is the reference size times `SCALE`.
"""

from __future__ import annotations

import math
from dataclasses import replace

from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.navigation.planner import MoveSettings
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.climb import ClimbSettings
from dungeons_desktops.rig.ik import IkChain
from dungeons_desktops.rig.skeleton import BoneDef, Skeleton
from dungeons_desktops.rig.walk import WalkSettings

SCALE = 1.0 / 3.0
LIMB = 0.65 * SCALE
"""Climbing poses use the stick figure's reference numbers times this (goblin legs
are 0.65 of a stick figure's at the same scale)."""

RUN = WalkSettings(
    speed=240.0 * SCALE,
    stride=36.0 * SCALE,
    stance_fraction=0.4,
    step_height=4.0 * SCALE,
    hip_bob=1.2 * SCALE,
    lean=0.18,
    arm_swing=0.7,
    arm_reach=0.85,
    stance_width=3.5 * SCALE,
    acceleration=6.0,
    crouch=0.06,
    heel_kick=0.5,
)
CLIMB = ClimbSettings(
    stride=18.0 * LIMB,
    hip_offset=12.0 * LIMB,
    hip_above_contact=12.0 * LIMB,
    hand_above_hip=27.0 * LIMB,
    grip_inset=1.5 * LIMB,
    pull_off=2.5 * LIMB,
    lean=0.0,
    ledge_reach=3.0 * LIMB,
    head_tilt=-0.2,
)
MOVES = MoveSettings(
    walk_speed=RUN.speed,
    climb_speed=stick_figure.MOVES.climb_speed * 2.2,
    hang_speed=stick_figure.MOVES.hang_speed * 2.2,
    max_jump=stick_figure.MOVES.max_jump,
    edge_clearance=10.0 * SCALE,
)
"""Same reach as a stickman (so the same jumps and climbs work), but quicker: they
run the invaders down."""
HANG_REACH = 16.0 * LIMB
MANTLE_DEPTH = 26.0 * LIMB
HANG_DEPTH = 40.0 * SCALE
"""Hands to feet when hanging from a ceiling (matches `hang.hang_depth` of the goblin)."""


def _limbs(side: str, scale: float) -> tuple[BoneDef, ...]:
    s = scale
    return (
        BoneDef(f"upper_arm_{side}", "torso", 8.0 * s, math.pi, -3.0, 3.0, mass=0.5),
        BoneDef(f"lower_arm_{side}", f"upper_arm_{side}", 8.0 * s, 0.0, -2.6, 0.0, mass=0.4),
        BoneDef(
            f"upper_leg_{side}",
            "pelvis",
            6.5 * s,
            math.pi,
            -2.0,
            0.6,
            mass=1.2,
            from_parent_start=True,
        ),
        BoneDef(f"lower_leg_{side}", f"upper_leg_{side}", 6.5 * s, 0.0, 0.0, 2.6, mass=0.9),
    )


def build_goblin(*, size: float = 1.0) -> BipedLayout:
    """`size` scales the figure (Goblin King uses 2); stride and line widths follow."""
    s = SCALE * size
    limb = 0.65 * s
    bones = (
        BoneDef("pelvis", None, 4.0 * s, UP, mass=1.5),
        BoneDef("torso", "pelvis", 10.0 * s, 0.0, -0.8, 0.8, mass=2.5),
        BoneDef("head", "torso", 7.0 * s, 0.0, -0.9, 0.9, mass=2.0),
        *_limbs("l", s),
        *_limbs("r", s),
    )
    walk = replace(
        RUN,
        speed=240.0 * s,
        stride=36.0 * s,
        step_height=4.0 * s,
        hip_bob=1.2 * s,
        stance_width=3.5 * s,
    )
    climb = replace(
        CLIMB,
        stride=18.0 * limb,
        hip_offset=12.0 * limb,
        hip_above_contact=12.0 * limb,
        hand_above_hip=27.0 * limb,
        grip_inset=1.5 * limb,
        pull_off=2.5 * limb,
        ledge_reach=3.0 * limb,
    )
    return BipedLayout(
        skeleton=Skeleton(bones),
        pelvis="pelvis",
        torso="torso",
        head="head",
        legs=(
            IkChain("leg_l", ("upper_leg_l", "lower_leg_l"), bend=1),
            IkChain("leg_r", ("upper_leg_r", "lower_leg_r"), bend=1),
        ),
        arms=(
            IkChain("arm_l", ("upper_arm_l", "lower_arm_l"), bend=-1),
            IkChain("arm_r", ("upper_arm_r", "lower_arm_r"), bend=-1),
        ),
        head_radius=7.5 * s,
        walk=walk,
        climb=climb,
        scale=s,
    )

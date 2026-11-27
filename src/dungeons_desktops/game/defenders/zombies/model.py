"""Adventurer-sized bones with a short, low, dragging stride."""

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.skeleton import Skeleton
from dungeons_desktops.rig.walk import WalkSettings

SPEED = 0.5
MOVES = replace(
    adventurer.MOVES,
    walk_speed=adventurer.MOVES.walk_speed * SPEED,
    climb_speed=adventurer.MOVES.climb_speed * SPEED,
    hang_speed=adventurer.MOVES.hang_speed * SPEED,
)
SHAMBLE = WalkSettings(
    speed=MOVES.walk_speed,
    stride=12.0,
    stance_fraction=0.76,
    step_height=0.9,
    hip_bob=0.7,
    lean=0.16,
    arm_swing=0.0,
    stance_width=1.6,
    crouch=0.06,
)


def build_zombie(*, size: float = 1.0) -> BipedLayout:
    """`size` scales the figure (Plague Horde uses 1.2); stride and line widths follow."""
    base = replace(adventurer.build_stick_figure(), walk=SHAMBLE)
    if size == 1.0:
        return base
    bones = tuple(replace(bone, length=bone.length * size) for bone in base.skeleton.bones)
    walk = replace(
        SHAMBLE,
        stride=SHAMBLE.stride * size,
        step_height=SHAMBLE.step_height * size,
        hip_bob=SHAMBLE.hip_bob * size,
        stance_width=SHAMBLE.stance_width * size,
    )
    return replace(
        base,
        skeleton=Skeleton(bones),
        walk=walk,
        head_radius=base.head_radius * size,
        scale=base.scale * size,
    )

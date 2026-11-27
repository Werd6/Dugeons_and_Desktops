"""The standard barbarian's proportions, enlarged by half."""

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.skeleton import Skeleton

SIZE = 1.5
BODY_WIDTH = 5.0
MOVES = replace(adventurer.MOVES, edge_clearance=adventurer.MOVES.edge_clearance * SIZE)
HANG_REACH = adventurer.HANG_REACH * SIZE
MANTLE_DEPTH = adventurer.MANTLE_DEPTH * SIZE
HANG_DEPTH = adventurer.HANG_DEPTH * SIZE


def build_mighty(multiplier: float = 1.0) -> BipedLayout:
    base = adventurer.build_stick_figure()
    size = SIZE * multiplier
    return replace(
        base,
        skeleton=Skeleton(
            tuple(replace(bone, length=bone.length * size) for bone in base.skeleton.bones)
        ),
        head_radius=base.head_radius * size,
        scale=base.scale * size,
        walk=replace(
            base.walk,
            stride=base.walk.stride * size,
            step_height=base.walk.step_height * size,
            hip_bob=base.walk.hip_bob * size,
            stance_width=base.walk.stance_width * size,
        ),
        climb=replace(
            base.climb,
            stride=base.climb.stride * size,
            hip_offset=base.climb.hip_offset * size,
            hip_above_contact=base.climb.hip_above_contact * size,
            hand_above_hip=base.climb.hand_above_hip * size,
            grip_inset=base.climb.grip_inset * size,
            pull_off=base.climb.pull_off * size,
            ledge_reach=base.climb.ledge_reach * size,
        ),
    )

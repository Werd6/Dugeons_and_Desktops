"""A half-height wizard with a regular wizard's full-size hat."""

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.skeleton import Skeleton

SIZE = 0.5
HAT_RADIUS = adventurer.build_stick_figure().head_radius
MOVES = replace(adventurer.MOVES, edge_clearance=adventurer.MOVES.edge_clearance * SIZE)
HANG_REACH = adventurer.HANG_REACH * SIZE
MANTLE_DEPTH = adventurer.MANTLE_DEPTH * SIZE
HANG_DEPTH = adventurer.HANG_DEPTH * SIZE


def build_gnome_wizard() -> BipedLayout:
    base = adventurer.build_stick_figure()
    return replace(
        base,
        skeleton=Skeleton(
            tuple(replace(bone, length=bone.length * SIZE) for bone in base.skeleton.bones)
        ),
        head_radius=base.head_radius * SIZE,
        scale=base.scale * SIZE,
        walk=replace(
            base.walk,
            stride=base.walk.stride * SIZE,
            step_height=base.walk.step_height * SIZE,
            hip_bob=base.walk.hip_bob * SIZE,
            stance_width=base.walk.stance_width * SIZE,
        ),
        climb=replace(
            base.climb,
            stride=base.climb.stride * SIZE,
            hip_offset=base.climb.hip_offset * SIZE,
            hip_above_contact=base.climb.hip_above_contact * SIZE,
            hand_above_hip=base.climb.hand_above_hip * SIZE,
            grip_inset=base.climb.grip_inset * SIZE,
            pull_off=base.climb.pull_off * SIZE,
            ledge_reach=base.climb.ledge_reach * SIZE,
        ),
    )

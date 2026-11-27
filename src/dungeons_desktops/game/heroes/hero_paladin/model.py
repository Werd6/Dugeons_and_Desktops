"""Longer limbs and torso add one ordinary head of height, with the head unchanged."""

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.skeleton import Skeleton

BODY_SIZE = 1.5
MOVES = replace(adventurer.MOVES, edge_clearance=adventurer.MOVES.edge_clearance * BODY_SIZE)
HANG_REACH = adventurer.HANG_REACH * BODY_SIZE
MANTLE_DEPTH = adventurer.MANTLE_DEPTH * BODY_SIZE
HANG_DEPTH = adventurer.HANG_DEPTH * BODY_SIZE


def build_hero_paladin() -> BipedLayout:
    base = adventurer.build_stick_figure()
    return replace(
        base,
        skeleton=Skeleton(tuple(
            replace(bone, length=bone.length * (1 if bone.name == base.head else BODY_SIZE))
            for bone in base.skeleton.bones
        )),
        scale=base.scale * BODY_SIZE,
        walk=replace(
            base.walk,
            stride=base.walk.stride * BODY_SIZE,
            step_height=base.walk.step_height * BODY_SIZE,
            hip_bob=base.walk.hip_bob * BODY_SIZE,
            stance_width=base.walk.stance_width * BODY_SIZE,
        ),
        climb=replace(
            base.climb,
            stride=base.climb.stride * BODY_SIZE,
            hip_offset=base.climb.hip_offset * BODY_SIZE,
            hip_above_contact=base.climb.hip_above_contact * BODY_SIZE,
            hand_above_hip=base.climb.hand_above_hip * BODY_SIZE,
            grip_inset=base.climb.grip_inset * BODY_SIZE,
            pull_off=base.climb.pull_off * BODY_SIZE,
            ledge_reach=base.climb.ledge_reach * BODY_SIZE,
        ),
    )

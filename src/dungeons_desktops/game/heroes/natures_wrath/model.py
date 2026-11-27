"""The goblin rig, five percent taller, moving at the regular druid's pace."""

from dataclasses import replace

from dungeons_desktops.game.adventurers import model as adventurer
from dungeons_desktops.game.defenders.goblins import model as goblin
from dungeons_desktops.rig.biped import BipedLayout
from dungeons_desktops.rig.skeleton import Skeleton

SIZE = 1.05
MOVES = replace(adventurer.MOVES, edge_clearance=goblin.MOVES.edge_clearance * SIZE)
HANG_REACH = goblin.HANG_REACH * SIZE
MANTLE_DEPTH = goblin.MANTLE_DEPTH * SIZE
HANG_DEPTH = goblin.HANG_DEPTH * SIZE


def build_natures_wrath() -> BipedLayout:
    base = goblin.build_goblin()
    return replace(
        base,
        skeleton=Skeleton(
            tuple(replace(bone, length=bone.length * SIZE) for bone in base.skeleton.bones)
        ),
        head_radius=base.head_radius * SIZE,
        scale=base.scale * SIZE,
        walk=replace(
            goblin.RUN,
            speed=adventurer.RUN.speed,
            stride=goblin.RUN.stride * SIZE,
            step_height=goblin.RUN.step_height * SIZE,
            hip_bob=goblin.RUN.hip_bob * SIZE,
            stance_width=goblin.RUN.stance_width * SIZE,
        ),
        climb=replace(
            goblin.CLIMB,
            stride=goblin.CLIMB.stride * SIZE,
            hip_offset=goblin.CLIMB.hip_offset * SIZE,
            hip_above_contact=goblin.CLIMB.hip_above_contact * SIZE,
            hand_above_hip=goblin.CLIMB.hand_above_hip * SIZE,
            grip_inset=goblin.CLIMB.grip_inset * SIZE,
            pull_off=goblin.CLIMB.pull_off * SIZE,
            ledge_reach=goblin.CLIMB.ledge_reach * SIZE,
        ),
    )

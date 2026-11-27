"""Safe retreat along a ledge and a tucked, rotating recoil-roll pose."""

import math
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.game.heroes.the_hunter.combat import ROLL_DISTANCE, ROLL_TIME
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.locomotion import air_pose
from dungeons_desktops.rig.skeleton import forward_kinematics, mirror_pose


def retreat_point(hero, distance: float, facing: int) -> Anchor | None:
    """Keep the whole body on its current horizontal surface, including narrow ledges."""
    start = hero.follower.current_anchor()
    surface = start.surface
    if not surface.horizontal:
        return None
    margin = min(hero.layout.head_radius + 3, surface.length / 2)
    x = clamp(start.point.x - facing * distance, surface.low + margin, surface.high - margin)
    # At an edge, shorten the retreat rather than stepping forward toward an enemy.
    if (x - start.point.x) * facing >= 0:
        return Anchor(surface, start.point)
    return Anchor(surface, surface.point_at(x))


@dataclass
class Roll:
    start: Vec2
    landing: Anchor
    facing: int
    age: float = 0.0
    duration: float = ROLL_TIME

    @property
    def progress(self) -> float:
        return min(1.0, self.age / self.duration)

    def point(self) -> Vec2:
        t = self.progress
        return self.start.lerp(self.landing.point, 1 - (1 - t) ** 2)


def start_roll(hero) -> Roll | None:
    if hero.follower.in_transition:
        return None
    landing = retreat_point(hero, ROLL_DISTANCE, hero.facing)
    return Roll(hero.contact(), landing, hero.facing) if landing is not None else None


def roll_pose(hero, roll: Roll):
    layout = hero.layout
    feet = roll.point()
    pose = air_pose(layout, Vec2(roll.facing * feet.x, feet.y), rising=True)
    pose.root = Vec2(roll.facing * feet.x, feet.y - layout.leg_length * 1.8)
    hip = pose.root
    for i, chain in enumerate(layout.legs):
        tucked = hip + Vec2((-0.25 if i else 0.25), 0.35) * layout.leg_length
        solve_two_bone(
            layout.skeleton, pose, chain, tucked,
        )
    shoulder = forward_kinematics(layout.skeleton, pose)[layout.torso].end
    for i, chain in enumerate(layout.arms):
        solve_two_bone(layout.skeleton, pose, chain, shoulder + Vec2(2 + i, 4))
    if roll.facing < 0:
        pose = mirror_pose(layout.skeleton, pose)
    # Rotate the skeleton itself so costume, hitboxes, and carried guns roll together.
    pivot = Vec2(feet.x, feet.y - layout.leg_length * 1.8)
    angle = -roll.facing * math.tau * roll.progress
    pose.root = pivot + (pose.root - pivot).rotated(angle)
    pose.root -= Vec2(0, 4 * math.sin(math.pi * roll.progress))
    pose.angles[layout.pelvis] += angle
    return pose

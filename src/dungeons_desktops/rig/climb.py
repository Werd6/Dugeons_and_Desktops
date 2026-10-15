"""Procedural wall climb for a biped, in a frame where the wall is on the figure's +x side.

Hands and feet grip the wall in a contralateral gait (left hand with right foot,
then right hand with left foot). Each grip stays planted while the body moves
past it, then swings to a new hold ahead in the direction of travel, pulling
slightly off the wall mid-swing. Hands cannot grip above the wall top; there
they rest over the lip instead. Feet below the wall's bottom dangle.

The driver works in feet-level `contact_y`: the height of the foot holds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics


@dataclass(frozen=True)
class ClimbSettings:
    stride: float = 44.0
    stance_fraction: float = 0.55
    hip_offset: float = 18.0
    hip_above_contact: float = 40.0
    hand_above_hip: float = 64.0
    grip_inset: float = 3.0
    pull_off: float = 5.0
    lean: float = 0.22
    ledge_reach: float = 10.0
    head_tilt: float = -0.35


@dataclass
class _Grip:
    y: float
    planted: float
    swing_from: float
    swinging: bool = False
    lift: float = 0.0


class ClimbDriver:
    def __init__(self, layout: BipedLayout, settings: ClimbSettings | None = None) -> None:
        self.layout = layout
        self.settings = settings or layout.climb or ClimbSettings()
        self.chains = layout.arms + layout.legs
        self.phases = (0.0, 0.5, 0.5, 0.0)
        self.is_hand = (True, True, False, False)
        self.wall_x = 0.0
        self.wall_top = 0.0
        self.wall_bottom = 0.0
        self.contact_y = 0.0
        self.cycle = 0.0
        self.grips = [_Grip(0.0, 0.0, 0.0) for _ in self.chains]
        self.pose: Pose = layout.skeleton.rest_pose(Vec2(0.0, 0.0))

    def place(self, wall_x: float, contact_y: float, wall_top: float, wall_bottom: float) -> None:
        self.wall_x, self.wall_top, self.wall_bottom = wall_x, wall_top, wall_bottom
        self.contact_y = contact_y
        self.cycle = 0.0
        quarter = self.settings.stride * 0.25
        for i, grip in enumerate(self.grips):
            y = self._base(i) + (-quarter if self.phases[i] == 0.0 else quarter)
            grip.y = grip.planted = grip.swing_from = y
            grip.swinging, grip.lift = False, 0.0
        self._solve()

    def shift(self, dy: float) -> None:
        self.contact_y += dy
        for grip in self.grips:
            grip.y += dy
            grip.planted += dy
            grip.swing_from += dy

    def update(
        self, contact_y: float, dt: float, wall_x: float, wall_top: float, wall_bottom: float
    ) -> Pose:
        self.wall_x, self.wall_top, self.wall_bottom = wall_x, wall_top, wall_bottom
        delta = contact_y - self.contact_y
        self.contact_y = contact_y
        if abs(delta) > 1e-9:
            direction = 1.0 if delta > 0 else -1.0
            self.cycle = (self.cycle + abs(delta) / self.settings.stride) % 1.0
            for i, grip in enumerate(self.grips):
                self._step_grip(i, grip, direction)
        else:
            for i, grip in enumerate(self.grips):
                if grip.swinging or grip.lift > 0.0:
                    grip.y += (self._base(i) - grip.y) * min(1.0, dt * 6.0)
                    grip.planted = grip.y
                    grip.lift *= max(0.0, 1.0 - dt * 8.0)
                    grip.swinging = False
        return self._solve()

    def _hip(self) -> Vec2:
        s = self.settings
        return Vec2(self.wall_x - s.hip_offset, self.contact_y - s.hip_above_contact)

    def _base(self, index: int) -> float:
        hip_y = self.contact_y - self.settings.hip_above_contact
        return hip_y - self.settings.hand_above_hip if self.is_hand[index] else self.contact_y

    def _step_grip(self, index: int, grip: _Grip, direction: float) -> None:
        s = self.settings
        phase = (self.cycle + self.phases[index]) % 1.0
        swinging = phase >= s.stance_fraction
        if swinging and not grip.swinging:
            grip.swing_from = grip.y
        elif not swinging and grip.swinging:
            grip.planted = grip.y
        grip.swinging = swinging

        if not swinging:
            grip.y, grip.lift = grip.planted, 0.0
            return
        t = (phase - s.stance_fraction) / (1.0 - s.stance_fraction)
        remaining = (1.0 - t) * (1.0 - s.stance_fraction) * s.stride
        landing = self._base(index) + direction * (remaining + s.stance_fraction * s.stride * 0.5)
        grip.y = grip.swing_from + (landing - grip.swing_from) * smoothstep(t)
        grip.lift = s.pull_off * math.sin(math.pi * t)

    def _target(self, index: int, hip: Vec2) -> Vec2:
        grip = self.grips[index]
        wall_side = self.wall_x - self.settings.grip_inset - grip.lift
        if self.is_hand[index]:
            if grip.y <= self.wall_top + 1.0:
                return Vec2(self.wall_x + self.settings.ledge_reach, self.wall_top)
            return Vec2(wall_side, min(grip.y, self.wall_bottom))
        if grip.y > self.wall_bottom + 1.0:
            leg = self.layout.leg_length
            return Vec2(hip.x + leg * 0.05, hip.y + leg * 0.95)
        return Vec2(wall_side, max(grip.y, self.wall_top))

    def _solve(self) -> Pose:
        layout = self.layout
        skeleton = layout.skeleton
        hip = self._hip()
        pose = self.pose
        pose.root = hip
        pose.angles[layout.pelvis] = UP + self.settings.lean
        pose.angles[layout.torso] = 0.05 * math.sin(math.tau * self.cycle)
        pose.angles[layout.head] = self.settings.head_tilt

        for i, chain in enumerate(self.chains):
            if not self.is_hand[i]:
                solve_two_bone(skeleton, pose, chain, self._target(i, hip))
        for i, chain in enumerate(self.chains):
            if self.is_hand[i]:
                solve_two_bone(skeleton, pose, chain, self._target(i, hip))
        return pose

    def hand_positions(self) -> list[Vec2]:
        transforms = forward_kinematics(self.layout.skeleton, self.pose)
        return [transforms[chain.bones[-1]].end for chain in self.layout.arms]

"""Procedural biped gait: planted feet, swing arcs, hip bob, and counter-swinging arms.

The driver only produces IK targets and a few spine angles; the IK solvers turn
them into a pose. Idle is the same driver at zero speed. A `stance_fraction`
below 0.5 gives a run: both feet leave the ground between steps.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp, smoothstep
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import Pose, forward_kinematics

IDLE_ARM_REACH = 0.92


@dataclass(frozen=True)
class WalkSettings:
    speed: float = 65.0
    stride: float = 60.0
    stance_fraction: float = 0.6
    step_height: float = 9.0
    hip_bob: float = 2.0
    lean: float = 0.08
    arm_swing: float = 0.5
    arm_reach: float = 0.92
    stance_width: float = 5.0
    acceleration: float = 4.0
    crouch: float = 0.0
    """Extra knee bend at full speed, as a fraction of leg length."""
    heel_kick: float = 0.0
    """0 lifts the swing foot symmetrically; toward 1 the lift peaks early, behind the body."""
    arm_forward: float = 0.0
    """Angle the arm swing is centered on, forward of straight down, at full speed."""


@dataclass
class _Foot:
    position: Vec2
    planted: Vec2
    swing_from: Vec2
    swinging: bool = False


@dataclass
class WalkDriver:
    layout: BipedLayout
    ground_y: float
    hip_x: float
    settings: WalkSettings | None = None

    def __post_init__(self) -> None:
        skeleton = self.layout.skeleton
        if self.settings is None:
            self.settings = self.layout.walk or WalkSettings()
        self.hip_height = self.layout.leg_length * 0.93
        self.speed = 0.0
        self.target_speed = 0.0
        self.direction = 1.0
        self.cycle = 0.0
        self.time = 0.0
        self.overrides: dict[str, Vec2] = {}
        self.targets: dict[str, Vec2] = {}
        self._feet = []
        for i in range(len(self.layout.legs)):
            rest = self._rest_foot(i)
            self._feet.append(_Foot(position=rest, planted=rest, swing_from=rest))
        self.pose: Pose = skeleton.rest_pose(Vec2(self.hip_x, self.ground_y - self.hip_height))
        self._solve()

    @property
    def walking(self) -> bool:
        return self.target_speed > 0.0

    def set_walking(self, walking: bool) -> None:
        self.target_speed = self.settings.speed if walking else 0.0

    def shift(self, dx: float) -> None:
        """Move the whole figure horizontally without affecting the gait."""
        offset = Vec2(dx, 0.0)
        self.hip_x += dx
        for foot in self._feet:
            foot.position += offset
            foot.planted += offset
            foot.swing_from += offset
        self.pose.root += offset
        for name, target in self.targets.items():
            self.targets[name] = target + offset

    def set_ground(self, ground_y: float) -> None:
        dy = ground_y - self.ground_y
        self.ground_y = ground_y
        offset = Vec2(0.0, dy)
        for foot in self._feet:
            foot.position += offset
            foot.planted += offset
            foot.swing_from += offset

    def foot_positions(self) -> list[Vec2]:
        return [foot.position for foot in self._feet]

    def place(self, hip_x: float, ground_y: float) -> None:
        """Stand at a new spot with both feet at rest, discarding the gait."""
        self.hip_x = hip_x
        self.ground_y = ground_y
        self.speed = 0.0
        self.cycle = 0.0
        for i, foot in enumerate(self._feet):
            rest = self._rest_foot(i)
            foot.position = foot.planted = foot.swing_from = rest
            foot.swinging = False
        self._solve()

    def update(self, dt: float) -> None:
        """Self-propelled: accelerate toward the target speed and walk forward."""
        s = self.settings
        self.speed += (self.target_speed - self.speed) * min(1.0, dt * s.acceleration)
        if self.target_speed == 0.0 and self.speed < 0.5:
            self.speed = 0.0
        self._advance(self.speed * dt, dt)

    def step_to(self, hip_x: float, dt: float) -> None:
        """Move to `hip_x`; a negative step backpedals while still facing +x."""
        distance = hip_x - self.hip_x
        if abs(distance) > self.settings.stride:
            self.place(hip_x, self.ground_y)
            return
        measured = abs(distance) / dt if dt > 0 else 0.0
        self.speed += (measured - self.speed) * min(1.0, dt * 8.0)
        if measured == 0.0 and self.speed < 0.5:
            self.speed = 0.0
        self._advance(distance, dt)

    def _advance(self, distance: float, dt: float) -> None:
        self.time += dt
        self.hip_x += distance
        if abs(distance) > 1e-9:
            self.direction = 1.0 if distance > 0 else -1.0
            self.cycle = (self.cycle + abs(distance) / self.settings.stride) % 1.0
            for i, foot in enumerate(self._feet):
                self._update_walking_foot(i, foot)
        else:
            for i, foot in enumerate(self._feet):
                self._settle_foot(i, foot, dt)
        self._solve()

    def _rest_foot(self, index: int) -> Vec2:
        side = 1.0 if index % 2 == 0 else -1.0
        return Vec2(self.hip_x + side * self.settings.stance_width, self.ground_y)

    def _update_walking_foot(self, index: int, foot: _Foot) -> None:
        s = self.settings
        phase = (self.cycle + index / len(self._feet)) % 1.0
        swinging = phase >= s.stance_fraction

        if swinging and not foot.swinging:
            foot.swing_from = foot.position
        elif not swinging and foot.swinging:
            foot.planted = Vec2(foot.position.x, self.ground_y)
        foot.swinging = swinging

        if not swinging:
            foot.position = foot.planted
            return

        t = (phase - s.stance_fraction) / (1.0 - s.stance_fraction)
        remaining_hip_travel = (1.0 - t) * (1.0 - s.stance_fraction) * s.stride
        landing = Vec2(
            self.hip_x + self.direction * (
                remaining_hip_travel + s.stance_fraction * s.stride * 0.5
            ), self.ground_y,
        )
        shaped = t ** (1.0 - 0.6 * s.heel_kick)
        lift = s.step_height * math.sin(math.pi * shaped) * min(1.0, self.speed / s.speed)
        foot.position = foot.swing_from.lerp(landing, smoothstep(t)) - Vec2(0.0, lift)

    def _settle_foot(self, index: int, foot: _Foot, dt: float) -> None:
        rest = self._rest_foot(index)
        foot.swinging = False
        foot.position = foot.position.lerp(rest, min(1.0, dt * 6.0))
        foot.position = Vec2(foot.position.x, min(foot.position.y, self.ground_y))
        foot.planted = foot.position

    def _solve(self) -> None:
        s = self.settings
        layout = self.layout
        skeleton = layout.skeleton
        pace = min(1.0, self.speed / s.speed) if s.speed else 0.0
        breath = math.sin(self.time * 2.2)

        # Hips are lowest at cycle 0 and 0.5 for a walk, and half a stance after each
        # footfall for a run.
        lowest = 0.0 if s.stance_fraction >= 0.5 else s.stance_fraction * 0.5
        bob = -s.hip_bob * math.cos(4.0 * math.pi * (self.cycle - lowest)) * pace
        bob += 0.6 * breath * (1 - pace)
        height = self.hip_height - s.crouch * self.layout.leg_length * pace
        pose = self.pose
        pose.root = Vec2(self.hip_x, self.ground_y - height + bob)
        pose.angles[layout.pelvis] = UP + s.lean * self.direction * pace
        pose.angles[layout.torso] = 0.04 * math.sin(4.0 * math.pi * self.cycle) * pace
        pose.angles[layout.head] = -s.lean * 0.6 * pace + 0.03 * breath

        for leg, foot in zip(layout.legs, self._feet, strict=True):
            target = self.overrides.get(leg.name, foot.position)
            self.targets[leg.name] = target
            solve_two_bone(skeleton, pose, leg, target)

        shoulder = forward_kinematics(skeleton, pose)[layout.torso].end
        half_stride = s.stride * 0.5
        for arm, foot in zip(layout.arms, self._feet, strict=True):
            reach_fraction = IDLE_ARM_REACH + (s.arm_reach - IDLE_ARM_REACH) * pace
            reach = sum(skeleton.bone(name).length for name in arm.bones) * reach_fraction
            swing = s.arm_swing * clamp(-(foot.position.x - self.hip_x) / half_stride, -1.0, 1.0)
            swing = swing * pace + s.arm_forward * pace + 0.04 * breath * (1 - pace)
            default = shoulder + Vec2.from_angle(math.pi / 2 - swing, reach)
            target = self.overrides.get(arm.name, default)
            self.targets[arm.name] = target
            solve_two_bone(skeleton, pose, arm, target)

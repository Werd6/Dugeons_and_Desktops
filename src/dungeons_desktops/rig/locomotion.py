"""One pose source for a moving biped: walking, climbing, hanging, or airborne.

Callers send a `LocomotionInput` every step: the pose mode, the contact point
(feet on the ground, or feet level on a wall or under a ceiling), which way the
figure faces, and
which surface it is on. When any of those change, the driver re-plants the new
gait and blends from the last displayed pose over `blend` seconds, so mantles,
grabs, landings, and turns are continuous.

Sub-drivers work in a canonical frame where the figure faces +x. Facing -x is
produced by mirroring the finished pose.
"""

from __future__ import annotations

from collections.abc import Hashable
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from dungeons_desktops.core.geometry import Vec2, smoothstep
from dungeons_desktops.rig.biped import UP, BipedLayout
from dungeons_desktops.rig.climb import ClimbDriver
from dungeons_desktops.rig.hang import HangDriver
from dungeons_desktops.rig.ik import solve_two_bone
from dungeons_desktops.rig.skeleton import Pose, blend_poses, forward_kinematics, mirror_pose
from dungeons_desktops.rig.walk import WalkDriver

DEFAULT_BLEND = 0.18


class PoseMode(Enum):
    WALK = "walk"
    CLIMB = "climb"
    HANG = "hang"
    AIR = "air"


@dataclass(frozen=True)
class Wall:
    x: float
    top: float
    bottom: float


@dataclass(frozen=True)
class LocomotionInput:
    mode: PoseMode
    contact: Vec2
    facing: int
    surface_key: Hashable
    wall: Wall | None = None
    blend: float = DEFAULT_BLEND
    rising: bool = False
    grip: float | None = None
    """HANG: the height of the line the hands hold."""


class UpperBodyLayer(Protocol):
    """Re-poses the upper body after the gait (e.g. holding a weapon), facing +x, in place."""

    def apply(self, pose: Pose, mode: PoseMode, dt: float, skip: frozenset[str]) -> None: ...


@dataclass
class LocomotionDriver:
    layout: BipedLayout
    initial: LocomotionInput
    overrides: dict[str, Vec2] = field(default_factory=dict)
    upper: UpperBodyLayer | None = None

    def __post_init__(self) -> None:
        contact = self.initial.contact
        self.walk = WalkDriver(self.layout, ground_y=contact.y, hip_x=contact.x)
        self.climb = ClimbDriver(self.layout)
        self.hang = HangDriver(self.layout)
        self.facing = self.initial.facing
        self.mode = self.initial.mode
        self._key: tuple | None = None
        self._blend_from: Pose | None = None
        self._blend_elapsed = 0.0
        self._blend_duration = 0.0
        self.pose: Pose = self.layout.skeleton.rest_pose(contact)
        self.teleport(self.initial)

    def teleport(self, command: LocomotionInput) -> None:
        """Jump straight to a command's state with no blend."""
        self._key = self._command_key(command)
        self._enter(command)
        self._blend_from = None
        self.pose = self._target(command, 0.0)

    def blend_from(self, pose: Pose, duration: float) -> None:
        """Ease from an externally supplied pose (e.g. a ragdoll getting up)."""
        self._blend_from = pose.copy()
        self._blend_elapsed = 0.0
        self._blend_duration = duration

    def shift(self, delta: Vec2) -> None:
        """Carry the whole figure by `delta`, e.g. when the surface under it moves."""
        f = self.facing
        self.walk.shift(f * delta.x)
        self.walk.set_ground(self.walk.ground_y + delta.y)
        self.walk.pose.root += Vec2(f * delta.x, delta.y)
        self.climb.shift(delta.y)
        self.hang.shift(f * delta.x, delta.y)
        self.pose.root += delta
        if self._blend_from is not None:
            self._blend_from.root += delta

    def update(self, dt: float, command: LocomotionInput) -> Pose:
        key = self._command_key(command)
        if key != self._key:
            self._enter(command)
            if command.blend > 0.0:
                self.blend_from(self.pose, command.blend)
            self._key = key

        target = self._target(command, dt)
        if self._blend_from is not None:
            self._blend_elapsed += dt
            t = self._blend_elapsed / self._blend_duration if self._blend_duration > 0 else 1.0
            if t >= 1.0:
                self._blend_from = None
            else:
                target = blend_poses(self._blend_from, target, smoothstep(t))
        self.pose = target
        return target

    def limb_tips(self) -> dict[str, Vec2]:
        transforms = forward_kinematics(self.layout.skeleton, self.pose)
        return {chain.name: transforms[chain.bones[-1]].end for chain in self.layout.chains}

    @staticmethod
    def _command_key(command: LocomotionInput) -> tuple:
        return (command.mode, command.facing, command.surface_key)

    def _enter(self, command: LocomotionInput) -> None:
        f = command.facing
        self.mode, self.facing = command.mode, f
        contact = command.contact
        if command.mode is PoseMode.WALK:
            self.walk.place(f * contact.x, contact.y)
        elif command.mode is PoseMode.CLIMB and command.wall is not None:
            wall = command.wall
            self.climb.place(f * wall.x, contact.y, wall.top, wall.bottom)
        elif command.mode is PoseMode.HANG and command.grip is not None:
            self.hang.place(f * contact.x, command.grip)

    def _target(self, command: LocomotionInput, dt: float) -> Pose:
        f = command.facing
        contact = command.contact
        if command.mode is PoseMode.WALK:
            if abs(self.walk.ground_y - contact.y) > 1e-6:
                self.walk.set_ground(contact.y)
            self.walk.overrides = {k: Vec2(f * v.x, v.y) for k, v in self.overrides.items()}
            self.walk.step_to(f * contact.x, dt)
            pose = self.walk.pose
        elif command.mode is PoseMode.CLIMB and command.wall is not None:
            wall = command.wall
            pose = self.climb.update(contact.y, dt, f * wall.x, wall.top, wall.bottom)
        elif command.mode is PoseMode.HANG and command.grip is not None:
            pose = self.hang.update(f * contact.x, command.grip, dt)
        else:
            pose = air_pose(self.layout, Vec2(f * contact.x, contact.y), command.rising)
        pose = pose.copy()
        if self.upper is not None:
            self.upper.apply(pose, command.mode, dt, frozenset(self.overrides))
        return mirror_pose(self.layout.skeleton, pose) if f < 0 else pose


def air_pose(layout: BipedLayout, contact: Vec2, rising: bool) -> Pose:
    """Tucked jump (arms reaching up) or a fall (arms out, legs ready to land), facing +x."""
    skeleton = layout.skeleton
    leg = layout.leg_length
    arm = sum(skeleton.bone(name).length for name in layout.arms[0].bones)
    hip = contact - Vec2(0.0, 0.8 * leg)
    pose = skeleton.rest_pose(hip)
    pose.angles[layout.pelvis] = UP + 0.12
    pose.angles[layout.torso] = 0.0
    pose.angles[layout.head] = -0.15 if rising else 0.1

    feet = ((0.18, 0.62), (-0.04, 0.73)) if rising else ((0.11, 0.84), (-0.11, 0.87))
    for chain, (dx, dy) in zip(layout.legs, feet, strict=True):
        solve_two_bone(skeleton, pose, chain, hip + Vec2(dx, dy) * leg)

    shoulder = forward_kinematics(skeleton, pose)[layout.torso].end
    hands = ((0.33, -0.67), (0.1, -0.76)) if rising else ((0.52, -0.19), (-0.38, -0.33))
    for chain, (dx, dy) in zip(layout.arms, hands, strict=True):
        solve_two_bone(skeleton, pose, chain, shoulder + Vec2(dx, dy) * arm)
    return pose

"""Bone hierarchy, poses, and forward kinematics.

Angles are radians in world space with y pointing down, so +pi/2 points down
the screen. A bone's local angle is relative to its parent's world angle; a
root bone's local angle is its world angle.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field

from dungeons_desktops.core.geometry import Vec2, clamp, wrap_angle


@dataclass(frozen=True)
class BoneDef:
    name: str
    parent: str | None
    length: float
    rest_angle: float
    min_offset: float = -math.inf
    max_offset: float = math.inf
    mass: float = 1.0
    from_parent_start: bool = False

    @property
    def limited(self) -> bool:
        return math.isfinite(self.min_offset) or math.isfinite(self.max_offset)

    def clamp_local(self, local_angle: float) -> float:
        """Clamp a local angle to this bone's limits, measured from its rest angle.

        Outside the range, snaps to whichever limit is angularly closer, so a joint
        that swings past the back of its range does not flip to the far limit.
        """
        if not self.limited:
            return local_angle
        offset = wrap_angle(local_angle - self.rest_angle)
        if self.min_offset <= offset <= self.max_offset:
            return self.rest_angle + offset
        to_min = abs(wrap_angle(offset - self.min_offset))
        to_max = abs(wrap_angle(offset - self.max_offset))
        nearest = self.min_offset if to_min < to_max else self.max_offset
        return self.rest_angle + clamp(nearest, self.min_offset, self.max_offset)


@dataclass(frozen=True)
class Skeleton:
    bones: tuple[BoneDef, ...]
    _index: Mapping[str, int] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        index: dict[str, int] = {}
        for i, bone in enumerate(self.bones):
            if bone.name in index:
                raise ValueError(f"duplicate bone {bone.name!r}")
            if bone.length <= 0:
                raise ValueError(f"bone {bone.name!r} needs a positive length")
            if bone.mass <= 0:
                raise ValueError(f"bone {bone.name!r} needs a positive mass")
            if bone.parent is None:
                if bone.from_parent_start:
                    raise ValueError(f"root bone {bone.name!r} cannot attach to a parent start")
            elif bone.parent not in index:
                raise ValueError(f"bone {bone.name!r} must come after its parent {bone.parent!r}")
            index[bone.name] = i
        if not self.bones:
            raise ValueError("skeleton needs at least one bone")
        object.__setattr__(self, "_index", index)

    def bone(self, name: str) -> BoneDef:
        return self.bones[self._index[name]]

    def __contains__(self, name: str) -> bool:
        return name in self._index

    def rest_pose(self, root: Vec2) -> Pose:
        return Pose(root=root, angles={bone.name: bone.rest_angle for bone in self.bones})


@dataclass
class Pose:
    root: Vec2
    angles: dict[str, float]

    def copy(self) -> Pose:
        return Pose(root=self.root, angles=dict(self.angles))


@dataclass(frozen=True, slots=True)
class BoneTransform:
    start: Vec2
    end: Vec2
    angle: float


def mirror_pose(skeleton: Skeleton, pose: Pose, axis_x: float = 0.0) -> Pose:
    """Reflect a pose across the vertical line x = axis_x (turn a +x-facing pose to face -x)."""
    angles = {}
    for bone in skeleton.bones:
        angle = pose.angles.get(bone.name, bone.rest_angle)
        angles[bone.name] = wrap_angle(math.pi - angle) if bone.parent is None else -angle
    return Pose(root=Vec2(2.0 * axis_x - pose.root.x, pose.root.y), angles=angles)


def blend_poses(a: Pose, b: Pose, t: float) -> Pose:
    """Interpolate root and joint angles, taking the short way around each angle."""
    angles = {
        name: a.angles.get(name, target) + wrap_angle(target - a.angles.get(name, target)) * t
        for name, target in b.angles.items()
    }
    return Pose(root=a.root.lerp(b.root, t), angles=angles)


def forward_kinematics(skeleton: Skeleton, pose: Pose) -> dict[str, BoneTransform]:
    transforms: dict[str, BoneTransform] = {}
    for bone in skeleton.bones:
        local = pose.angles.get(bone.name, bone.rest_angle)
        if bone.parent is None:
            start, world = pose.root, local
        else:
            parent = transforms[bone.parent]
            start = parent.start if bone.from_parent_start else parent.end
            world = parent.angle + local
        transforms[bone.name] = BoneTransform(
            start=start, end=start + Vec2.from_angle(world, bone.length), angle=world
        )
    return transforms

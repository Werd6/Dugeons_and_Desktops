"""Inverse kinematics: analytic two-bone IK and FABRIK.

Both solvers produce world-space joint points. `apply_chain_points` then writes
those points back into a pose as local angles, clamping each bone to its joint
limits, so every solver respects limits the same way and bone lengths never
change.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from dungeons_desktops.core.geometry import Vec2, clamp
from dungeons_desktops.rig.skeleton import Pose, Skeleton, forward_kinematics


@dataclass(frozen=True)
class IkChain:
    """Bones from chain root to tip. `bend` picks the side a two-bone joint folds toward.

    With y pointing down, bend=+1 folds the joint so the child's local angle is
    positive (a knee on a figure facing +x); bend=-1 folds the other way (an elbow).
    """

    name: str
    bones: tuple[str, ...]
    bend: int = 1


def two_bone_points(
    root: Vec2, upper: float, lower: float, target: Vec2, bend: int = 1
) -> tuple[Vec2, Vec2, Vec2]:
    """Return (root, joint, tip). Out-of-reach targets give a straight limb aimed at the target."""
    to_target = target - root
    distance = to_target.length()
    base = to_target.angle() if distance > 1e-9 else math.pi / 2
    distance = clamp(distance, max(abs(upper - lower), 1e-6), upper + lower)

    cos_root = (upper * upper + distance * distance - lower * lower) / (2.0 * upper * distance)
    upper_angle = base - bend * math.acos(clamp(cos_root, -1.0, 1.0))
    joint = root + Vec2.from_angle(upper_angle, upper)
    tip = root + Vec2.from_angle(base, distance)
    return root, joint, tip


def fabrik(
    points: Sequence[Vec2], target: Vec2, iterations: int = 20, tolerance: float = 0.01
) -> list[Vec2]:
    """Solve a chain with a fixed base. Returns new joint points, same count as `points`."""
    joints = list(points)
    if len(joints) < 2:
        return joints
    lengths = [joints[i].distance_to(joints[i + 1]) for i in range(len(joints) - 1)]
    base = joints[0]

    if base.distance_to(target) >= sum(lengths):
        direction = (target - base).normalized()
        for i, length in enumerate(lengths):
            joints[i + 1] = joints[i] + direction * length
        return joints

    for _ in range(iterations):
        joints[-1] = target
        for i in range(len(joints) - 2, -1, -1):
            direction = (joints[i] - joints[i + 1]).normalized()
            joints[i] = joints[i + 1] + direction * lengths[i]
        joints[0] = base
        for i in range(len(joints) - 1):
            direction = (joints[i + 1] - joints[i]).normalized()
            joints[i + 1] = joints[i] + direction * lengths[i]
        if joints[-1].distance_to(target) <= tolerance:
            break
    return joints


def _check_chain(skeleton: Skeleton, chain: Sequence[str]) -> None:
    for previous, name in zip(chain, chain[1:], strict=False):
        bone = skeleton.bone(name)
        if bone.parent != previous or bone.from_parent_start:
            raise ValueError(f"{name!r} must attach to the end of {previous!r} in an IK chain")


def apply_chain_points(
    skeleton: Skeleton, pose: Pose, chain: Sequence[str], points: Sequence[Vec2]
) -> None:
    """Aim each chain bone at the matching solved point, clamped to its joint limits.

    `points[0]` is the chain root and is ignored; `points[i + 1]` is where bone i should end.
    """
    _check_chain(skeleton, chain)
    transforms = forward_kinematics(skeleton, pose)
    first = skeleton.bone(chain[0])
    parent_angle = transforms[first.parent].angle if first.parent else 0.0
    start = transforms[chain[0]].start

    for i, name in enumerate(chain):
        bone = skeleton.bone(name)
        desired = (points[i + 1] - start).angle()
        local = bone.clamp_local(desired - parent_angle)
        pose.angles[name] = local
        parent_angle += local
        start = start + Vec2.from_angle(parent_angle, bone.length)


def solve_two_bone(skeleton: Skeleton, pose: Pose, chain: IkChain, target: Vec2) -> None:
    if len(chain.bones) != 2:
        raise ValueError(f"two-bone IK needs 2 bones, {chain.name!r} has {len(chain.bones)}")
    upper, lower = (skeleton.bone(name) for name in chain.bones)
    root = forward_kinematics(skeleton, pose)[upper.name].start
    points = two_bone_points(root, upper.length, lower.length, target, chain.bend)
    apply_chain_points(skeleton, pose, chain.bones, points)


def solve_fabrik(
    skeleton: Skeleton, pose: Pose, chain: IkChain, target: Vec2, iterations: int = 20
) -> None:
    transforms = forward_kinematics(skeleton, pose)
    points = [transforms[chain.bones[0]].start] + [transforms[name].end for name in chain.bones]
    apply_chain_points(skeleton, pose, chain.bones, fabrik(points, target, iterations))


def chain_tip(skeleton: Skeleton, pose: Pose, chain: IkChain) -> Vec2:
    return forward_kinematics(skeleton, pose)[chain.bones[-1]].end

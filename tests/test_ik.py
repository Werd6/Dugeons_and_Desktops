import math

import pytest

from dungeons_desktops.core.geometry import Vec2, wrap_angle
from dungeons_desktops.game.adventurers.model import build_stick_figure
from dungeons_desktops.rig.ik import (
    IkChain,
    chain_tip,
    fabrik,
    solve_fabrik,
    solve_two_bone,
    two_bone_points,
)
from dungeons_desktops.rig.skeleton import BoneDef, Skeleton, forward_kinematics


def lengths_of(points):
    return [a.distance_to(b) for a, b in zip(points, points[1:], strict=False)]


def test_two_bone_hits_reachable_target_and_keeps_lengths():
    root, joint, tip = two_bone_points(Vec2(0, 0), 10.0, 8.0, Vec2(12.0, 5.0), bend=1)

    assert tip.distance_to(Vec2(12.0, 5.0)) < 1e-9
    assert root.distance_to(joint) == pytest.approx(10.0)
    assert joint.distance_to(tip) == pytest.approx(8.0)


@pytest.mark.parametrize("bend", [1, -1])
def test_two_bone_bend_picks_the_fold_side(bend):
    root, joint, tip = two_bone_points(Vec2(0, 0), 10.0, 10.0, Vec2(0.0, 15.0), bend=bend)
    relative = wrap_angle((tip - joint).angle() - (joint - root).angle())

    assert math.copysign(1, relative) == bend


def test_two_bone_unreachable_target_fully_extends_toward_it():
    target = Vec2(100.0, 100.0)
    root, joint, tip = two_bone_points(Vec2(0, 0), 10.0, 8.0, target, bend=1)
    direction = target.normalized()

    assert root.distance_to(tip) == pytest.approx(18.0)
    assert (joint / 10.0).distance_to(direction) < 1e-6
    assert (tip / 18.0).distance_to(direction) < 1e-6


def test_fabrik_reaches_target_and_preserves_lengths():
    points = [Vec2(0, 0), Vec2(10, 0), Vec2(20, 0), Vec2(30, 0), Vec2(40, 0)]
    target = Vec2(15.0, 20.0)

    solved = fabrik(points, target, iterations=50, tolerance=1e-4)

    assert solved[0] == Vec2(0, 0)
    assert solved[-1].distance_to(target) < 1e-3
    assert lengths_of(solved) == pytest.approx([10.0] * 4, abs=1e-6)


def test_fabrik_unreachable_target_extends_straight():
    points = [Vec2(0, 0), Vec2(10, 0), Vec2(20, 0)]
    solved = fabrik(points, Vec2(0.0, 100.0))

    assert solved[-1].distance_to(Vec2(0.0, 20.0)) < 1e-9


def test_skeleton_fabrik_moves_chain_tip_to_target():
    skeleton = Skeleton(
        tuple(BoneDef(f"seg{i}", f"seg{i - 1}" if i else None, 10.0, 0.0) for i in range(5))
    )
    chain = IkChain("tail", tuple(f"seg{i}" for i in range(5)))
    pose = skeleton.rest_pose(Vec2(0, 0))

    solve_fabrik(skeleton, pose, chain, Vec2(20.0, 25.0), iterations=60)

    assert chain_tip(skeleton, pose, chain).distance_to(Vec2(20.0, 25.0)) < 0.05


def test_joint_limits_block_a_backwards_knee():
    layout = build_stick_figure()
    skeleton = layout.skeleton
    pose = skeleton.rest_pose(Vec2(0.0, 0.0))
    backwards = IkChain("leg_r", ("upper_leg_r", "lower_leg_r"), bend=-1)

    solve_two_bone(skeleton, pose, backwards, Vec2(0.0, 40.0))

    knee = skeleton.bone("lower_leg_r")
    offset = wrap_angle(pose.angles["lower_leg_r"] - knee.rest_angle)
    assert knee.min_offset - 1e-9 <= offset <= knee.max_offset + 1e-9


def test_stick_figure_leg_ik_keeps_bone_lengths():
    layout = build_stick_figure()
    skeleton = layout.skeleton
    pose = skeleton.rest_pose(Vec2(0.0, 0.0))

    target = Vec2(0.2, 0.85) * layout.leg_length
    solve_two_bone(skeleton, pose, layout.legs[0], target)
    transforms = forward_kinematics(skeleton, pose)

    assert transforms["lower_leg_l"].end.distance_to(target) < 1e-6
    for bone in skeleton.bones:
        t = transforms[bone.name]
        assert t.start.distance_to(t.end) == pytest.approx(bone.length)

import math

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.model import build_stick_figure
from dungeons_desktops.rig.skeleton import BoneDef, Pose, Skeleton, forward_kinematics


def two_bone_arm() -> Skeleton:
    return Skeleton((BoneDef("upper", None, 10.0, 0.0), BoneDef("lower", "upper", 5.0, 0.0)))


def test_fk_places_two_bone_tip():
    skeleton = two_bone_arm()
    pose = Pose(root=Vec2(1.0, 2.0), angles={"upper": math.pi / 2, "lower": -math.pi / 2})

    transforms = forward_kinematics(skeleton, pose)

    assert transforms["upper"].end.distance_to(Vec2(1.0, 12.0)) < 1e-9
    assert transforms["lower"].end.distance_to(Vec2(6.0, 12.0)) < 1e-9
    assert transforms["lower"].angle == pytest.approx(0.0)


def test_from_parent_start_attaches_at_parent_root():
    skeleton = Skeleton(
        (
            BoneDef("pelvis", None, 10.0, -math.pi / 2),
            BoneDef("leg", "pelvis", 20.0, math.pi, from_parent_start=True),
        )
    )
    transforms = forward_kinematics(skeleton, skeleton.rest_pose(Vec2(0.0, 0.0)))

    assert transforms["leg"].start == Vec2(0.0, 0.0)
    assert transforms["leg"].end.distance_to(Vec2(0.0, 20.0)) < 1e-9


def test_parent_must_be_declared_first():
    with pytest.raises(ValueError):
        Skeleton((BoneDef("lower", "upper", 5.0, 0.0), BoneDef("upper", None, 10.0, 0.0)))


def test_stick_figure_rest_pose_stands_upright():
    layout = build_stick_figure()
    transforms = forward_kinematics(layout.skeleton, layout.skeleton.rest_pose(Vec2(0.0, 0.0)))

    assert transforms["head"].end.y < transforms["torso"].start.y < 0
    assert transforms["lower_leg_l"].end.y == pytest.approx(layout.leg_length)
    assert transforms["lower_arm_r"].end.y > transforms["torso"].end.y

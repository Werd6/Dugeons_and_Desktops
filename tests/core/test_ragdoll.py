import copy

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2, wrap_angle
from dungeons_desktops.game.adventurers.model import build_stick_figure
from dungeons_desktops.rig.ragdoll import Ragdoll
from dungeons_desktops.rig.skeleton import forward_kinematics, mirror_pose
from dungeons_desktops.rig.walk import WalkDriver

DT = 1.0 / 60.0
GROUND = 300.0


def walking_ragdoll(steps: int = 90) -> tuple[WalkDriver, Ragdoll]:
    layout = build_stick_figure()
    driver = WalkDriver(layout, ground_y=GROUND, hip_x=100.0)
    ragdoll = Ragdoll(layout.skeleton, ground_y=GROUND)
    driver.set_walking(True)
    for _ in range(steps):
        driver.update(DT)
        ragdoll.drive(driver.pose, DT)
    return driver, ragdoll


def test_motors_on_ragdoll_matches_animated_pose():
    driver, ragdoll = walking_ragdoll()
    expected = forward_kinematics(driver.layout.skeleton, driver.pose)

    for name, transform in expected.items():
        start, end = ragdoll.segment(name)
        assert start.distance_to(transform.start) < 1e-9
        assert end.distance_to(transform.end) < 1e-9


def test_released_ragdoll_falls_and_keeps_bone_lengths():
    driver, ragdoll = walking_ragdoll()
    skeleton = driver.layout.skeleton
    ragdoll.release()
    ragdoll.apply_impulse(ragdoll.segment("torso")[1], Vec2(250.0, -150.0))

    for _ in range(360):
        ragdoll.step(DT)

    for bone in skeleton.bones:
        start, end = ragdoll.segment(bone.name)
        assert start.distance_to(end) == pytest.approx(bone.length, abs=0.05)
        assert start.y <= GROUND + 1e-6 and end.y <= GROUND + 1e-6
    assert max(ragdoll.pin_gaps()) < 0.1
    head_end = ragdoll.segment("head")[1]
    assert head_end.y > GROUND - 40.0, "figure should have collapsed toward the ground"


def test_ragdoll_respects_knee_limits_after_settling():
    driver, ragdoll = walking_ragdoll()
    ragdoll.release()
    for _ in range(360):
        ragdoll.step(DT)

    pose = ragdoll.pose()
    for name in ("lower_leg_l", "lower_leg_r"):
        knee = driver.layout.skeleton.bone(name)
        offset = wrap_angle(pose.angles[name] - knee.rest_angle)
        assert knee.min_offset - 0.15 <= offset <= knee.max_offset + 0.15


def test_ragdoll_does_not_change_the_skeleton_definition():
    driver, ragdoll = walking_ragdoll()
    before = copy.deepcopy(driver.layout.skeleton)
    ragdoll.release()
    for _ in range(120):
        ragdoll.step(DT)

    assert driver.layout.skeleton == before
    assert ragdoll.skeleton is driver.layout.skeleton


def test_ragdoll_lands_on_a_box_instead_of_falling_through():
    driver, ragdoll = walking_ragdoll()
    box = Rect(0.0, GROUND, 400.0, 100.0)  # the figure walks on this box's top
    ragdoll.ground_y = GROUND + 100.0
    ragdoll.obstacles = (box,)
    ragdoll.release()
    for _ in range(360):
        ragdoll.step(DT)

    for bone in driver.layout.skeleton.bones:
        for point in ragdoll.segment(bone.name):
            assert point.y <= box.top + 1e-6


def test_mirrored_ragdoll_bends_knees_the_mirrored_way():
    layout = build_stick_figure()
    driver = WalkDriver(layout, ground_y=GROUND, hip_x=100.0)
    ragdoll = Ragdoll(layout.skeleton, ground_y=GROUND)
    ragdoll.facing = -1
    ragdoll.drive(mirror_pose(layout.skeleton, driver.pose, axis_x=100.0), DT, snap=True)
    ragdoll.release()
    for _ in range(360):
        ragdoll.step(DT)

    pose = ragdoll.pose()
    for name in ("lower_leg_l", "lower_leg_r"):
        knee = layout.skeleton.bone(name)
        offset = wrap_angle(-pose.angles[name] - knee.rest_angle)
        assert knee.min_offset - 0.15 <= offset <= knee.max_offset + 0.15


def test_engage_snaps_back_without_velocity():
    driver, ragdoll = walking_ragdoll()
    ragdoll.release()
    for _ in range(60):
        ragdoll.step(DT)

    ragdoll.engage(driver.pose, DT)
    expected = forward_kinematics(driver.layout.skeleton, driver.pose)
    assert ragdoll.segment("torso")[0].distance_to(expected["torso"].start) < 1e-9

    ragdoll.release()
    ragdoll.step(DT)
    moved = ragdoll.segment("torso")[0].distance_to(expected["torso"].start)
    assert moved < 2.0

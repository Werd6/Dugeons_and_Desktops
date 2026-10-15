import math

import pytest

from dungeons_desktops.core.geometry import Vec2, wrap_angle
from dungeons_desktops.creatures import stick_figure
from dungeons_desktops.creatures.stick_figure import build_stick_figure
from dungeons_desktops.rig.climb import ClimbDriver
from dungeons_desktops.rig.skeleton import blend_poses, forward_kinematics, mirror_pose

DT = 1.0 / 60.0
WALL_X, WALL_TOP, WALL_BOTTOM = 300.0, 100.0, 400.0
CLIMB_END = WALL_TOP + stick_figure.MANTLE_DEPTH


def climb_up(driver: ClimbDriver, start: float, end: float, speed: float = 40.0):
    y = start
    while y > end:
        y = max(end, y - speed * DT)
        yield driver.update(y, DT, WALL_X, WALL_TOP, WALL_BOTTOM)


def test_climber_stays_beside_the_wall_with_hands_below_the_top():
    layout = build_stick_figure()
    driver = ClimbDriver(layout)
    driver.place(WALL_X, WALL_BOTTOM, WALL_TOP, WALL_BOTTOM)

    for pose in climb_up(driver, WALL_BOTTOM, CLIMB_END):
        transforms = forward_kinematics(layout.skeleton, pose)
        assert transforms["pelvis"].start.x < WALL_X
        for hand in driver.hand_positions():
            # Joint limits can leave a hand a hair off its hold when the hold is right
            # above the shoulder; it must never float above the wall or sink into it.
            assert hand.y >= WALL_TOP - 1.0
            inside_box = hand.x > WALL_X + 1.0 and hand.y > WALL_TOP + 1.0
            assert not inside_box

    hands = driver.hand_positions()
    ledge_hold = Vec2(WALL_X + driver.settings.ledge_reach, WALL_TOP)
    assert min(hand.distance_to(ledge_hold) for hand in hands) < 3.0, (
        "at the top of the climb a hand should rest on the ledge"
    )


def test_grips_move_in_alternating_pairs():
    driver = ClimbDriver(build_stick_figure())
    driver.place(WALL_X, WALL_BOTTOM, WALL_TOP, WALL_BOTTOM)
    swinging_together = 0
    frames = 0
    for _ in climb_up(driver, WALL_BOTTOM, WALL_BOTTOM - 120):
        arm_l, arm_r, leg_l, leg_r = (g.swinging for g in driver.grips)
        assert not (arm_l and arm_r), "both hands should never let go at once"
        swinging_together += arm_l == leg_r
        frames += 1
    assert swinging_together == frames


def test_planted_grip_holds_still_while_the_body_rises():
    driver = ClimbDriver(build_stick_figure())
    driver.place(WALL_X, WALL_BOTTOM, WALL_TOP, WALL_BOTTOM)
    previous = [g.y for g in driver.grips]
    holds = 0
    for _ in climb_up(driver, WALL_BOTTOM, WALL_BOTTOM - 100):
        for grip, before in zip(driver.grips, previous, strict=True):
            if not grip.swinging and grip.planted == before:
                assert grip.y == before
                holds += 1
        previous = [g.y for g in driver.grips]
    assert holds > 100


def test_mirror_pose_reflects_world_positions():
    layout = build_stick_figure()
    driver = ClimbDriver(layout)
    pose = driver.update(WALL_BOTTOM, DT, WALL_X, WALL_TOP, WALL_BOTTOM)

    mirrored = mirror_pose(layout.skeleton, pose, axis_x=0.0)
    original = forward_kinematics(layout.skeleton, pose)
    reflected = forward_kinematics(layout.skeleton, mirrored)
    for name, t in original.items():
        assert reflected[name].end.distance_to(Vec2(-t.end.x, t.end.y)) < 1e-6


def test_blend_poses_takes_short_way_round():
    layout = build_stick_figure()
    a = layout.skeleton.rest_pose(Vec2(0, 0))
    b = a.copy()
    a.angles["pelvis"] = math.pi - 0.1
    b.angles["pelvis"] = -math.pi + 0.1

    mid = blend_poses(a, b, 0.5)

    assert abs(math.cos(mid.angles["pelvis"]) + 1.0) < 1e-6
    end = blend_poses(a, b, 1.0).angles["pelvis"]
    assert wrap_angle(end - (-math.pi + 0.1)) == pytest.approx(0.0, abs=1e-9)

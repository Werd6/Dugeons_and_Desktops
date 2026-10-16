import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.model import build_stick_figure
from dungeons_desktops.rig.skeleton import forward_kinematics
from dungeons_desktops.rig.walk import WalkDriver

DT = 1.0 / 60.0
GROUND = 300.0


def make_driver() -> WalkDriver:
    return WalkDriver(build_stick_figure(), ground_y=GROUND, hip_x=100.0)


def test_idle_stands_with_feet_on_ground():
    driver = make_driver()
    for _ in range(120):
        driver.update(DT)

    transforms = forward_kinematics(driver.layout.skeleton, driver.pose)
    for leg in driver.layout.legs:
        assert transforms[leg.bones[-1]].end.y == pytest.approx(GROUND, abs=0.5)
    assert driver.hip_x == pytest.approx(100.0)


def test_walking_moves_forward_and_feet_never_sink():
    driver = make_driver()
    driver.set_walking(True)
    for _ in range(300):
        driver.update(DT)
        transforms = forward_kinematics(driver.layout.skeleton, driver.pose)
        for leg in driver.layout.legs:
            assert transforms[leg.bones[-1]].end.y <= GROUND + 1e-6

    assert driver.hip_x > 200.0


def test_planted_foot_does_not_slide():
    driver = make_driver()
    driver.set_walking(True)
    for _ in range(240):
        driver.update(DT)

    previous = driver.foot_positions()
    stance_checks = 0
    for _ in range(60):
        driver.update(DT)
        current = driver.foot_positions()
        for foot, before, after in zip(driver._feet, previous, current, strict=True):
            if not foot.swinging and after.y == GROUND and before.y == GROUND:
                assert after.x == pytest.approx(before.x)
                stance_checks += 1
        previous = current
    assert stance_checks > 30


def test_override_drags_a_hand():
    driver = make_driver()
    arm = driver.layout.arms[1]
    shoulder = forward_kinematics(driver.layout.skeleton, driver.pose)["torso"].end
    target = shoulder + Vec2(12.0, -5.0) * driver.layout.scale

    driver.overrides[arm.name] = target
    driver.update(DT)

    hand = forward_kinematics(driver.layout.skeleton, driver.pose)[arm.bones[-1]].end
    assert hand.distance_to(target) < 1.0

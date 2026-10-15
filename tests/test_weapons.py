import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.creatures.stick_figure import build_stick_figure
from dungeons_desktops.navigation.planner import Move
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import LocomotionDriver, LocomotionInput, PoseMode
from dungeons_desktops.rig.skeleton import forward_kinematics
from dungeons_desktops.rig.weapons import Rifle, Sword

DT = 1.0 / 60.0
GROUND = 300.0


def standing(facing: int = 1) -> LocomotionInput:
    return LocomotionInput(PoseMode.WALK, Vec2(100.0, GROUND), facing, "floor")


def make_driver(weapon_type, facing: int = 1):
    layout = build_stick_figure()
    weapon = weapon_type(layout)
    driver = LocomotionDriver(layout, standing(facing), upper=weapon)
    for _ in range(30):
        driver.update(DT, standing(facing))
    return driver, weapon


def run(controller: RigPreviewController, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        controller.advance(DT)


@pytest.mark.parametrize("facing", [1, -1])
def test_sword_swing_chops_from_behind_the_head_to_forward_and_down(facing):
    driver, sword = make_driver(Sword, facing)
    assert sword.start()

    tips = []
    while sword.busy:
        driver.update(DT, standing(facing))
        transforms = forward_kinematics(driver.layout.skeleton, driver.pose)
        tips.append((sword.tip(transforms, facing), transforms["head"].end))

    behind_and_up = [t for t, head in tips if facing * (t.x - head.x) < -5 and t.y < head.y]
    forward_and_down = [t for t, head in tips if facing * (t.x - head.x) > 10 and t.y > head.y]
    assert behind_and_up, "the wind-up should raise the blade behind the head"
    assert forward_and_down, "the strike should end forward and low"
    assert not sword.busy


def test_weapon_stays_in_the_hand_through_a_swing():
    driver, sword = make_driver(Sword)
    sword.start()
    while sword.busy:
        driver.update(DT, standing())
        transforms = forward_kinematics(driver.layout.skeleton, driver.pose)
        hand = transforms["lower_arm_r"].end
        strokes = sword.strokes(transforms, 1)
        assert strokes[0].end.distance_to(hand) < 1e-6


@pytest.mark.parametrize("facing", [1, -1])
def test_rifle_aims_level_and_both_hands_hold_it(facing):
    driver, rifle = make_driver(Rifle, facing)
    rifle.start()
    for _ in range(int(0.5 / DT)):
        driver.update(DT, standing(facing))

    transforms = forward_kinematics(driver.layout.skeleton, driver.pose)
    muzzle, direction = rifle.muzzle(transforms, facing)
    assert direction.x == pytest.approx(facing, abs=0.05)
    support = transforms["lower_arm_l"].end
    grip = transforms["lower_arm_r"].end
    on_line = abs((support - grip).cross(direction))
    assert on_line < 1.0, "the support hand should be on the rifle"
    assert facing * (muzzle.x - transforms["head"].end.x) > 10


def test_can_attack_while_climbing():
    controller = RigPreviewController(1000, 600)
    controller.set_variant("barbarian")
    box = controller.boxes[0]
    controller.press(Vec2(box.x + 60, box.top - 10))
    for _ in range(int(20 / DT)):
        controller.advance(DT)
        step = controller.follower.step
        if step is not None and step.move is Move.CLIMB:
            break
    assert controller.locomotion.mode is PoseMode.CLIMB
    controller.attack()
    assert controller.weapon.busy
    run(controller, 1.0)
    assert controller.selected.animated

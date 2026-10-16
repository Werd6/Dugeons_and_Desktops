from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import StickMode
from dungeons_desktops.navigation.planner import Move
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1.0 / 60.0


def run(controller: RigPreviewController, seconds: float) -> None:
    for _ in range(int(seconds / DT)):
        controller.advance(DT)


def run_until_arrived(controller: RigPreviewController, max_seconds: float = 90.0) -> None:
    for _ in range(int(max_seconds / DT)):
        controller.advance(DT)
        if not controller.follower.moving:
            return
    raise AssertionError("figure never arrived")


def make() -> RigPreviewController:
    return RigPreviewController(1000, 600)


def test_clicking_a_floating_box_top_routes_up_through_the_overlapping_box():
    controller = make()
    floating = controller.boxes[2]
    target = Vec2(floating.x + 40, floating.top - 20)

    controller.press(target)
    moves = {step.move for step in controller.route_steps()}
    run_until_arrived(controller)

    assert {Move.CLIMB, Move.MANTLE} <= moves
    assert controller.contact().distance_to(Vec2(floating.x + 40, floating.top)) < 1e-6


def test_dragging_the_box_under_the_figure_carries_it():
    controller = make()
    box = controller.boxes[0]
    controller.press(Vec2(box.x + 60, box.top - 10))
    run_until_arrived(controller)
    before = controller.contact()

    controller.press(Vec2(box.x + 140, box.top + 60))  # grab the box body, away from the figure
    controller.drag(Vec2(box.x + 120, box.top + 60))
    controller.drop()
    run(controller, 0.2)

    assert controller.animated
    assert controller.contact().distance_to(before + Vec2(-20, 0)) < 1e-6


def test_dragging_a_box_away_mid_walk_replans_without_teleporting():
    controller = make()
    controller.press(Vec2(controller.width - 30, controller.floor_y - 5))
    run(controller, 0.3)
    assert controller.locomotion.mode is PoseMode.WALK
    before = controller.contact()

    box = controller.boxes[0]
    controller.press(Vec2(box.x + 75, box.top + 80))
    controller.drag(Vec2(box.x + 75, box.top + 40))
    controller.drop()
    controller.advance(DT)

    assert controller.contact().distance_to(before) < 3.0
    assert controller.follower.moving


def test_knocking_over_and_getting_up():
    controller = make()
    run(controller, 0.3)
    torso = controller.transforms()["torso"].end

    controller.press(torso)
    assert controller.mode is StickMode.RAGDOLL
    run(controller, 2.0)

    controller.get_up()
    run(controller, 1.0)
    assert controller.mode is StickMode.ANIMATED
    assert controller.follower.anchor.surface.walkable


def test_wander_keeps_finding_reachable_goals():
    controller = make()
    controller.toggle_wander()
    goals = set()
    for _ in range(int(80 / DT)):
        controller.advance(DT)
        if controller.goal is not None:
            goals.add((round(controller.goal.x), round(controller.goal.y)))
    assert len(goals) >= 3
    assert controller.animated


def test_unreachable_goal_reports_no_route():
    controller = make()
    floating = controller.boxes[2]
    controller.press(Vec2(floating.x + 100, floating.y + 100))
    controller.drag(Vec2(floating.x + 100, floating.y - 100))  # lift it out of jump reach
    controller.drop()
    floating = controller.boxes[2]

    controller.press(Vec2(floating.x + 200, floating.top - 10))

    assert not controller.goal_reachable
    assert controller.status == "No route there"

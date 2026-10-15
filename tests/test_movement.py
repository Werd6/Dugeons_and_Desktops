import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.creatures.stick_figure import build_stick_figure
from dungeons_desktops.navigation.planner import Move, Planner
from dungeons_desktops.navigation.terrain import Terrain
from dungeons_desktops.rig.locomotion import LocomotionDriver, PoseMode
from dungeons_desktops.rig.skeleton import forward_kinematics
from dungeons_desktops.systems.movement import RouteFollower

DT = 1.0 / 60.0
FLOOR = 500.0


START = Vec2(100, FLOOR)


def setup(*boxes: Rect, start=START):
    terrain = Terrain(boxes, floor_y=FLOOR, left=0.0, right=1000.0)
    planner = Planner(terrain)
    follower = RouteFollower(planner.anchor_near(start))
    layout = build_stick_figure()
    driver = LocomotionDriver(layout, follower.command())
    return planner, follower, driver, layout


def run_route(planner, follower, driver, goal: Vec2, max_seconds: float = 60.0):
    follower.set_route(planner.plan(follower.current_anchor(), planner.anchor_near(goal)))
    modes = []
    contacts = []
    for _ in range(int(max_seconds / DT)):
        command = follower.update(DT)
        driver.update(DT, command)
        modes.append(command.mode)
        contacts.append(command.contact)
        if not follower.moving:
            break
    return modes, contacts


def test_follower_walks_climbs_and_arrives_on_top():
    planner, follower, driver, layout = setup(Rect(400, 300, 100, 200))

    modes, contacts = run_route(planner, follower, driver, Vec2(450, 300))

    assert not follower.moving
    assert contacts[-1].distance_to(Vec2(450, 300)) < 1e-6
    assert PoseMode.CLIMB in modes and modes[-1] is PoseMode.WALK
    for _ in range(60):
        driver.update(DT, follower.update(DT))
    transforms = forward_kinematics(layout.skeleton, driver.pose)
    for leg in layout.legs:
        assert transforms[leg.bones[-1]].end.y == pytest.approx(300.0, abs=1.0)


def test_contact_moves_continuously_along_walks_and_climbs():
    planner, follower, driver, _ = setup(Rect(400, 300, 100, 200))
    follower.set_route(planner.plan(follower.current_anchor(), planner.anchor_near(Vec2(450, 300))))

    previous = follower.contact()
    while follower.moving:
        step = follower.step
        follower.update(DT)
        current = follower.contact()
        if step is follower.step and step.move in (Move.WALK, Move.CLIMB):
            assert current.distance_to(previous) <= 65.0 * DT + 1e-6
        previous = current


def test_climber_faces_the_wall_on_either_side():
    planner, follower, driver, layout = setup(Rect(400, 300, 100, 200), start=Vec2(800, FLOOR))
    run_route(planner, follower, driver, Vec2(450, 300))

    assert follower.facing == -1, "approached from the right, the figure climbs facing -x"


def test_dropping_off_a_ledge_lands_on_the_floor():
    planner, follower, driver, layout = setup(Rect(400, 380, 100, 120), start=Vec2(450, 380))

    modes, contacts = run_route(planner, follower, driver, Vec2(800, FLOOR))

    assert PoseMode.AIR in modes
    assert contacts[-1].distance_to(Vec2(800, FLOOR)) < 1e-6
    transforms = forward_kinematics(layout.skeleton, driver.pose)
    assert transforms["pelvis"].start.y < FLOOR


def test_replanning_mid_walk_does_not_jump():
    planner, follower, driver, _ = setup()
    follower.set_route(
        planner.plan(follower.current_anchor(), planner.anchor_near(Vec2(900, FLOOR)))
    )
    for _ in range(60):
        driver.update(DT, follower.update(DT))
    before = follower.contact()

    follower.reset(follower.current_anchor())
    follower.set_route(
        planner.plan(follower.current_anchor(), planner.anchor_near(Vec2(50, FLOOR)))
    )
    follower.update(DT)

    assert follower.contact().distance_to(before) <= 65.0 * DT + 1e-6
    assert follower.facing == -1

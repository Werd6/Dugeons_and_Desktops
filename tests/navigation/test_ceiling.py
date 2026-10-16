"""Hanging from ceilings (window undersides and the screen top) and dropping from them."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers import model as stick_figure
from dungeons_desktops.game.adventurers.actor import StickMode
from dungeons_desktops.game.defenders.goblins import model as goblin
from dungeons_desktops.game.defenders.goblins.actor import GoblinPack
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor, Move, Planner
from dungeons_desktops.navigation.terrain import SurfaceKind, Terrain, TerrainChange
from dungeons_desktops.rig.hang import HangDriver, hang_depth
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.rig.skeleton import forward_kinematics

DT = 1.0 / 60.0
FLOOR, WIDTH, TOP = 600.0, 900.0, 20.0
HANG = 26.0
FLOATING = Rect(400, 250, 200, 120)
"""Bottom 230 above the floor: far out of jumping reach, and nothing near it."""


def terrain(*boxes: Rect, ceiling: float | None = TOP, hang: float | None = HANG) -> Terrain:
    return Terrain(boxes, FLOOR, 0.0, WIDTH, ceiling=ceiling, hang_depth=hang)


def ceilings(t: Terrain) -> list:
    return [s for s in t.surfaces if s.kind is SurfaceKind.CEILING]


def moves(route) -> list[Move]:
    return [step.move for step in route.steps]


def plan(t: Terrain, start: Vec2, goal: Vec2, settings=None):
    planner = Planner(t, settings)
    return planner.plan(planner.anchor_near(start), planner.anchor_near(goal))


def run(world: SimWorld, seconds: float, until=None) -> float:
    for k in range(int(seconds / DT)):
        world.advance(DT)
        if until is not None and until():
            return k * DT
    return seconds


# ----- terrain ---------------------------------------------------------------------


def test_box_bottoms_and_the_screen_top_are_ceilings_at_feet_level():
    t = terrain(FLOATING)
    under, screen = sorted(ceilings(t), key=lambda s: s.box is None)
    assert under.box == 0 and under.grip == FLOATING.bottom
    assert (under.low, under.high) == (FLOATING.left, FLOATING.right)
    assert under.start.y == FLOATING.bottom + HANG
    assert screen.box is None and screen.grip == TOP and screen.start.y == TOP + HANG
    assert (screen.low, screen.high) == (0.0, WIDTH)


def test_no_ceilings_without_a_hang_depth():
    assert ceilings(terrain(FLOATING, hang=None)) == []


def test_ceiling_is_clipped_where_the_hanging_body_would_be_inside_a_box():
    t = terrain(Rect(300, 100, 400, 100), Rect(450, 210, 100, 390), ceiling=None)
    pieces = [(s.low, s.high) for s in ceilings(t)]
    assert pieces == [(300.0, 450.0), (550.0, 700.0)]


def test_bottom_too_close_to_the_floor_to_hang_from_is_not_a_ceiling():
    assert ceilings(terrain(Rect(400, 450, 100, 140), ceiling=None)) == []


# ----- planning ----------------------------------------------------------------------


def test_floating_window_is_reached_from_the_screen_top_by_dropping():
    route = plan(terrain(FLOATING), Vec2(800, FLOOR), Vec2(500, FLOATING.top))

    assert route is not None
    assert {Move.CLIMB, Move.SWING, Move.HANG, Move.DROP} <= set(moves(route))
    drop = next(s for s in route.steps if s.move is Move.DROP)
    assert drop.from_surface.hanging and drop.from_surface.box is None
    assert drop.surface.box == 0
    for a, b in zip(route.steps, route.steps[1:], strict=False):
        assert a.end.distance_to(b.start) < 1e-6


def test_floating_window_is_unreachable_without_ceilings():
    assert plan(terrain(FLOATING, hang=None), Vec2(800, FLOOR), Vec2(500, 250)) is None


def test_floating_window_reached_through_another_windows_underside():
    tower = Rect(100, 300, 80, 300)
    shelf = Rect(60, 200, 500, 100)  # sits on the tower, overhangs the floating box
    low_float = Rect(350, 420, 150, 60)  # 120 above the floor: no jump reaches it
    t = terrain(tower, shelf, low_float, ceiling=None)

    route = plan(t, Vec2(800, FLOOR), Vec2(420, 420))

    assert route is not None
    drop = next(s for s in route.steps if s.move is Move.DROP)
    assert drop.from_surface.hanging and drop.from_surface.box == 1
    assert drop.surface.box == 2
    swing = next(s for s in route.steps if s.move is Move.SWING)
    assert swing.from_surface.wall and swing.from_surface.box == 0


def test_climber_goes_round_a_boxs_bottom_corner_onto_its_underside():
    t = terrain(Rect(100, 300, 80, 300), Rect(60, 200, 500, 100), ceiling=None)
    planner = Planner(t)
    under = next(s for s in ceilings(t) if s.box == 1 and s.low > 150)
    route = planner.plan(planner.anchor_near(Vec2(800, FLOOR)), planner.anchor_near(under.start))
    assert route is not None
    assert Move.SWING in moves(route) and route.steps[-1].surface.hanging


def test_a_floating_window_can_be_left_by_letting_go_of_its_wall():
    high = Rect(400, 150, 200, 100)  # wall bottoms hang 305 above the floor
    route = plan(terrain(high, hang=None), Vec2(500, high.top), Vec2(100, FLOOR))
    assert route is not None
    drop = next(s for s in route.steps if s.move is Move.DROP)
    assert drop.end.y - drop.start.y > Planner(terrain()).settings.max_drop


def test_low_underside_is_jumped_up_to_and_hung_from():
    t = terrain(Rect(300, 400, 300, 140), ceiling=None)  # feet hang 34 above the floor
    planner = Planner(t, stick_figure.MOVES)
    under = ceilings(t)[0]
    route = planner.plan(planner.anchor_near(Vec2(50, FLOOR)), planner.anchor_near(under.start))
    assert route is not None and Move.JUMP in moves(route)


def test_reachable_lists_every_surface_a_route_can_get_to():
    t = terrain(FLOATING, ceiling=None)
    planner = Planner(t)
    floor = planner.anchor_near(Vec2(50, FLOOR)).surface
    top = planner.anchor_near(Vec2(500, FLOATING.top)).surface
    assert top.id not in planner.reachable(floor)
    assert floor.id in planner.reachable(top)


# ----- the hanging rig -------------------------------------------------------------


def test_hang_depth_constants_match_the_rigs():
    assert hang_depth(stick_figure.build_stick_figure()) == pytest.approx(
        stick_figure.HANG_DEPTH, abs=1.0
    )
    assert hang_depth(goblin.build_goblin()) == pytest.approx(goblin.HANG_DEPTH, abs=1.0)


@pytest.mark.parametrize("build", [stick_figure.build_stick_figure, goblin.build_goblin])
def test_hanger_holds_the_grip_with_one_hand_always_on(build):
    layout = build()
    driver = HangDriver(layout)
    grip = 100.0
    driver.place(0.0, grip)
    for hand in driver.hand_positions():
        assert hand.y == pytest.approx(grip, abs=0.5)
    x = 0.0
    for _ in range(240):
        x += 30.0 * DT
        pose = driver.update(x, grip, DT)
        assert not all(h.swinging for h in driver.holds)
        transforms = forward_kinematics(layout.skeleton, pose)
        hip = transforms[layout.pelvis].start
        assert hip.y > grip and abs(hip.x - x) < layout.leg_length
        assert min(h.y for h in driver.hand_positions()) == pytest.approx(grip, abs=0.6)
        head = transforms[layout.head].end
        assert head.y - layout.head_radius > grip - 1.5, "the head stays under the grip"


# ----- actors ------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["stickman", "goblin"])
def test_actors_reach_a_floating_window_by_hanging_and_dropping(kind):
    world = SimWorld([FLOATING], FLOOR, WIDTH, ceiling=TOP)
    if kind == "stickman":
        actor = world.add_stickman(Vec2(800, FLOOR))
    else:
        actor = world.add_goblin(Vec2(800, FLOOR - 2))
        actor._replan_wait = 1e9  # no pack orders: just the goal below
    actor.set_goal(Vec2(500, FLOATING.top))
    modes = set()

    def arrived() -> bool:
        modes.add(actor.locomotion.mode)
        return not actor.follower.moving

    run(world, 90.0, arrived)

    assert actor.contact().distance_to(Vec2(500, FLOATING.top)) < 1.0
    assert {PoseMode.CLIMB, PoseMode.HANG, PoseMode.AIR} <= modes
    assert getattr(actor, "animated", True)


def hanging_stickman(world: SimWorld, box: int | None):
    under = next(s for s in world.planner.surfaces if s.hanging and s.box == box)
    man = world.add_stickman(Vec2(50, FLOOR))
    man.follower.reset(Anchor(under, under.point_at(under.low + 30)))
    man.locomotion.teleport(man.follower.command())
    return man


def test_hanging_weapon_is_slung():
    world = SimWorld([FLOATING], FLOOR, WIDTH, ceiling=TOP)
    man = hanging_stickman(world, None)
    man.set_variant("barbarian")
    run(world, 0.2)
    assert man.locomotion.mode is PoseMode.HANG
    assert not man.weapon.held
    grip = man.follower.current_anchor().surface.grip
    for stroke in man.weapon_strokes():
        assert min(stroke.start.y, stroke.end.y) > grip, "slung upside down, under the ceiling"


def test_hanging_actor_is_carried_by_its_moving_box():
    world = SimWorld([Rect(300, 100, 400, 100)], FLOOR, WIDTH, ceiling=TOP)
    man = hanging_stickman(world, 0)
    run(world, 0.2)
    before = man.contact()
    world.boxes[0] = Rect(340, 80, 400, 100)
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -20)}))

    assert man.contact().distance_to(before + Vec2(40, -20)) < 1e-6
    assert man.follower.current_anchor().surface.hanging
    run(world, 0.2)
    assert man.locomotion.mode is PoseMode.HANG and man.animated


def test_hanging_stickman_falls_when_its_window_closes():
    world = SimWorld([Rect(300, 100, 400, 100)], FLOOR, WIDTH, ceiling=TOP)
    man = hanging_stickman(world, 0)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert man.mode is StickMode.RAGDOLL


def test_hanging_goblin_drops_to_the_floor_when_its_window_closes():
    world = SimWorld([Rect(300, 100, 400, 100)], FLOOR, WIDTH, ceiling=TOP)
    gob = world.add_goblin(Vec2(500, FLOOR - 2))
    under = next(s for s in world.goblin_planner.surfaces if s.hanging and s.box == 0)
    gob.follower.reset(Anchor(under, under.point_at(500)))
    gob._replan_wait = 1e9
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert gob.follower.step.move is Move.DROP
    run(world, 2.0)
    assert gob.contact().y == FLOOR


def test_box_moving_mid_mantle_carries_the_climber_instead_of_dropping_him():
    world = SimWorld([Rect(400, 300, 100, 200)], 500.0, 1000.0)
    man = world.add_stickman(Vec2(100, 500))
    man.set_goal(Vec2(450, 300))
    run(
        world, 60.0, lambda: man.follower.step is not None and man.follower.step.move is Move.MANTLE
    )
    assert man.follower.step.move is Move.MANTLE

    world.boxes[0] = Rect(430, 275, 100, 200)
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -25)}))
    run(world, 5.0, lambda: not man.follower.moving)

    assert man.animated
    anchor = man.follower.current_anchor()
    assert anchor.surface.kind is SurfaceKind.TOP and anchor.point.y == 275


def test_wander_only_tries_goals_it_can_reach(monkeypatch):
    world = SimWorld([FLOATING], FLOOR, WIDTH)  # no screen top: the floating top is cut off
    man = world.add_stickman(Vec2(100, FLOOR), wander=True)
    results = []
    original = Planner.plan

    def counting(self, start, goal):
        route = original(self, start, goal)
        results.append(route is not None)
        return route

    monkeypatch.setattr(Planner, "plan", counting)
    for _ in range(40):
        man._pick_wander_goal()
        man.follower.set_route(None)
    assert results and all(results)


def test_goblin_rally_points_are_reachable():
    world = SimWorld([FLOATING], FLOOR, WIDTH)  # floating top is cut off for goblins too
    world.add_goblin(Vec2(100, FLOOR - 2))
    pack = GoblinPack(world)
    floating_top = world.goblin_planner.anchor_near(Vec2(500, FLOATING.top)).surface
    for _ in range(40):
        pack._pick_rally()
        assert pack.rally is not None
        assert not floating_top.contains(pack.rally)

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.planner import Move, Planner
from dungeons_desktops.navigation.terrain import SurfaceKind, Terrain

FLOOR = 500.0


def terrain(*boxes: Rect) -> Terrain:
    return Terrain(boxes, floor_y=FLOOR, left=0.0, right=1000.0)


def kinds(t: Terrain, box: int | None) -> dict[SurfaceKind, list]:
    out: dict[SurfaceKind, list] = {}
    for s in t.surfaces:
        if s.box == box:
            out.setdefault(s.kind, []).append(s)
    return out


def moves(route) -> list[Move]:
    return [step.move for step in route.steps]


def plan_between(t: Terrain, start: Vec2, goal: Vec2):
    planner = Planner(t)
    return planner.plan(planner.anchor_near(start), planner.anchor_near(goal))


def test_box_on_floor_gives_top_two_sides_and_split_floor():
    t = terrain(Rect(400, 300, 100, 200))

    floors = kinds(t, None)[SurfaceKind.FLOOR]
    assert [(f.low, f.high) for f in floors] == [(0.0, 400.0), (500.0, 1000.0)]
    box = kinds(t, 0)
    assert box[SurfaceKind.TOP][0].start == Vec2(400, 300)
    left = box[SurfaceKind.LEFT][0]
    assert left.lip == Vec2(400, 300)
    assert left.start == Vec2(400, 370), "climb ends with hands at the lip, mantle_depth below it"
    assert left.end == Vec2(400, 500)


def test_wall_shorter_than_mantle_depth_mantles_straight_from_the_floor():
    t = terrain(Rect(400, 435, 100, 65))  # too tall to jump onto, shorter than mantle depth
    left = kinds(t, 0)[SurfaceKind.LEFT][0]
    assert left.start == left.end == Vec2(400, 500)

    route = plan_between(t, Vec2(100, FLOOR), Vec2(450, 435))

    assert moves(route) == [Move.WALK, Move.GRAB, Move.MANTLE, Move.WALK]


def test_knee_high_box_is_jumped_onto():
    t = terrain(Rect(400, 450, 100, 50))

    route = plan_between(t, Vec2(100, FLOOR), Vec2(450, 450))

    assert Move.JUMP in moves(route)


def test_overlapping_box_clips_hidden_surfaces():
    # Second box sits over the right half of the first box's top.
    t = terrain(Rect(400, 300, 200, 200), Rect(500, 200, 200, 300))

    first_top = kinds(t, 0)[SurfaceKind.TOP]
    assert [(s.low, s.high) for s in first_top] == [(400.0, 500.0)]
    assert SurfaceKind.RIGHT not in kinds(t, 0), "right side of box 0 is buried inside box 1"
    for surface in t.surfaces:
        for box in t.boxes:
            mid = surface.point_at((surface.low + surface.high) / 2) + surface.normal * 1.0
            assert not (box.left < mid.x < box.right and box.top < mid.y < box.bottom)


def test_floating_wall_extends_down_by_hang_reach():
    t = terrain(Rect(400, 100, 100, 200))
    left = kinds(t, 0)[SurfaceKind.LEFT][0]

    assert left.wall_bottom == 300
    assert left.end.y == pytest.approx(345.0)


def test_route_onto_box_walks_grabs_climbs_and_mantles():
    t = terrain(Rect(400, 300, 100, 200))

    route = plan_between(t, Vec2(100, FLOOR), Vec2(450, 300))

    assert moves(route) == [Move.WALK, Move.GRAB, Move.CLIMB, Move.MANTLE, Move.WALK]
    assert route.steps[-1].end == Vec2(450, 300)
    for a, b in zip(route.steps, route.steps[1:], strict=False):
        assert a.end.distance_to(b.start) < 1e-6


def test_down_from_a_short_box_drops_off_the_edge():
    t = terrain(Rect(400, 380, 100, 120))

    route = plan_between(t, Vec2(450, 380), Vec2(800, FLOOR))

    assert Move.DROP in moves(route)
    assert Move.CLIMB not in moves(route)


def test_low_floating_wall_reached_by_hanging_grab():
    t = terrain(Rect(400, 200, 100, 270))  # bottom 30 above the floor, within hang reach

    route = plan_between(t, Vec2(100, FLOOR), Vec2(450, 200))

    assert route is not None
    assert moves(route)[:3] == [Move.WALK, Move.GRAB, Move.CLIMB]


def test_jump_up_to_a_wall_just_beyond_hang_reach():
    t = terrain(Rect(400, 200, 100, 200))  # bottom 100 above the floor: hang 45 + jump 55

    route = plan_between(t, Vec2(100, FLOOR), Vec2(450, 200))

    assert route is not None
    assert Move.JUMP in moves(route)


def test_high_floating_box_is_unreachable():
    t = terrain(Rect(400, 50, 100, 150))

    assert plan_between(t, Vec2(100, FLOOR), Vec2(450, 50)) is None


def test_stacked_boxes_route_uses_the_lower_box_as_a_step():
    lower = Rect(400, 300, 300, 200)
    upper = Rect(450, 150, 100, 150)  # sits on the lower box
    t = terrain(lower, upper)

    route = plan_between(t, Vec2(100, FLOOR), Vec2(500, 150))

    assert route is not None
    climbs = [s for s in route.steps if s.move is Move.CLIMB]
    assert {s.surface.box for s in climbs} == {0, 1}

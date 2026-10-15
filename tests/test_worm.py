from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.systems.actors import StickMode
from dungeons_desktops.systems.debris import HOLE_LIFE
from dungeons_desktops.systems.world import SimWorld
from dungeons_desktops.systems.worm import (
    MAX_SEGMENTS,
    MAX_SIZE,
    OUT_OF_GROUND_GRACE,
    SEGMENTS_PER_MEAL,
    SPACING,
    WormMode,
)

STEP = 1 / 60
WINDOW = Rect(300, 300, 500, 300)


def world_with(boxes, seed=4) -> SimWorld:
    return SimWorld(boxes, 700.0, 1200.0, ceiling=20.0, seed=seed)


def run(world: SimWorld, seconds: float, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()


def test_burrowing_stays_underground_and_meanders_with_leaps_that_land():
    world = world_with([WINDOW])
    worm = world.add_worm(Vec2(550, 450), 0.0)
    out = {"frames": 0, "longest": 0, "run": 0, "landed": 0, "was_leaping": False}

    def check() -> None:
        if worm.mode is WormMode.BURROW:
            if out["was_leaping"]:
                out["landed"] += 1
            out["was_leaping"] = False
            out["frames"] += not worm.buried(worm.head)
            out["run"] = out["run"] + 1 if not worm.buried(worm.head) else 0
            out["longest"] = max(out["longest"], out["run"])
        else:
            out["was_leaping"] = True

    run(world, 40.0, check)
    assert worm.leaps >= 1
    assert out["landed"] >= 1
    assert out["longest"] * STEP <= OUT_OF_GROUND_GRACE + STEP


def test_body_keeps_its_segment_spacing():
    world = world_with([WINDOW])
    worm = world.add_worm(Vec2(550, 450), 0.0)
    run(world, 10.0)
    for a, b in zip(worm.points, worm.points[1:], strict=False):
        assert abs(a.distance_to(b) - SPACING) < 1e-6


def test_hunts_and_catches_a_stickman_standing_on_its_window():
    world = world_with([WINDOW])
    stickman = world.add_stickman(Vec2(600, WINDOW.top - 2))
    worm = world.add_worm(Vec2(450, 520), 0.0)
    for _ in range(round(12.0 / STEP)):
        world.advance(STEP)
        if worm.catches:
            break
    assert worm.catches >= 1
    assert world.kills == worm.catches
    assert stickman.mode is StickMode.RAGDOLL
    bones = {bone.name for bone in stickman.layout.skeleton.bones}
    assert stickman.severed and stickman.severed <= bones
    assert world.gore.drops
    run(world, 1.0)
    assert world.gore.splats


def test_reaches_a_stickman_standing_on_a_fullscreen_window():
    fullscreen = Rect(0, 20, 1200, 680)
    world = world_with([fullscreen])
    stickman = world.add_stickman(Vec2(600, fullscreen.top - 2))
    worm = world.add_worm(Vec2(450, 300), 0.0)
    assert not worm.buried(stickman.center())
    run(world, 15.0)
    assert worm.catches >= 1
    assert stickman.mode is StickMode.RAGDOLL or stickman not in world.stickmen


def test_each_meal_makes_it_thicker_and_longer_up_to_a_limit():
    world = world_with([WINDOW])
    world.add_stickman(Vec2(600, WINDOW.top - 2))
    worm = world.add_worm(Vec2(450, 520), 0.0)
    length, head = len(worm.points), worm.radius(0)
    run(world, 12.0)
    assert worm.catches >= 1
    assert len(worm.points) == length + SEGMENTS_PER_MEAL * worm.catches
    assert worm.radius(0) > head
    run(world, 1.0)
    for a, b in zip(worm.points, worm.points[1:], strict=False):
        assert abs(a.distance_to(b) - SPACING) < 1e-6

    for _ in range(100):
        worm.grow()
    assert len(worm.points) == MAX_SEGMENTS
    assert worm.size == MAX_SIZE


def test_breaking_out_and_landing_throw_dirt():
    world = world_with([WINDOW])
    world.add_stickman(Vec2(600, WINDOW.top - 2))
    worm = world.add_worm(Vec2(450, 520), 0.0)
    seen = {"rings": 0, "cracked": 0}

    def look() -> None:
        seen["rings"] = max(seen["rings"], len(world.debris.rings))
        seen["cracked"] += any(ring.cracks for ring in world.debris.rings)

    run(world, 12.0, look)
    assert worm.leaps >= 1
    assert seen["rings"] >= 1 and seen["cracked"] > 0


def test_worm_rides_along_with_its_window():
    world = world_with([WINDOW])
    worm = world.add_worm(Vec2(550, 450), 0.0)
    before = list(worm.points)
    world.boxes[0] = WINDOW.moved(60, -30)
    world.apply_terrain(TerrainChange(moves={0: Vec2(60, -30)}))
    moved = [q + Vec2(60, -30) for q in before]
    assert all(p.distance_to(q) < 1e-9 for p, q in zip(worm.points, moved, strict=True))


def test_worm_falls_when_its_window_closes_and_burrows_somewhere_else():
    world = world_with([WINDOW])
    worm = world.add_worm(Vec2(550, 450), 0.0)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 0.5)
    assert worm.mode is WormMode.LEAP
    run(world, 2.0)
    assert worm.mode is WormMode.BURROW
    assert worm.head.y >= world.floor_y - 2.0


def test_breaking_out_tears_a_hole_that_rides_its_window_and_closes():
    world = world_with([WINDOW])
    world.add_stickman(Vec2(600, WINDOW.top - 2))
    worm = world.add_worm(Vec2(450, 520), 0.0)
    for _ in range(round(12.0 / STEP)):
        world.advance(STEP)
        if world.debris.holes:
            break
    hole = world.debris.holes[0]
    assert hole.box == 0 and hole.center.y == WINDOW.top
    assert worm.mode is WormMode.LEAP

    before = hole.center
    world.boxes[0] = WINDOW.moved(30, 10)
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, 10)}))
    assert hole.center == before + Vec2(30, 10)

    run(world, HOLE_LIFE + 0.1)
    assert hole not in world.debris.holes


def test_breaking_out_of_the_bottom_border_tears_a_hole_there():
    world = world_with([])
    world.add_stickman(Vec2(600, world.floor_y))
    world.add_worm(Vec2(450, world.floor_y + 30), 0.0)
    for _ in range(round(12.0 / STEP)):
        world.advance(STEP)
        if world.debris.holes:
            break
    hole = world.debris.holes[0]
    assert hole.box is None and hole.center.y == world.floor_y
    assert hole.ground(world.boxes).top == world.floor_y

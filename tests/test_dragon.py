from itertools import pairwise

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.rig.locomotion import PoseMode
from dungeons_desktops.systems.actors import StickMode
from dungeons_desktops.systems.dragon import STANCE, DragonMode, Flame
from dungeons_desktops.systems.fire import BURN_TIME
from dungeons_desktops.systems.world import SimWorld

STEP = 1 / 60
WINDOW = Rect(300, 400, 500, 300)


def world_with(boxes, seed=3) -> SimWorld:
    return SimWorld(boxes, 700.0, 1200.0, ceiling=20.0, seed=seed)


def run(world: SimWorld, seconds: float, each=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if each is not None:
            each()


def landed(world: SimWorld, point: Vec2, facing: int = 1):
    dragon = world.add_dragon(point - Vec2(0, 40), facing)
    dragon._touch_down(point)
    dragon.ground_timer = 1e9
    return dragon


def test_trot_keeps_planted_feet_still_on_the_ground():
    world = world_with([])
    dragon = landed(world, Vec2(400, 700))
    dragon.wander_x = 900.0
    run(world, 0.5)

    def planted() -> list[bool]:
        return [(dragon.phase + leg.phase_offset) % 1.0 < STANCE for leg in dragon.legs]

    previous, was_planted = [leg.foot for leg in dragon.legs], planted()
    slid = 0.0
    for _ in range(240):
        world.advance(STEP)
        now_planted = planted()
        for i, leg in enumerate(dragon.legs):
            if was_planted[i] and now_planted[i] and dragon.gait > 0.99:
                slid = max(slid, abs(leg.foot.x - previous[i].x))
        previous, was_planted = [leg.foot for leg in dragon.legs], now_planted
    assert dragon.x > 420.0
    assert slid < 0.5
    assert all(leg.foot.y <= world.floor_y + 1e-6 for leg in dragon.legs)


def test_swipes_a_stickman_in_reach():
    world = world_with([])
    dragon = landed(world, Vec2(400, 700))
    stickman = world.add_stickman(Vec2(470, 700))
    modes = set()
    run(world, 5.0, lambda: modes.add(dragon.mode))
    assert DragonMode.SWIPE in modes
    assert stickman.mode is StickMode.RAGDOLL or stickman not in world.stickmen
    assert world.kills >= 1


def test_flies_strafes_with_fire_and_lands_on_a_surface():
    world = world_with([WINDOW])
    dragon = world.add_dragon(Vec2(100, 150), 1, variant="red")
    for x in (500, 900, 1100):
        world.add_stickman(Vec2(x, 700), wander=True)
    seen = {"fire": False, "low": 1e9, "high": -1e9}

    def watch() -> None:
        seen["fire"] |= bool(dragon.flames)
        seen["low"] = min(seen["low"], dragon.body.x)
        seen["high"] = max(seen["high"], dragon.body.x)
        assert world.ceiling <= dragon.body.y <= world.floor_y

    run(world, 30.0, watch)
    assert seen["fire"]
    assert world.kills >= 1
    assert seen["high"] - seen["low"] > 600.0
    assert dragon.mode in (DragonMode.WALK, DragonMode.SWIPE)
    assert any(leg.foot.y in (WINDOW.top, world.floor_y) for leg in dragon.legs)


def climber_on(world: SimWorld, start: Vec2, hold: Vec2):
    stickman = world.add_stickman(start)
    stickman.set_goal(hold)
    run(world, 25.0)
    assert stickman.locomotion.mode is PoseMode.CLIMB
    assert stickman.contact().distance_to(hold) < 1.0
    return stickman


@pytest.mark.parametrize(
    ("start", "hold", "dragon_x", "facing"),
    [
        (Vec2(250, 700), Vec2(WINDOW.left, 520), 100, 1),
        (Vec2(850, 700), Vec2(WINDOW.right, 560), 1100, -1),
        (Vec2(60, 700), Vec2(0, 450), 600, 1),
        (Vec2(1140, 700), Vec2(1200, 420), 600, -1),
    ],
)
def test_strafes_a_stickman_climbing_a_wall(start, hold, dragon_x, facing):
    world = world_with([WINDOW])
    stickman = climber_on(world, start, hold)
    dragon = world.add_dragon(Vec2(dragon_x, 150), facing, variant="red")
    dragon.flight_timer = 1e9

    def watch() -> None:
        for point in (dragon.head, dragon.shoulder, dragon.body, dragon.hip):
            assert not WINDOW.contains(point)
            assert world.left <= point.x <= world.width

    for _ in range(round(10.0 / STEP)):
        world.advance(STEP)
        watch()
        if not stickman.animated:
            break
    assert stickman.burn is not None and stickman.mode is StickMode.RAGDOLL
    assert stickman.contact().distance_to(hold) < 1.0


def test_rides_its_window_and_takes_off_when_it_closes():
    world = world_with([WINDOW])
    dragon = landed(world, Vec2(550, WINDOW.top))
    world.boxes[0] = WINDOW.moved(40, -20)
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -20)}))
    run(world, STEP)
    assert abs(dragon.x - 590) < 2.0
    assert dragon.support.start.y == WINDOW.top - 20

    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert dragon.mode is DragonMode.FLY


def test_fire_sets_a_stickman_burning_until_he_despawns():
    world = world_with([])
    dragon = world.add_dragon(Vec2(100, 150), 1, variant="red")
    dragon.flight_timer = 1e9
    stickman = world.add_stickman(Vec2(600, 700))
    run(world, 0.2)
    dragon.flames.append(Flame(stickman.center(), Vec2(0, 0)))
    run(world, STEP)
    assert stickman.burn is not None and stickman.mode is StickMode.RAGDOLL
    assert world.kills == 1

    run(world, BURN_TIME * 0.7)
    assert stickman in world.stickmen
    assert stickman.burn.embers
    assert stickman.burn.char == 1.0
    run(world, BURN_TIME * 0.3 + 0.1)
    assert stickman not in world.stickmen


@pytest.mark.parametrize("offset", [-20.0, 0.0, 12.0])
def test_mauls_a_stickman_under_its_body_without_turning_round(offset):
    world = world_with([])
    dragon = landed(world, Vec2(400, 700))
    stickman = world.add_stickman(Vec2(400 + offset, 700))
    stickman.update = lambda dt: None
    hits = []
    stickman.hurt = lambda *args, **kwargs: hits.append(1) or False
    run(world, 3.0)
    assert len(hits) >= 2
    assert dragon.facing == 1 or offset < 0.0


def flying_over(world: SimWorld, dragon_x: float, man_x: float, height: float = 150.0):
    dragon = world.add_dragon(Vec2(dragon_x, height), 1, variant="red")
    dragon.flight_timer = 1e9
    dragon.velocity = Vec2(190, 0)
    stickman = world.add_stickman(Vec2(man_x, 700))
    stickman.update = lambda dt: None
    deaths = []
    stickman.hurt = lambda *args, **kwargs: deaths.append(args[4]) or False
    return dragon, deaths


def test_wheels_round_in_the_air_to_breathe_on_prey_behind_it():
    world = world_with([])
    dragon, deaths = flying_over(world, 700, 450, height=600)
    run(world, 0.6)
    assert dragon.facing == -1
    assert dragon.body.x < 800.0
    run(world, 1.5)
    assert "Roasted by the red dragon!" in deaths


def test_does_not_flip_flop_over_prey_right_below_it():
    world = world_with([])
    dragon, _ = flying_over(world, 600, 605)
    flips, facing = [], dragon.facing
    for i in range(round(12.0 / STEP)):
        world.advance(STEP)
        if dragon.facing != facing:
            flips.append(i * STEP)
            facing = dragon.facing
    gaps = [b - a for a, b in pairwise(flips)]
    assert len(flips) >= 2
    assert min(gaps) > 1.5


def test_does_not_maul_a_stickman_well_behind_it():
    world = world_with([])
    dragon = landed(world, Vec2(400, 700))
    stickman = world.add_stickman(Vec2(330, 700))
    assert not dragon._within_claws(stickman)

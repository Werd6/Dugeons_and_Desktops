import math

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.actors.mortal import (
    DRAGON_HP,
    FADE_TIME,
    GOBLIN_HP,
    WORM_HP,
)
from dungeons_desktops.game.defenders.dragon.actor import LYING_HEIGHT, DragonMode
from dungeons_desktops.game.defenders.goblins.actor import PACK
from dungeons_desktops.game.defenders.worm.actor import WormMode
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1.0 / 60.0
FLOOR = 700.0
PUSH = Vec2(100.0, -40.0)


def world_with(boxes=(), seed=3) -> SimWorld:
    return SimWorld(list(boxes), FLOOR, 1200.0, ceiling=20.0, seed=seed)


def run(world, seconds: float) -> None:
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def frozen_goblin(world: SimWorld, x: float):
    """A goblin that stands still, so every attack on it is in reach."""
    goblin = world.add_goblin(Vec2(x, FLOOR), "flag")
    goblin.update = lambda dt: None
    return goblin


def kill(world, monster) -> None:
    while monster in world.goblins or monster in world.worms or monster in world.dragons:
        world.hurt_monster(monster, 1, world.locate(monster) or monster_point(monster), PUSH)


def monster_point(monster) -> Vec2:
    return getattr(monster, "body", None) or monster.head


def test_monster_hp():
    world = world_with()
    assert (GOBLIN_HP, WORM_HP, DRAGON_HP) == (5, 4, 15)
    assert world.add_goblin(Vec2(300, FLOOR)).hp == GOBLIN_HP
    assert world.add_worm().hp == WORM_HP
    assert world.add_dragon().hp == DRAGON_HP


@pytest.mark.parametrize("name", ["barbarian", "rogue", "paladin"])
def test_each_melee_attack_does_exactly_one_damage(name):
    world = world_with()
    fighter = world.add_stickman(Vec2(300, FLOOR), name)
    goblin = frozen_goblin(world, 318)
    attacks, busy = 0, False
    for _ in range(round(3.0 / DT)):
        world.advance(DT)
        attacks += fighter.weapon.busy and not busy
        busy = fighter.weapon.busy
    while fighter.weapon.busy:
        world.advance(DT)
    assert attacks >= 2
    assert goblin.damage == attacks


def test_an_arrow_that_hits_does_one_damage():
    world = world_with()
    goblin = frozen_goblin(world, 600)
    world.spells.shoot(goblin.center() - Vec2(80, 0), Vec2(700, 0))
    run(world, 1.0)
    assert not world.spells.arrows
    assert goblin.damage == 1


def test_a_missile_that_arrives_does_one_damage():
    world = world_with()
    goblin = frozen_goblin(world, 600)
    world.spells.cast_missile(goblin.center() - Vec2(200, 0), goblin, goblin.center())
    run(world, 1.5)
    assert not world.spells.missiles
    assert goblin.damage == 1


@pytest.mark.parametrize("name", ["ranger", "wizard", "sorcerer"])
def test_ranged_adventurers_wear_a_goblin_down(name):
    world = world_with()
    world.add_stickman(Vec2(300, FLOOR), name)
    goblin = frozen_goblin(world, 520)
    run(world, 6.0)
    assert goblin.damage >= 2


def test_seven_hits_kill_a_goblin_which_ragdolls_fades_and_despawns():
    world = world_with()
    goblin = world.add_goblin(Vec2(400, FLOOR), "sword")
    for _ in range(GOBLIN_HP - 1):
        assert not world.hurt_monster(goblin, 1, goblin.center(), PUSH)
    assert goblin in world.goblins and goblin.hp == 1
    assert world.hurt_monster(goblin, 1, goblin.center(), PUSH)
    assert goblin not in world.goblins and goblin in world.fallen
    assert goblin.dead and goblin.ragdoll is not None and not goblin.weapon.held
    assert not world.hurt_monster(goblin, 1, goblin.center(), PUSH), "already dead"

    head_before = goblin.transforms()[goblin.layout.head].end
    run(world, 1.0)
    head_after = goblin.transforms()[goblin.layout.head].end
    assert head_after.y > head_before.y + 3.0, "it slumps to the ground"
    assert goblin.fade == 0.0
    run(world, goblin.linger - 1.0 + FADE_TIME * 0.5)
    assert 0.0 < goblin.fade < 1.0
    run(world, FADE_TIME)
    assert goblin.gone and goblin not in world.fallen


def test_dragon_shot_down_in_the_air_falls_onto_the_window_below():
    box = Rect(450, 500, 300, 200)
    world = world_with([box])
    dragon = world.add_dragon(Vec2(600, 200), facing=1)
    run(world, 0.2)
    assert dragon.flying
    kill(world, dragon)
    assert dragon in world.fallen and dragon.mode is DragonMode.DEAD
    run(world, 3.0)
    assert dragon.body.y == pytest.approx(box.top - LYING_HEIGHT, abs=1.0)
    assert all(leg.foot.y <= box.top + 1.0 for leg in dragon.legs)
    assert all(p.y <= box.top + 1.0 for p in dragon.tail)
    assert dragon.head.y <= box.top


def test_dragon_falls_to_the_floor_with_nothing_below():
    world = world_with()
    dragon = world.add_dragon(Vec2(600, 150), facing=-1)
    kill(world, dragon)
    run(world, 3.0)
    assert dragon.body.y == pytest.approx(FLOOR - LYING_HEIGHT, abs=1.0)
    assert dragon.flames == [] or all(f.position.y < FLOOR for f in dragon.flames)


def test_worm_killed_mid_leap_flops_onto_the_floor():
    world = world_with()
    worm = world.add_worm(Vec2(600, 400), 0.0)
    worm.mode = WormMode.LEAP
    worm.velocity = Vec2(150, -100)
    kill(world, worm)
    assert worm in world.fallen and worm.dead
    run(world, 3.0)
    for i, point in enumerate(worm.points):
        assert point.y == pytest.approx(FLOOR - worm.radius(i), abs=1.5)


def test_worm_half_out_of_the_ground_keeps_its_buried_part_in_place():
    world = world_with()
    worm = world.add_worm(Vec2(600, FLOOR - 40), -math.pi / 2)
    worm.mode = WormMode.LEAP
    buried = [i for i, p in enumerate(worm.points) if worm.buried(p)]
    assert buried and 0 not in buried
    before = {i: worm.points[i] for i in buried}
    kill(world, worm)
    run(world, 3.0)
    assert all(worm.points[i] == before[i] for i in buried)
    assert worm.head.y <= FLOOR - worm.radius(0) + 1.0
    assert worm.head.y > FLOOR - 40 + 10, "the exposed part flops over"


# ----- desktop session ---------------------------------------------------------

SCREEN = Rect(0, 0, 1400, 900)
USABLE = Rect(0, 30, 1400, 800)


def session(**kwargs) -> DesktopSession:
    options = {"seed": 5, "max_stickmen": 0, **kwargs}
    return DesktopSession(SCREEN, USABLE, FakeWindowSource([]), **options)


def test_the_next_defender_takes_over_once_the_current_one_is_dead_not_on_kills():
    world = session(defenders=("worm", "goblins"))
    worm = world.worms[0]
    world.kills = 12
    run(world, DT)
    assert world.defender == "worm" and world.defender_health == 1.0
    kill(world, worm)
    run(world, DT)
    assert world.defender == "goblins" and len(world.goblins) == len(PACK)
    assert worm in world.fallen, "the body is left to fade"
    assert world.defender_health == 1.0


def test_goblin_health_is_the_whole_pack():
    world = session(defenders=("goblins",))
    assert world.defender_max_hp == len(PACK) * GOBLIN_HP
    first, second = world.goblins[0], world.goblins[1]
    kill(world, first)
    world.hurt_monster(second, 3, second.center(), PUSH)
    assert world.defender_health == pytest.approx(
        (len(PACK) * GOBLIN_HP - GOBLIN_HP - 3) / (len(PACK) * GOBLIN_HP)
    )
    for goblin in list(world.goblins):
        kill(world, goblin)
    run(world, DT)
    assert len(world.goblins) == len(PACK) and world.defender_health == 1.0


def test_dragon_health_bar():
    world = session(defenders=("dragon",))
    dragon = world.dragons[0]
    world.hurt_monster(dragon, 5, dragon.body, PUSH)
    assert world.defender_health == pytest.approx((DRAGON_HP - 5) / DRAGON_HP)


def test_dismissing_a_defender_leaves_its_dead_behind():
    world = session(defenders=("goblins", "dragon"))
    dead = world.goblins[0]
    kill(world, dead)
    world.rotate()
    assert dead in world.fallen and not world.goblins
    assert world.defender == "dragon" and len(world.dragons) == 1


def test_no_defenders_means_no_health_bar_and_no_rotation():
    world = session(defenders=())
    run(world, DT)
    assert world.defender_health is None and not world.dragons

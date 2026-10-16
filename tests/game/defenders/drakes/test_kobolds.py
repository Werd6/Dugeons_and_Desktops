from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DEFENDERS, DRAKE_PACK, DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.defenders.drakes.drake import ARROW_DAMAGE, DRAKE_HP
from dungeons_desktops.game.defenders.drakes.kobold import (
    FLEE_RANGE,
    KOBOLD_HP,
    TRAP_ARMING,
    TRAP_COOLDOWN,
    TRAP_DAMAGE,
    Kobold,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

STEP = 1 / 60


def run(world, seconds: float, until=None) -> None:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until is not None and until():
            return


def unkillable(*stickmen):
    hits = []
    for stickman in stickmen:

        def hurt(amount, point, push, source, death, bleed=True, who=stickman):
            hits.append((who, source, amount))
            return False

        stickman.hurt = hurt
    return hits


def test_when_its_drake_dies_the_kobold_jumps_off_and_lands_on_his_feet():
    world = SimWorld([Rect(300, 300, 300, 100)], 400.0, 1000.0, ceiling=0.0, seed=2)
    drake = world.add_drake(Vec2(450, 300), "green", facing=1)
    seat = drake.seat
    world.hurt_monster(drake, DRAKE_HP, drake.body, Vec2(0.0, 0.0))
    assert len(world.kobolds) == 1
    kobold = world.kobolds[0]
    assert kobold.variant == "green" and kobold.airborne
    assert kobold.foot.distance_to(seat) < 1.0
    assert kobold in world.monsters() and world.monster_at(kobold.rider_head) is kobold
    run(world, 1.5, until=lambda: not kobold.airborne)
    assert not kobold.airborne and kobold.foot.y == 300.0


def test_on_foot_he_shoots_then_runs_from_a_close_adventurer_while_he_reloads():
    world = SimWorld([], 400.0, 1400.0, ceiling=0.0, seed=2)
    kobold = world.add_kobold(Vec2(500, 400), "blue")
    man = world.add_stickman(Vec2(540, 400))
    man.stop()
    hits = unkillable(man)
    kobold.trap_cooldown = 99.0
    kobold.bow_cooldown = 0.0
    run(world, 1.0, until=lambda: bool(kobold.arrows))
    assert kobold.arrows and abs(kobold.foot.x - 500.0) < 2.0
    run(world, 0.6)
    assert kobold.speed < -20.0
    run(world, 3.0)
    assert man.contact().x - kobold.foot.x >= FLEE_RANGE - 2.0
    run(world, 4.0)
    assert (man, "kobold", ARROW_DAMAGE) in hits
    assert sum(1 for _, source, _ in hits if source == "kobold") >= 3


def test_he_runs_off_a_window_edge_to_get_away():
    world = SimWorld([Rect(300, 300, 200, 100)], 400.0, 1000.0, ceiling=0.0, seed=2)
    kobold = world.add_kobold(Vec2(330, 300), "white")
    man = world.add_stickman(Vec2(420, 300))
    man.stop()
    unkillable(man)
    kobold.bow_cooldown = 5.0
    kobold.trap_cooldown = 99.0
    run(world, 3.0, until=lambda: kobold.foot.y == 400.0 and not kobold.airborne)
    assert kobold.foot.y == 400.0 and kobold.foot.x < 300.0


def test_mounted_or_not_kobolds_drop_traps_on_a_cooldown_that_fall_to_the_ground():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=2)
    drake = world.add_drake(Vec2(300, 400), "red")
    drake.max_hp = 999
    man = world.add_stickman(Vec2(450, 400))
    man.stop()
    unkillable(man)
    drake.trap_cooldown = 0.2
    drake._walk = lambda dt: None
    run(world, 0.5)
    assert len(world.traps.traps) == 1
    run(world, 1.0)
    trap = world.traps.traps[0]
    assert not trap.falling and trap.position.y == 400.0
    assert abs(drake.trap_cooldown - (TRAP_COOLDOWN - 1.3)) < 0.1
    kobold = world.add_kobold(Vec2(600, 400), "black")
    kobold.trap_cooldown = 0.1
    run(world, 0.3)
    assert len(world.traps.traps) >= 2


def test_a_trap_arms_then_snaps_shut_on_the_first_adventurer_to_step_on_it():
    world = SimWorld([], 400.0, 1000.0, ceiling=0.0, seed=2)
    trap = world.traps.drop(Vec2(500, 380), "red")
    man = world.add_stickman(Vec2(498, 400))
    man.stop()
    hits = unkillable(man)
    run(world, TRAP_ARMING * 0.5)
    assert not trap.armed and not hits
    run(world, TRAP_ARMING + 0.2)
    assert hits == [(man, "kobold trap", TRAP_DAMAGE)]
    run(world, 1.0)
    assert not world.traps.traps


def test_a_trap_rides_its_window_and_drops_when_the_window_closes():
    world = SimWorld([Rect(300, 300, 300, 100)], 400.0, 1000.0, ceiling=0.0, seed=2)
    trap = world.traps.drop(Vec2(450, 290), "blue")
    run(world, 0.5)
    assert trap.position.y == 300.0
    world.boxes[0] = Rect(330, 280, 300, 120)
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}))
    assert trap.position == Vec2(480, 280) and not trap.falling
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    run(world, 1.0)
    assert trap.position.y == 400.0


def test_riders_on_foot_fight_on_until_the_last_drake_dies_then_vanish():
    window = Rect(300, 300, 600, 400)
    world = DesktopSession(
        Rect(0, 0, 1400, 900),
        Rect(0, 30, 1400, 800),
        FakeWindowSource([WindowRecord(1, window)]),
        seed=3,
        max_stickmen=0,
        defenders=DEFENDERS[DEFENDERS.index("drakes") :],
    )
    assert world.defender == "drakes"
    assert world.defender_max_hp == DRAKE_PACK * (DRAKE_HP + KOBOLD_HP)
    assert world.defender_health == 1.0
    *first, last = list(world.drakes)
    for drake in first:
        world.hurt_monster(drake, DRAKE_HP, drake.body, Vec2(0.0, 0.0))
    run(world, 1.0)
    assert world.defender == "drakes" and len(world.kobolds) == DRAKE_PACK - 1
    assert all(isinstance(k, Kobold) and k in world.live_monsters for k in world.kobolds)
    world.hurt_monster(world.kobolds[0], KOBOLD_HP, world.kobolds[0].center(), Vec2(0.0, 0.0))
    assert world.defender == "drakes" and len(world.kobolds) == DRAKE_PACK - 2
    world.hurt_monster(last, DRAKE_HP, last.body, Vec2(0.0, 0.0))
    run(world, 0.1)
    assert not world.kobolds and not world.drakes
    assert world.defender == "hydra"

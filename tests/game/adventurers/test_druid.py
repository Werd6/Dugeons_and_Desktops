from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.adventurers.weapons import DruidStaff
from dungeons_desktops.game.defenders.worm.actor import WormMode
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1.0 / 60.0


def run(world: SimWorld, seconds: float, until=None) -> None:
    for _ in range(int(seconds / DT)):
        world.advance(DT)
        if until is not None and until():
            return


def test_druid_carries_a_staff_and_has_short_reach():
    world = SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=3)
    druid = world.add_stickman(Vec2(300, 700), "druid")
    assert isinstance(druid.weapon, DruidStaff)
    assert druid.calling.reach <= 80.0


def test_vines_hit_a_goblin_in_reach_for_one():
    world = SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=3)
    world.add_stickman(Vec2(300, 700), "druid")
    goblin = world.add_goblin(Vec2(340, 700), "flag")
    grew = False

    def hit() -> bool:
        nonlocal grew
        grew |= bool(world.spells.vines)
        return goblin.damage > 0

    run(world, 2.0, until=hit)
    assert grew and goblin.damage == 1


def test_vines_ignore_monsters_out_of_reach():
    world = SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=3)
    world.add_stickman(Vec2(300, 700), "druid")
    goblin = world.add_goblin(Vec2(600, 700), "flag")
    goblin.update = lambda dt: None
    run(world, 1.5)
    assert goblin.damage == 0 and not world.spells.vines


def burrowing_worm_beside(world: SimWorld, box: Rect):
    worm = world.add_worm(Vec2(box.left + 20, box.bottom - 25), heading=0.0)
    worm.update = lambda dt: None
    assert worm.mode is WormMode.BURROW and worm.buried(worm.head)
    return worm


def test_vines_reach_a_worm_burrowing_in_a_window():
    box = Rect(330, 600, 200, 100)
    world = SimWorld([box], 700.0, 1200.0, ceiling=20.0, seed=3)
    world.add_stickman(Vec2(300, 700), "druid")
    worm = burrowing_worm_beside(world, box)
    run(world, 2.0, until=lambda: worm.damage > 0)
    assert worm.damage == 1


def test_other_classes_cannot_reach_a_burrowing_worm():
    box = Rect(330, 600, 200, 100)
    world = SimWorld([box], 700.0, 1200.0, ceiling=20.0, seed=3)
    world.add_stickman(Vec2(300, 700), "barbarian")
    world.add_stickman(Vec2(250, 700), "ranger")
    worm = burrowing_worm_beside(world, box)
    run(world, 2.0)
    assert worm.damage == 0

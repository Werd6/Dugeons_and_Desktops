from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import WORM_DAMAGE
from dungeons_desktops.game.adventurers.weapons import Bombs
from dungeons_desktops.game.defenders.worm.actor import WormMode
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1.0 / 60.0


def world_with(seed=3) -> SimWorld:
    return SimWorld([], 700.0, 1200.0, ceiling=20.0, seed=seed)


def run(world: SimWorld, seconds: float, until=None) -> None:
    for _ in range(int(seconds / DT)):
        world.advance(DT)
        if until is not None and until():
            return


def test_alchemist_carries_bombs():
    world = world_with()
    alchemist = world.add_stickman(Vec2(300, 700), "alchemist")
    assert isinstance(alchemist.weapon, Bombs)
    kinds = {stroke.kind for stroke in alchemist.weapon_strokes()}
    assert "bomb" in kinds


def test_lobs_a_bomb_that_hurts_a_goblin_for_one():
    world = world_with()
    alchemist = world.add_stickman(Vec2(300, 700), "alchemist")
    goblin = world.add_goblin(Vec2(450, 700), "flag")
    thrown = False

    def landed() -> bool:
        nonlocal thrown
        thrown |= bool(world.vials.flying)
        return goblin.damage > 0

    run(world, 3.0, until=landed)
    assert thrown and goblin.damage == 1
    assert alchemist.damage == 0


def test_a_blast_hits_every_monster_in_it_once_and_spares_adventurers():
    world = world_with()
    friend = world.add_stickman(Vec2(400, 700), "wizard")
    near = [world.add_goblin(Vec2(400 + dx, 700), "flag") for dx in (-8, 8)]
    far = world.add_goblin(Vec2(600, 700), "flag")
    world.detonate(near[0].center().lerp(near[1].center(), 0.5))
    world.advance(DT)
    assert [g.damage for g in near] == [1, 1]
    assert far.damage == 0 and friend.damage == 0 and friend.animated
    assert world.vials.explosions


def test_eaten_by_the_worm_it_explodes_for_one():
    world = world_with()
    alchemist = world.add_stickman(Vec2(400, 700), "alchemist")
    worm = world.add_worm(alchemist.center() + Vec2(0, 5), heading=-1.57)
    worm.mode = WormMode.LEAP
    assert alchemist.hurt(WORM_DAMAGE, alchemist.center(), Vec2(0, -100), "worm", "Eaten!")
    world.advance(DT)
    assert worm.damage == 1


def test_other_classes_eaten_by_the_worm_do_not_explode():
    world = world_with()
    wizard = world.add_stickman(Vec2(400, 700), "wizard")
    worm = world.add_worm(wizard.center() + Vec2(0, 5), heading=-1.57)
    worm.mode = WormMode.LEAP
    wizard.hurt(WORM_DAMAGE, wizard.center(), Vec2(0, -100), "worm", "Eaten!")
    world.advance(DT)
    assert worm.damage == 0

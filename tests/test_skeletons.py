from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource, WindowRecord
from dungeons_desktops.game.actors.mortal import LICH_HP
from dungeons_desktops.game.defenders.goblins.actor import Goblin
from dungeons_desktops.game.defenders.lich.skeletons import RISE_TIME, SKELETON_CAP, Skeleton
from dungeons_desktops.game.defenders.lich.spells import RISE_DELAY, WORD_DELAY
from dungeons_desktops.game.world.simulation import SimWorld

STEP = 1 / 60
FLOOR = 700.0


def run(world, seconds: float, until=None) -> bool:
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if until is not None and until():
            return True
    return until is None


def world_with_lich(*boxes: Rect) -> SimWorld:
    world = SimWorld(list(boxes), FLOOR, 1400.0, ceiling=20.0, seed=3)
    lich = world.add_lich(Vec2(60, FLOOR))
    lich.cast_wait = lich.door_wait = 1e9
    return world


def idle(world: SimWorld, x: float, variant: str = "wizard"):
    man = world.add_stickman(Vec2(x, FLOOR), variant)
    man.wander = False
    return man


def raised(world: SimWorld, x: float) -> Skeleton:
    body = idle(world, x)
    body.hurt(99, body.center(), Vec2(0, 0), "lich", "Slain")
    skeleton = world.raise_skeleton(body)
    assert skeleton is not None
    return skeleton


def test_a_lich_spell_kill_rises_as_a_two_hp_skeleton_where_he_fell():
    world = world_with_lich()
    victim = idle(world, 600, "ranger")
    world.necromancy.cast("power_word_kill", None, Vec2(200, 670), victim)
    run(world, WORD_DELAY + 0.1)
    assert not victim.animated and not world.skeletons
    run(world, RISE_DELAY)
    assert len(world.skeletons) == 1 and victim not in world.stickmen
    skeleton = world.skeletons[0]
    assert isinstance(skeleton, Goblin) and skeleton.hp == skeleton.max_hp == 2
    assert abs(skeleton.contact().x - 600) < 30 and skeleton.contact().y == FLOOR
    assert skeleton.variant == "ranger" and skeleton.rising < 1.0
    assert world.necromancy.raised == 1


def test_skeletons_hunt_and_cut_down_adventurers_who_stay_dead():
    world = world_with_lich()
    skeleton = raised(world, 400)
    foe = idle(world, 520)
    foe.paralyze(30.0)
    assert run(world, 15.0, until=lambda: not foe.animated)
    assert skeleton.kills == 1 and world.kills >= 2
    run(world, RISE_DELAY + 0.5)
    assert len(world.skeletons) == 1


def test_adventurers_can_find_hit_and_destroy_skeletons():
    world = world_with_lich()
    skeleton = raised(world, 500)
    run(world, RISE_TIME + 0.1)
    assert skeleton in world.monsters() and world.locate(skeleton) is not None
    assert world.monster_at(skeleton.center()) is skeleton
    assert world.closest_part(skeleton, Vec2(500, 600)) is not None
    world.hurt_monster(skeleton, 1, skeleton.center(), Vec2(0, 0))
    assert not skeleton.dead
    world.hurt_monster(skeleton, 1, skeleton.center(), Vec2(30, -10))
    assert skeleton.dead and skeleton not in world.skeletons and skeleton in world.fallen
    assert run(world, 6.0, until=lambda: skeleton not in world.fallen)


def test_skeletons_keep_their_distance_from_each_other():
    world = world_with_lich()
    bones = [raised(world, 500 + i) for i in range(4)]
    foe = idle(world, 800, "barbarian")
    foe.paralyze(30.0)
    run(world, 7.5)
    assert foe.animated
    xs = sorted(b.contact().x for b in bones if not b.dead)
    assert len(xs) == 4 and all(b - a > 8.0 for a, b in zip(xs, xs[1:], strict=False))


def test_no_more_than_the_cap_rise():
    world = world_with_lich()
    for i in range(SKELETON_CAP + 3):
        body = idle(world, 200 + 60 * i)
        body.hurt(99, body.center(), Vec2(0, 0), "lich", "Slain")
        world.raise_skeleton(body)
    assert len(world.skeletons) == SKELETON_CAP


def test_only_the_lich_spells_raise_the_dead():
    world = world_with_lich()
    victim = idle(world, 600)
    victim.hurt(99, victim.center(), Vec2(0, 0), "goblin", "Slain")
    run(world, RISE_DELAY + 0.5)
    assert not world.skeletons


def test_skeletons_are_not_the_defender_and_crumble_when_the_lich_falls():
    screen, usable = Rect(0, 0, 1400, 900), Rect(0, 30, 1400, 800)
    source = FakeWindowSource([WindowRecord(1, Rect(400, 400, 400, 200))])
    session = DesktopSession(screen, usable, source, seed=2, max_stickmen=0)
    session.rotate()  # past the chimera
    session.rotate()  # past the drow
    session.rotate()  # past the drake riders
    session.rotate()
    session.rotate()
    lich = session.liches[0]
    bones = [raised(session, 300), raised(session, 900)]
    assert session.live_monsters == [lich] and session.defender_health == 1.0
    session.hurt_monster(bones[0], 1, bones[0].center(), Vec2(0, 0))
    assert session.defender_health == 1.0
    session.hurt_monster(lich, LICH_HP, lich.center(), Vec2(0, -40))
    run(session, 0.1)
    assert session.defender == "minotaur"
    assert run(session, 2.0, until=lambda: not session.skeletons)
    assert all(b.dead for b in bones)

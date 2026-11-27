"""Soul collection, orbiting, and Heroes Never Die resurrection."""

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.hero_cleric.souls import RESURRECTION_RELEASE
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def scene():
    world = SimWorld([], 300, 1000, seed=4)
    hero = world.add_stickman(Vec2(500, 300), "hero_cleric")
    return world, hero


def kill(actor, source="test"):
    point = actor.transforms()[actor.layout.head].end
    actor.hurt(actor.max_hp, point, Vec2(0, -10), source, "Fallen")


def test_fallen_adventurer_soul_zooms_to_the_nearest_cleric_and_orbits():
    world, hero = scene()
    other = world.add_stickman(Vec2(900, 300), "hero_cleric")
    fighter = world.add_stickman(Vec2(420, 300), "fighter")
    death_point = fighter.transforms()[fighter.layout.head].end
    kill(fighter)
    assert len(hero.souls) == 1 and not other.souls
    soul = hero.souls[0]
    assert soul.original_variant == "fighter" and soul.point == death_point and soul.flying
    advance(world, 0.5)
    assert not soul.flying and soul.point.distance_to(hero.soul_center()) < 50
    before = soul.point
    advance(world, 0.25)
    assert soul.orbit_age > 0 and soul.point.distance_to(before) > 1


def test_only_regular_free_adventurers_leave_resurrectable_souls():
    world, hero = scene()
    slayer = world.add_stickman(Vec2(400, 300), "hero_rogue")
    thrall = world.add_stickman(Vec2(430, 300), "wizard")
    thrall.enthrall()
    kill(slayer)
    kill(thrall)
    assert not hero.souls


@pytest.mark.parametrize("death", ["damage", "fire", "acid"])
def test_damage_fire_and_demise_each_capture_exactly_one_soul(death):
    world, hero = scene()
    ranger = world.add_stickman(Vec2(400, 300), "ranger")
    if death == "damage":
        kill(ranger)
    elif death == "fire":
        ranger.ignite()
        ranger.ignite()
    else:
        ranger.succumb("acid")
        ranger.succumb("acid")
    assert len(hero.souls) == 1 and hero.souls[0].original_variant == "ranger"


def test_manual_cast_resurrects_every_soul_with_the_requested_class_odds(monkeypatch):
    world, hero = scene()
    for variant in ("fighter", "ranger", "wizard"):
        soul = hero.capture_soul(variant, hero.center())
        soul.flying = False
    rolls = iter((0.1, 0.3, 0.8))
    monkeypatch.setattr(world.random, "random", lambda: next(rolls, 0.8))
    spawn_points = []
    add_stickman = world.add_stickman

    def record_spawn(point=None, variant="unarmed", wander=False):
        spawn_points.append(point)
        return add_stickman(point, variant, wander)

    monkeypatch.setattr(world, "add_stickman", record_spawn)
    cast_point = hero.contact()
    assert hero.heroes_never_die() and hero.resurrection_cast
    advance(world, RESURRECTION_RELEASE + 0.1)
    raised = [actor for actor in world.stickmen if actor is not hero and actor.animated]
    assert [actor.variant for actor in raised] == ["cleric", "paladin", "wizard"]
    assert all(actor.hp == actor.max_hp and actor.wander for actor in raised)
    assert spawn_points == [cast_point, cast_point, cast_point]
    assert not hero.souls and hero.resurrection_flash > 0


def test_autonomous_cast_waits_for_the_soul_to_arrive_and_complete_a_visible_orbit():
    world, hero = scene()
    fighter = world.add_stickman(Vec2(100, 300), "fighter")
    kill(fighter)
    advance(world, 2.5)
    assert hero.souls and not hero.resurrection_cast
    assert not [s for s in world.stickmen if s is not hero and s.animated]
    advance(world, 2)
    assert not hero.souls
    assert any(s is not hero and s.animated for s in world.stickmen)


def test_interrupted_resurrection_keeps_the_souls_for_another_attempt():
    world, hero = scene()
    soul = hero.capture_soul("barbarian", hero.center())
    soul.flying = False
    hero.attack()
    advance(world, 0.1)
    hero.paralyze(1)
    advance(world, 0.5)
    assert not hero.resurrection_cast and hero.souls == [soul]
    assert not [actor for actor in world.stickmen if actor is not hero]


def test_heroes_never_die_casts_while_climbing_and_keeps_a_support_hand():
    world = SimWorld([], 300, 1000, seed=4, ceiling=0)
    hero = world.add_stickman(Vec2(500, 300), "hero_cleric")
    soul = hero.capture_soul("fighter", hero.center())
    soul.flying = False
    surface = next(surface for surface in hero.planner.surfaces if surface.wall)
    point = surface.point_at(180)
    hero.follower.reset(Anchor(surface, point))
    hero.locomotion.teleport(hero.follower.command())
    support_bone = hero.layout.arms[0].bones[-1]
    support = hero.transforms()[support_bone].end
    assert hero.heroes_never_die()
    advance(world, 0.2)
    assert hero.transforms()[support_bone].end.distance_to(support) < 0.5
    advance(world, RESURRECTION_RELEASE)
    assert not hero.souls
    assert any(actor is not hero for actor in world.stickmen)

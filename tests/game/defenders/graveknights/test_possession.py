"""A slain Graveknight can twice possess and replace a regular adventurer host."""

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.graveknights.actor import (
    GRAVEKNIGHT_STATS,
    Graveknight,
    GraveknightRole,
)
from dungeons_desktops.game.defenders.legendary import apply_legendary
from dungeons_desktops.game.world.simulation import SimWorld

FLOOR = 600.0
DT = 1 / 60
ROLE_FOR_VARIANT = {
    "ranger": GraveknightRole.ARCHER,
    "fighter": GraveknightRole.FIGHTER,
    "paladin": GraveknightRole.FIGHTER,
    "wizard": GraveknightRole.MAGE,
    "sorcerer": GraveknightRole.MAGE,
    "cleric": GraveknightRole.MAGE,
    "druid": GraveknightRole.MAGE,
    "alchemist": GraveknightRole.MAGE,
    "barbarian": GraveknightRole.BARBARIAN,
    "rogue": GraveknightRole.BARBARIAN,
}


def kill_with(world: SimWorld, knight: Graveknight, variant: str) -> tuple[object, Graveknight]:
    killer = world.add_stickman(Vec2(500.0, FLOOR), variant)
    killer.follower.facing = -1
    contact = killer.contact()

    assert world.hurt_monster(
        knight,
        knight.hp,
        knight.center(),
        Vec2(20.0, -10.0),
        attacker=killer,
    )

    replacements = [candidate for candidate in world.graveknights if candidate is not knight]
    assert len(replacements) == 1
    replacement = replacements[0]
    assert killer not in world.stickmen
    assert replacement.contact().distance_to(contact) < 1.0
    assert replacement.facing == -1
    return killer, replacement


@pytest.mark.parametrize(("variant", "role"), ROLE_FOR_VARIANT.items())
def test_regular_adventurer_killer_becomes_the_most_similar_graveknight(variant, role):
    world = SimWorld([], FLOOR, 1000, seed=51)
    fallen = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.ARCHER)

    _, possessed = kill_with(world, fallen, variant)

    assert fallen in world.fallen and fallen not in world.graveknights
    assert possessed.role is role
    assert possessed.hp == possessed.max_hp == GRAVEKNIGHT_STATS[role].hp
    assert possessed.possessions_left == 1
    assert possessed in world.monsters() and possessed in world.actors


def test_possession_passes_two_charges_down_the_lineage_then_stops():
    world = SimWorld([], FLOOR, 1000, seed=52)
    first = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.ARCHER)
    assert first.possessions_left == 2

    first_killer, second = kill_with(world, first, "fighter")
    assert first_killer not in world.stickmen
    assert second.role is GraveknightRole.FIGHTER
    assert second.possessions_left == 1

    second_killer, third = kill_with(world, second, "sorcerer")
    assert second_killer not in world.stickmen
    assert third.role is GraveknightRole.MAGE
    assert third.possessions_left == 0

    final_killer = world.add_stickman(Vec2(500.0, FLOOR), "ranger")
    assert world.hurt_monster(
        third,
        third.hp,
        third.center(),
        Vec2(20.0, -10.0),
        attacker=final_killer,
    )
    assert not world.graveknights
    assert final_killer in world.stickmen and final_killer.prey
    assert (first, second, third) == tuple(world.fallen)


@pytest.mark.parametrize("role", tuple(GraveknightRole))
def test_every_fresh_graveknight_starts_with_two_possessions(role):
    world = SimWorld([], FLOOR, 1000, seed=53)

    knight = world.add_graveknight(Vec2(300.0, FLOOR), role)

    assert knight.possessions_left == 2


@pytest.mark.parametrize("attacker_kind", ("hero", "unarmed", "thrall", "none"))
def test_only_a_living_free_regular_adventurer_can_be_possessed(attacker_kind):
    world = SimWorld([], FLOOR, 1000, seed=54)
    knight = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.FIGHTER)
    if attacker_kind == "hero":
        attacker = world.add_stickman(Vec2(500.0, FLOOR), "hero_fighter")
    elif attacker_kind == "unarmed":
        attacker = world.add_stickman(Vec2(500.0, FLOOR), "unarmed")
    elif attacker_kind == "thrall":
        attacker = world.add_stickman(Vec2(500.0, FLOOR), "wizard")
        attacker.enthrall()
    else:
        attacker = None

    assert world.hurt_monster(
        knight,
        knight.hp,
        knight.center(),
        Vec2(20.0, -10.0),
        attacker=attacker,
    )

    assert not world.graveknights
    if attacker is not None:
        assert attacker in world.stickmen


def test_hero_kill_possesses_a_random_adventurer_instead_of_the_hero():
    world = SimWorld([], FLOOR, 1000, seed=58)
    knight = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.ARCHER)
    hero = world.add_stickman(Vec2(500.0, FLOOR), "hero_fighter")
    bystander = world.add_stickman(Vec2(700.0, FLOOR), "sorcerer")
    bystander.follower.facing = 1
    contact = bystander.contact()

    assert world.hurt_monster(
        knight,
        knight.hp,
        knight.center(),
        Vec2(20.0, -10.0),
        attacker=hero,
    )

    assert hero in world.stickmen and hero.prey
    assert bystander not in world.stickmen
    assert len(world.graveknights) == 1
    possessed = world.graveknights[0]
    assert possessed.role is GraveknightRole.MAGE
    assert possessed.possessions_left == 1
    assert possessed.contact().distance_to(contact) < 1.0
    assert possessed.facing == 1


@pytest.mark.parametrize("legendary", (False, True))
def test_hero_kill_with_no_adventurers_leaves_the_hero_alive(legendary):
    world = SimWorld([], FLOOR, 1000, seed=59)
    knight = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.FIGHTER)
    if legendary:
        apply_legendary(knight)
    hero = world.add_stickman(Vec2(310.0, FLOOR), "hero_cleric")

    assert world.hurt_monster(
        knight,
        knight.hp,
        knight.center(),
        Vec2(20.0, -10.0),
        attacker=hero,
    )

    assert not world.graveknights
    assert hero in world.stickmen and hero.prey and hero.animated


def test_real_fighter_melee_kill_attributes_the_killer_and_triggers_possession():
    world = SimWorld([], FLOOR, 1000, seed=55)
    fighter = world.add_stickman(Vec2(400.0, FLOOR), "fighter")
    knight = world.add_graveknight(Vec2(418.0, FLOOR), GraveknightRole.ARCHER)
    knight.damage = knight.max_hp - 1
    knight.update = lambda dt: None

    for _ in range(2 * 60):
        world.advance(DT)
        if fighter not in world.stickmen:
            break

    assert fighter not in world.stickmen
    assert knight in world.fallen
    assert len(world.graveknights) == 1
    possessed = world.graveknights[0]
    assert possessed is not knight
    assert possessed.role is GraveknightRole.FIGHTER
    assert possessed.possessions_left == 1


def test_nonlethal_hit_never_spends_a_possession_or_replaces_the_attacker():
    world = SimWorld([], FLOOR, 1000, seed=56)
    knight = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.FIGHTER)
    attacker = world.add_stickman(Vec2(500.0, FLOOR), "ranger")

    assert not world.hurt_monster(
        knight,
        knight.hp - 1,
        knight.center(),
        Vec2(20.0, -10.0),
        attacker=attacker,
    )

    assert world.graveknights == [knight]
    assert knight.hp == 1 and knight.possessions_left == 2
    assert attacker in world.stickmen


def test_delayed_projectile_from_an_attacker_no_longer_in_the_world_cannot_possess():
    world = SimWorld([], FLOOR, 1000, seed=57)
    attacker = world.add_stickman(Vec2(100.0, FLOOR), "wizard")
    knight = world.add_graveknight(Vec2(300.0, FLOOR), GraveknightRole.BARBARIAN)
    knight.damage = knight.max_hp - 1
    knight.update = lambda dt: None
    world.spells.cast_missile(
        attacker.center(),
        knight,
        knight.center(),
        owner=attacker,
    )
    world.stickmen.remove(attacker)

    for _ in range(2 * 60):
        world.advance(DT)
        if knight in world.fallen:
            break

    assert knight in world.fallen
    assert not world.graveknights
    assert attacker not in world.stickmen

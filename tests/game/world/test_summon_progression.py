"""Summon attacks and thrall deaths belong to their summoner's lifetime total."""

import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.lich.skeletons import RISE_TIME
from dungeons_desktops.game.world.simulation import SimWorld

FLOOR = 700.0
STEP = 1 / 60
ZERO = Vec2(0, 0)


def world_with() -> SimWorld:
    return SimWorld([], FLOOR, 1400, seed=3)


def run_until_dead(world, victim, seconds=12):
    for _ in range(round(seconds / STEP)):
        world.advance(STEP)
        if not victim.animated:
            return
    pytest.fail("The summon did not finish its attack")


def defeat_monster(world, monster):
    assert world.hurt_monster(monster, monster.max_hp, monster.center(), ZERO)


def test_skeleton_sword_kill_credits_lich_even_after_lich_dies():
    world = world_with()
    lich = world.add_lich(Vec2(60, FLOOR))
    body = world.add_stickman(Vec2(400, FLOOR), "wizard")
    assert body.hurt(body.max_hp, body.center(), ZERO, "lich", "Slain")
    skeleton = world.raise_skeleton(body)
    assert skeleton is not None
    skeleton.risen = RISE_TIME
    foe = world.add_stickman(Vec2(410, FLOOR), "ranger")
    foe.damage = foe.max_hp - 1
    defeat_monster(world, lich)
    assert not world.liches

    skeleton.target = foe
    skeleton.weapon.start()
    skeleton.weapon.apply(skeleton.pose().copy(), skeleton.locomotion.mode, 0.5, frozenset())
    skeleton._resolve_attack()
    skeleton._resolve_attack()

    assert not foe.animated and skeleton.kills == 1
    assert world.progression.monster_kills == {"lich": 2}
    assert world.progression.enemies_killed == {"wizard": 1, "ranger": 1}
    assert world.progression.skulls_earned == 2


@pytest.mark.parametrize("variant", ["barbarian", "wizard"])
def test_thrall_melee_and_projectile_kills_credit_dead_mindflayer(variant):
    world = world_with()
    flayer = world.add_mindflayer(Vec2(1000, FLOOR))
    thrall = world.add_stickman(Vec2(150, FLOOR), variant)
    thrall.enthrall()
    foe = world.add_stickman(Vec2(200, FLOOR), "paladin")
    foe.damage = foe.max_hp - 1
    foe.paralyze(30)
    defeat_monster(world, flayer)

    run_until_dead(world, foe)

    assert not world.mindflayers and thrall.animated
    assert world.progression.monster_kills == {"mindflayer": 1}
    assert world.progression.enemies_killed == {"paladin": 1}
    assert world.progression.skulls_earned == 1


def test_thrall_death_credits_mindflayer_once_and_keeps_original_enemy_type():
    world = world_with()
    thrall = world.add_stickman(Vec2(150, FLOOR), "wizard")
    thrall.enthrall()
    adventurer = world.add_stickman(Vec2(200, FLOOR), "fighter")

    assert world.hurt_monster(thrall, thrall.max_hp, thrall.center(), ZERO, attacker=adventurer)
    assert not world.hurt_monster(thrall, thrall.max_hp, thrall.center(), ZERO, attacker=adventurer)
    assert not thrall.hurt(thrall.max_hp, thrall.center(), ZERO, "adventurer", "Slain again")

    assert world.progression.monster_kills == {"mindflayer": 1}
    assert world.progression.enemies_killed == {"wizard": 1}
    assert world.progression.skulls_earned == world.kills == 1
    assert len(world.devourers) == len(world.kill_marks) == 1


def test_devourer_born_from_thrall_credits_mindflayer_without_a_living_summoner():
    world = world_with()
    flayer = world.add_mindflayer(Vec2(1000, FLOOR))
    thrall = world.add_stickman(Vec2(150, FLOOR), "wizard")
    thrall.enthrall()
    defeat_monster(world, flayer)
    defeat_monster(world, thrall)
    assert len(world.devourers) == 1 and not world.mindflayers
    foe = world.add_stickman(Vec2(250, FLOOR), "barbarian")
    foe.damage = foe.max_hp - 1
    foe.paralyze(30)

    run_until_dead(world, foe)

    assert world.progression.monster_kills == {"mindflayer": 2}
    assert world.progression.enemies_killed == {"wizard": 1, "barbarian": 1}
    assert world.progression.skulls_earned == 2


def test_released_thrall_death_credits_its_actual_killer():
    world = world_with()
    victim = world.add_stickman(Vec2(150, FLOOR), "wizard")
    victim.enthrall()
    victim.release()

    assert victim.hurt(victim.max_hp, victim.center(), ZERO, "goblin", "Slain")

    assert world.progression.monster_kills == {"goblin": 1}
    assert world.progression.enemies_killed == {"wizard": 1}
    assert world.progression.skulls_earned == 1
    assert not world.devourers

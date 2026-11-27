import pytest

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.adventurers.actor import Stickman
from dungeons_desktops.game.adventurers.model import CALLINGS
from dungeons_desktops.game.defenders.drakes.kobold import TRAP_ARMING
from dungeons_desktops.game.defenders.lich.spells import WORD_DELAY
from dungeons_desktops.game.progression import MONSTER_NAMES
from dungeons_desktops.game.world.simulation import SimWorld


def world_with() -> SimWorld:
    return SimWorld([], 700, 1200, seed=3)


def kill(victim, source="goblin"):
    return victim.hurt(1000, victim.center(), Vec2(0, -10), source, "Defeated")


def test_only_the_finishing_hit_earns_one_skull_and_credits_its_monster():
    world = world_with()
    victim = world.add_stickman(Vec2(200, 700), "fighter")
    assert not victim.hurt(1, victim.center(), Vec2(0, 0), "goblin", "Defeated")
    assert world.progression.skulls_earned == 0
    assert kill(victim, "lich")
    assert not kill(victim, "dragon")
    victim.ignite()
    victim.succumb("acid")
    assert world.progression.skulls_earned == world.kills == 1
    assert world.progression.enemies_killed == {"fighter": 1}
    assert world.progression.monster_kills == {"lich": 1}
    assert len(world.kill_marks) == 1


@pytest.mark.parametrize("variant", CALLINGS)
def test_each_enemy_class_and_named_hero_has_its_own_bucket(variant):
    world = world_with()
    victim = world.add_stickman(Vec2(200, 700), variant)
    # Exercise the shared death path, independently of a hero's damage immunity.
    assert Stickman.hurt(victim, 1000, victim.center(), Vec2(0, 0), "mimic", "Defeated")
    assert world.progression.enemies_killed == {variant: 1}


@pytest.mark.parametrize("source", MONSTER_NAMES)
def test_defender_types_keep_separate_totals(source):
    world = world_with()
    assert kill(world.add_stickman(Vec2(200, 700)), source)
    assert world.progression.monster_kills == {source: 1}


@pytest.mark.parametrize(("sources", "monster"), [
    (("chimera", "chimera's fire"), "chimera"),
    (("hydra", "acid glob"), "hydra"),
    (("kobold", "kobold trap"), "kobold"),
    (("mind flayer",), "mindflayer"),
    (("lich", "skeleton"), "lich"),
    (("mind flayer", "thrall", "devourer"), "mindflayer"),
    ])
def test_different_attack_labels_credit_the_same_monster(sources, monster):
    world = world_with()
    for source in sources:
        assert kill(world.add_stickman(Vec2(200, 700)), source)
    assert world.progression.monster_kills == {monster: len(sources)}
    assert world.progression.skulls_earned == len(sources)


def test_defender_deaths_do_not_earn_progress():
    world = world_with()
    goblin = world.add_goblin(Vec2(400, 700))
    assert world.hurt_monster(goblin, 1000, goblin.center(), Vec2(0, 0))
    assert world.progression.total_kills == world.progression.skulls_earned == world.kills == 0
    assert not world.progression.monster_kills and not world.kill_marks


def test_delayed_lich_spell_keeps_credit_after_the_lich_is_gone():
    world = world_with()
    lich = world.add_lich(Vec2(800, 700))
    victim = world.add_stickman(Vec2(200, 700), "barbarian")
    world.necromancy.cast("power_word_kill", lich, lich.center(), victim)
    assert world.hurt_monster(lich, 1000, lich.center(), Vec2(0, 0))
    for _ in range(round((WORD_DELAY + 0.5) * 60)):
        world.necromancy.update(1 / 60)
    assert world.progression.monster_kills == {"lich": 1}
    assert world.progression.enemies_killed == {"barbarian": 1}


def test_lingering_trap_credits_kobold_without_a_living_owner():
    world = world_with()
    victim = world.add_stickman(Vec2(200, 700), "wizard")
    victim.damage = victim.max_hp - 1
    trap = world.traps.drop(victim.contact(), "red")
    trap.falling = False
    trap.age = TRAP_ARMING
    world.traps.update(1 / 60)
    world.traps.update(1 / 60)
    assert world.progression.monster_kills == {"kobold": 1}
    assert world.progression.skulls_earned == 1


def test_resurrected_enemy_counts_as_a_new_kill_without_recounting_the_corpse():
    world = world_with()
    cleric = world.add_stickman(Vec2(500, 700), "hero_cleric")
    victim = world.add_stickman(Vec2(400, 700), "wizard")
    assert kill(victim, "dragon")
    assert len(cleric.souls) == 1
    cleric._resurrect_souls()
    revived = world.stickmen[-1]
    assert revived is not victim and revived is not cleric
    assert not kill(victim, "dragon")
    assert kill(revived, "dragon")
    assert world.progression.total_kills == world.progression.skulls_earned == 2
    assert world.progression.monster_kills == {"dragon": 2}

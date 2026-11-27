"""Assassinate spins in place, throws at distant marks, and exits cleanly."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.heroes.the_slayer.assassinate import (
    COOLDOWN,
    DAGGER_DAMAGE,
    EMBED_DELAY,
    HIT_INTERVAL,
    SPIN_DAMAGE,
    SPIN_TIME,
    Phase,
)
from dungeons_desktops.game.heroes.the_slayer.shadow import ShadowClone
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange

DT = 1 / 60


def setup(*, airborne=False):
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    target = (
        world.add_dragon(Vec2(260, 160), facing=1)
        if airborne else world.add_minotaur(Vec2(280, 300))
    )
    return world, hero, target


def wait(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def until(hero, phase):
    for _ in range(300):
        if hero.assassinate.phase is phase:
            return
        hero.update(DT)
    pytest.fail(f"Never reached {phase}; current phase: {hero.assassinate.phase}")


def test_throw_embeds_then_waits_before_teleporting_and_deals_eight_spin_hits():
    world, hero, target = setup()
    hp = target.hp
    hero.attack()
    ability = hero.assassinate
    assert ability.phase is Phase.THROW and ability.cooldown == COOLDOWN
    wait(hero, 0.2)
    assert target.hp == hp, "the throw animation must not also land a melee hit"
    until(hero, Phase.EMBEDDED)
    assert target.hp == hp - DAGGER_DAMAGE
    original = hero.center()
    wait(hero, EMBED_DELAY - DT)
    assert ability.phase is Phase.EMBEDDED
    assert hero.center().distance_to(original) < 1
    hero.update(DT)
    assert ability.spinning and hero.center().distance_to(ability.point) < 1e-6
    assert hero.center().distance_to(original) > 50
    wait(hero, SPIN_TIME)
    expected_hits = round(SPIN_TIME / HIT_INTERVAL)
    assert ability.hits == expected_hits == 8
    assert target.hp == hp - DAGGER_DAMAGE - expected_hits * SPIN_DAMAGE
    assert not ability.active and ability.cooldown > 0
    assert not ability.start(), "the ten-second cooldown survives the end of the spin"


def test_embedding_tracks_the_mark_but_spin_stays_put_when_the_mark_moves():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.EMBEDDED)
    before = hero.assassinate.point
    shift = Vec2(35, -15)
    target.position += shift
    hero.update(DT)
    assert hero.assassinate.point.distance_to(before + shift) < 1e-6
    until(hero, Phase.SPIN)
    origin = hero.assassinate.point
    hp = target.hp
    other = world.add_goblin(Vec2(280, 300), "flag")
    other_hp = other.hp
    target.position += Vec2(400, -100)
    wait(hero, 0.5)
    assert hero.assassinate.point == origin
    assert hero.center().distance_to(origin) < 1e-6
    assert hero.assassinate.target is target and other.hp == other_hp
    assert len(hero.assassinate.daggers) == 2 and target.hp == hp


@pytest.mark.parametrize("airborne", [False, True])
def test_each_distant_tick_launches_a_dagger_and_damage_waits_for_impact(airborne):
    world, hero, target = setup(airborne=airborne)
    hero.attack()
    until(hero, Phase.SPIN)
    ability = hero.assassinate
    origin = ability.point
    hp = target.hp
    shift = Vec2(220, -100)
    if airborne:
        target.body += shift
    else:
        target.position += shift
    wait(hero, HIT_INTERVAL)
    assert ability.hits == 1 and len(ability.daggers) == 1
    assert ability.daggers[0].point == origin and target.hp == hp
    hero.update(DT)
    assert ability.daggers[0].point.distance_to(origin) > 0
    assert hero.center().distance_to(origin) < 1e-6 and target.hp == hp
    for _ in range(120):
        hero.update(DT)
        assert ability.point == origin and hero.center().distance_to(origin) < 1e-6
        if target.hp < hp:
            break
    assert target.hp == hp - SPIN_DAMAGE


def test_all_eight_ranged_ticks_finish_in_flight_after_the_spin_ends():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.SPIN)
    target.position += Vec2(600, 0)
    hp = target.hp
    wait(hero, SPIN_TIME)
    assert not hero.assassinate.active and hero.assassinate.hits == 8
    assert hero.assassinate.daggers, "late daggers must survive the spin's final tick"
    assert hero.prey and not hero.invulnerable, "flying daggers do not extend spin protection"
    assert target.hp > hp - 8 * SPIN_DAMAGE
    wait(hero, 2)
    assert not hero.assassinate.daggers and target.hp == hp - 8 * SPIN_DAMAGE


def test_returning_to_melee_range_does_not_double_the_damage_ticks():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.SPIN)
    hp = target.hp
    shift = Vec2(200, 0)
    target.position += shift
    wait(hero, HIT_INTERVAL)
    assert len(hero.assassinate.daggers) == 1
    target.position -= shift
    wait(hero, HIT_INTERVAL)
    assert hero.assassinate.hits == 2 and not hero.assassinate.daggers
    assert target.hp == hp - 2 * SPIN_DAMAGE


def test_flying_spin_daggers_are_discarded_when_their_mark_dies():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.SPIN)
    target.position += Vec2(200, 0)
    wait(hero, HIT_INTERVAL)
    assert hero.assassinate.daggers
    other = world.add_goblin(Vec2(280, 300), "flag")
    hp = other.hp
    world.hurt_monster(target, 10000, target.center(), Vec2(0, 0))
    hero.update(DT)
    assert not hero.assassinate.active and not hero.assassinate.daggers
    assert other.hp == hp


@pytest.mark.parametrize("phase", list(Phase))
def test_dead_target_cancels_the_mark_and_recovers_navigation(phase):
    world, hero, target = setup()
    hero.attack()
    until(hero, phase)
    world.hurt_monster(target, 10000, target.center(), Vec2(0, 0))
    hero.update(DT)
    assert not hero.assassinate.active and hero.assassinate.target is None
    assert hero.prey and not hero.invulnerable
    assert hero.animated and hero.planner.owns(hero.follower.current_anchor().surface)
    hero.set_goal(Vec2(450, 300))
    wait(hero, 6)
    assert hero.contact().distance_to(Vec2(450, 300)) < 1


@pytest.mark.parametrize("phase", [Phase.THROW, Phase.FLIGHT, Phase.EMBEDDED])
def test_a_slayer_killed_before_the_spin_cannot_teleport_or_deal_more_damage(phase):
    world, hero, target = setup()
    hero.attack()
    until(hero, phase)
    hp = target.hp
    hero.hurt(10000, hero.center(), Vec2(0, 0), "dragon", "defeated")
    wait(hero, 1)
    assert not hero.animated and not hero.assassinate.active
    assert target.hp == hp


def test_airborne_kill_and_terrain_changes_end_with_a_valid_shadow_retreat():
    world, hero, target = setup(airborne=True)
    hero.attack()
    until(hero, Phase.SPIN)
    assert hero.contact().y < world.floor_y - 50
    world.apply_terrain(TerrainChange(), [Rect(240, 240, 180, 60)])
    wait(hero, SPIN_TIME + 2)
    assert hero.animated and not hero.assassinate.active
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    assert target not in world.dragons
    clone = next(actor for actor in world.stickmen if isinstance(actor, ShadowClone))
    assert clone.contact().y < 240 and clone.prey
    assert hero.contact().x < 240 and hero.contact().y == pytest.approx(300)
    assert hero.stealthed


def test_auto_cast_reveals_stealth_and_spin_restarts_the_timer_on_every_tick():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    wait(hero, 3)
    assert hero.stealthed
    target = world.add_minotaur(Vec2(280, 300))
    hero.update(DT)
    assert hero.assassinate.active and not hero.stealthed and hero.prey
    until(hero, Phase.SPIN)
    wait(hero, 1.5)
    assert not hero.stealthed and hero.since_attack == 0
    world.hurt_monster(target, 10000, target.center(), Vec2(0, 0))
    hero.update(DT)
    wait(hero, 3)
    assert hero.stealthed


def test_large_spin_updates_keep_the_same_tick_count_and_never_exceed_eight_hits():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.SPIN)
    hp = target.hp
    for dt in (0.37, 0.53, 0.71, 0.49):
        hero.assassinate.update(dt)
    assert hero.assassinate.hits == 8
    assert target.hp == hp - 8 * SPIN_DAMAGE


def test_spin_blocks_damage_status_hits_and_targeting_until_its_last_frame():
    world, hero, target = setup()
    hero.attack()
    until(hero, Phase.EMBEDDED)
    hunt = Hunt(retarget_every=60)
    assert hunt.update(DT, target.center(), world.stickmen) is hero
    assert hero.prey and hero.hits(hero.center()) and not hero.invulnerable
    until(hero, Phase.SPIN)
    hp = hero.hp
    assert hero.invulnerable and not hero.stealthed and hero.visibility == 1
    assert hunt.update(DT, target.center(), world.stickmen) is None
    assert not hero.prey and not hero.hits(hero.center(), margin=100)
    assert world.locate_prey(hero) is None and world._spear_hits(hero.center()) is None
    assert not hero.hurt(10000, hero.center(), Vec2(100, -100), "dragon", "defeated")
    assert not hero.hurt_from(target, 10000, hero.center(), Vec2(0, 0), "minotaur", "defeated")
    world._blast_prey(hero.center(), 100)
    hero.ignite()
    for breath in ("acid", "cold", "poison", "lightning"):
        hero.succumb(breath)
    hero.paralyze(1)
    hero.knock_down(hero.center(), 100, 1, 1)
    assert hero.hp == hp and hero.animated and not hero.paralysed
    assert hero.burn is None and hero.demise is None and not hero._grace
    assert world.kills == 0 and not world.gore.drops
    hero._grace["dragon"] = 0.1
    wait(hero, 0.2)
    assert hero._grace["dragon"] <= 0
    wait(hero, SPIN_TIME - 0.2 - DT)
    assert hero.assassinate.spinning and hero.invulnerable
    hero.update(DT)
    assert not hero.assassinate.active and not hero.invulnerable
    assert hero.prey and hero.hits(hero.center())
    assert hunt.update(DT, target.center(), world.stickmen) is hero
    hero.hurt(1, hero.center(), Vec2(0, 0), "dragon", "defeated")
    assert hero.hp == hp - 1
    hero.paralyze(1)
    assert hero.paralysed


def test_no_target_or_out_of_range_does_not_spend_cooldown():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    assert not hero.assassinate.start()
    world.add_minotaur(Vec2(900, 300))
    assert not hero.assassinate.start()
    assert hero.assassinate.cooldown == 0

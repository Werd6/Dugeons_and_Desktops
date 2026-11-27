"""Credited kills refresh the Slayer's attacks and immediately trigger a shadow escape."""

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.defenders.mimic.actor import KNIFE_DAMAGE, KNIFE_TIME, Knife
from dungeons_desktops.game.heroes.the_slayer.assassinate import (
    COOLDOWN,
    DAGGER_DAMAGE,
    HIT_INTERVAL,
    SPIN_DAMAGE,
    SPIN_TIME,
    Phase,
    SpinDagger,
)
from dungeons_desktops.game.heroes.the_slayer.shadow import ESCAPE_RECOVERY, ShadowClone
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1 / 60


def setup():
    world = SimWorld([], 300, 1400, seed=3)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    hero.cooldown = 4
    return world, hero


def wait(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def until(hero, done):
    for _ in range(360):
        if done():
            return
        hero.update(DT)
    assert done()


def assert_reset(hero):
    assert hero.cooldown <= 0 and hero.assassinate.cooldown == 0
    assert hero.stealthed and not hero.prey and not hero.assassinate.active
    assert not hero.weapon.busy
    shadows = [actor for actor in hero.world.stickmen if isinstance(actor, ShadowClone)]
    assert len(shadows) == 1 and shadows[0].prey and shadows[0].hp == 1
    assert hero.contact().x < shadows[0].contact().x


def test_normal_melee_kill_refreshes_both_cooldowns():
    world, hero = setup()
    hero.assassinate.cooldown = 7
    goblin = world.add_goblin(Vec2(118, 300), "flag")
    goblin.damage = goblin.max_hp - 1
    hero.attack()
    until(hero, lambda: goblin not in world.goblins)
    assert_reset(hero)


def test_opening_dagger_kill_refreshes_both_cooldowns():
    world, hero = setup()
    goblin = world.add_goblin(Vec2(240, 300), "flag")
    goblin.damage = goblin.max_hp - DAGGER_DAMAGE
    hero.attack()
    assert hero.assassinate.cooldown == COOLDOWN
    until(hero, lambda: goblin not in world.goblins)
    assert not hero.assassinate.active
    assert_reset(hero)


def test_spin_kill_does_not_reapply_the_landing_recovery_cooldown():
    world, hero = setup()
    target = world.add_minotaur(Vec2(280, 300))
    target.damage = target.max_hp - DAGGER_DAMAGE - SPIN_DAMAGE
    hero.attack()
    until(hero, lambda: hero.assassinate.spinning)
    wait(hero, HIT_INTERVAL)
    assert target not in world.minotaurs and not hero.assassinate.active
    assert_reset(hero)


def test_a_dagger_kill_after_the_spin_ends_still_refreshes_both_cooldowns():
    world, hero = setup()
    target = world.add_minotaur(Vec2(280, 300))
    hero.attack()
    until(hero, lambda: hero.assassinate.spinning)
    wait(hero, SPIN_TIME - HIT_INTERVAL)
    target.position += Vec2(400, 0)
    target.damage = target.max_hp - SPIN_DAMAGE
    wait(hero, HIT_INTERVAL)
    assert not hero.assassinate.active and len(hero.assassinate.daggers) == 1
    assert target in world.minotaurs and hero.assassinate.cooldown > 0
    hero.cooldown = 4
    until(hero, lambda: target not in world.minotaurs)
    assert_reset(hero)


def test_kill_reset_keeps_the_escape_stealthed_before_assassinating_the_next_target():
    world, hero = setup()
    first = world.add_goblin(Vec2(240, 300), "flag")
    first.damage = first.max_hp - DAGGER_DAMAGE
    second = world.add_goblin(Vec2(280, 300), "flag")
    hero.attack()
    until(hero, lambda: first not in world.goblins)
    assert_reset(hero)
    wait(hero, ESCAPE_RECOVERY - 2 * DT)
    assert not hero.assassinate.active and hero.stealthed
    until(hero, lambda: hero.assassinate.active)
    assert hero.assassinate.phase is Phase.THROW and hero.assassinate.target is second
    assert hero.assassinate.cooldown == COOLDOWN


def test_nonlethal_hits_other_actors_kills_and_repeat_corpse_hits_do_not_refresh():
    world, hero = setup()
    hero.assassinate.cooldown = 7
    other = world.add_stickman(Vec2(900, 300), "rogue")
    target = world.add_goblin(Vec2(240, 300), "flag")
    assert not world.hurt_monster(target, 1, target.center(), Vec2(0, 0), attacker=hero)
    assert (hero.cooldown, hero.assassinate.cooldown) == (4, 7)
    assert world.hurt_monster(target, 1000, target.center(), Vec2(0, 0), attacker=other)
    assert (hero.cooldown, hero.assassinate.cooldown) == (4, 7)
    assert not world.hurt_monster(target, 1000, target.center(), Vec2(0, 0), attacker=hero)
    assert (hero.cooldown, hero.assassinate.cooldown) == (4, 7)
    assert not any(isinstance(actor, ShadowClone) for actor in world.stickmen)
    assert not hero.stealthed


def test_a_kill_of_a_mind_controlled_adventurer_also_counts():
    world, hero = setup()
    hero.assassinate.cooldown = 7
    victim = world.add_stickman(Vec2(240, 300), "rogue")
    victim.enthrall()
    assert world.hurt_monster(victim, 1000, victim.center(), Vec2(0, 0), attacker=hero)
    assert_reset(hero)


def test_the_mimic_revealing_dagger_credits_its_rogue_owner():
    world, hero = setup()
    hero.assassinate.cooldown = 7
    mimic = world.add_mimic(Vec2(400, 300))
    mimic.damage = mimic.max_hp - KNIFE_DAMAGE
    mimic.knife = Knife(hero.center(), hero.center(), owner=hero)
    mimic._fly_knife(KNIFE_TIME)
    assert mimic not in world.mimics
    assert_reset(hero)


def test_a_late_dagger_kill_interrupts_a_new_spin_without_moving_him_back_to_it():
    world, hero = setup()
    target = world.add_minotaur(Vec2(280, 300))
    hero.attack()
    until(hero, lambda: hero.assassinate.spinning)
    origin, feet, hp = hero.center(), hero.contact(), target.hp
    other = world.add_goblin(Vec2(500, 300), "flag")
    other.damage = other.max_hp - SPIN_DAMAGE
    hero.assassinate.daggers.append(SpinDagger(other, other.center(), Vec2(1, 0)))
    hero.update(DT)
    assert other not in world.goblins and target.hp == hp
    assert_reset(hero)
    clone = next(actor for actor in world.stickmen if isinstance(actor, ShadowClone))
    assert clone.center() == origin and clone.contact() == feet
    landing = hero.contact()
    wait(hero, 0.2)
    assert hero.contact() == landing and hero.stealthed and target.hp == hp


def test_every_kill_can_escape_again_without_consuming_health_thresholds():
    world = SimWorld([], 300, 1400, seed=3)
    hero = world.add_stickman(Vec2(600, 300), "hero_rogue")
    thresholds = hero.escape_thresholds.copy()
    for x in (800, 900):
        target = world.add_goblin(Vec2(x, 300), "flag")
        target.damage = target.max_hp - SPIN_DAMAGE
        hero.assassinate.daggers.append(SpinDagger(target, target.center(), Vec2(1, 0)))
    hero.update(DT)
    shadows = [actor for actor in world.stickmen if isinstance(actor, ShadowClone)]
    assert not world.goblins and len(shadows) == 2
    assert [clone.contact().x for clone in shadows] == [600, 440]
    assert hero.contact().x == 280 and hero.stealthed
    assert hero.escape_thresholds == thresholds
    hero.reveal()
    hero.hurt(15, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert len([actor for actor in world.stickmen if isinstance(actor, ShadowClone)]) == 3
    assert hero.contact().x == 120 and hero.hp == 45 and hero.stealthed


def test_a_posthumous_mimic_dagger_kill_does_not_blink_or_spawn_a_clone():
    world, hero = setup()
    mimic = world.add_mimic(Vec2(400, 300))
    mimic.damage = mimic.max_hp - KNIFE_DAMAGE
    mimic.knife = Knife(hero.center(), hero.center(), owner=hero)
    hero.hurt(1000, hero.center(), Vec2(0, 0), "goblin", "defeated")
    before = hero.center()
    mimic._fly_knife(KNIFE_TIME)
    assert mimic not in world.mimics and not hero.animated
    assert hero.center() == before and not any(isinstance(s, ShadowClone) for s in world.stickmen)

"""Stealth timing, defender target loss, and damage immunity use live hero state."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.actors.hunting import Hunt
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def make_hero():
    world = SimWorld([], 300, 1200)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    hero.assassinate.cooldown = 999  # Isolate passive stealth from automatic Assassinate casts.
    return world, hero


def wait(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def test_three_seconds_since_attack_reveals_immediately_and_rearms_on_a_miss():
    world, hero = make_hero()
    wait(hero, 3 - DT)
    assert not hero.stealthed and hero.prey and hero.visibility == 1
    hero.update(DT)
    assert hero.stealthed and not hero.prey and hero.visibility < 0.5
    hero.attack()  # Swinging at empty space still breaks stealth.
    assert hero.weapon.busy and not hero.stealthed and hero.prey
    assert hero.visibility == 1 and hero.since_attack == 0
    wait(hero, 3 - DT)
    assert not hero.stealthed
    hero.update(DT)
    assert hero.stealthed


def test_auto_attack_reveals_before_the_hit_and_failed_attack_does_not():
    world, hero = make_hero()
    wait(hero, 3)
    hero.blind = 1.0
    hero.attack()
    assert hero.stealthed and not hero.weapon.busy
    hero.blind = 0.0
    goblin = world.add_goblin(Vec2(118, 300), "flag")
    before = goblin.hp
    hero.update(DT)
    assert hero.weapon.busy and hero.prey and not hero.stealthed
    assert goblin.hp == before
    wait(hero, 0.2)
    assert goblin.hp == before - 1


def test_defenders_drop_cached_targets_and_skip_stealth_in_spells_and_collision():
    world, hero = make_hero()
    other = world.add_stickman(Vec2(700, 300), "rogue")
    hunt = Hunt(retarget_every=60)
    origin = Vec2(300, 300)
    assert hunt.update(DT, origin, world.stickmen) is hero
    lich = world.add_lich(Vec2(300, 300))
    minotaur = world.add_minotaur(Vec2(350, 300))
    lich.foe = minotaur.foe = hero
    wait(hero, 3)
    assert hunt.update(DT, origin, world.stickmen) is other
    assert lich._choose_foe() is other
    assert minotaur._choose_foe() is other
    assert hero not in world.necromancy._prey()
    assert world.locate_prey(hero) is None
    assert world.prey_at(hero.center()) is None
    assert world._spear_hits(hero.center()) is None
    hero.attack()
    assert world.locate_prey(hero) is not None
    assert world.prey_at(hero.center()) is hero


@pytest.mark.parametrize("source", ["goblin", "dragon", "lich", "minotaur", "thrall"])
def test_stealth_blocks_direct_and_attributed_lethal_hits_without_side_effects(source):
    world, hero = make_hero()
    wait(hero, 3)
    point, push = hero.center(), Vec2(100, -100)
    assert not hero.hurt(1000, point, push, source, "defeated")
    assert not hero.hurt_from(object(), 1000, point, push, source, "defeated")
    assert hero.hp == hero.max_hp and hero.animated and hero.stealthed
    assert not hero._grace and not world.gore.drops and world.kills == 0
    hero.attack()
    assert not hero.hurt(1, point, push, source, "defeated")
    assert hero.hp == hero.max_hp - 1


def test_area_damage_and_elemental_death_cannot_harm_a_shadow():
    world, hero = make_hero()
    wait(hero, 3)
    world._blast_prey(hero.center(), 50)
    hero.ignite()
    for breath in ("acid", "cold", "poison", "lightning"):
        hero.succumb(breath)
    assert hero.hp == hero.max_hp and hero.animated
    assert hero.burn is None and hero.demise is None


def test_taking_damage_does_not_restart_the_attack_timer_and_death_is_not_stealth():
    world, hero = make_hero()
    wait(hero, 2.9)
    hero.hurt(1, hero.center(), Vec2(0, 0), "goblin", "defeated")
    wait(hero, 0.1)
    assert hero.stealthed
    hero.attack()
    hero.hurt(1000, hero.center(), Vec2(0, 0), "lich", "defeated")
    wait(hero, 3.1)
    assert not hero.animated and not hero.stealthed and hero.visibility == 1


def test_render_is_translucent_without_mutating_gameplay_or_leaking_opacity():
    world, hero = make_hero()
    wait(hero, 3)

    def render():
        image = QImage(160, 320, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        draw_actors(painter, (), [hero])
        assert painter.opacity() == 1
        painter.end()
        return sum(image.pixelColor(x, y).alpha() for y in range(260, 310) for x in range(60, 140))

    before = (hero.since_attack, hero.cape_time, world.random.getstate())
    shadow_alpha = render()
    assert before == (hero.since_attack, hero.cape_time, world.random.getstate())
    hero.reveal()
    assert 0 < shadow_alpha < render() * 0.75  # Wisps cover extra pixels around the body.

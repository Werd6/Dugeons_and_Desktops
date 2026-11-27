"""The third landed strike summons three hammers and heals nearby allies once."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.hero_paladin.render import draw_paladin_effects
from dungeons_desktops.game.heroes.hero_paladin.smite import HAMMER_DAMAGE
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def scene():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(400, 300), "hero_paladin")
    target = world.add_minotaur(Vec2(425, 300))
    target.max_hp = 1000
    ally = world.add_stickman(Vec2(350, 300), "fighter")
    ally.damage = 5
    return world, hero, target, ally


def advance(hero, seconds):
    for _ in range(round(seconds / DT)):
        hero.update(DT)


def swing(hero):
    hero.attack()
    advance(hero, 0.8)


def test_every_third_landed_hit_adds_three_hammers_and_heals_two_once():
    _, hero, target, ally = scene()
    for number in range(1, 7):
        swing(hero)
        assert hero.melee_hits == number
        assert target.damage == number + (number // 3) * 3 * HAMMER_DAMAGE
        assert ally.damage == max(0, 5 - (number // 3) * 2)


def test_hammers_appear_during_swing_and_land_in_succession():
    _, hero, target, ally = scene()
    swing(hero)
    swing(hero)
    hero.attack()
    assert hero.smite is not None and not hero.smite.confirmed
    advance(hero, 0.3)
    assert target.damage == 2 and ally.damage == 5
    advance(hero, DT * 2)
    assert hero.smite.confirmed and hero.smite.hits == 1
    assert target.damage == 3 + HAMMER_DAMAGE and ally.damage == 3
    advance(hero, 0.1)
    assert hero.smite.hits == 2 and target.damage == 3 + 2 * HAMMER_DAMAGE
    advance(hero, 0.1)
    assert hero.smite.hits == 3 and target.damage == 3 + 3 * HAMMER_DAMAGE
    advance(hero, 0.3)
    assert hero.smite is None and ally.damage == 3


def test_heal_is_limited_to_living_allies_in_aura_and_caps_at_max_hp():
    world, hero, _, ally = scene()
    healthy = world.add_stickman(Vec2(320, 300), "rogue")
    scratched = world.add_stickman(Vec2(330, 300), "wizard")
    scratched.damage = 1
    far = world.add_stickman(Vec2(650, 300), "fighter")
    far.damage = 4
    thrall = world.add_stickman(Vec2(340, 300), "fighter")
    thrall.damage = 4
    thrall.enthrall()
    dead = world.add_stickman(Vec2(700, 300), "fighter")
    dead.hurt(100, dead.center(), Vec2(0, 0), "test", "defeated")
    hero.damage = 10
    hero.melee_hits = 2
    swing(hero)
    assert ally.damage == 3 and scratched.damage == healthy.damage == 0
    assert far.damage == thrall.damage == 4 and hero.damage == 10
    assert dead.damage == 100


def test_missed_third_swing_does_not_spend_smite_or_heal():
    world, hero, target, ally = scene()
    hero.melee_hits = 2
    hero.attack()
    world.minotaurs.remove(target)
    advance(hero, 0.8)
    assert hero.melee_hits == 2 and ally.damage == 5 and hero.smite is None
    world.minotaurs.append(target)
    swing(hero)
    assert hero.melee_hits == 3 and target.damage == 1 + 3 * HAMMER_DAMAGE and ally.damage == 3


@pytest.mark.parametrize("interruption", ["stun", "death", "thrall"])
def test_interrupted_windup_does_not_hit_or_heal(interruption):
    _, hero, target, ally = scene()
    hero.melee_hits = 2
    hero.attack()
    advance(hero, 0.15)
    if interruption == "stun":
        hero.paralyze(2)
    elif interruption == "thrall":
        hero.enthrall()
    else:
        hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 0.8)
    assert hero.melee_hits == 2 and target.damage == 0
    assert ally.damage == 5 and hero.smite is None


def test_killing_blow_still_heals_without_hammers_retargeting():
    world, hero, target, ally = scene()
    target.max_hp = 1
    other = world.add_goblin(Vec2(450, 300), "flag")
    hero.melee_hits = 2
    swing(hero)
    assert target.hp == 0 and other.damage == 0
    assert hero.melee_hits == 3 and ally.damage == 3


def test_hammers_finish_on_large_frame_without_extra_damage():
    _, hero, target, ally = scene()
    hero.melee_hits = 2
    hero.attack()
    advance(hero, 0.35)
    hero.cooldown = 100
    hero.update(0.6)
    assert target.damage == 1 + 3 * HAMMER_DAMAGE and hero.melee_hits == 3 and ally.damage == 3
    assert hero.smite is None


def test_render_smite_halos_and_aura_without_mutating_combat():
    world, hero, target, ally = scene()
    hero.melee_hits = 2
    hero.attack()
    image = QImage(1000, 500, QImage.Format.Format_ARGB32_Premultiplied)
    for _ in range(8):
        advance(hero, 0.1)
        state = (target.damage, ally.damage, hero.melee_hits, hero.contact())
        image.fill(0)
        painter = QPainter(image)
        draw_actors(painter, (), world.stickmen)
        draw_paladin_effects(painter, world.heroes)
        assert painter.opacity() == 1
        painter.end()
        assert state == (target.damage, ally.damage, hero.melee_hits, hero.contact())
    assert any(
        image.pixelColor(x, y).alpha()
        for x in range(300, 500) for y in range(250, 300)
    )

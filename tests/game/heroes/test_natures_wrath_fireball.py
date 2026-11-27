"""Rotation timing, ranged area damage, interruptions, and fire rendering."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.defenders.lich.spells import FIREBALL_RADIUS as LICH_RADIUS
from dungeons_desktops.game.heroes.natures_wrath.spell_render import CORE, FIRE, draw_nature_spells
from dungeons_desktops.game.heroes.natures_wrath.spells import (
    CAST_DELAY,
    CAST_RANGE,
    CAST_RELEASE,
    CAST_TIME,
    FIREBALL_DAMAGE,
    FIREBALL_RADIUS,
    Ability,
)
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def setup():
    world = SimWorld([], 300, 900, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_druid")
    hero.queue_index = hero.rotation.index(Ability.FIREBALL)
    target = world.add_minotaur(Vec2(350, 300))
    target.update = lambda dt: None
    return world, hero, target


def until(world, condition, seconds=4):
    for _ in range(round(seconds / DT)):
        world.advance(DT)
        if condition():
            return
    raise AssertionError("condition not reached")


def test_auto_rotation_charges_releases_once_waits_and_repeats():
    world, hero, target = setup()
    hero.rotation = (Ability.FIREBALL, Ability.FIREBALL)
    hero.queue_index = 0
    advance(world, CAST_RELEASE - 0.1)
    assert hero.casting is Ability.FIREBALL and not hero.spells.fireballs
    until(world, lambda: bool(hero.spells.fireballs))
    assert len(hero.spells.fireballs) == 1
    assert hero.cast_released and hero.weapon is None
    until(world, lambda: hero.queue_index == 1)
    assert hero.casting is None and hero.cast_wait == CAST_DELAY
    hero.attack()
    assert hero.casting is None  # Manual attacks cannot bypass recovery.
    advance(world, CAST_DELAY - 0.1)
    assert hero.casting is None
    until(world, lambda: hero.queue_index == 0)
    until(world, lambda: target.damage == 2 * FIREBALL_DAMAGE)
    assert hero.weapon is None and not hero.weapon_strokes()


def test_larger_blast_hurts_defenders_once_and_spares_the_caster_and_allies():
    world, hero, target = setup()
    center = Vec2(350, 280)
    extra = world.add_goblin(Vec2(440, 300), "flag")
    far = world.add_goblin(Vec2(510, 300), "flag")
    ally = world.add_stickman(Vec2(350, 300), "druid")
    other_hero = world.add_stickman(Vec2(350, 300), "hero_fighter")
    assert FIREBALL_RADIUS == LICH_RADIUS * 1.5
    assert extra.center().distance_to(center) > LICH_RADIUS
    hero.spells.cast(Ability.FIREBALL, center, center)
    hero.spells.update(DT)
    assert target.damage == extra.damage == FIREBALL_DAMAGE
    assert far.damage == ally.damage == other_hero.damage == hero.damage == 0
    for _ in range(100):
        hero.spells.update(DT)
    assert target.damage == FIREBALL_DAMAGE and not hero.spells.blasts


def test_lob_uses_an_arc_and_continues_after_the_caster_dies():
    world, hero, target = setup()
    until(world, lambda: bool(hero.spells.fireballs))
    ball = hero.spells.fireballs[0]
    assert ball.velocity.y < 0
    start = ball.position
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    assert not hero.animated and hero.casting is None
    advance(world, 0.2)
    assert ball.position.x > start.x and ball.position.y < start.y
    until(world, lambda: target.damage == FIREBALL_DAMAGE)


@pytest.mark.parametrize("condition", ["stun", "blind", "thrall", "ragdoll"])
def test_conditions_interrupt_windup_without_consuming_the_rotation_slot(condition):
    world, hero, target = setup()
    hero.rotation = (Ability.FIREBALL, Ability.FIREBALL)
    hero.queue_index = 0
    advance(world, 0.2)
    assert hero.casting is Ability.FIREBALL
    if condition == "stun":
        hero.paralyze(2)
    elif condition == "blind":
        hero.blind_for(2)
    elif condition == "thrall":
        hero.enthrall()
    else:
        hero.go_ragdoll()
    advance(world, 0.8)
    assert hero.casting is None and hero.queue_index == 0
    assert not hero.spells.fireballs and target.damage == 0


def test_lost_target_cancels_cast_and_a_new_target_can_be_acquired():
    world, hero, target = setup()
    advance(world, 0.2)
    world.hurt_monster(target, target.hp, target.center(), Vec2(0, 0))
    advance(world, 0.6)
    assert hero.casting is None and not hero.spells.fireballs
    replacement = world.add_goblin(Vec2(300, 300), "flag")
    replacement.update = lambda dt: None
    until(world, lambda: replacement.damage > 0)


@pytest.mark.parametrize("surface_kind", ["wall", "hanging"])
def test_casts_while_clinging_and_preserves_the_support_hand(surface_kind):
    world, hero, target = setup()
    surface = next(s for s in hero.planner.surfaces if getattr(s, surface_kind))
    point = surface.point_at(100 if surface.wall else 200)
    hero.follower.reset(Anchor(surface, point))
    hero.locomotion.teleport(hero.follower.command())
    support = hero.transforms()[hero.layout.arms[0].bones[-1]].end
    advance(world, 0.3)
    after = hero.transforms()[hero.layout.arms[0].bones[-1]].end
    assert after.distance_to(support) < 0.5
    until(world, lambda: target.damage > 0)


def test_manual_route_pauses_faces_target_then_resumes():
    world, hero, target = setup()
    hero.set_goal(Vec2(20, 300))  # Walking away from the foe.
    before = hero.contact()
    advance(world, 0.3)
    assert hero.casting is Ability.FIREBALL and hero.facing == 1
    assert hero.contact() == before
    advance(world, CAST_TIME)
    assert hero.contact().x < before.x


def test_out_of_range_target_is_not_cast_at():
    world = SimWorld([], 300, 1000)
    hero = world.add_stickman(Vec2(50, 300), "hero_druid")
    goblin = world.add_goblin(Vec2(50 + CAST_RANGE + 80, 300), "flag")
    goblin.update = lambda dt: None
    hero.attack()
    advance(world, 1)
    assert hero.casting is None and not hero.spells.fireballs


def test_fireball_passes_through_windows_and_stops_at_floor_or_flight_end():
    world = SimWorld([Rect(200, 150, 60, 150)], 300, 900)
    hero = world.add_stickman(Vec2(100, 300), "hero_druid")
    hero.spells.cast(Ability.FIREBALL, Vec2(100, 280), Vec2(450, 280))
    for _ in range(35):
        hero.spells.update(DT)
    assert hero.spells.fireballs and hero.spells.fireballs[0].position.x > 260
    for _ in range(40):
        hero.spells.update(DT)
    assert not hero.spells.fireballs and hero.spells.blasts
    hero.spells.cast(Ability.FIREBALL, Vec2(100, 290), Vec2(130, 500))
    for _ in range(20):
        hero.spells.update(DT)
    assert not hero.spells.fireballs
    assert hero.spells.blasts[-1].center.y <= world.floor_y


def test_projectile_renders_with_warm_fire_and_bright_core():
    world, hero, _ = setup()
    until(world, lambda: bool(hero.spells.fireballs))
    image = QImage(900, 340, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_nature_spells(painter, world.heroes)
    painter.end()
    colors = {image.pixelColor(x, y).name() for x in range(50, 180) for y in range(230, 310)}
    assert {FIRE.name(), CORE.name()} <= colors

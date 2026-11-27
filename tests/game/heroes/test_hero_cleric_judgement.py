"""Coordinated prayer, beam duration, damage cadence, and sunlight rendering."""

from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.hero_cleric.judgement import (
    ALLY_BEAM_BONUS,
    BASE_BEAM_TIME,
    JUDGEMENT_COOLDOWN,
    JUDGEMENT_RANGE,
    PRAYER_TIME,
    TICK_DAMAGE,
)
from dungeons_desktops.game.heroes.hero_cleric.render import draw_divine_judgements
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.planner import Anchor
from dungeons_desktops.render.scene import draw_actors

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def scene():
    world = SimWorld([], 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(180, 300), "hero_cleric")
    cleric = world.add_stickman(Vec2(260, 300), "cleric")
    paladin = world.add_stickman(Vec2(320, 300), "paladin")
    fighter = world.add_stickman(Vec2(380, 300), "fighter")
    for ally in (cleric, paladin, fighter):
        ally.cooldown = 100
    target = world.add_minotaur(Vec2(400, 300))
    target.max_hp = 100
    target.update = lambda dt: None
    return world, hero, cleric, paladin, fighter, target


def test_clerics_and_paladins_stop_and_extend_the_sustained_beam():
    world, hero, cleric, paladin, fighter, target = scene()
    advance(world, DT)
    assert hero.judgement is not None
    assert hero.judgement.prayers == [cleric, paladin]
    assert hero.judgement.beam_duration == BASE_BEAM_TIME + 2 * ALLY_BEAM_BONUS
    assert cleric.divine_prayer > 0 and paladin.divine_prayer > 0
    assert fighter.divine_prayer == 0
    assert not cleric.weapon_held and not paladin.weapon_held
    positions = cleric.contact(), paladin.contact()
    advance(world, PRAYER_TIME / 2)
    assert (cleric.contact(), paladin.contact()) == positions
    assert target.damage == 0

    advance(world, PRAYER_TIME / 2 + 0.95)
    assert target.damage == 0
    advance(world, 0.1)
    assert target.damage == TICK_DAMAGE
    advance(world, 2.0)
    assert target.damage == 3 * TICK_DAMAGE
    assert hero.judgement is None and not hero.weapon.busy
    assert 0 < hero.judgement_cooldown < JUDGEMENT_COOLDOWN


def test_praying_hero_paladin_cancels_hammer_actions_and_counts_once():
    world = SimWorld([], 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(180, 300), "hero_cleric")
    paladin = world.add_stickman(Vec2(300, 300), "hero_paladin")
    target = world.add_minotaur(Vec2(400, 300))
    target.max_hp = 100
    target.update = lambda dt: None
    paladin.hammer_throw.pending = True
    advance(world, DT)
    assert hero.judgement is not None and hero.judgement.prayers == [paladin]
    assert not paladin.hammer_throw.active and not paladin.hammer_throw.pending
    assert paladin.divine_prayer > 0


def test_interrupting_the_caster_ends_the_channel_without_damage():
    world, hero, _, _, _, target = scene()
    advance(world, 0.2)
    assert hero.judgement is not None and hero.weapon.busy
    hero.paralyze(2)
    advance(world, 1.0)
    assert hero.judgement is None and not hero.weapon.busy
    assert target.damage == 0


def test_judgement_waits_until_an_enemy_is_near_the_cleric():
    world = SimWorld([], 300, 1000, ceiling=0)
    hero = world.add_stickman(Vec2(180, 300), "hero_cleric")
    far = world.add_minotaur(Vec2(180 + JUDGEMENT_RANGE + 80, 300))
    far.max_hp = 100
    far.update = lambda dt: None
    advance(world, 1.0)
    assert hero.judgement is None and hero.judgement_cooldown == 0

    near = world.add_goblin(Vec2(180 + JUDGEMENT_RANGE - 20, 300), "flag")
    near.update = lambda dt: None
    advance(world, DT)
    assert hero.judgement is not None and hero.judgement.target is near


def test_divine_judgement_casts_while_climbing_and_keeps_a_support_hand():
    world, hero, _, _, _, target = scene()
    surface = next(surface for surface in hero.planner.surfaces if surface.wall)
    point = surface.point_at(180)
    hero.follower.reset(Anchor(surface, point))
    hero.locomotion.teleport(hero.follower.command())
    target = world.add_goblin(Vec2(100, 300), "flag")
    target.update = lambda dt: None
    support_bone = hero.layout.arms[0].bones[-1]
    support = hero.transforms()[support_bone].end
    assert hero.divine_judgement()
    advance(world, 0.3)
    assert hero.judgement is not None and hero.weapon.busy
    assert hero.transforms()[support_bone].end.distance_to(support) < 0.5
    advance(world, PRAYER_TIME + 1.0)
    assert target.damage == TICK_DAMAGE


def test_sunlight_and_prayer_effects_render_without_mutating_combat():
    world, hero, cleric, _, _, target = scene()
    advance(world, PRAYER_TIME + 0.2)
    image = QImage(1000, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    before = (target.damage, hero.judgement.beam_age, cleric.divine_prayer)
    painter = QPainter(image)
    draw_actors(painter, (), world.stickmen)
    draw_divine_judgements(painter, world.heroes)
    painter.end()
    assert before == (target.damage, hero.judgement.beam_age, cleric.divine_prayer)
    assert any(image.pixelColor(x, y).alpha() for x in range(380, 420) for y in range(0, 300, 4))

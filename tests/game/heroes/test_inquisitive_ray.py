"""The sweeping ray pierces enemies and applies a single color's result to each."""

import math
import random

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.game.actors.base import Actor
from dungeons_desktops.game.defenders.minotaur.render import draw_minotaur
from dungeons_desktops.game.effects.beam import beam_body
from dungeons_desktops.game.effects.breath import DEATH_TIME, SHATTER_AT
from dungeons_desktops.game.effects.chromatic import RAY_COLORS, RayEffect, body_center
from dungeons_desktops.game.heroes.the_inquisitive.spells import Ability
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.render.chromatic import draw_chromatic_effects

DT = 1 / 60


def advance(actor, seconds):
    for _ in range(round(seconds / DT)):
        actor.update(DT)


def scene():
    world = SimWorld([], 600, 1200, ceiling=0)
    hero = world.add_stickman(Vec2(100, 600), "hero_wizard")
    target = world.add_minotaur(Vec2(350, 600))
    hero.cooldowns = {spell: 0 if spell is Ability.CHROMATIC_RAY else 999 for spell in Ability}
    return world, hero, target


def hit(world, hero, target, effect):
    world.chromatic.hit(effect, target, body_center(target), Vec2(0, 0), hero)


@pytest.mark.parametrize("effect", list(RayEffect))
def test_sweep_hits_multiple_enemies_once_with_one_effect_and_spares_allies(effect):
    world, hero, target = scene()
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.3)
    ray = hero.spells.rays[-1]
    ray.effect = effect
    targets = [target, world.add_minotaur(Vec2(480, 600)), world.add_minotaur(Vec2(650, 600))]
    behind = world.add_minotaur(Vec2(20, 600))
    distant = world.add_minotaur(Vec2(950, 600))
    ally = world.add_stickman(Vec2(400, 600), "cleric")
    assert not ray.struck and all(t.damage == 0 for t in targets)
    points = []
    for _ in range(95):
        hero.update(DT)
        points.append(ray.end)
        assert ray.start.distance_to(hero.wand_tip()) < 1e-7
        wand = ray.start - hero.transforms()[hero.weapon.hand_chain.bones[-1]].end
        assert wand.normalized().dot(Vec2.from_angle(ray.angle)) > 0.999
    assert len(set(points)) > 50
    assert ray.struck == set(targets)
    assert ray.color == RAY_COLORS[effect]
    if effect in (RayEffect.PETRIFY, RayEffect.POLYMORPH):
        assert all(world.chromatic.blocked(t) and t.damage == 0 for t in targets)
    else:
        assert [t.damage for t in targets] == [12 if effect is RayEffect.DISINTEGRATE else 4] * 3
    assert behind.damage == distant.damage == ally.damage == hero.damage == 0
    assert behind not in world.chromatic.active and distant not in world.chromatic.active
    assert hero.cat not in world.chromatic.active
    advance(hero, 0.3)
    assert not hero.spells.rays and hero.casting is None


@pytest.mark.parametrize("interrupt", ["stun", "death"])
def test_interrupt_stops_channel_before_it_crosses_the_target(interrupt):
    _, hero, target = scene()
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.35)
    assert target.damage == 0
    if interrupt == "stun":
        hero.paralyze(2)
    else:
        hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    advance(hero, 2)
    assert target.damage == 0 and not hero.spells.rays


def test_ray_continues_through_original_targets_death():
    world, hero, target = scene()
    target.damage = target.max_hp - 4
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.3)
    hero.spells.rays[-1].effect = RayEffect.ACID
    behind_target = world.add_minotaur(Vec2(520, 600))
    advance(hero, 1.8)
    assert target in world.fallen and behind_target.damage == 4


@pytest.mark.parametrize("effect", [RayEffect.POLYMORPH, RayEffect.PETRIFY])
@pytest.mark.parametrize("kind", ["goblin", "minotaur", "dragon", "chimera", "lich"])
def test_transformed_enemy_cannot_attack_and_recovers_after_five_seconds(effect, kind):
    world = SimWorld([], 600, 1400, ceiling=0)
    hero = world.add_stickman(Vec2(100, 600), "hero_wizard")
    hero.cooldowns = dict.fromkeys(Ability, 999)
    target = getattr(world, "add_" + kind)(Vec2(800, 600))
    hit(world, hero, target, effect)
    calls = []
    target.update = lambda dt: calls.append(dt)
    # The caster can die without shortening the target's transformation.
    hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    for _ in range(299):
        world.advance(DT)
    assert not calls and target.chromatic_status.effect is effect
    assert target.hp == target.max_hp
    world.advance(DT)
    assert calls and target.chromatic_status is None
    assert target not in world.chromatic.active


def test_refreshing_or_replacing_a_transformation_does_not_stack_or_change_hp():
    world, hero, target = scene()
    hit(world, hero, target, RayEffect.POLYMORPH)
    world.chromatic.update(4)
    hit(world, hero, target, RayEffect.PETRIFY)
    world.chromatic.update(4)
    assert target.chromatic_status.effect is RayEffect.PETRIFY
    assert target.hp == target.max_hp and len(world.chromatic.active) == 1
    world.chromatic.update(1)
    assert target.chromatic_status is None
    hit(world, hero, target, RayEffect.POLYMORPH)
    world.hurt_monster(target, target.hp, target.center(), Vec2(0, 0))
    world.chromatic.update(DT)
    assert target.chromatic_status is None and target in world.fallen


@pytest.mark.parametrize("effect", [RayEffect.ACID, RayEffect.ICE])
def test_elemental_deaths_only_trigger_on_kill_use_dragon_particles_and_clean_up(effect):
    world, hero, target = scene()
    hit(world, hero, target, effect)
    assert target.damage == 4 and target not in world.chromatic.active
    target.damage = target.max_hp - 4
    hit(world, hero, target, effect)
    state = target.chromatic_status
    assert target in world.fallen and world.monster_kills == 1
    assert state.demise.kind == ("acid" if effect is RayEffect.ACID else "cold")
    hero.cooldowns = dict.fromkeys(Ability, 999)
    for _ in range(math.ceil((SHATTER_AT + 0.1) / DT)):
        world.advance(DT)
    assert state.demise.motes
    if effect is RayEffect.ICE:
        assert state.demise.shattered and any(m.kind == "shard" for m in state.demise.motes)
    else:
        assert state.demise.melt > 0.5
        assert any(m.kind in ("bubble", "steam") for m in state.demise.motes)
    for _ in range(math.ceil(DEATH_TIME / DT)):
        world.advance(DT)
    assert target not in world.fallen and target not in world.chromatic.active


@pytest.mark.parametrize("effect", [RayEffect.POLYMORPH, RayEffect.PETRIFY,
                                     RayEffect.ACID, RayEffect.ICE])
def test_transformed_visual_is_distinct_and_rendering_does_not_advance_it(effect):
    world, hero, target = scene()

    def render():
        image = QImage(420, 400, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(3, 3)
        painter.translate(-280, -490)
        draw_minotaur(painter, target)
        painter.end()
        return image

    original = render()
    if effect in (RayEffect.ACID, RayEffect.ICE):
        target.damage = target.max_hp - 4
    hit(world, hero, target, effect)
    world.chromatic.update(0.5)
    state = target.chromatic_status
    rng = world.random.getstate()
    first = render()
    assert first != original and first == render()
    assert world.random.getstate() == rng and state.time == 0.5
    assert any(first.pixelColor(x, y).alpha() > 0
               for x in range(20, 400, 8) for y in range(20, 380, 8))


def test_ray_and_statue_follow_moved_window():
    world = SimWorld([Rect(50, 300, 650, 300)], 600, 1200)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    target = world.add_minotaur(Vec2(350, 300))
    hit(world, hero, target, RayEffect.PETRIFY)
    hero.cooldowns = {spell: 0 if spell is Ability.CHROMATIC_RAY else 999 for spell in Ability}
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.4)
    ray = hero.spells.rays[-1]
    point = target.center()
    world.apply_terrain(TerrainChange(moves={0: Vec2(40, -25)}), [Rect(90, 275, 650, 300)])
    assert target.center() == point + Vec2(40, -25)
    assert ray.start == ray.previous_start == hero.wand_tip()
    assert not ray.trail and world.chromatic.blocked(target)


@pytest.mark.parametrize("source", ["melee", "missile", "acid", "ice", "disintegrate"])
def test_lethal_hit_from_any_attack_shatters_a_petrified_enemy(source):
    world, hero, target = scene()
    hit(world, hero, target, RayEffect.PETRIFY)
    world.hurt_monster(target, 1, target.center(), Vec2(0, 0))
    assert not world.chromatic.shatters and world.chromatic.blocked(target)
    target.damage = target.max_hp - 1
    if source == "melee":
        world.hurt_monster(target, 1, target.center(), Vec2(20, -10))
    elif source == "missile":
        hero.spells.missile(hero.wand_tip(), target, target.center())
        hero.spells.update(2)
    else:
        hit(world, hero, target, RayEffect(source))
    assert target.chromatic_shattered and target.chromatic_status is None
    assert target in world.fallen and world.monster_kills == 1
    assert len(world.chromatic.shatters) == 1
    assert any(m.kind == "shard" for m in world.chromatic.shatters[0].motes)
    world.chromatic.update(0.1)
    image = QImage(1200, 650, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    draw_minotaur(painter, target)
    assert image.pixelColor(350, 560).alpha() == 0  # The intact statue disappears.
    draw_chromatic_effects(painter, world.chromatic)
    painter.end()
    assert any(image.pixelColor(x, y).alpha() > 0
               for x in range(290, 420, 2) for y in range(490, 610, 2))
    world.chromatic.update(3)
    assert not world.chromatic.shatters


def test_expired_stone_effect_does_not_shatter_on_a_later_death():
    world, hero, target = scene()
    hit(world, hero, target, RayEffect.PETRIFY)
    world.chromatic.update(5)
    world.hurt_monster(target, target.hp, target.center(), Vec2(0, 0))
    assert not world.chromatic.shatters and not getattr(target, "chromatic_shattered", False)


def test_multiple_beams_do_not_rebuild_skeletons_at_every_sample(monkeypatch):
    world = SimWorld([], 600, 1400, ceiling=0)
    hero = world.add_stickman(Vec2(100, 600), "hero_wizard")
    casters = [hero] + [hero._summon() for _ in range(4)]
    targets = [world.add_goblin(Vec2(260 + i * 30, 600), "sword") for i in range(12)]
    for caster in casters:
        caster.spells.ray(caster.wand_tip(), targets[0], RayEffect.POLYMORPH)
        ray = caster.spells.rays[-1]
        ray.angle = ray.previous_angle = -0.4
        ray.sweep = -1
    calls = 0
    original = Actor.transforms

    def transforms(actor):
        nonlocal calls
        calls += 1
        return original(actor)

    monkeypatch.setattr(Actor, "transforms", transforms)
    for caster in casters:
        caster.spells.advance_ray(DT)
        caster.spells.resolve_ray(caster.wand_tip())
    assert calls < 300  # The old ray rebuilt skeletons tens of thousands of times per frame.


def test_fast_ray_still_catches_small_enemies_between_coarse_frames():
    world, hero, _ = scene()
    world.minotaurs.clear()
    targets = [world.add_goblin(Vec2(x, 600), "sword") for x in (350, 440, 560)]
    assert hero.cast_spell(Ability.CHROMATIC_RAY)
    advance(hero, 0.3)
    ray = hero.spells.rays[-1]
    ray.effect = RayEffect.POLYMORPH
    for _ in range(8):
        hero.update(0.2)
    assert ray.struck == set(targets)


@pytest.mark.parametrize("kind", ["goblin", "minotaur", "chimera", "displacer", "lich",
                                  "drake", "kobold", "lizard", "hydra"])
def test_optimized_body_intersections_preserve_the_creatures_hit_geometry(kind):
    world = SimWorld([], 600, 1400, ceiling=0)
    target = getattr(world, "add_" + kind)(Vec2(500, 600))
    body = beam_body(target, 3)
    middle = body_center(target)
    rng = random.Random(23)
    for _ in range(250):
        point = middle + Vec2(rng.uniform(-90, 90), rng.uniform(-90, 90))
        assert (body.intersect(point, point) is not None) == target.hits(point, margin=3)

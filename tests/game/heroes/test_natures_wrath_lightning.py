"""Alternating abilities, defender-only chain targeting, and literal lightning rendering."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Vec2
from dungeons_desktops.game.heroes.natures_wrath.spell_render import draw_nature_spells
from dungeons_desktops.game.heroes.natures_wrath.spells import (
    ARC_TIME,
    CHAIN_DAMAGE,
    CHAIN_HOPS,
    CHAIN_STEP,
    Ability,
)
from dungeons_desktops.game.world.simulation import SimWorld

DT = 1 / 60


def make_chain(count=5):
    world = SimWorld([], 300, 2400, ceiling=0)
    hero = world.add_stickman(Vec2(50, 300), "hero_druid")
    targets = [world.add_goblin(Vec2(200 + 120 * i, 300), "flag") for i in range(count)]
    for target in targets:
        target.update = lambda dt: None
    return world, hero, targets


def cast_chain(hero, target):
    hero.spells.cast(Ability.CHAIN_LIGHTNING, hero.flame_point(), target.center(), target)


def test_default_rotation_is_fireball_bear_lightning_then_dragon_and_repeats():
    world = SimWorld([], 300, 900)
    hero = world.add_stickman(Vec2(100, 300), "hero_druid")
    target = world.add_minotaur(Vec2(350, 300))
    target.update = lambda dt: None
    casts = []
    previous = None
    for _ in range(60 * 10):
        world.advance(DT)
        if hero.casting is not None and previous is None:
            casts.append(hero.casting)
        previous = hero.casting
        if hero.bear is not None:
            # Full form durations are covered by the transformation tests.
            hero._end_form()
        if hero.dragon is not None:
            break
    assert casts == [Ability.FIREBALL, Ability.BEAR, Ability.CHAIN_LIGHTNING, Ability.MAGMA_DRAGON]
    assert hero.dragon is not None and target.damage >= 7
    hero._end_form()
    assert hero.current_ability is Ability.FIREBALL


def test_chain_hits_nearest_unique_defenders_with_staggered_damage_and_no_friendly_fire():
    world, hero, targets = make_chain()
    ally = world.add_stickman(Vec2(205, 300), "druid")
    other_hero = world.add_stickman(Vec2(310, 300), "hero_fighter")
    cast_chain(hero, targets[0])
    assert [arc.target for arc in hero.spells.arcs] == targets
    hero.spells.update(DT)
    assert [target.damage for target in targets] == [3, 0, 0, 0, 0]
    for _ in range(80):
        hero.spells.update(DT)
    expected = [CHAIN_DAMAGE[min(i, len(CHAIN_DAMAGE) - 1)] for i in range(5)]
    assert [target.damage for target in targets] == expected
    assert hero.damage == ally.damage == other_hero.damage == 0
    assert not hero.spells.arcs


def test_chain_stops_at_hop_cap_and_does_not_jump_across_large_gaps():
    _, hero, targets = make_chain(CHAIN_HOPS + 4)
    cast_chain(hero, targets[0])
    assert len(hero.spells.arcs) == CHAIN_HOPS + 1
    for _ in range(100):
        hero.spells.update(DT)
    assert all(target.damage == 0 for target in targets[CHAIN_HOPS + 1 :])

    world, hero, targets = make_chain(1)
    far = world.add_goblin(Vec2(650, 300), "flag")
    cast_chain(hero, targets[0])
    assert [arc.target for arc in hero.spells.arcs] == targets
    hero.spells.update(0.5)
    assert far.damage == 0


def test_delayed_hop_skips_a_dead_target_and_keeps_already_scheduled_hops():
    world, hero, targets = make_chain(3)
    cast_chain(hero, targets[0])
    world.hurt_monster(targets[1], targets[1].hp, targets[1].center(), Vec2(0, 0))
    killed_damage = targets[1].damage
    for _ in range(30):
        hero.spells.update(DT)
    assert targets[1].damage == killed_damage
    assert targets[2].damage == CHAIN_DAMAGE[2]


@pytest.mark.parametrize("interrupt", ["blind", "stun", "death"])
def test_lightning_windup_interrupts_without_skipping_its_rotation_slot(interrupt):
    world, hero, targets = make_chain(2)
    hero.queue_index = hero.rotation.index(Ability.CHAIN_LIGHTNING)
    world.advance(DT)
    assert hero.casting is Ability.CHAIN_LIGHTNING
    if interrupt == "blind":
        hero.blind_for(2)
    elif interrupt == "stun":
        hero.paralyze(2)
    else:
        hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    for _ in range(45):
        world.advance(DT)
    assert hero.current_ability is Ability.CHAIN_LIGHTNING and hero.casting is None
    assert not hero.spells.arcs and not hero.spells.fireballs
    assert not any(target.damage for target in targets)


def test_released_chain_finishes_after_caster_death():
    world, hero, targets = make_chain(5)
    cast_chain(hero, targets[0])
    hero.hurt(hero.hp, hero.center(), Vec2(0, 0), "test", "defeated")
    for _ in range(60):
        world.advance(DT)
    assert all(target.damage > 0 for target in targets)


def test_blue_yellow_bolts_render_without_advancing_effects_or_gameplay_rng():
    world, hero, targets = make_chain(3)
    cast_chain(hero, targets[0])
    hero.spells.update(CHAIN_STEP * 2 + DT)
    ages = [arc.age for arc in hero.spells.arcs]
    rng = world.random.getstate()

    def render():
        image = QImage(1100, 150, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(2, 2)
        painter.translate(0, -240)
        draw_nature_spells(painter, world.heroes)
        painter.end()
        return image

    image = render()
    assert image == render()
    assert world.random.getstate() == rng and ages == [arc.age for arc in hero.spells.arcs]
    colors = [image.pixelColor(x, y) for x in range(70, 950) for y in range(55, 130)]
    # The fading yellow center blends over its blue corona.
    assert any(c.blue() > 220 and c.red() < 100 for c in colors)
    assert any(c.red() > 220 and c.green() > 200 and c.blue() < 180 for c in colors)
    hero.spells.update(ARC_TIME)
    assert not hero.spells.arcs

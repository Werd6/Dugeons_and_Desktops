"""Hero Cleric model, visuals, healing, and spawn entrypoints."""

import pytest
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.defenders.mindflayer.actor import PULSE_WINDUP, Power
from dungeons_desktops.game.heroes.hero_cleric import HeroCleric
from dungeons_desktops.game.heroes.hero_cleric.actor import HOLY_PULSE_DAMAGE
from dungeons_desktops.game.heroes.hero_cleric.weapon import SunStaff
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_hero_cleric_keeps_base_cleric_movement_and_healing_setup():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric")
    cleric = world.add_stickman(Vec2(500, 300), "cleric")
    assert isinstance(hero, HeroCleric) and isinstance(hero.weapon, SunStaff)
    assert hero.display_name == "The Burning Dawn" and hero.hp == hero.max_hp == 60
    assert "hero_cleric" in HEROES and "hero_cleric" not in CLASSES
    assert hero.layout.skeleton.bones == cleric.layout.skeleton.bones
    assert hero.calling.speed == cleric.calling.speed
    assert hero.calling.cooldown == cleric.calling.cooldown


def test_hero_cleric_retains_the_clerics_healing_pulse():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric", wander=True)
    ally = world.add_stickman(Vec2(340, 300), "barbarian")
    ally.damage = 3
    pulsed = False
    for _ in range(round(2 / DT)):
        world.advance(DT)
        pulsed |= bool(world.spells.pulses)
    assert ally.damage < 3
    assert hero.weapon.name == "sun staff"
    assert pulsed


def test_sun_pulse_heals_allies_not_the_caster_and_damages_nearby_enemies():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric")
    ally = world.add_stickman(Vec2(330, 300), "barbarian")
    target = world.add_minotaur(Vec2(350, 300))
    target.max_hp = 100
    target.update = lambda dt: None
    hero.damage = 5
    ally.damage = 3
    ally.cooldown = 100
    hero.weapon.start()
    advance(world, 0.4)
    assert hero.damage == 5
    assert ally.damage == 1
    assert target.damage == HOLY_PULSE_DAMAGE


def test_sun_pulse_releases_every_thrall_in_its_radius_without_hurting_them():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric")
    near = [
        world.add_stickman(Vec2(325, 300), "barbarian"),
        world.add_stickman(Vec2(350, 300), "wizard"),
    ]
    far = world.add_stickman(Vec2(450, 300), "paladin")
    for actor in (*near, far):
        actor.enthrall()
    hero.weapon.start()
    advance(world, 0.4)
    assert all(not actor.thrall and actor.damage == 0 for actor in near)
    assert far.thrall and far.damage == 0


def test_hero_cleric_ignores_mindflayer_blast_and_pulse_stuns():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric")
    ordinary = world.add_stickman(Vec2(315, 300), "cleric")
    flayer = world.add_mindflayer(Vec2(330, 300))
    flayer._blast(hero, hero.center())
    assert hero.stun == 0 and not hero.knocked
    flayer._start(Power.PULSE, None)
    flayer._use_power(PULSE_WINDUP)
    assert hero.stun == 0 and not hero.knocked and hero.animated
    assert ordinary.stun > 0 and ordinary.knocked
    hero.paralyze(2)
    assert hero.stun == 2


def test_sun_halo_and_aura_render_without_changing_state():
    world = SimWorld([], 300, 800)
    hero = world.add_stickman(Vec2(300, 300), "hero_cleric")
    advance(world, 0.3)
    kinds = {stroke.kind for stroke in hero.weapon_strokes()}
    assert {"sun_glow", "sun_gold", "sun_core"} <= kinds
    image = QImage(800, 400, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    before = (hero.contact(), hero.hp, hero.weapon.time, hero.divine_time)
    draw_stickman(painter, hero)
    painter.end()
    assert before == (hero.contact(), hero.hp, hero.weapon.time, hero.divine_time)
    assert any(
        image.pixelColor(x, y).alpha()
        for y in range(190, 305, 4)
        for x in range(250, 355, 4)
    )


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_preview_entrypoint(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        max_stickmen=0,
        defenders=(),
        seed=3,
    )
    hero = session.spawn_at_edge(edge, variant="hero_cleric")
    assert isinstance(hero, HeroCleric) and hero in session.heroes
    assert session.hero_health_bars == [("The Burning Dawn", 1)]

    preview = RigPreviewController(700, 400)
    preview.spawn_hero_cleric()
    assert isinstance(preview.selected, HeroCleric)
    assert preview.selected.variant == "hero_cleric"

"""The gnome wizard keeps a full-size hat and joins the shared hero systems."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import HAT, ROBE, draw_stickman
from dungeons_desktops.game.adventurers.weapons import Wand
from dungeons_desktops.game.defenders.mindflayer.actor import PULSE_WINDUP, Power
from dungeons_desktops.game.heroes.the_inquisitive import Iggy
from dungeons_desktops.game.heroes.the_inquisitive import appearance as iggy
from dungeons_desktops.game.heroes.the_inquisitive.spells import Ability
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def test_iggy_and_his_copies_ignore_mindflayer_blast_and_pulse_stuns():
    world = SimWorld([], 400, 900)
    hero = world.add_stickman(Vec2(120, 400), "hero_wizard")
    copy = hero._summon()
    ordinary = world.add_stickman(Vec2(135, 400), "wizard")
    flayer = world.add_mindflayer(Vec2(145, 400))
    for actor in (hero, copy):
        flayer._blast(actor, actor.center())
        assert actor.stun == 0 and not actor.knocked
    flayer._start(Power.PULSE, None)
    flayer._use_power(PULSE_WINDUP)
    assert ordinary.stun > 0 and ordinary.knocked
    assert all(actor.stun == 0 and not actor.knocked and actor.animated for actor in (hero, copy))
    hero.paralyze(2)  # Other sources of paralysis still work.
    assert hero.stun == 2


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_gnome_is_half_height_and_retains_wizard_speed_and_hero_membership():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    wizard = world.add_stickman(Vec2(100, 300), "wizard")
    assert isinstance(hero, Iggy) and isinstance(hero.weapon, Wand)
    assert "hero_wizard" in HEROES and "hero_wizard" not in CLASSES
    assert hero in world.heroes and hero in world.stickmen and hero.prey
    heights = [
        actor.contact().y - actor.transforms()[actor.layout.head].end.y + actor.layout.head_radius
        for actor in (hero, wizard)
    ]
    assert heights[0] == pytest.approx(heights[1] / 2)
    hero.cooldowns = dict.fromkeys(Ability, 999)  # Compare travel speed outside a summon cast.
    for actor in (hero, wizard):
        actor.set_goal(Vec2(500, 300))
    advance(world, 2)
    assert hero.contact().x > 150
    assert hero.contact().x == pytest.approx(wizard.contact().x)


def test_small_rig_climbs_mantles_and_follows_moved_or_removed_support():
    world = SimWorld([Rect(180, 100, 200, 200)], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    hero.set_goal(Vec2(250, 100))
    modes = set()
    for _ in range(60 * 22):
        world.advance(DT)
        modes.add(hero.locomotion.mode)
    assert PoseMode.CLIMB in modes
    assert hero.contact().distance_to(Vec2(250, 100)) < 1
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(210, 80, 200, 200)])
    assert hero.contact().distance_to(Vec2(280, 80)) < 1
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert not hero.animated
    advance(world, 1)
    assert hero.center().y > 180


def test_hero_uses_his_own_magic_missiles_against_enemies():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard", wander=True)
    hero.cooldowns = {spell: 0 if spell is Ability.MAGIC_MISSILE else 99 for spell in Ability}
    goblin = world.add_goblin(Vec2(300, 300), "flag")
    cast = None
    before = goblin.hp
    for _ in range(60 * 3):
        world.advance(DT)
        if hero.spells.missiles:
            cast = hero.spells.missiles[0]
        if goblin.hp < before:
            break
    assert cast is not None and cast.monster is goblin
    assert goblin.hp < before and hero.animated


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_cleanup(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500), Rect(0, 0, 700, 450), FakeWindowSource(),
        seed=3, max_stickmen=0, defenders=(),
    )
    hero = session.spawn_at_edge(edge, variant="hero_wizard")
    assert isinstance(hero, Iggy) and hero.wander
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    assert session.hero_health_bars == [("The Inquisitive", 1.0)]
    hero.hurt(15, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert session.hero_health_bars == [("The Inquisitive", 0.75)]
    hero.heal(15)
    assert hero.hp == hero.max_hp
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert not session.hero_health_bars
    advance(session, 4)
    assert hero not in session.heroes and hero not in session.stickmen


def test_preview_selects_iggy_and_preserves_his_hero_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_iggy()
    hero = preview.selected
    assert isinstance(hero, Iggy) and hero in preview.heroes
    preview.set_variant("cleric")
    assert hero.variant == "hero_wizard" and isinstance(hero.weapon, Wand)


def render(actor, hide=()):
    image = QImage(320, 320, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.scale(6, 6)
    painter.translate(-74, -250)
    draw_stickman(painter, actor, hide=hide)
    painter.end()
    return image


def pixels(image, color):
    return [
        (x, y) for y in range(image.height()) for x in range(image.width())
        if image.pixel(x, y) == color.rgba()
    ]


@pytest.mark.parametrize("facing", [-1, 1])
def test_full_size_hat_and_cleric_robe_render_and_follow_hidden_body_parts(facing):
    world = SimWorld([], 300, 600)
    wizard = world.add_stickman(Vec2(100, 300), "wizard")
    hero = world.add_stickman(Vec2(100, 300), "hero_wizard")
    hero.cooldowns = dict.fromkeys(Ability, 999)
    for actor in (wizard, hero):
        actor.follower.facing = facing
    advance(world, 0.1)
    images = [render(actor) for actor in (wizard, hero)]
    hats = [pixels(images[0], HAT), pixels(images[1], iggy.HAT)]
    assert all(hats)
    # Compare actual rendered extents: the small rig must not shrink the hat.
    for axis in (0, 1):
        extents = [max(p[axis] for p in hat) - min(p[axis] for p in hat) for hat in hats]
        assert abs(extents[0] - extents[1]) <= 1
    assert pixels(images[1], iggy.ROBE) and pixels(images[1], iggy.ROBE_SASH)
    assert not pixels(images[0], ROBE)
    assert not pixels(render(hero, hide=(hero.layout.head,)), iggy.HAT)
    assert not pixels(render(hero, hide=(hero.layout.torso,)), iggy.ROBE)

"""The druid hero participates in the game without inheriting goblin combat."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.adventurers.render import draw_stickman
from dungeons_desktops.game.defenders.goblins.appearance import GOBLIN_HEAD
from dungeons_desktops.game.defenders.goblins.model import build_goblin
from dungeons_desktops.game.heroes.natures_wrath import NaturesWrath
from dungeons_desktops.game.heroes.natures_wrath.render import MOHAWK
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_explicit_unarmed_hero_is_prey_and_uses_the_goblin_rig():
    world = SimWorld([], 200, 500)
    hero = world.add_stickman(Vec2(100, 200), "hero_druid")
    assert isinstance(hero, NaturesWrath)
    assert "hero_druid" in HEROES and "hero_druid" not in CLASSES
    assert hero.display_name == "Natures Wrath"
    assert hero in world.heroes and hero in world.stickmen and hero in world.actors
    assert hero not in world.goblins and hero.prey
    assert all(monster is not hero for monster, _ in world.monsters_near(hero.center(), 100))
    assert hero.weapon is None and hero.locomotion.upper is hero.casting_pose
    assert not hero.weapon_strokes()
    base = build_goblin()
    for bone in base.skeleton.bones:
        assert hero.layout.skeleton.bone(bone.name).length == pytest.approx(bone.length * 1.05)


@pytest.mark.parametrize("surface_kind", ["walkable", "wall", "hanging"])
def test_travel_speed_matches_regular_druid_on_floor_wall_and_ceiling(surface_kind):
    world = SimWorld([], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_druid")
    druid = world.add_stickman(Vec2(100, 300), "druid")
    starts = []
    for actor in (hero, druid):
        surface = next(s for s in actor.planner.surfaces if getattr(s, surface_kind))
        start = actor.planner.anchor_near(surface.point_at(100))
        actor.follower.reset(start)
        actor.locomotion.teleport(actor.follower.command())
        actor.set_goal(surface.point_at(200))
        starts.append(actor.contact())
    advance(world, 1)
    distances = [
        actor.contact().distance_to(start)
        for actor, start in zip((hero, druid), starts, strict=True)
    ]
    assert distances[0] > 10
    assert distances[0] == pytest.approx(distances[1])


def test_climbs_mantles_and_follows_changed_window_terrain():
    box = Rect(180, 100, 200, 100)
    world = SimWorld([box], 200, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 200), "hero_druid")
    hero.set_goal(Vec2(250, 100))
    modes = set()
    for _ in range(60 * 14):
        world.advance(DT)
        modes.add(hero.locomotion.mode)
    assert PoseMode.CLIMB in modes
    assert hero.contact().distance_to(Vec2(250, 100)) < 1
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(210, 80, 200, 100)])
    assert hero.contact().distance_to(Vec2(280, 80)) < 1
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    world.apply_terrain(TerrainChange(remap={0: None}), [])
    assert not hero.animated  # The shared adventurer lifecycle ragdolls on lost support.
    advance(world, 1)
    assert hero.center().y > 180


def test_wanders_without_casting_when_no_monster_is_in_reach():
    world = SimWorld([], 200, 500)
    hero = world.add_stickman(Vec2(100, 200), "hero_druid", wander=True)
    hero.attack()
    advance(world, 3)
    assert not hero.spells.fireballs and hero.casting is None
    assert hero.weapon is None and hero.quarry is None
    assert hero.contact().distance_to(Vec2(100, 200)) > 1


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_damage_heal_and_cleanup(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500),
        Rect(0, 0, 700, 450),
        FakeWindowSource(),
        seed=3,
        max_stickmen=0,
        defenders=(),
    )
    hero = session.spawn_at_edge(edge, variant="hero_druid")
    assert isinstance(hero, NaturesWrath) and hero.wander
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    assert session.hero_health_bars == [("Natures Wrath", 1.0)]
    hero.hurt(15, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert session.hero_health_bars == [("Natures Wrath", 0.75)]
    hero.heal(15)
    assert hero.hp == hero.max_hp
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert not hero.animated and not hero.prey
    assert not session.hero_health_bars
    advance(session, 4)
    assert hero not in session.heroes and hero not in session.stickmen


def test_preview_spawn_is_selected_and_cannot_change_into_an_ordinary_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_natures_wrath()
    hero = preview.selected
    assert isinstance(hero, NaturesWrath) and hero in preview.heroes
    preview.set_variant("druid")
    assert hero.variant == "hero_druid" and hero.weapon is None
    preview.attack()
    assert "target in range" in preview.status


@pytest.mark.parametrize("facing", [-1, 1])
@pytest.mark.parametrize("ragdoll", [False, True])
def test_goblin_head_and_red_mohawk_render_and_hide_with_severed_head(facing, ragdoll):
    world = SimWorld([], 200, 500)
    hero = world.add_stickman(Vec2(100, 200), "hero_druid")
    hero.follower.facing = facing
    advance(world, 0.1)
    if ragdoll:
        hero.go_ragdoll()

    def colors():
        image = QImage(160, 160, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.scale(4, 4)
        painter.translate(-80, -170)
        draw_stickman(painter, hero)
        painter.end()
        return {image.pixelColor(x, y).name() for x in range(160) for y in range(160)}

    assert {MOHAWK.name(), GOBLIN_HEAD.name()} <= colors()
    hero.severed.add(hero.layout.head)
    assert MOHAWK.name() not in colors()

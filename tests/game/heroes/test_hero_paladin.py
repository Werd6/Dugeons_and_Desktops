"""The tall armored paladin uses normal adventurer navigation and hero entrypoints."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES
from dungeons_desktops.game.heroes.hero_paladin import HeroPaladin
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def test_one_head_taller_with_tower_shield_and_slower_paladin_speed():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_paladin")
    regular = world.add_stickman(Vec2(200, 300), "paladin")
    assert isinstance(hero, HeroPaladin) and hero in world.heroes
    assert "hero_paladin" in HEROES and "hero_paladin" not in CLASSES
    assert hero.max_hp == 120 and hero.calling.speed == regular.calling.speed * 0.9
    assert hero.layout.head_radius == regular.layout.head_radius
    heads = [actor.transforms()[actor.layout.head].end for actor in (regular, hero)]
    assert heads[0].y - heads[1].y == pytest.approx(regular.layout.head_radius * 2, abs=1)
    assert hero.layout.walk.speed == regular.layout.walk.speed
    shield = hero.weapon._shield(Vec2(0, 0))
    assert [stroke.kind for stroke in shield] == ["hilt", "shield", "hilt", "hilt"]
    height = max(p.y for p in shield[0].shape) - min(p.y for p in shield[0].shape)
    assert height > 27


@pytest.mark.parametrize("facing", [-1, 1])
def test_forward_hammer_stays_in_far_hand_through_swing(facing):
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(300, 300), "hero_paladin")
    hero.follower.facing = facing
    hero.locomotion.teleport(hero.follower.command())
    hero.update(DT)
    haft = hero.weapon_strokes()[0]
    assert (haft.end.x - haft.start.x) * facing > 0
    hero.attack()
    for _ in range(42):
        hero.update(DT)
        hand = hero.transforms()[hero.layout.arms[0].bones[-1]].end
        haft = hero.weapon_strokes()[0]
        assert abs((hand - haft.start).cross((haft.end - haft.start).normalized())) < 1e-6


def test_climbs_with_taller_rig_and_rides_moving_window():
    world = SimWorld([Rect(180, 100, 200, 200)], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_paladin")
    hero.set_goal(Vec2(250, 100))
    modes = set()
    for _ in range(60 * 22):
        world.advance(DT)
        modes.add(hero.locomotion.mode)
    assert PoseMode.CLIMB in modes and hero.contact().distance_to(Vec2(250, 100)) < 1
    world.apply_terrain(TerrainChange(moves={0: Vec2(30, -20)}), [Rect(210, 80, 200, 200)])
    assert hero.contact().distance_to(Vec2(280, 80)) < 1
    assert hero.planner.owns(hero.follower.current_anchor().surface)


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_cleanup(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500), Rect(0, 0, 700, 450), FakeWindowSource(),
        seed=3, max_stickmen=0, defenders=(),
    )
    hero = session.spawn_at_edge(edge, variant="hero_paladin")
    assert isinstance(hero, HeroPaladin) and hero.wander
    assert session.hero_health_bars == [("The Indomitable", 1)]
    hero.hurt(30, hero.center(), Vec2(0, 0), "test", "defeated")
    assert session.hero_health_bars == [("The Indomitable", 0.75)]
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "test", "defeated")
    for _ in range(240):
        session.advance(DT)
    assert hero not in session.heroes and hero not in session.stickmen


def test_preview_selects_hero_and_preserves_his_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_hero_paladin()
    hero = preview.selected
    assert isinstance(hero, HeroPaladin) and hero in preview.heroes
    preview.set_variant("paladin")
    assert hero.variant == "hero_paladin" and hero.weapon.name == "warhammer and tower shield"

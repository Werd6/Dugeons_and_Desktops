"""The larger barbarian stays compatible with adventurer movement and combat."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES, build_stick_figure
from dungeons_desktops.game.heroes.the_mighty import TheMighty
from dungeons_desktops.game.heroes.the_mighty.weapon import HeavyAxe
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.navigation.terrain import TerrainChange
from dungeons_desktops.preview.controller import RigPreviewController
from dungeons_desktops.rig.equipment import Axe
from dungeons_desktops.rig.locomotion import PoseMode

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_hero_uses_larger_barbarian_rig_and_stays_out_of_regular_spawn_pool():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_barbarian")
    assert isinstance(hero, TheMighty)
    assert "hero_barbarian" in HEROES and "hero_barbarian" not in CLASSES
    assert hero in world.heroes and hero in world.stickmen and hero.prey
    base = build_stick_figure()
    for bone in base.skeleton.bones:
        assert hero.layout.skeleton.bone(bone.name).length == pytest.approx(bone.length * 1.5)
    assert hero.layout.head_radius == pytest.approx(base.head_radius * 1.5)
    assert hero.layout.walk.speed == base.walk.speed
    assert isinstance(hero.weapon, HeavyAxe)
    regular_axe = Axe(base)
    assert hero.weapon.haft > regular_axe.haft * 1.9
    normal_head = regular_axe._held(Vec2(0, 0), Vec2(0, -1), 1)[1].shape
    hero_head = hero.weapon._held(Vec2(0, 0), Vec2(0, -1), 1)[1].shape
    assert max(p.x for p in hero_head) > max(p.x for p in normal_head) * 2.5


def test_climbs_mantles_and_tracks_moving_window_with_larger_rig():
    box = Rect(180, 100, 200, 200)
    world = SimWorld([box], 300, 600, ceiling=0)
    hero = world.add_stickman(Vec2(100, 300), "hero_barbarian")
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


@pytest.mark.parametrize("facing", [-1, 1])
def test_heavy_axe_stays_in_hand_and_lands_one_hit_at_the_strike(facing):
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(200, 300), "hero_barbarian")
    goblin = world.add_goblin(Vec2(200 + facing * 30, 300), "flag")
    before = goblin.hp
    hero.attack()
    assert hero.weapon.busy
    advance(world, 0.2)
    assert goblin.hp == before
    for _ in range(30):
        world.advance(DT)
        hand = hero.transforms()["lower_arm_r"].end
        haft = hero.weapon_strokes()[0]
        direction = (haft.end - haft.start).normalized()
        assert abs((hand - haft.start).cross(direction)) < 1e-6
    assert goblin.hp == before - 2
    assert hero.trail or not hero.weapon.trail_active


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_cleanup(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500), Rect(0, 0, 700, 450), FakeWindowSource(),
        seed=3, max_stickmen=0, defenders=(),
    )
    hero = session.spawn_at_edge(edge, variant="hero_barbarian")
    assert isinstance(hero, TheMighty) and hero.wander
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    assert session.hero_health_bars == [("The Mighty", 1.0)]
    hero.hurt(15, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert session.hero_health_bars == [("The Mighty", 0.75)]
    hero.heal(15)
    assert hero.hp == hero.max_hp
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert not session.hero_health_bars
    advance(session, 4)
    assert hero not in session.heroes and hero not in session.stickmen


def test_preview_selects_hero_and_preserves_his_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_mighty()
    hero = preview.selected
    assert isinstance(hero, TheMighty) and hero in preview.heroes
    preview.set_variant("barbarian")
    assert hero.variant == "hero_barbarian" and isinstance(hero.weapon, HeavyAxe)

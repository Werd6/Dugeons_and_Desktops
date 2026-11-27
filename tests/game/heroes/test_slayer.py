"""The Slayer participates in the existing rogue combat and named hero systems."""

import pytest

from dungeons_desktops.core.geometry import Rect, Vec2
from dungeons_desktops.desktop.session import DesktopSession
from dungeons_desktops.desktop.windows import FakeWindowSource
from dungeons_desktops.game.adventurers.model import CLASSES, HEROES, build_stick_figure
from dungeons_desktops.game.heroes.the_slayer import TheSlayer
from dungeons_desktops.game.heroes.the_slayer.weapon import SlayerDaggers
from dungeons_desktops.game.world.simulation import SimWorld
from dungeons_desktops.preview.controller import RigPreviewController

DT = 1 / 60


def advance(world, seconds):
    for _ in range(round(seconds / DT)):
        world.advance(DT)


def test_slayer_uses_rogue_rig_and_speed_but_has_named_hero_health():
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(100, 300), "hero_rogue")
    rogue = world.add_stickman(Vec2(200, 300), "rogue")
    assert isinstance(hero, TheSlayer) and isinstance(hero.weapon, SlayerDaggers)
    assert hero in world.heroes and hero in world.stickmen and hero.prey
    assert "hero_rogue" in HEROES and "hero_rogue" not in CLASSES
    assert hero.hp == hero.max_hp == 60
    assert hero.layout.head_radius == build_stick_figure().head_radius
    hero.set_goal(Vec2(200, 300))
    rogue.set_goal(Vec2(300, 300))
    start = hero.contact()
    rogue_start = rogue.contact()
    advance(world, 0.5)
    assert hero.contact().distance_to(start) == pytest.approx(
        rogue.contact().distance_to(rogue_start)
    )
    assert hero.contact().distance_to(start) > 20
    assert hero.cape_time == pytest.approx(0.5)


@pytest.mark.parametrize("facing", [-1, 1])
def test_jagged_daggers_follow_hands_and_keep_rogue_hit_timing(facing):
    world = SimWorld([], 300, 600)
    hero = world.add_stickman(Vec2(200, 300), "hero_rogue")
    hero.assassinate.cooldown = 999
    goblin = world.add_goblin(Vec2(200 + facing * 18, 300), "flag")
    before = goblin.hp
    hero.attack()
    assert hero.weapon.busy
    advance(world, 0.1)
    assert goblin.hp == before
    advance(world, 0.1)
    assert goblin.hp == before - 1
    strokes = hero.weapon_strokes()
    for chain, hilt in zip(
        (hero.weapon.support_chain, hero.weapon.hand_chain), (strokes[0], strokes[5]),
        strict=True,
    ):
        assert hilt.end.distance_to(hero.transforms()[chain.bones[-1]].end) < 1e-6


@pytest.mark.parametrize("edge", ["left", "right", "top"])
def test_desktop_spawn_health_and_cleanup(edge):
    session = DesktopSession(
        Rect(0, 0, 700, 500), Rect(0, 0, 700, 450), FakeWindowSource(),
        seed=3, max_stickmen=0, defenders=(),
    )
    hero = session.spawn_at_edge(edge, variant="hero_rogue")
    assert isinstance(hero, TheSlayer) and hero.wander
    assert hero.planner.owns(hero.follower.current_anchor().surface)
    assert session.hero_health_bars == [("The Slayer", 1.0)]
    hero.hurt(15, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert session.hero_health_bars == [("The Slayer", 0.75)]
    hero.heal(15)
    assert hero.hp == hero.max_hp
    hero.reveal()  # The health-threshold escape now grants immediate stealth.
    hero.hurt(hero.max_hp, hero.center(), Vec2(0, 0), "goblin", "defeated")
    assert not session.hero_health_bars
    advance(session, 4)
    assert hero not in session.heroes and hero not in session.stickmen


def test_preview_selects_slayer_and_preserves_his_class():
    preview = RigPreviewController(700, 400)
    preview.spawn_slayer()
    hero = preview.selected
    assert isinstance(hero, TheSlayer) and hero in preview.heroes
    preview.set_variant("rogue")
    assert hero.variant == "hero_rogue" and isinstance(hero.weapon, SlayerDaggers)
